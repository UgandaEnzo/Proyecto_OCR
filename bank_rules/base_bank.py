from abc import ABC, abstractmethod
import re

class BankStrategy(ABC):
    def __init__(self, name):
        self.name = name

    def limpiar_monto(self, valor_ocr):
        """Normaliza string '1.250,50' a float 1250.50"""
        clean = re.sub(r'[^\d.,]', '', valor_ocr)
        if ',' in clean:
            clean = clean.replace('.', '').replace(',', '.')
        else:
            if not re.search(r'\.\d{2}$', clean):
                 clean = clean.replace('.', '')
        try:
            return float(clean)
        except:
            return 0.0

    def limpiar_referencia(self, texto):
        """Limpia caracteres OCR confusos (O->0, I->1)"""
        r = texto.upper().replace('O', '0').replace('I', '1').replace('|', '1')
        return re.sub(r'\D', '', r)

    def extract_generic_reference(self, texto):
        """Búsqueda estándar de referencia para bancos sin lógica especial"""
        prefijos_invalidos = ("0412", "0414", "0416", "0424", "0426")
        patron_ref = r'(?:Ref|Ret|Rel|ReF|Referencia|Referenda|Nro|Nr0|Num|Operaci[oó0]n|Oper|Documento)[:\s\.]*([O0I1\|\d\s\.-]+)'
        
        for m in re.finditer(patron_ref, texto, re.IGNORECASE):
            candidato_clean = self.limpiar_referencia(m.group(1))
            if 5 <= len(candidato_clean) <= 12 and not candidato_clean.startswith(prefijos_invalidos):
                return candidato_clean
        
        for m in re.finditer(r'(?<!\w)([0-9O0I1\|]{5,12})(?!\w)', texto):
            candidato_clean = self.limpiar_referencia(m.group(1))
            if 5 <= len(candidato_clean) <= 12 and not candidato_clean.startswith(prefijos_invalidos):
                return candidato_clean
        return "No detectada"

    @abstractmethod
    def procesar_comprobante(self, imagen, texto_completo):
        pass