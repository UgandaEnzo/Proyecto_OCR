from .base_bank import BankStrategy
import cv2
import numpy as np
import pytesseract
import re

class MercantilStrategy(BankStrategy):
    def __init__(self):
        super().__init__("Mercantil")

    def procesar_comprobante(self, imagen, texto_completo):
        # 1. Recorte Centro + Sharpen
        h, w = imagen.shape[:2]
        roi = imagen[int(h*0.25):int(h*0.75), int(w*0.1):int(w*0.9)]
        
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        kernel = np.array([[0, -1, 0], [-1, 5, -1], [0, -1, 0]])
        sharpened = cv2.filter2D(gray, -1, kernel)
        _, thresh = cv2.threshold(sharpened, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        
        txt_monto = pytesseract.image_to_string(thresh, config='--psm 6')
        
        referencia = "No detectada"
        monto = 0.0

        # 2. Referencia (Regla de 12)
        # Limpieza agresiva: solo números
        ref_clean = re.sub(r'\D', '', txt_monto)
        # Buscar secuencias de 12 dígitos en el string limpio
        matches_ref = re.findall(r'(\d{12})', ref_clean)
        if matches_ref:
            referencia = matches_ref[-1] # Tomamos la última por si hay otras cuentas
        
        # 3. Monto (Busca 'Monto (Bs.):' y toma la línea siguiente)
        lines = txt_monto.split('\n')
        for i, line in enumerate(lines):
            if 'monto (bs.):' in line.lower():
                # Intentar buscar en la misma línea primero (por si el OCR pegó el texto)
                matches = re.findall(r'(\d[\d.,]*)', line)
                # Si no hay número válido en la misma línea, mirar la siguiente
                if not any(self.limpiar_monto(m) > 0 for m in matches):
                    if i + 1 < len(lines):
                        next_line = lines[i+1]
                        matches = re.findall(r'(\d[\d.,]*)', next_line)
                
                for m in matches:
                    val = self.limpiar_monto(m)
                    if val > 0:
                        monto = val
                        break
            if monto > 0: break
        
        # Fallback
        if monto == 0.0:
            matches = re.findall(r'(\d+,\d{2,})', txt_monto)
            for m in matches:
                val = self.limpiar_monto(m)
                if val > 0:
                    monto = val
                    break
        
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}