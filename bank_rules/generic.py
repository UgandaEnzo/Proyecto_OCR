from .base_bank import BankStrategy
import re

class GenericStrategy(BankStrategy):
    def __init__(self, name="Desconocido"):
        super().__init__(name)

    def procesar_comprobante(self, imagen, texto_completo):
        monto = 0.0
        # Regex estándar
        matches = re.findall(r'Bs\.?\s*[:\.]?\s*(\d[\d\.,]*)', texto_completo, re.IGNORECASE)
        matches.extend(re.findall(r'(\d[\d\.,]*)\s*Bs', texto_completo, re.IGNORECASE))
        
        if not matches:
             matches = re.findall(r'(\d[\d\.,]*,\d{2})', texto_completo)

        for m in matches:
            val = self.limpiar_monto(m)
            if val > 0: monto = max(monto, val)
            
        referencia = self.extract_generic_reference(texto_completo)
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}