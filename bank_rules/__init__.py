from .mercantil import MercantilStrategy
from .venezuela import VenezuelaStrategy
from .bbva import BBVAStrategy
from .generic import GenericStrategy
from .bnc import BncStrategy
from .delsur import DelsurStrategy
import cv2
import numpy as np
import re

AVAILABLE_BANKS = [
    "Banco de Venezuela",
    "BBVA Provincial",
    "Mercantil",
    "DELSUR",
    "BNC",
    "Banesco",
    "BDT",
    "Banco Exterior",
    "Banco del Tesoro",
    "Provincial",
    "Banco Bicentenario",
    "Banco de la Fuerza Armada Nacional Bolivariana (BFA)",
    "Banco Venezolano de Crédito",
    "Banco Plaza",
    "Banco Activo",
    "Banco Fondo Común",
    "BOD",
    "Banco Caroní",
    "Banco Sofitasa",
    "Banco Agrícola de Venezuela",
    "Banco del Caribe",
    "Banco del Pueblo Soberano",
    "BANDEs",
    "Desconocido"
]


def get_available_banks():
    return list(AVAILABLE_BANKS)


def limpiar_texto_identificacion(texto):
    """Elimina frases que pueden confundir Banco Destino con Origen"""
    t = texto.lower()
    t = re.sub(r'banco\s*destino', ' ', t)
    t = re.sub(r'destino\s*:', ' ', t)
    return t


