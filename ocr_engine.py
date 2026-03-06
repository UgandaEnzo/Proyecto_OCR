import cv2
import pytesseract
from pytesseract import Output
import re
import numpy as np
from PIL import Image
import unicodedata
import os
import bank_rules

# IMPORTANTE: Configura la ruta donde instalaste Tesseract en Windows
# Se busca en variable de entorno, luego en ruta por defecto de Windows, o se asume en PATH
DEFAULT_TESSERACT_PATH = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
tesseract_cmd = os.getenv("TESSERACT_CMD", DEFAULT_TESSERACT_PATH)

if os.path.exists(tesseract_cmd):
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
# Si no existe la ruta específica, confiamos en que 'tesseract' esté en el PATH del sistema

def procesar_imagen(image_path):
    print(f"[OCR] Imagen recibida: {image_path}")
    
    # 1. Cargar Imagen
    img_initial = cv2.imread(image_path)
    if img_initial is None:
        try:
            pil_img = Image.open(image_path).convert("RGB")
            img_initial = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)
        except Exception:
            return {"referencia": "No detectada", "monto": 0.0, "banco": "Desconocido", "texto_completo": ""}

    # 2. Lectura Inicial (Identificación)
    gray_initial = cv2.cvtColor(img_initial, cv2.COLOR_BGR2GRAY)
    gray_initial = cv2.resize(gray_initial, None, fx=1.5, fy=1.5, interpolation=cv2.INTER_CUBIC)
    texto_completo = pytesseract.image_to_string(gray_initial, config='--psm 6')
    
    # 3. Obtener Estrategia (Factory)
    # Pasamos la imagen original para análisis de color/fondo
    estrategia = bank_rules.get_bank_strategy(texto_completo, img_initial)
    print(f"[OCR] Banco detectado: {estrategia.name}")
    
    # 4. Ejecutar Estrategia
    resultado = estrategia.procesar_comprobante(img_initial, texto_completo)
    
    print(f"[OCR] Monto extraído: {resultado['monto']}")
    print(f"[OCR] Referencia extraída: {resultado['referencia']}")
    
    return resultado