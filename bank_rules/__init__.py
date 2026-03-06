from .mercantil import MercantilStrategy
from .venezuela import VenezuelaStrategy
from .bbva import BBVAStrategy
from .generic import GenericStrategy
from .bnc import BncStrategy
from .delsur import DelsurStrategy
import cv2
import numpy as np

def get_bank_strategy(texto_ocr, imagen=None):
    """
    Selector de Estrategia Robusto basado en 'Puntos de Confianza'.
    Analiza texto (keywords, códigos) y visuales (color, fondo).
    """
    texto = texto_ocr.lower()
    
    # Inicializar puntajes
    scores = {
        "BNC": 0,
        "Venezuela": 0,
        "Delsur": 0,
        "Mercantil": 0,
        "BBVA": 0,
        "Banesco": 0,
        "BDT": 0
    }

    # --- 1. Anclajes de Identidad (Texto) ---

    # BNC (0191)
    if "app bnc" in texto: scores["BNC"] += 2
    if "soluciones financieras" in texto: scores["BNC"] += 2
    if "0191" in texto: scores["BNC"] += 3  # Prioridad Código
    if "bnc" in texto: scores["BNC"] += 1

    # Venezuela (0102)
    if "pagomóvilbdv" in texto or "pagomovilbdv" in texto: scores["Venezuela"] += 2
    if "s.a.c.a. banco universal" in texto: scores["Venezuela"] += 2
    if "0102" in texto: scores["Venezuela"] += 3  # Prioridad Código
    if "transferencias a terceros" in texto: scores["Venezuela"] += 1

    # Delsur (0157)
    # Nota: Verificamos frase específica aunque esté en minúsculas por robustez OCR
    if "número de referencia:" in texto: scores["Delsur"] += 2
    if "0157" in texto: scores["Delsur"] += 3  # Prioridad Código
    if "delsur" in texto: scores["Delsur"] += 1

    # Mercantil (734 / Tpago)
    if "tpago" in texto: scores["Mercantil"] += 2
    if "734" in texto: scores["Mercantil"] += 3
    if "mercantil" in texto: scores["Mercantil"] += 1

    # Otros
    if "dinero rápido" in texto or "bbva" in texto: scores["BBVA"] += 2
    if "banesco" in texto: scores["Banesco"] += 2
    if "bdt" in texto: scores["BDT"] += 2

    # --- 2. Reglas Especiales Visuales (Imagen) ---
    if imagen is not None:
        try:
            # Regla BNC: Color Verde (RGB ~ 0, 150, 0)
            # Usamos HSV para detectar rango de verdes
            hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
            # Rango verde aprox (H: 35-85)
            mask_green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
            ratio_green = cv2.countNonZero(mask_green) / (imagen.shape[0] * imagen.shape[1])
            
            if ratio_green > 0.01: # Si >1% es verde
                scores["BNC"] += 3

            # Regla BDV: Fondo Oscuro (Header)
            # Analizar brillo promedio del tercio superior
            header = imagen[:int(imagen.shape[0]*0.3), :]
            if np.mean(header) < 100: # Umbral de oscuridad
                scores["Venezuela"] += 3
        except Exception:
            pass

    # --- 3. Selección de Estrategia ---
    # Obtener el banco con mayor puntaje
    best_bank = max(scores, key=scores.get)
    max_score = scores[best_bank]

    if max_score >= 2:
        if best_bank == "Mercantil": return MercantilStrategy()
        if best_bank == "Venezuela": return VenezuelaStrategy()
        if best_bank == "BNC": return BncStrategy()
        if best_bank == "Delsur": return DelsurStrategy()
        if best_bank == "BBVA": return BBVAStrategy()
        if best_bank == "Banesco": return GenericStrategy("Banesco")
        if best_bank == "BDT": return GenericStrategy("BDT")
    
    return GenericStrategy("Desconocido")