import re
from typing import List, Dict, Optional, Any

"""
bank_rules.py
-------------
Módulo de reglas locales para la identificación, normalización y validación
de instituciones bancarias venezolanas.
"""

# Lista canónica de bancos (Fuente: Sudeban / BCV)
BANCOS_VENEZUELA = [
    {"id": "0102", "nombre": "Banco de Venezuela"},
    {"id": "0105", "nombre": "Mercantil"},
    {"id": "0108", "nombre": "Provincial"},
    {"id": "0114", "nombre": "Bancaribe"},
    {"id": "0115", "nombre": "Exterior"},
    {"id": "0128", "nombre": "Banco Caroní"},
    {"id": "0134", "nombre": "Banesco"},
    {"id": "0151", "nombre": "BFC Banco Fondo Común"},
    {"id": "0156", "nombre": "100% Banco"},
    {"id": "0157", "nombre": "DelSur"},
    {"id": "0163", "nombre": "Banco del Tesoro"},
    {"id": "0166", "nombre": "Banco Agrícola de Venezuela"},
    {"id": "0168", "nombre": "Bancrecer"},
    {"id": "0169", "nombre": "Mi Banco"},
    {"id": "0171", "nombre": "Banco Activo"},
    {"id": "0172", "nombre": "Bancamiga"},
    {"id": "0174", "nombre": "Banplus"},
    {"id": "0175", "nombre": "Banco Bicentenario"},
    {"id": "0177", "nombre": "Banfanb"},
    {"id": "0191", "nombre": "BNC Nacional de Crédito"},
]

# Diccionario de patrones Regex para detección reforzada vía OCR

class BankStrategy:
    """Clase base para estrategias de extracción por banco."""
    def __init__(self, bank_id: str, name: str, patterns: List[str]):
        self.bank_id = bank_id
        self.name = name
        self.patterns = patterns

    def matches(self, text: str) -> bool:
        text_lower = text.lower()
        return any(re.search(p, text_lower) for p in self.patterns)

    def _parse_amount(self, s: str) -> float:
        """Lógica interna de limpieza de montos para las reglas."""
        if not s: return 0.0
        s = re.sub(r'[^\d.,]', '', s).strip('.,')
        try:
            if ',' in s and '.' in s:
                if s.rfind(',') > s.rfind('.'): s = s.replace('.', '').replace(',', '.')
                else: s = s.replace(',', '')
            elif ',' in s: s = s.replace(',', '.')
            return float(s)
        except: return 0.0

    def procesar_comprobante(self, image, text: str) -> dict:
        """Extrae datos usando patrones comunes."""
        text_lower = text.lower()
        
        # Referencia: busca 6 a 14 dígitos después de palabras clave
        ref_match = re.search(r'(?:ref|referencia|operaci.n|nro|confirmaci.n)[:\s#]*(\d{6,14})', text_lower)
        referencia = ref_match.group(1) if ref_match else "No detectada"
        
        # Monto: busca patrones numéricos cerca de Bs o Monto
        monto = 0.0
        monto_match = re.search(r'(?:monto|bs\.?|importe)[:\s]*([\d\., ]+)', text_lower)
        if monto_match:
            monto = self._parse_amount(monto_match.group(1))
            
        return {
            "banco": self.name,
            "banco_origen": self.name,
            "referencia": referencia,
            "monto": monto
        }

class BNCStrategy(BankStrategy):
    """Estrategia optimizada para el Banco Nacional de Crédito."""
    def procesar_comprobante(self, image, text: str) -> dict:
        res = super().procesar_comprobante(image, text)
        text_lower = text.lower()
        
        # Refinamiento para BNC: El monto suele estar precedido por "Total Bs." o estar solo en una línea
        if res["monto"] == 0:
            # Patrón más agresivo para BNC: busca números con decimales después de Total o Bs
            # Captura formatos como "1.250,00", "1250,00" o incluso con espacios "1.250 , 00"
            bnc_monto = re.search(r'(?:total|monto|pagado)\s*(?:bs\.?|ves)?[:\s]*([\d\.]+\s*,\s*\d{2})', text_lower)
            if bnc_monto:
                res["monto"] = self._parse_amount(bnc_monto.group(1))
        
        return res

# Mapeo de estrategias
STRATEGIES = [
    BNCStrategy("0191", "BNC Nacional de Crédito", [r"bnc", r"b\.n\.c", r"nacional de cr.dito", r"banco nacional"]),
    BankStrategy("0102", "Banco de Venezuela", [r"venezuela", r"bdv", r"b\.d\.v"]),
    BankStrategy("0105", "Mercantil", [r"mercantil"]),
    BankStrategy("0108", "Provincial", [r"provincial", r"bbva"]),
    BankStrategy("0134", "Banesco", [r"banesco"]),
    BankStrategy("0172", "Bancamiga", [r"bancamiga"]),
]

def get_available_banks() -> List[str]:
    """Retorna los nombres de los bancos para el frontend (usado en main.py)."""
    return [b["nombre"] for b in BANCOS_VENEZUELA]

def get_canonical_banks() -> List[Dict[str, str]]:
    """Retorna la lista completa de bancos para selectores en el frontend."""
    return BANCOS_VENEZUELA

def get_bank_strategy(text: str, image=None) -> Optional[BankStrategy]:
    """Detecta qué estrategia de banco aplicar según el texto del OCR."""
    for strategy in STRATEGIES:
        if strategy.matches(text):
            return strategy
    return BankStrategy("0000", "Desconocido", [])

def normalize_bank_name(name: Optional[str]) -> str:
    """
    Toma un string (nombre o código) y lo convierte al nombre oficial.
    Utilizado para limpiar entradas de formularios manuales.
    """
    if not name:
        return "Desconocido"
    
    name_clean = name.strip().upper()
    for banco in BANCOS_VENEZUELA:
        if name_clean == banco["nombre"].upper() or name_clean == banco["id"]:
            return banco["nombre"]
    
    return name

def detect_bank_from_ocr(text: str) -> str:
    """Mantiene compatibilidad con versiones anteriores."""
    strategy = get_bank_strategy(text)
    return strategy.name if strategy else "Desconocido"