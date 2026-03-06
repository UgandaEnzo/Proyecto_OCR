from .mercantil import MercantilStrategy
from .venezuela import VenezuelaStrategy
from .bbva import BBVAStrategy
from .generic import GenericStrategy
from .bnc import BncStrategy
from .delsur import DelsurStrategy
import cv2
import numpy as np
import re

def limpiar_texto_identificacion(texto):
    """Elimina frases que pueden confundir Banco Destino con Origen"""
    t = texto.lower()
    t = re.sub(r'banco\s*destino', ' ', t)
    t = re.sub(r'destino\s*:', ' ', t)
    return t

def get_bank_strategy(texto_ocr, imagen=None):
    """
    Selector de Estrategia Robusto basado en 'Puntos de Confianza'.
    Analiza texto (keywords, códigos) y visuales (color, fondo).
    """
    texto = texto_ocr.lower()
    texto_limpio = limpiar_texto_identificacion(texto)
    
    # --- 1. Prioridad 1: Los 'Dueños' de la App (Marcas Únicas) ---
    
    # BNC
    if "app bnc" in texto_limpio or "soluciones financieras" in texto_limpio:
        return BncStrategy()
        
    # BBVA Provincial
    if "dinero rápido" in texto_limpio or "bbva" in texto_limpio:
        return BBVAStrategy()
        
    # Banco de Venezuela
    if "pagomóvilbdv" in texto_limpio or "pagomovilbdv" in texto_limpio:
        return VenezuelaStrategy()

    # --- 2. Otros Bancos (Sin conflicto conocido, usamos lógica estándar o scores) ---
    scores = {
        "Delsur": 0,
        "Mercantil": 0,
        "BDT": 0
    }


    # Delsur (0157)
    # Nota: Verificamos frase específica aunque esté en minúsculas por robustez OCR
    if "número de referencia:" in texto: scores["Delsur"] += 2
    if "0157" in texto: scores["Delsur"] += 3  # Prioridad Código
    if "delsur" in texto: scores["Delsur"] += 1

    # Mercantil (734 / Tpago)
    if "tpago" in texto: scores["Mercantil"] += 2
    if "734" in texto: scores["Mercantil"] += 3
    if "mercantil" in texto: scores["Mercantil"] += 1

    # BDT
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
                return BncStrategy()

            # Regla BDV: Fondo Oscuro (Header)
            # Analizar brillo promedio del tercio superior
            header = imagen[:int(imagen.shape[0]*0.3), :]
            if np.mean(header) < 100: # Umbral de oscuridad
                pass # Ya cubierto por texto o muy genérico
        except Exception:
            pass

    # --- 3. Selección de Estrategia ---
    # Obtener el banco con mayor puntaje
    best_bank = max(scores, key=scores.get)
    max_score = scores[best_bank]

    if max_score >= 2:
        if best_bank == "Mercantil": return MercantilStrategy()
        if best_bank == "Delsur": return DelsurStrategy()
        if best_bank == "BDT": return GenericStrategy("BDT")
        
    # --- 3. Prioridad 2: Banesco (Último recurso) ---
    if "banesco móvil" in texto_limpio or "banesco movil" in texto_limpio or "0134" in texto_limpio:
        return GenericStrategy("Banesco")
    
    return GenericStrategy("Desconocido")