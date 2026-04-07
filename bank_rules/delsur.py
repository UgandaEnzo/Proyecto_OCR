from .base_bank import BankStrategy
import cv2
from ocr_utils import extraer_texto_de_imagen_cv2
import re

class DelsurStrategy(BankStrategy):
    def __init__(self):
        super().__init__("DELSUR")

    def procesar_comprobante(self, imagen, texto_completo):
        # Procesamiento estándar
        gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        txt_ocr = extraer_texto_de_imagen_cv2(thresh)
        
        monto = 0.0
        # Patrón: Monto: Bs. 123,45
        matches = re.findall(r'Monto:\s*Bs\.\s*([\d.,]+)', txt_ocr, re.IGNORECASE)
        for m in matches:
            val = self.limpiar_monto(m)
            if val > 0: monto = max(monto, val)
            
        referencia = self.extract_generic_reference(texto_completo)
            
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}