def get_bank_strategy(texto_ocr, imagen=None):
    """
    Selector de Estrategia Robusto basado en patrones de texto y visuales.
    Analiza texto (keywords, códigos) y visuales (color, fondo).
    """
    texto = texto_ocr.lower()
    texto_limpio = limpiar_texto_identificacion(texto)

    # --- 1. Detección directa de banco ---
    if "app bnc" in texto_limpio or "soluciones financieras" in texto_limpio or "bnc" in texto_limpio:
        return BncStrategy()

    if "bbva" in texto_limpio or "dinero rápido" in texto_limpio:
        return BBVAStrategy()

    if "banco de venezuela" in texto_limpio or "bdv" in texto_limpio or "pagomovilbdv" in texto_limpio or "pagomóvil" in texto_limpio or "0102" in texto_limpio:
        return VenezuelaStrategy()

    if "mercantil" in texto_limpio or "734" in texto_limpio or "tpago" in texto_limpio:
        return MercantilStrategy()

    if "delsur" in texto_limpio or "0157" in texto_limpio:
        return DelsurStrategy()

    if "banesco" in texto_limpio or "0134" in texto_limpio:
        return GenericStrategy("Banesco")

    if "bdt" in texto_limpio:
        return GenericStrategy("BDT")

    if "exterior" in texto_limpio or "0412" in texto_limpio:
        return GenericStrategy("Banco Exterior")

    if "tesoro" in texto_limpio or "0172" in texto_limpio:
        return GenericStrategy("Banco del Tesoro")

    if "provincial" in texto_limpio or "1002" in texto_limpio:
        return GenericStrategy("Provincial")

    if "bod" in texto_limpio or "0114" in texto_limpio or "banco occidental de descuento" in texto_limpio:
        return GenericStrategy("BOD")

    if "bicentenario" in texto_limpio or "0404" in texto_limpio:
        return GenericStrategy("Banco Bicentenario")

    if "banco de la fuerza" in texto_limpio or "fuerza armada" in texto_limpio or "bfa" in texto_limpio:
        return GenericStrategy("Banco de la Fuerza Armada Nacional Bolivariana (BFA)")

    if "venezolano de crédito" in texto_limpio or "bvc" in texto_limpio:
        return GenericStrategy("Banco Venezolano de Crédito")

    if "banco plaza" in texto_limpio or ("plaza" in texto_limpio and "provincial" not in texto_limpio and "bbva" not in texto_limpio):
        return GenericStrategy("Banco Plaza")

    if "banco activo" in texto_limpio or "activo" in texto_limpio:
        return GenericStrategy("Banco Activo")

    if "fondo comun" in texto_limpio or "fondo común" in texto_limpio:
        return GenericStrategy("Banco Fondo Común")

    if "caroní" in texto_limpio or "caroni" in texto_limpio:
        return GenericStrategy("Banco Caroní")

    if "sofitasa" in texto_limpio:
        return GenericStrategy("Banco Sofitasa")

    if "banco agrícola" in texto_limpio or "bav" in texto_limpio:
        return GenericStrategy("Banco Agrícola de Venezuela")

    if "banco del caribe" in texto_limpio or "caribe" in texto_limpio:
        return GenericStrategy("Banco del Caribe")

    if "bandes" in texto_limpio or "desarrollo económico" in texto_limpio:
        return GenericStrategy("BANDEs")

    if "banco del pueblo soberano" in texto_limpio or "bps" in texto_limpio:
        return GenericStrategy("Banco del Pueblo Soberano")

    # --- 2. Reglas visuales ---
    if imagen is not None:
        try:
            hsv = cv2.cvtColor(imagen, cv2.COLOR_BGR2HSV)
            mask_green = cv2.inRange(hsv, np.array([35, 40, 40]), np.array([85, 255, 255]))
            ratio_green = cv2.countNonZero(mask_green) / (imagen.shape[0] * imagen.shape[1])
            if ratio_green > 0.01:
                return BncStrategy()

            header = imagen[:int(imagen.shape[0] * 0.3), :]
            if np.mean(header) < 100 and "pagomovil" in texto_limpio:
                return VenezuelaStrategy()
        except Exception:
            pass

    # --- 3. Selección basada en puntaje ---
    scores = {
        "Mercantil": 0,
        "DELSUR": 0,
        "Banesco": 0,
        "BDT": 0,
        "Banco Exterior": 0,
        "Banco del Tesoro": 0,
        "Provincial": 0,
        "BOD": 0,
        "Banco Bicentenario": 0,
        "Banco de la Fuerza Armada Nacional Bolivariana (BFA)": 0,
        "Banco Venezolano de Crédito": 0,
        "Banco Plaza": 0,
        "Banco Activo": 0,
        "Banco Fondo Común": 0,
        "Banco Caroní": 0,
        "Banco Sofitasa": 0,
        "Banco Agrícola de Venezuela": 0,
        "Banco del Caribe": 0,
        "BANDEs": 0,
        "Banco del Pueblo Soberano": 0
    }

    if "número de referencia:" in texto_limpio or "número de referencia" in texto_limpio:
        scores["DELSUR"] += 2
    if "0157" in texto_limpio:
        scores["DELSUR"] += 3

    if "tpago" in texto_limpio:
        scores["Mercantil"] += 2
    if "734" in texto_limpio:
        scores["Mercantil"] += 3

    if "0134" in texto_limpio:
        scores["Banesco"] += 3
    if "banesco" in texto_limpio:
        scores["Banesco"] += 2

    if "bdt" in texto_limpio:
        scores["BDT"] += 3

    if "0412" in texto_limpio or "exterior" in texto_limpio:
        scores["Banco Exterior"] += 3

    if "0172" in texto_limpio or "tesoro" in texto_limpio:
        scores["Banco del Tesoro"] += 3

    if "provincial" in texto_limpio or "1002" in texto_limpio:
        scores["Provincial"] += 3

    if "bod" in texto_limpio or "0114" in texto_limpio or "banco occidental de descuento" in texto_limpio:
        scores["BOD"] += 3

    if "bicentenario" in texto_limpio or "0404" in texto_limpio:
        scores["Banco Bicentenario"] += 3

    if "bfa" in texto_limpio or "fuerza armada" in texto_limpio or "bolivariana" in texto_limpio:
        scores["Banco de la Fuerza Armada Nacional Bolivariana (BFA)"] += 3

    if "bvc" in texto_limpio or "venezolano de crédito" in texto_limpio:
        scores["Banco Venezolano de Crédito"] += 3

    if "banco plaza" in texto_limpio or ("plaza" in texto_limpio and "provincial" not in texto_limpio and "bbva" not in texto_limpio):
        scores["Banco Plaza"] += 3

    if "banco activo" in texto_limpio or "activo" in texto_limpio:
        scores["Banco Activo"] += 3

    if "fondo comun" in texto_limpio or "fondo común" in texto_limpio:
        scores["Banco Fondo Común"] += 3

    if "caroní" in texto_limpio or "caroni" in texto_limpio:
        scores["Banco Caroní"] += 3

    if "sofitasa" in texto_limpio:
        scores["Banco Sofitasa"] += 3

    if "banco agrícola" in texto_limpio or "bav" in texto_limpio:
        scores["Banco Agrícola de Venezuela"] += 3

    if "banco del caribe" in texto_limpio or "caribe" in texto_limpio:
        scores["Banco del Caribe"] += 3

    if "bandes" in texto_limpio or "desarrollo económico" in texto_limpio:
        scores["BANDEs"] += 3

    if "banco del pueblo soberano" in texto_limpio or "bps" in texto_limpio:
        scores["Banco del Pueblo Soberano"] += 3

    best_bank = max(scores, key=scores.get)
    if scores[best_bank] >= 2:
        if best_bank == "Mercantil":
            return MercantilStrategy()
        if best_bank == "DELSUR":
            return DelsurStrategy()
        return GenericStrategy(best_bank)

    return GenericStrategy("Desconocido")
