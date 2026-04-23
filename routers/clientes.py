
from fastapi import APIRouter, Depends, HTTPException, File, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session
from sqlalchemy import desc
from typing import Optional, List
import io
import csv
import models
import schemas
from database import get_db

router = APIRouter(tags=['clientes'])

@router.post('/clientes/', response_model=schemas.Cliente, status_code=201)
def crear_cliente(cliente: schemas.ClienteBase, db: Session=Depends(get_db)):
    """Crea un nuevo cliente en la base de datos."""
    db_cliente = db.query(models.Cliente).filter(models.Cliente.cedula == cliente.cedula).first()
    if db_cliente:
        raise HTTPException(status_code=409, detail=f'Un cliente con la cédula {cliente.cedula} ya existe.')
    nuevo_cliente = models.Cliente(nombre=cliente.nombre, cedula=cliente.cedula, telefono=cliente.telefono)
    db.add(nuevo_cliente)
    db.commit()
    db.refresh(nuevo_cliente)
    return nuevo_cliente

@router.get('/clientes/', response_model=List[schemas.Cliente])
def leer_clientes(q: Optional[str]=None, db: Session=Depends(get_db)):
    """Obtiene una lista de todos los clientes, opcionalmente filtrada."""
    query = db.query(models.Cliente)
    if q:
        query = query.filter(models.Cliente.nombre.ilike(f'%{q}%') | models.Cliente.cedula.ilike(f'%{q}%') | models.Cliente.telefono.ilike(f'%{q}%'))
    return query.all()

@router.put('/clientes/{cliente_id}', response_model=schemas.Cliente)
def actualizar_cliente(cliente_id: int, cliente_data: schemas.ClienteBase, db: Session=Depends(get_db)):
    db_cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail='Cliente no encontrado')
    db_cliente.nombre = cliente_data.nombre
    db_cliente.cedula = cliente_data.cedula
    db_cliente.telefono = cliente_data.telefono
    db.commit()
    db.refresh(db_cliente)
    return db_cliente

@router.put('/clientes/{cliente_id}/', include_in_schema=False)
def actualizar_cliente_trailing_slash(cliente_id: int, cliente_data: schemas.ClienteBase, db: Session=Depends(get_db)):
    return actualizar_cliente(cliente_id, cliente_data, db)

@router.delete('/clientes/{cliente_id}')
def eliminar_cliente(cliente_id: int, db: Session=Depends(get_db)):
    db_cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not db_cliente:
        raise HTTPException(status_code=404, detail='Cliente no encontrado')
    db.delete(db_cliente)
    db.commit()
    return {'mensaje': 'Cliente eliminado'}

@router.delete('/clientes/{cliente_id}/', include_in_schema=False)
def eliminar_cliente_trailing_slash(cliente_id: int, db: Session=Depends(get_db)):
    return eliminar_cliente(cliente_id, db)

@router.get('/clientes/{cliente_id}/pagos', response_model=schemas.ClienteConPagos)
def leer_pagos_de_cliente(cliente_id: int, db: Session=Depends(get_db)):
    """Obtiene los detalles de un cliente y todos sus pagos asociados."""
    cliente = db.query(models.Cliente).filter(models.Cliente.id == cliente_id).first()
    if not cliente:
        raise HTTPException(status_code=404, detail='Cliente no encontrado')
    pagos = cliente.pagos or []
    total_bs = sum((float(p.monto or 0.0) for p in pagos))
    total_usd = sum((float(p.monto_usd or 0.0) for p in pagos))
    total_pagos = len(pagos)
    return {'id': cliente.id, 'nombre': cliente.nombre, 'cedula': cliente.cedula, 'telefono': cliente.telefono, 'pagos': pagos, 'total_bs': total_bs, 'total_usd': total_usd, 'total_pagos': total_pagos}

@router.post('/gestion/clientes/clear')
def limpiar_clientes(data: schemas.ConfirmBody, db: Session=Depends(get_db)):
    if not data.confirm:
        raise HTTPException(status_code=400, detail='Se requiere confirmación para borrar los clientes.')
    clientes = db.query(models.Cliente).all()
    deleted = len(clientes)
    for cliente in clientes:
        db.delete(cliente)
    db.commit()
    return {'mensaje': f'{deleted} clientes eliminados correctamente.'}

@router.get('/gestion/clientes/export')
def exportar_clientes_csv(db: Session=Depends(get_db)):
    clientes = db.query(models.Cliente).order_by(models.Cliente.id).all()
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['nombre', 'cedula', 'telefono'])
    for cliente in clientes:
        writer.writerow([cliente.nombre, cliente.cedula, cliente.telefono or ''])
    return Response(output.getvalue(), media_type='text/csv', headers={'Content-Disposition': 'attachment; filename=clientes_export.csv'})

@router.post('/gestion/clientes/import')
def importar_clientes(archivo: UploadFile=File(...), db: Session=Depends(get_db)):
    if not archivo.filename.lower().endswith('.csv'):
        raise HTTPException(status_code=400, detail='El archivo debe ser CSV.')
    contenido = archivo.file.read().decode('utf-8', errors='replace')
    lector = csv.DictReader(io.StringIO(contenido))
    creados = 0
    actualizados = 0
    for fila in lector:
        nombre = (fila.get('nombre') or fila.get('Nombre') or '').strip()
        cedula = (fila.get('cedula') or fila.get('Cédula') or fila.get('cedula') or '').strip()
        telefono = (fila.get('telefono') or fila.get('Telefono') or fila.get('teléfono') or '').strip()
        if not nombre or not cedula:
            continue
        existente = db.query(models.Cliente).filter(models.Cliente.cedula == cedula).first()
        if existente:
            existente.nombre = nombre
            existente.telefono = telefono
            actualizados += 1
        else:
            db.add(models.Cliente(nombre=nombre, cedula=cedula, telefono=telefono))
            creados += 1
    db.commit()
    return {'mensaje': f'Clientes importados: {creados}, actualizados: {actualizados}', 'creados': creados, 'actualizados': actualizados}

@router.get('/gestion/clientes/summary')
def resumen_clientes(db: Session=Depends(get_db)):
    total = db.query(models.Cliente).count()
    ultimos = db.query(models.Cliente).order_by(desc(models.Cliente.id)).limit(5).all()
    return {'total': total, 'ultimos': [{'nombre': c.nombre, 'cedula': c.cedula, 'telefono': c.telefono or ''} for c in ultimos]}

