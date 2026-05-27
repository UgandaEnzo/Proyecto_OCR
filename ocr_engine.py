import os
import re
import json
import io
import base64
import cv2
from groq import AsyncGroq
import numpy as np
from PIL import Image
from pydantic import BaseModel, Field
from dotenv import load_dotenv
from ocr_utils import engine
import bank_rules


class OcrData(BaseModel):
    monto: float = 0.0
    referencia: str = "No detectada"
    cedula: str | None = None
    banco: str | None = None
    sudeban_code: str | None = None

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"

client = AsyncGroq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def extraer_texto(ruta_imagen):
    """Usa RapidOCR para extraer texto plano de la imagen."""
    if engine is None:
        return ""
    
    try:
        # RapidOCR devuelve (result, elapse_time)
        # result es una lista de [dt_boxes, rec_res, score]
        result, _ = engine(ruta_imagen)
        if result:
            # Unimos todos los rec_res (texto detectado) en un solo string
            textos = [line[1] for line in result]
            return " ".join(textos)
    except Exception as e:
        print(f"❌ [OCR] Error procesando imagen con RapidOCR: {e}")
    return ""

def _extraer_json_de_texto(texto: str) -> dict | None:
    if not texto:
        return None
    texto = texto.strip()
    encontrado = re.search(r'\{.*\}', texto, re.DOTALL)
    if encontrado:
        try:
            return json.loads(encontrado.group(0))
        except json.JSONDecodeError:
            pass
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None


async def limpiar_datos_ia(texto_ocr):
    """Utiliza Groq (Async) para estructurar el texto sucio del OCR en un JSON limpio."""
    if not client or not texto_ocr:
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
        response = await client.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto_ocr}
            ],
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        contenido = response.choices[0].message.content
        datos = _extraer_json_de_texto(contenido)
        if datos:
            validated = OcrData(**datos)
            return validated.model_dump()
        return None
    except Exception as e:
        print(f"⚠️ [IA] Error en limpieza con Groq: {e}")
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


VISION_MODEL = "llama-3.2-11b-vision-preview"


async def _extraer_datos_con_vision(image_bytes: bytes) -> dict | None:
    """Envía la imagen directamente a Groq Vision para extraer todos los datos del comprobante."""
    api_key = os.getenv("GROQ_API_KEY", "").strip()
    if not api_key:
        return None
    try:
        from groq import AsyncGroq
        client = AsyncGroq(api_key=api_key)
        with Image.open(io.BytesIO(image_bytes)) as img:
            img = img.convert("RGB")
            max_dim = max(img.width, img.height)
            if max_dim > 720:
                scale = 720 / max_dim
                img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=60, optimize=True)
            compressed = buf.getvalue()
        image_b64 = base64.b64encode(compressed).decode("utf-8")
        prompt = """Eres un extractor de datos de comprobantes de pago venezolanos.
Analiza la imagen y devuelve SOLO un JSON válido con estos campos:
- "monto": el monto como número float (ej: 1500.50)
- "referencia": el número de referencia/confirmación (string de dígitos)
- "banco": nombre del banco emisor
- "cedula": cédula de identidad si aparece
- "sudeban_code": código SUDEBAN de 4 dígitos si aparece

Responde ÚNICAMENTE con el JSON, sin texto adicional."""
        response = await client.chat.completions.create(
            messages=[{"role": "user", "content": [{"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}}, {"type": "text", "text": prompt}]}],
            model=VISION_MODEL, temperature=0.0, max_tokens=300
        )
        content = response.choices[0].message.content or ""
        encontrado = re.search(r'\{.*\}', content, re.DOTALL)
        if encontrado:
            return json.loads(encontrado.group(0))
    except Exception as e:
        print(f"⚠️ [VISION] Error extrayendo datos con Groq Vision: {e}")
    return None


async def procesar_pago_ocr(image_path, aggressive=False):
    """Flujo Principal: RapidOCR -> Groq, con fallback a Groq Vision si no hay OCR local."""
    img_cv = cv2.imread(image_path)
    img_bytes = None
    if img_cv is None:
        try:
            pil_img = Image.open(image_path).convert("RGB")
            img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"❌ [OCR] Imagen inválida o ilegible: {e}")
            return {"referencia": "No detectada", "monto": 0.0, "banco_predicho": "Desconocido", "texto_completo": ""}

    texto_completo = extraer_texto(image_path)
    ai_data = None

    # Si hay texto OCR, usa Groq texto
    if texto_completo.strip():
        ai_data = await limpiar_datos_ia(texto_completo)

    # Fallback: si no hay OCR o no se extrajeron datos, usa Groq Vision
    if not ai_data:
        with open(image_path, "rb") as f:
            img_bytes = f.read()
        vision_data = await _extraer_datos_con_vision(img_bytes)
        if vision_data:
            texto_completo = texto_completo or f"Vision: ref={vision_data.get('referencia')} monto={vision_data.get('monto')}"
            ai_data = vision_data

    pred_banco_ia = None
    pred_sudeban = None
    if ai_data and isinstance(ai_data, dict):
        pred_banco_ia = ai_data.get("banco")
        pred_sudeban = ai_data.get("sudeban_code")

    strategy = bank_rules.get_bank_strategy(texto_completo, img_cv)
    banco_predicho = strategy.name if strategy else "Desconocido"
    sudeban_code = pred_sudeban or extract_sudeban_code(texto_completo)
    if sudeban_code:
        banco_desde_sudeban = bank_rules.get_bank_by_sudeban_code(sudeban_code)
        if banco_desde_sudeban and banco_desde_sudeban != "Desconocido":
            banco_predicho = banco_desde_sudeban

    if pred_banco_ia and isinstance(pred_banco_ia, str) and pred_banco_ia.strip():
        banco_ia = pred_banco_ia.strip()
        if banco_ia not in bank_rules.get_available_banks():
            banco_normalizado = bank_rules.normalize_bank_name(banco_ia)
            banco_ia = banco_normalizado if banco_normalizado else banco_ia
    else:
        banco_ia = None

    if ai_data and isinstance(ai_data, dict):
        return {
            "referencia": str(ai_data.get("referencia") or "No detectada"),
            "monto": limpiar_monto(ai_data.get("monto")),
            "cedula": ai_data.get("cedula"),
            "banco_ia": banco_ia,
            "banco_predicho": banco_predicho,
            "sudeban_code": sudeban_code,
            "texto_completo": texto_completo,
            "source": "VISION" if not texto_completo.strip() else "AI_GROQ"
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
