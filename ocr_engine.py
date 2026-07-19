import os
import re
import asyncio
import io
import cv2
import numpy as np
from PIL import Image
from pydantic import BaseModel
from ocr_utils import get_engine
import bank_rules
from utils import _extraer_datos_vision, logger
from ai_client import openrouter


class OcrData(BaseModel):
    monto: float = 0.0
    referencia: str = "No detectada"
    cedula: str | None = None
    banco: str | None = None
    sudeban_code: str | None = None

def _modo_ocr():
    """Retorna 'local' o 'nube' según MOTOR_OCR_ACTIVO."""
    return 'local' if os.getenv("MOTOR_OCR_ACTIVO", "rapidocr").lower() == "rapidocr" else 'nube'

def extraer_texto(ruta_imagen):
    """Usa RapidOCR para extraer texto plano de la imagen."""
    eng = get_engine()
    if eng is None:
        return ""
    
    try:
        # RapidOCR devuelve (result, elapse_time)
        # result es una lista de [dt_boxes, rec_res, score]
        result, _ = eng(ruta_imagen)
        if result:
            # Unimos todos los rec_res (texto detectado) en un solo string
            textos = [line[1] for line in result]
            return " ".join(textos)
    except Exception as e:
        print(f"❌ [OCR] Error procesando imagen con RapidOCR: {e}")
    return ""

async def limpiar_datos_ia(texto_ocr):
    """Usa OpenRouter (gemma) para estructurar el texto sucio del OCR en un JSON limpio."""
    if not openrouter.is_available() or not texto_ocr:
        return None

    prompt = """
    Actúa como un extractor de datos financieros experto en comprobantes de pago venezolanos.
    Tu objetivo es limpiar y estructurar el texto sucio de un OCR.
    Extrae los siguientes campos y devuélvelos en un JSON puro:
    1. 'monto': Busca el monto de la operación. Interpreta formatos como "1.500,00" o "Bs. 200" y conviértelo a un número float estándar (ej: 1500.0).
    2. 'referencia': Extrae el número de confirmación o referencia (usualmente 6-12 dígitos).
    3. 'cedula': Extrae la cédula de identidad si está presente.
    4. 'banco': Si el nombre del banco aparece en el texto, devuélvelo con su nombre completo.
    5. 'sudeban_code': Extrae cualquier código SUDEBAN de 4 dígitos si está presente.

    REGLA CRÍTICA: Responde ÚNICAMENTE con el objeto JSON, sin explicaciones ni texto adicional.
    Campos requeridos: {"monto": float, "referencia": "string", "cedula": "string" or null, "banco": "string" or null, "sudeban_code": "string" or null}.
    """

    try:
        datos = await openrouter.extract_json(texto_ocr, prompt)
        if datos:
            validated = OcrData(**datos)
            return validated.model_dump()
        return None
    except Exception as e:
        print(f"⚠️ [IA] Error en limpieza con OpenRouter: {e}")
    return None

def limpiar_monto(valor):
    """Simplificación extrema: Confía en la IA y solo asegura el tipo float."""
    if valor is None: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    try:
        # Por si la IA devolvió un string con formato regional
        s = str(valor).replace(',', '.')
        return float(re.sub(r'[^\d.]', '', s))
    except:
        return 0.0

def extract_sudeban_code(texto):
    if not texto:
        return None
    for match in re.finditer(r'\b(\d{4})\b', texto):
        code = match.group(1)
        if bank_rules.get_bank_by_sudeban_code(code) != "Desconocido":
            return code
    return None


def _parse_local_fallback(texto_ocr):
    """Parsea el texto del OCR local sin IA. Extrae referencia, monto y cédula con regex."""
    if not texto_ocr:
        return None
    resultado = {"referencia": "No detectada", "monto": 0.0, "cedula": None, "banco": None, "sudeban_code": None}
    texto = texto_ocr.strip()
    refs = re.findall(r'\b(\d{6,20})\b', texto)
    refs_ordenadas = sorted(set(refs), key=len, reverse=True)
    if refs_ordenadas:
        for ref in refs_ordenadas:
            if len(ref) >= 6 and len(ref) <= 20:
                resultado["referencia"] = ref
                break
    montos = re.findall(r'(?:Bs\.?\s*|Bs\s*|Monto\s*:?\s*|Total\s*:?\s*|\.?)\s*([0-9]{1,3}(?:\.[0-9]{3})*(?:\,[0-9]{2})?|[0-9]{1,9}(?:\,[0-9]{2})?)', texto, re.IGNORECASE)
    for m in montos:
        try:
            limpio = m.replace('.', '').replace(',', '.')
            valor = float(limpio)
            if valor > 0 and valor < 999999999:
                resultado["monto"] = valor
                break
        except ValueError:
            continue
    if resultado["monto"] == 0.0:
        montos_simples = re.findall(r'\b(\d{3,9}(?:[.,]\d{1,2})?)\b', texto)
        for m in montos_simples:
            try:
                limpio = m.replace(',', '.')
                valor = float(limpio)
                if 50 < valor < 999999999:
                    resultado["monto"] = valor
                    break
            except ValueError:
                continue
    cedulas = re.findall(r'\b(V|E|J|G|C|L)?[-.]?\s?(\d{6,9})\b', texto, re.IGNORECASE)
    for prefijo, num in cedulas:
        if 6 <= len(num) <= 9:
            resultado["cedula"] = f"{prefijo.upper() if prefijo else ''}{num}"
            break
    sudeban = extract_sudeban_code(texto)
    if sudeban:
        resultado["sudeban_code"] = sudeban
    if resultado["referencia"] != "No detectada" or resultado["monto"] > 0:
        return resultado
    return None

