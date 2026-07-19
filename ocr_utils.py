import os
import unicodedata
from dotenv import load_dotenv

load_dotenv()

# Motor RapidOCR con carga diferida (se evalúa en cada llamada para respetar cambios en MOTOR_OCR_ACTIVO)
_engine = None

def get_engine():
    """Retorna el motor RapidOCR si el modo actual es local, None si está en modo nube."""
    global _engine
    modo = os.getenv("MOTOR_OCR_ACTIVO", "rapidocr").lower()
    if modo == "rapidocr":
        if _engine is None:
            try:
                from rapidocr_onnxruntime import RapidOCR
                _engine = RapidOCR()
                print("🚀 [SISTEMA] Motor OCR Único: RapidOCR inicializado correctamente.")
            except Exception as e:
                print(f"❌ [SISTEMA] Error al cargar RapidOCR: {e}. El OCR usará solo IA.")
                _engine = None
    else:
        _engine = None
    return _engine

# Mantener compatibilidad con imports antiguos (ocr_engine.py)
engine = None

def normalizar_texto(texto):
    if not texto:
        return ""
    if isinstance(texto, bytes):
        texto = texto.decode("utf-8", "ignore")
    texto = unicodedata.normalize("NFKD", str(texto))
    texto = texto.encode("ascii", "ignore").decode("ascii")
    return texto.lower()

def extraer_texto_de_imagen_cv2(imagen):
    """Extrae texto de un objeto numpy (imagen cargada con CV2) usando RapidOCR."""
    eng = get_engine()
    if eng is None:
        return ""
    try:
        result, _ = eng(imagen)
        if result:
            textos = [line[1] for line in result]
            return " ".join(textos)
    except Exception as e:
        print(f"⚠️ [OCR_UTILS] Error en extracción CV2: {e}")
    return ""
