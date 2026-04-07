import os
import re
import json
import cv2
import numpy as np
import base64
from groq import Groq
from PIL import Image
import bank_rules
from dotenv import load_dotenv
from ocr_utils import engine, normalizar_texto

load_dotenv()

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")
GROQ_VISION_MODEL = "llama-3.2-11b-vision-preview"

client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY else None

def encode_image(image_path):
    """Codifica la imagen en base64 para los modelos de visión de Groq."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

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

def analizar_con_vision(image_path):
    """Fallback avanzado: Envía la imagen directamente a Llama Vision."""
    if not client: return None
    try:
        base64_image = encode_image(image_path)
        prompt = """
        Analiza este comprobante de pago venezolano. 
        Extrae: banco, monto, referencia y cedula.
        El monto suele estar cerca de 'Bs.' o 'Total'.
        Responde estrictamente en JSON: {"banco": "...", "monto": 0.0, "referencia": "...", "cedula": "..."}
        """
        response = client.chat.completions.create(
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                    }
                ]
            }],
            model=GROQ_VISION_MODEL,
            response_format={"type": "json_object"},
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        print(f"⚠️ [Vision] Error: {e}")
        return None

def limpiar_datos_ia(texto_ocr):
    """Utiliza Groq para estructurar el texto sucio del OCR en un JSON limpio."""
    if not client or not texto_ocr:
        return None
    
    prompt = """
    Eres un experto financiero analizando comprobantes de pago en Venezuela (Pago Móvil y Transferencias). 
    Del siguiente texto extraído por OCR, extrae:
    1. 'banco': Nombre del banco emisor.
    2. 'monto': Valor numérico (usa punto como decimal).
    3. 'referencia': Número de operación (6-12 dígitos). Corrige 'O' por '0' si es necesario.
    4. 'cedula': Documento de identidad del emisor si aparece.

    Responde estrictamente en formato JSON con estas llaves: {"banco": "...", "monto": 0.0, "referencia": "...", "cedula": "..."}.
    Si no estás seguro de un campo, pon null.
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
    if valor is None: return 0.0
    if isinstance(valor, (int, float)): return float(valor)
    s = str(valor).lower().strip()
    s = re.sub(r'bs\.?|bol[ií]vares|ves|monto|total|pagado|importe', '', s)
    s = re.sub(r'[^\d.,]', '', s).strip('.,')
    if not s: return 0.0
    dots = s.count('.')
    commas = s.count(',')
    if commas == 1:
        parts = s.split(',')
        entero = parts[0].replace('.', '')
        decimal = parts[1]
        try: return float(f"{entero}.{decimal}")
        except: pass
    if dots > 0 and commas == 0:
        parts = s.split('.')
        if dots > 1: return float("".join(parts))
        last_part = parts[-1]
        if len(last_part) <= 2: return float(f"{parts[0]}.{last_part}")
        else: return float("".join(parts))
    try: return float(s.replace('.', '').replace(',', ''))
    except: return 0.0

def procesar_pago_ocr(image_path, aggressive=False):
    """Flujo Principal: RapidOCR -> bank_rules -> Groq Fallback."""
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
    
    # 3. Clasificación mediante reglas locales (Rápido y privado)
    estrategia = bank_rules.get_bank_strategy(texto_completo, img_cv)
    resultado_final = {
        "referencia": "No detectada",
        "monto": 0.0,
        "banco": "Desconocido",
        "texto_completo": texto_completo,
        "source": "UNKNOWN"
    }

    # Si detectamos un banco específico, intentamos procesarlo localmente
    if estrategia and estrategia.name.lower() != "desconocido":
        resultado_local = estrategia.procesar_comprobante(img_cv, texto_completo)
        
        # Validación de calidad: Si tenemos monto y referencia, terminamos aquí
        if resultado_local.get("referencia") != "No detectada" and resultado_local.get("monto", 0) > 0:
            resultado_local["source"] = "RULES_LOCAL"
            return resultado_local
        else:
            # Si las reglas fallaron en extraer datos clave, marcamos para IA
            print(f"[OCR] Reglas para {estrategia.name} incompletas. Usando IA...")
            resultado_final.update(resultado_local)

    # 4. Fallback con IA (Texto)
    ai_data = limpiar_datos_ia(texto_completo)
    
    # 5. ULTIMA INSTANCIA: Si la IA de texto no tiene monto, usamos VISION
    if (not ai_data or not ai_data.get("monto")) and not aggressive:
        print("[OCR] Fallback de texto fallido. Activando Llama Vision...")
        ai_data = analizar_con_vision(image_path)

    if ai_data and isinstance(ai_data, dict):
        banco_ia = ai_data.get("banco") or resultado_final.get("banco")
        monto_ia = limpiar_monto(ai_data.get("monto")) or resultado_final.get("monto")
        ref_ia = str(ai_data.get("referencia") or resultado_final.get("referencia"))

        return {
            "banco": banco_ia,
            "banco_origen": banco_ia,
            "referencia": ref_ia,
            "monto": monto_ia,
            "cedula": ai_data.get("cedula"),
            "texto_completo": texto_completo,
            "source": "AI_GROQ"
        }

    return resultado_final

def procesar_imagen(image_path, aggressive=False):
    return procesar_pago_ocr(image_path, aggressive)
