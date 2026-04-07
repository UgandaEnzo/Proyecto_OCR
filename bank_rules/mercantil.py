from .base_bank import BankStrategy
import cv2
import numpy as np
from ocr_utils import extraer_texto_de_imagen_cv2
import re

class MercantilStrategy(BankStrategy):
    def __init__(self):
        super().__init__("Mercantil")

    def procesar_comprobante(self, imagen, texto_completo):
        # Mercantil tiene un formato muy estándar. Usamos el texto completo para mayor robustez
        # en lugar de recortes que pueden fallar si el capture es parcial.
        referencia = "No detectada"
        monto = 0.0

        # 1. Extraer Referencia de 12 dígitos usando etiquetas conocidas
        patrones_ref = [
            r'referencia[:\s]*([0-9O0I1\|]{8,14})',
            r'nro\.?\s*de\s*operaci[oó]n[:\s]*([0-9O0I1\|]{8,14})',
            r'confirmaci[oó]n[:\s]*([0-9O0I1\|]{8,14})'
        ]
        
        for p in patrones_ref:
            match = re.search(p, texto_completo, re.IGNORECASE)
            if match:
                ref_candidata = self.limpiar_referencia(match.group(1))
                if 8 <= len(ref_candidata) <= 12:
                    referencia = ref_candidata
                    break
        
        if referencia == "No detectada":
            referencia = self.extract_generic_reference(texto_completo)
        
        # 2. Monto usando el nuevo extractor genérico robusto
        monto = self.extract_amount(texto_completo)
        
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}