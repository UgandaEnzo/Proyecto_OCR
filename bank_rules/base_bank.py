from abc import ABC, abstractmethod
import re

class BankStrategy(ABC):
    def __init__(self, name):
        self.name = name

    def limpiar_monto(self, valor_ocr):
        """Normaliza string '1.250,50' a float 1250.50"""
        from ocr_engine import limpiar_monto as generic_clean
        return generic_clean(valor_ocr)

    def extract_amount(self, texto):
        """Busca montos numéricos asociados a etiquetas de dinero."""
        # 1. Buscar montos con etiquetas (ej: Monto: 1.500,00)
        patrones = [
            r'(?:monto|total|importe|pagado|bs\.?|ves)[:\s]*([\d.,]+)',
            r'([\d.,]+)\s*(?:bs\.?|bol[ií]vares|ves)'
        ]
        for p in patrones:
            for m in re.finditer(p, texto, re.IGNORECASE):
                val = self.limpiar_monto(m.group(1))
                if val > 0: return val
        
        # 2. Fallback: buscar cualquier número con formato de moneda (,XX)
        matches = re.findall(r'(\d+[\d.,]*[\.,]\d{2})', texto)
        for m in matches:
            val = self.limpiar_monto(m)
            if val > 0: return val
        return 0.0

    def limpiar_referencia(self, texto):
        """Limpia caracteres OCR confusos (O->0, I->1)"""
        if not texto: return ""
        r = texto.upper().replace('O', '0').replace('I', '1').replace('|', '1').replace('L', '1').replace('S', '5')
        return re.sub(r'\D', '', r)

    def extract_generic_reference(self, texto):
        """Búsqueda estándar de referencia para bancos sin lógica especial"""
        prefijos_invalidos = ("0412", "0414", "0416", "0424", "0426")
        # Ampliamos el rango de búsqueda para capturar referencias que el OCR separó con espacios
        patron_ref = r'(?:Ref|Ret|Rel|ReF|Referencia|Referenda|Nro|Nr0|Num|Operaci[oó0]n|Oper|Documento|Confirmaci[oó0]n)[:\s\.]*([O0I1\|\d\s\.-]{6,20})'
        
        for m in re.finditer(patron_ref, texto, re.IGNORECASE):
            candidato_clean = self.limpiar_referencia(m.group(1))
            if 8 <= len(candidato_clean) <= 12 and not candidato_clean.startswith(prefijos_invalidos):
                return candidato_clean[:12] # Mercantil usa 12
        
        for m in re.finditer(r'(?<!\w)([0-9O0I1\|]{5,12})(?!\w)', texto):
            candidato_clean = self.limpiar_referencia(m.group(1))
            if 5 <= len(candidato_clean) <= 12 and not candidato_clean.startswith(prefijos_invalidos):
                return candidato_clean
        return "No detectada"

    @abstractmethod
    def procesar_comprobante(self, imagen, texto_completo):
        pass