import cv2
import pytesseract
from pytesseract import Output
import re
import numpy as np
from PIL import Image
import unicodedata
import os
import bank_rules
from skill_engine import SkillEngine
from dotenv import load_dotenv
 
# --- Configuración de Tesseract ---
# Aseguramos que se carguen las variables de entorno para detectar TESSERACT_CMD
load_dotenv()

# Busca la ruta del ejecutable de Tesseract en la variable de entorno TESSERACT_CMD.
# Si la variable está definida y la ruta es válida, se usa.
# Si no, se asume que 'tesseract' está en el PATH del sistema.
tesseract_cmd = os.getenv("TESSERACT_CMD")
if tesseract_cmd and os.path.exists(tesseract_cmd):
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    print(f"[OCR] Tesseract configurado en: {tesseract_cmd}")
else:
    print("❌ [OCR] ADVERTENCIA: TESSERACT_CMD no configurada o ruta inválida.")
    print("   Asegúrate de instalar Tesseract OCR y definir TESSERACT_CMD en tu archivo .env")
    print("   Ejemplo: TESSERACT_CMD=C:\\Program Files\\Tesseract-OCR\\tesseract.exe")

# Instancia global del motor de skills
skill_engine = SkillEngine()

def procesar_con_skill(texto_crudo):
    """Intenta procesar el texto usando la Skill de IA."""
    print("[OCR] Intentando extracción con Skill IA...")
    data = skill_engine.extraer_datos(texto_crudo)
    
    # Validación simple para saber si la IA falló
    if not data or not data.get("referencia") or data.get("referencia") in ["S/R", "No detectada", ""]:
        print("[OCR] Skill IA no encontró referencia o falló.")
        return None
    
    # Normalizar salida
    data["source"] = "AI_SKILL"
    
    # --- MEJORA: Limpieza robusta del monto ---
    # A veces la IA devuelve strings como "1.500,00" aunque le pidamos float.
    raw_monto = data.get("monto")
    try:
        if isinstance(raw_monto, str):
            # Eliminar todo lo que no sea número, punto o coma
            clean = re.sub(r'[^\d.,]', '', raw_monto)
            # Lógica Venezuela: Si hay coma, reemplazar por punto para Python
            if ',' in clean:
                clean = clean.replace('.', '').replace(',', '.')
            data["monto"] = float(clean)
        else:
            data["monto"] = float(raw_monto or 0.0)
    except Exception as e:
        print(f"[OCR] Error parseando monto IA: {e}")
        data["monto"] = 0.0

    print(f"[OCR] Skill IA Éxito: {data}")
    return data

def procesar_imagen(image_path, aggressive=False):
    print(f"[OCR] Imagen recibida: {image_path}")
    
    # 1. Cargar Imagen
    img_initial = cv2.imread(image_path)
    if img_initial is None:
        try:
            pil_img = Image.open(image_path).convert("RGB")
            img_initial = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception:
            return {"referencia": "No detectada", "monto": 0.0, "banco": "Desconocido", "texto_completo": ""}

    if aggressive:
        print("[OCR] Aplicando pre-procesamiento agresivo (Reintento)...")
        # CLAHE en canal L (Lab) para mejorar contraste local
        lab = cv2.cvtColor(img_initial, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8,8))
        cl = clahe.apply(l)
        limg = cv2.merge((cl,a,b))
        img_initial = cv2.cvtColor(limg, cv2.COLOR_LAB2BGR)

    # 2. Lectura Inicial (Identificación)
    gray_initial = cv2.cvtColor(img_initial, cv2.COLOR_BGR2GRAY)
    
    # --- MEJORA: Detección automática de Modo Oscuro ---
    # Si el brillo promedio es bajo (< 110), invertimos los colores para que Tesseract lea mejor.
    if np.mean(gray_initial) < 110:
        print("[OCR] Detectado fondo oscuro. Invirtiendo colores para mejorar lectura...")
        gray_initial = cv2.bitwise_not(gray_initial)

    # Aumentamos más la escala (2.0x) para capturar números pequeños o borrosos
    gray_initial = cv2.resize(gray_initial, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    texto_completo = pytesseract.image_to_string(gray_initial, config='--psm 6')
    
    # 3. Intento Principal: Skill IA (LLM)
    resultado = procesar_con_skill(texto_completo)
    
    # 4. Fallback: Reglas Rígidas (Legacy)
    if not resultado:
        print("[OCR] Usando Fallback: Reglas Rígidas (bank_rules)")
        # Obtener Estrategia (Factory)
        estrategia = bank_rules.get_bank_strategy(texto_completo, img_initial)
        print(f"[OCR] Banco detectado (Reglas): {estrategia.name}")
        
        # Ejecutar Estrategia
        resultado = estrategia.procesar_comprobante(img_initial, texto_completo)
        resultado["source"] = "RULES_LEGACY"
    
    # Asegurar que el texto completo viaje en la respuesta para depuración
    resultado["texto_completo"] = texto_completo
    
    print(f"[OCR] Monto extraído: {resultado['monto']}")
    print(f"[OCR] Referencia extraída: {resultado['referencia']}")
    print(f"[OCR] Método utilizado: {resultado.get('source', 'Unknown')}")
    
    return resultado