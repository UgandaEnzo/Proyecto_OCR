from .base_bank import BankStrategy
import cv2
import pytesseract
import re
import numpy as np

class VenezuelaStrategy(BankStrategy):
    def __init__(self):
        super().__init__("Banco de Venezuela")

    def procesar_comprobante(self, imagen, texto_completo):
        # Detectar si es modo oscuro (promedio de píxeles < 127)
        promedio_brillo = np.mean(imagen)
        
        if promedio_brillo < 127:
            # Inversión de colores (letras blancas a negras)
            imagen = cv2.bitwise_not(imagen)
            
        gray = cv2.cvtColor(imagen, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        txt_monto = pytesseract.image_to_string(thresh, config='--psm 6')
        
        monto = 0.0
        matches = re.findall(r'(\d[\d\.,]*)\s*Bs', txt_monto, re.IGNORECASE)
        matches.extend(re.findall(r'Monto\s*[:\.]?\s*(\d[\d\.,]*)', txt_monto, re.IGNORECASE))
        
        for m in matches:
            val = self.limpiar_monto(m)
            if val > 0: monto = max(monto, val)
            
        referencia = self.extract_generic_reference(texto_completo)
        if referencia != "No detectada" and len(referencia) > 12:
            referencia = referencia[-12:]
            
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}