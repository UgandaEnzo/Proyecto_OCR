import re
import cv2
import numpy as np
from .data import get_available_banks, get_bank_by_sudeban_code, SUD_BANK_CODES
from .generic import GenericStrategy
from .mercantil import MercantilStrategy
from .venezuela import VenezuelaStrategy
from .bbva import BBVAStrategy
from .bnc import BncStrategy
from .delsur import DelsurStrategy


def extract_sudeban_code(texto):
    if not texto:
        return None
    for match in re.finditer(r'\b(\d{4})\b', texto):
        code = match.group(1)
        if code in SUD_BANK_CODES:
            return code
    return None


def normalize_bank_name(texto):
    if not texto:
        return "Desconocido"
    candidate = texto.strip()
    if candidate in get_available_banks():
        return candidate
    try:
        estrategia = get_bank_strategy(candidate)
        if estrategia and estrategia.name:
            return estrategia.name
    except Exception:
        pass
    return candidate


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

    codigo_sudeban = extract_sudeban_code(texto_limpio)
    if codigo_sudeban:
        banco_por_codigo = get_bank_by_sudeban_code(codigo_sudeban)
        if banco_por_codigo != "Desconocido":
            return GenericStrategy(banco_por_codigo)

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

    if "0412" in texto_limpio or "banco exterior" in texto_limpio:
        return GenericStrategy("Banco Exterior")

    if "0172" in texto_limpio or "banco del tesoro" in texto_limpio:
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

    if "banco plaza" in texto_limpio or "0171" in texto_limpio:
        return GenericStrategy("Banco Plaza")

    if "banco activo" in texto_limpio or "0173" in texto_limpio:
        return GenericStrategy("Banco Activo")

    if "fondo comun" in texto_limpio or "fondo común" in texto_limpio:
        return GenericStrategy("Banco Fondo Común")

    if "caroní" in texto_limpio or "caroni" in texto_limpio:
        return GenericStrategy("Banco Caroní")

    if "sofitasa" in texto_limpio:
        return GenericStrategy("Banco Sofitasa")

    if "banco agrícola" in texto_limpio or "bav" in texto_limpio:
        return GenericStrategy("Banco Agrícola de Venezuela")

    if "banco del caribe" in texto_limpio or "banco caribe" in texto_limpio:
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

    return GenericStrategy("Desconocido")
