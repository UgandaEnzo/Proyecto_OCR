from .base_bank import BankStrategy
import cv2
import pytesseract
import re

class BncStrategy(BankStrategy):
    def __init__(self):
        super().__init__("BNC")

    def procesar_comprobante(self, imagen, texto_completo):
        # Escala de grises con alto contraste para resaltar texto verde/color
        gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        # Aumentar contraste: alpha=1.5 (contraste), beta=0 (brillo)
        contrast = cv2.convertScaleAbs(gray, alpha=1.5, beta=0)
        _, thresh = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        txt_ocr = pytesseract.image_to_string(thresh, config='--psm 6')
        
        monto = 0.0
        # Patrón: Monto: 120,00 Bs.
        matches = re.findall(r'Monto:\s*([\d.,]+)\s*Bs', txt_ocr, re.IGNORECASE)
        for m in matches:
            val = self.limpiar_monto(m)
            if val > 0: monto = max(monto, val)
            
        referencia = self.extract_generic_reference(texto_completo)
            
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}