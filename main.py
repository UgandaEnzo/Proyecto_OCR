from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Header
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import exc as sa_exc
import shutil
import os
import uuid
import json
import hashlib

# Importamos nuestros módulos
from database import engine, Base, get_db
import models
import threading

# Instancia de la app
app = FastAPI()

# Montar static y garantizar carpeta uploads
if not os.path.exists("uploads"):
    os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")


# Función simple para validar API key opcional
def require_api_key(x_api_key: Optional[str]):
    configured = os.getenv("API_KEY")
    if configured:
        if not x_api_key or x_api_key != configured:
            raise HTTPException(status_code=401, detail="API key inválida")
    return True

# Crear tablas en background para no bloquear el proceso principal
def _create_tables_bg():
    try:
        models.Base.metadata.create_all(bind=engine)
    except Exception as e:
        print(f"Advertencia: no se pudieron crear tablas en startup: {e}")
    # no devolvemos nada; la creación de tablas fue intentada en background


# Lanzar background thread para crear tablas sin bloquear import
threading.Thread(target=_create_tables_bg, daemon=True).start()


@app.post("/subir-pago/")
def subir_pago(file: UploadFile = File(...), db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)):
    """Subir imagen de comprobante, ejecutar OCR, detectar duplicados por hash y crear/mergear registro.
    Captura y registra cualquier excepción en `logs/subir_trace.log` para debugging.
    """
    require_api_key(x_api_key)
    import traceback
    try:
        filename = f"{uuid.uuid4().hex}_{os.path.basename(file.filename)}"
        file_path = f"uploads/{filename}"

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # Calcular hash SHA256 del archivo subido para detectar duplicados
        def _sha256(path):
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(1024*64), b""):
                    h.update(chunk)
            return h.hexdigest()

        try:
            new_hash = _sha256(file_path)
            new_size = os.path.getsize(file_path)
        except Exception:
            new_hash = None
            new_size = None

        # Buscar duplicados comparando tamaño y hash de archivos ya subidos
        if new_hash:
            try:
                existing = db.query(models.Pago).filter(models.Pago.file_hash == new_hash).first()
                if existing:
                    try:
                        os.remove(file_path)
                    except Exception:
                        pass
                    return {"mensaje": "Archivo duplicado detectado (hash). Ya existe un pago con este archivo.", "id_existente": existing.id, "referencia": existing.referencia}

                # Si no hay match por hash en DB, comprobamos contra archivos guardados (registros antiguos)
                # ADVERTENCIA: Esto es costoso (O(N)). Idealmente, ejecutar un script de migración para calcular hashes de todos los archivos antiguos
                # y guardarlos en DB, para eliminar este bloque 'else' en el futuro.
                all_pagos = db.query(models.Pago).filter(models.Pago.ruta_imagen.isnot(None)).all()
                for p in all_pagos:
                    try:
                        if not p.ruta_imagen:
                            continue
                        if not os.path.exists(p.ruta_imagen):
                            continue
                        if new_size is not None and os.path.getsize(p.ruta_imagen) != new_size:
                            continue
                        if _sha256(p.ruta_imagen) == new_hash:
                            try:
                                import ocr_engine
                                resultado_dup = ocr_engine.procesar_imagen(file_path)
                            except Exception:
                                resultado_dup = {}

                            detalles = {}
                            updated = False
                            try:
                                if resultado_dup.get('referencia') and resultado_dup.get('referencia') != p.referencia:
                                    detalles['referencia'] = {'old': p.referencia, 'new': resultado_dup.get('referencia')}
                                    p.referencia = resultado_dup.get('referencia')
                                    updated = True
                                if resultado_dup.get('banco') and resultado_dup.get('banco') != p.banco_origen:
                                    detalles['banco_origen'] = {'old': p.banco_origen, 'new': resultado_dup.get('banco')}
                                    p.banco_origen = resultado_dup.get('banco')
                                    updated = True
                                if resultado_dup.get('monto') is not None and resultado_dup.get('monto') != p.monto:
                                    detalles['monto'] = {'old': p.monto, 'new': resultado_dup.get('monto')}
                                    p.monto = resultado_dup.get('monto')
                                    updated = True

                                if not p.file_hash and new_hash:
                                    p.file_hash = new_hash
                                    detalles['file_hash'] = {'old': None, 'new': new_hash}
                                    updated = True

                                if updated:
                                    db.add(p)
                                    db.commit()
                                    db.refresh(p)
                                    try:
                                        hist = models.PagoHistory(pago_id=p.id, accion="merge", detalles=json.dumps(detalles), usuario=None)
                                        db.add(hist)
                                        db.commit()
                                    except Exception:
                                        db.rollback()
                            except Exception:
                                db.rollback()

                            try:
                                os.remove(file_path)
                            except Exception:
                                pass

                            return {"mensaje": "Archivo duplicado detectado. Registro existente actualizado" if updated else "Archivo duplicado detectado. No se realizaron cambios", "id_existente": p.id, "referencia": p.referencia}
                    except Exception:
                        continue
            except Exception:
                # si falla la comprobación de duplicados, continuamos normalmente
                pass

        # Ejecutar OCR
        try:
            import ocr_engine
            resultado = ocr_engine.procesar_imagen(file_path)
        except Exception as e:
            print(f"Error crítico en OCR: {e}")
            resultado = {
                "referencia": "Error OCR",
                "banco": "Desconocido",
                "monto": 0.0,
                "status": "requiere_revision"
            }

        # Crear objeto para guardar en BD
        nuevo_pago = models.Pago(
            referencia=resultado.get("referencia", "No detectada"),
            banco_origen=resultado.get("banco", "Desconocido"),
            monto=resultado.get("monto", 0.0),
            ruta_imagen=file_path,
            file_hash=new_hash if new_hash else None,
        )

        # Guardar en PostgreSQL (asegurar que la sesión no está en estado abortado)
        try:
            db.rollback()
        except Exception:
            pass
        try:
            db.add(nuevo_pago)
            db.commit()
            db.refresh(nuevo_pago)
        except sa_exc.ProgrammingError:
            # Posible esquema antiguo sin columna `file_hash`.
            db.rollback()
            # Reintentar sin `file_hash` para compatibilidad con BD antigua
            nuevo_pago_nohash = models.Pago(
                referencia=resultado.get("referencia", "No detectada"),
                banco_origen=resultado.get("banco", "Desconocido"),
                monto=resultado.get("monto", 0.0),
                ruta_imagen=file_path,
            )
            db.add(nuevo_pago_nohash)
            db.commit()
            db.refresh(nuevo_pago_nohash)
            nuevo_pago = nuevo_pago_nohash

        # Registrar historial de creación
        try:
            detalles = {"file_hash": new_hash}
            hist = models.PagoHistory(pago_id=nuevo_pago.id, accion="create", detalles=json.dumps(detalles), usuario=None)
            db.add(hist)
            db.commit()
        except Exception:
            db.rollback()

        return {
            "mensaje": "Pago procesado exitosamente",
            "datos_extraidos": resultado,
            "id_registro": nuevo_pago.id,
        }
    except Exception:
        tb = traceback.format_exc()
        try:
            os.makedirs('logs', exist_ok=True)
            with open('logs/subir_trace.log', 'a', encoding='utf-8') as fh:
                fh.write(tb + "\n---\n")
        except Exception:
            pass
        return {"error": "Internal Server Error", "trace": tb}