async def procesar_pago_ocr(image_path, aggressive=False):
    """Solo decide qué OCR usar según MOTOR_OCR_ACTIVO, sin mezclar cadenas."""
    try:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
    except Exception as e:
        logger.error("No se pudo leer la imagen: %s", e)
        return {"referencia": "No detectada", "monto": 0.0, "banco_predicho": "Desconocido", "texto_completo": ""}

    img_cv = cv2.imdecode(np.frombuffer(img_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img_cv is None:
        try:
            pil = Image.open(io.BytesIO(img_bytes)).convert("RGB")
            img_cv = cv2.cvtColor(np.array(pil), cv2.COLOR_RGB2BGR)
        except Exception as e:
            logger.error("Imagen inválida: %s", e)
            return {"referencia": "No detectada", "monto": 0.0, "banco_predicho": "Desconocido", "texto_completo": ""}

    modo = _modo_ocr()
    texto_completo = ""
    ai_data = None
    source = "UNKNOWN"

    if modo == 'local':
        try:
            texto_completo = await asyncio.wait_for(
                asyncio.to_thread(extraer_texto, image_path), timeout=8.0
            )
        except asyncio.TimeoutError:
            logger.info("OCR local tardó >8s")

        if texto_completo.strip():
            ai_data = await limpiar_datos_ia(texto_completo)
            if ai_data:
                source = "AI_OPENROUTER"
                logger.info("IA limpió OCR local: ref=%s monto=%s", ai_data.get('referencia'), ai_data.get('monto'))
            else:
                local_data = _parse_local_fallback(texto_completo)
                if local_data:
                    ai_data = local_data
                    source = "LOCAL_FALLBACK"
                    logger.info("Parseo local (fallback) extrajo: ref=%s monto=%s", local_data.get('referencia'), local_data.get('monto'))
    else:
        try:
            vision_data = await _extraer_datos_vision(img_bytes)
            if vision_data:
                ai_data = vision_data
                texto_completo = f"Vision: ref={vision_data.get('referencia')} monto={vision_data.get('monto')}"
                source = "VISION_OPENROUTER"
        except Exception as e:
            logger.error("Vision fallback error: %s", e)

    pred_banco_ia = ai_data.get("banco") if isinstance(ai_data, dict) else None
    pred_sudeban = ai_data.get("sudeban_code") if isinstance(ai_data, dict) else None

    strategy = bank_rules.get_bank_strategy(texto_completo, img_cv)
    banco_predicho = strategy.name if strategy else "Desconocido"
    sudeban_code = pred_sudeban or extract_sudeban_code(texto_completo)
    if sudeban_code:
        banco_desde_sudeban = bank_rules.get_bank_by_sudeban_code(sudeban_code)
        if banco_desde_sudeban and banco_desde_sudeban != "Desconocido":
            banco_predicho = banco_desde_sudeban

    banco_ia = None
    if pred_banco_ia and isinstance(pred_banco_ia, str) and pred_banco_ia.strip():
        banco_ia = pred_banco_ia.strip()
        if banco_ia not in bank_rules.get_available_banks():
            banco_normalizado = bank_rules.normalize_bank_name(banco_ia)
            banco_ia = banco_normalizado if banco_normalizado else banco_ia

    if isinstance(ai_data, dict):
        return {
            "referencia": str(ai_data.get("referencia") or "No detectada"),
            "monto": limpiar_monto(ai_data.get("monto")),
            "cedula": ai_data.get("cedula"),
            "banco_ia": banco_ia,
            "banco_predicho": banco_predicho,
            "sudeban_code": sudeban_code,
            "texto_completo": texto_completo,
            "source": source
        }

    return {
        "referencia": "No detectada",
        "monto": 0.0,
        "cedula": None,
        "banco_ia": None,
        "banco_predicho": banco_predicho,
        "sudeban_code": sudeban_code,
        "texto_completo": texto_completo,
        "source": "UNKNOWN"
    }

async def procesar_imagen(image_path, aggressive=False):
    return await procesar_pago_ocr(image_path, aggressive)
