from .base_bank import BankStrategy
import cv2
from ocr_utils import extraer_texto_de_imagen_cv2
import re

class BBVAStrategy(BankStrategy):
    def __init__(self):
        super().__init__("BBVA Provincial")

    def procesar_comprobante(self, imagen, texto_completo):
        # 1. Recorte del tercio superior (Header)
        h, w = imagen.shape[:2]
        header = imagen[:int(h * 0.33), :]
        
        # 2. Preprocesamiento: Invertir colores (Letras blancas -> Negras)
        gray = cv2.cvtColor(header, cv2.COLOR_BGR2GRAY)
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        
        txt_header = extraer_texto_de_imagen_cv2(thresh)
        
        monto = 0.0
        
        # Función para buscar el número más grande que empiece por 'Bs.'
        def buscar_maximo_monto(txt):
            # Regex: Bs. (espacio opcional) numero
            matches = re.findall(r'Bs\.?\s*(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})', txt, re.IGNORECASE)
            max_val = 0.0
            for m in matches:
                val = self.limpiar_monto(m)
                if val > max_val: max_val = val
            return max_val

        # Intentar en header procesado (prioridad)
        monto = buscar_maximo_monto(txt_header)
        
        # Fallback: Intentar en texto completo si no se halló en header
        if monto == 0.0:
            monto = buscar_maximo_monto(texto_completo)
            
        referencia = self.extract_generic_reference(texto_completo)
        return {"banco": self.name, "referencia": referencia, "monto": monto, "status": "procesado", "texto_completo": texto_completo}