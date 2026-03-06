from .base_bank import BankStrategy
import cv2
import pytesseract
import re

class BncStrategy(BankStrategy):
    def __init__(self):
        super().__init__("BNC")

    def procesar_comprobante(self, imagen, texto_completo):
        # Pre-procesamiento: Escala de grises + CLAHE para resaltar verde
        gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
        contrast = clahe.apply(gray)
        
        _, thresh = cv2.threshold(contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        txt_ocr = pytesseract.image_to_string(thresh, config='--psm 6')
        
        monto = 0.0
        
        # 1. Patrón específico: Monto: ... 120,00 Bs. (Punto al final clave)
        matches = re.findall(r'Monto:.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*Bs\.', txt_ocr, re.IGNORECASE)
        for m in matches:
            val = self.limpiar_monto(m)
            if val > 0: monto = max(monto, val)
            
        # 2. Fallback: Formato moneda + Bs. (sin contexto Monto:)
        if monto == 0.0:
            matches = re.findall(r'(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s*Bs\.?', txt_ocr, re.IGNORECASE)
            for m in matches:
                val = self.limpiar_monto(m)
                if val > 0: monto = max(monto, val)
            
        referencia = self.extract_generic_reference(texto_completo)
            
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}