@app.get("/ver-pagos/")
def leer_pagos(limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Ver pagos con paginación server-side. Devuelve items y total."""
    query = db.query(models.Pago)
    total = query.count()
    items = query.order_by(models.Pago.id.desc()).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


@app.get("/buscar-pagos/")
def buscar_pagos(q: Optional[str] = None, limit: int = 50, offset: int = 0, db: Session = Depends(get_db)):
    """Buscar pagos por referencia u otras coincidencias parciales con paginación."""
    query = db.query(models.Pago)
    if not q:
        total = query.count()
        items = query.order_by(models.Pago.id.desc()).offset(offset).limit(limit).all()
        return {"items": items, "total": total}

    q_clean = q.strip()
    if len(q_clean) <= 4 and q_clean.isdigit():
        filt = models.Pago.referencia.ilike(f"%{q_clean}")
    else:
        filt = models.Pago.referencia.ilike(f"%{q_clean}%")

    qobj = query.filter(filt)
    total = qobj.count()
    items = qobj.order_by(models.Pago.id.desc()).offset(offset).limit(limit).all()
    return {"items": items, "total": total}


class PagoUpdate(BaseModel):
    referencia: Optional[str] = None
    banco_origen: Optional[str] = None
    monto: Optional[float] = None


@app.put("/editar-pago/{pago_id}")
def editar_pago_id(pago_id: int, cambios: PagoUpdate, db: Session = Depends(get_db), x_api_key: Optional[str] = Header(None)):
    """Editar un pago directamente por su ID interno.
    Actualiza solo los campos enviados (referencia, banco_origen, monto).
    """
    require_api_key(x_api_key)

    pago = db.query(models.Pago).filter(models.Pago.id == pago_id).first()
    if not pago:
        raise HTTPException(status_code=404, detail="Pago no encontrado")

    old_values = {"referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto}
    updated = False

    if cambios.referencia is not None:
        pago.referencia = cambios.referencia
        updated = True
    if cambios.banco_origen is not None:
        pago.banco_origen = cambios.banco_origen
        updated = True
    if cambios.monto is not None:
        pago.monto = cambios.monto
        updated = True

    if updated:
        db.add(pago)
        db.commit()
        db.refresh(pago)
        
        # Historial de cambios
        try:
            detalles = {}
            for k in ("referencia", "banco_origen", "monto"):
                if old_values.get(k) != getattr(pago, k):
                    detalles[k] = {"old": old_values.get(k), "new": getattr(pago, k)}
            
            if detalles:
                hist = models.PagoHistory(pago_id=pago.id, accion="edit_id", detalles=json.dumps(detalles), usuario=None)
                db.add(hist)
                db.commit()
        except Exception:
            db.rollback()

    return {"mensaje": "Pago actualizado exitosamente", "pago": {"id": pago.id, "referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto}}


@app.get("/_rutas_debug", include_in_schema=False)
def rutas_debug():
    """Endpoint temporal para listar rutas registradas y métodos.
    Útil para depurar 404s por path o método incorrecto.
    """
    salida = []
    for r in app.routes:
        try:
            methods = list(r.methods) if hasattr(r, "methods") and r.methods else []
        except Exception:
            methods = []
        salida.append({"path": getattr(r, "path", str(r)), "methods": methods})
    return salida


@app.put("/editar-pago-ref/{referencia}")
def editar_pago_por_referencia(referencia: str, cambios: PagoUpdate, db: Session = Depends(get_db), confirm: bool = False, x_api_key: Optional[str] = Header(None)):
    """Editar un pago buscando por su `referencia` (insensible a mayúsculas).
    No aplicará cambios automáticamente: si hay varias coincidencias devuelve la lista;
    si hay una coincidencia, requiere `confirm=true` para aplicar los cambios.
    """
    # Validar API key si aplica
    require_api_key(x_api_key)

    matches = db.query(models.Pago).filter(models.Pago.referencia.ilike(f"%{referencia}%")).all()
    if not matches:
        raise HTTPException(status_code=404, detail="Pago no encontrado por referencia")

    if len(matches) > 1:
        # Devolver coincidencias para que el usuario elija
        resumen = []
        for p in matches:
            resumen.append({"id": p.id, "referencia": p.referencia, "banco_origen": p.banco_origen, "monto": p.monto})
        return {"mensaje": "Varios pagos coinciden, especifica el id para editar o afina la búsqueda", "coincidencias": resumen}

    pago = matches[0]
    if not confirm:
        return {"mensaje": "Pago encontrado. Pasa query param `confirm=true` para aplicar cambios", "pago": {"id": pago.id, "referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto}}

    old_values = {"referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto}
    updated = False
    if cambios.referencia is not None:
        pago.referencia = cambios.referencia
        updated = True
    if cambios.banco_origen is not None:
        pago.banco_origen = cambios.banco_origen
        updated = True
    if cambios.monto is not None:
        pago.monto = cambios.monto
        updated = True

    if updated:
        db.add(pago)
        db.commit()
        db.refresh(pago)
        # Registrar historial
        try:
            detalles = {}
            for k in ("referencia", "banco_origen", "monto"):
                if old_values.get(k) != getattr(pago, k):
                    detalles[k] = {"old": old_values.get(k), "new": getattr(pago, k)}
            hist = models.PagoHistory(pago_id=pago.id, accion="edit", detalles=json.dumps(detalles), usuario=None)
            db.add(hist)
            db.commit()
        except Exception:
            db.rollback()

    return {"mensaje": "Pago actualizado (por referencia)", "pago": {"id": pago.id, "referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto}}


@app.delete("/eliminar-pago-ref/{referencia}")
def eliminar_pago_por_referencia(referencia: str, db: Session = Depends(get_db), confirm: bool = False, x_api_key: Optional[str] = Header(None)):
    """Eliminar un pago buscando por su `referencia` (insensible a mayúsculas).
    No eliminará automáticamente si hay varias coincidencias; si hay una coincidencia
    requiere `confirm=true` para proceder.
    """
    require_api_key(x_api_key)

    matches = db.query(models.Pago).filter(models.Pago.referencia.ilike(f"%{referencia}%")).all()
    if not matches:
        raise HTTPException(status_code=404, detail="Pago no encontrado por referencia")

    if len(matches) > 1:
        resumen = []
        for p in matches:
            resumen.append({"id": p.id, "referencia": p.referencia, "banco_origen": p.banco_origen, "monto": p.monto})
        return {"mensaje": "Varios pagos coinciden, especifica el id para eliminar o afina la búsqueda", "coincidencias": resumen}

    pago = matches[0]
    if not confirm:
        return {"mensaje": "Pago encontrado. Pasa query param `confirm=true` para eliminar", "pago": {"id": pago.id, "referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto}}

    # registrar info antes de eliminar
    try:
        detalles = {"referencia": pago.referencia, "banco_origen": pago.banco_origen, "monto": pago.monto, "ruta_imagen": pago.ruta_imagen}
        hist = models.PagoHistory(pago_id=pago.id, accion="delete", detalles=json.dumps(detalles), usuario=None)
        db.add(hist)
        db.commit()
    except Exception:
        db.rollback()

    try:
        if pago.ruta_imagen and os.path.exists(pago.ruta_imagen):
            os.remove(pago.ruta_imagen)
    except Exception:
        pass

    db.delete(pago)
    db.commit()

    return {"mensaje": "Pago eliminado (por referencia)", "id": pago.id}


# Variantes con barra final (ocultas del esquema) para evitar 404 por diferencias de trailing slash
@app.put("/editar-pago-ref/{referencia}/", include_in_schema=False)
def editar_pago_por_referencia_slash(referencia: str, cambios: PagoUpdate, db: Session = Depends(get_db), confirm: bool = False, x_api_key: Optional[str] = Header(None)):
    return editar_pago_por_referencia(referencia, cambios, db, confirm, x_api_key)


@app.delete("/eliminar-pago-ref/{referencia}/", include_in_schema=False)
def eliminar_pago_por_referencia_slash(referencia: str, db: Session = Depends(get_db), confirm: bool = False, x_api_key: Optional[str] = Header(None)):
    return eliminar_pago_por_referencia(referencia, db, confirm, x_api_key)
