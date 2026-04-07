import os
import re
import json
import cv2
from groq import Groq
import numpy as np
from PIL import Image
from dotenv import load_dotenv
from ocr_utils import engine, normalizar_texto

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

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

def limpiar_datos_ia(texto_ocr):
    """Utiliza Groq para estructurar el texto sucio del OCR en un JSON limpio."""
    if not client or not texto_ocr:
        return None
    
    prompt = """
    Actúa como un extractor de datos financieros experto en comprobantes de pago venezolanos.
    Tu objetivo es limpiar y estructurar el texto sucio de un OCR.
    Extrae los siguientes campos y devuélvelos en un JSON puro:
    1. 'monto': Busca el monto de la operación. Interpreta formatos como "1.500,00" o "Bs. 200" y conviértelo a un número float estándar (ej: 1500.0).
    2. 'referencia': Extrae el número de confirmación o referencia (usualmente 6-12 dígitos).
    3. 'cedula': Extrae la cédula de identidad si está presente.

    REGLA CRÍTICA: Responde ÚNICAMENTE con el objeto JSON, sin explicaciones ni texto adicional.
    Campos requeridos: {"monto": float, "referencia": "string", "cedula": "string" or null}.
    """

    try:
        response = client.chat.completions.create(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": texto_ocr}
            ],
            model=GROQ_MODEL,
            response_format={"type": "json_object"},
            temperature=0.0,
        )
        contenido = response.choices[0].message.content
        return json.loads(contenido)
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

def procesar_pago_ocr(image_path, aggressive=False):
    """Flujo Principal Optimizado: RapidOCR -> Groq (Extractor Principal)."""
    # 1. Carga de imagen con validación
    img_cv = cv2.imread(image_path)
    if img_cv is None:
        try:
            pil_img = Image.open(image_path).convert("RGB")
            img_cv = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception as e:
            print(f"❌ [OCR] Imagen inválida o ilegible: {e}")
            return {"referencia": "No detectada", "monto": 0.0, "banco": "Desconocido", "texto_completo": ""}

    # 2. Ejecutar RapidOCR (Extracción de texto base)
    texto_completo = extraer_texto(image_path)
    
    # 3. Procesar texto bruto con IA (Groq) - Ahora es el filtro principal
    ai_data = limpiar_datos_ia(texto_completo)
    
    if ai_data and isinstance(ai_data, dict):
        return {
            "referencia": str(ai_data.get("referencia") or "No detectada"),
            "monto": limpiar_monto(ai_data.get("monto")),
            "cedula": ai_data.get("cedula"),
            "texto_completo": texto_completo,
            "source": "AI_GROQ"
        }

    return {
        "referencia": "No detectada",
        "monto": 0.0,
        "texto_completo": texto_completo,
        "source": "UNKNOWN"
    }

def procesar_imagen(image_path, aggressive=False):
    return procesar_pago_ocr(image_path, aggressive)
