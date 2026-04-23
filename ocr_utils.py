import unicodedata
from dotenv import load_dotenv
from rapidocr_onnxruntime import RapidOCR

load_dotenv()

# Inicialización única del motor RapidOCR
try:
    engine = RapidOCR()
    print("🚀 [SISTEMA] Motor OCR Único: RapidOCR inicializado correctamente.")
except Exception as e:
    print(f"❌ [SISTEMA] Error crítico al cargar RapidOCR: {e}")
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
    if engine is None:
        return ""
    try:
        result, _ = engine(imagen)
        if result:
            textos = [line[1] for line in result]
            return " ".join(textos)
    except Exception as e:
        print(f"⚠️ [OCR_UTILS] Error en extracción CV2: {e}")
    return ""
