from .base_bank import BankStrategy
import cv2
import pytesseract
import re

class BBVAStrategy(BankStrategy):
    def __init__(self):
        super().__init__("BBVA Provincial")

    def procesar_comprobante(self, imagen, texto_completo):
        # Re-escalado 200% y Denoising
        resized = cv2.resize(imagen, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
        gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
        denoised = cv2.fastNlMeansDenoising(gray, None, h=10, templateWindowSize=7, searchWindowSize=21)
        _, thresh = cv2.threshold(denoised, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        txt_monto = pytesseract.image_to_string(thresh, config='--psm 6')
        
        monto = 0.0
        matches = re.findall(r'(\d[\d\.,]*)', txt_monto)
        for m in matches:
            if re.match(r'^\d{1,3}(\.\d{3})*,\d{2}$', m):
                val = self.limpiar_monto(m)
                if val > 0: monto = max(monto, val)
                
        referencia = self.extract_generic_reference(texto_completo)
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}