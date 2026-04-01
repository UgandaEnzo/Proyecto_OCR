import os
import json
from groq import Groq
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

class SkillEngine:
    def __init__(self):
        self.api_key = os.getenv("GROQ_API_KEY")
        self.model = "llama-3.3-70b-versatile" # El modelo más potente y actual
        
        if not self.api_key:
            print("⚠️ [SkillEngine] GROQ_API_KEY no encontrada. Modo IA desactivado.")
            self.client = None
        else:
            self.client = Groq(api_key=self.api_key)
            print(f"[SkillEngine] Activado con modelo: {self.model}")

    def _load_skill_file(self, skill_name: str):
        """Lee el archivo Markdown de la carpeta /skills"""
        try:
            if not skill_name.endswith(".md"):
                skill_name += ".md"
            skill_path = os.path.join("skills", skill_name)
            with open(skill_path, "r", encoding="utf-8") as f:
                return f.read()
        except FileNotFoundError:
            print(f"❌ [SkillEngine] No se encontró la skill: {skill_name}")
            return None

    def extraer_datos(self, texto_ocr: str, skill_name: str = "get_payment_data"):
        """Envía el texto sucio a la IA para estructurarlo"""
        if not self.client:
            return None

        # Cargamos las instrucciones que escribimos en el Markdown
        prompt_skill = self._load_skill_file(skill_name)
        if not prompt_skill:
            return None

        try:
            # Llamada a Groq
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": prompt_skill},
                    {"role": "user", "content": f"Texto extraído del OCR: \n{texto_ocr}"}
                ],
                model=self.model,
                # JSON Mode: Fuerza a la IA a devolver un objeto procesable
                response_format={"type": "json_object"},
                temperature=0.1, # Creatividad baja para mayor precisión técnica
            )
            
            # Convertimos la respuesta de texto a un diccionario de Python
            resultado_texto = response.choices[0].message.content
            return json.loads(resultado_texto)

        except Exception as e:
            print(f"❌ [SkillEngine] Error en la llamada a Groq: {str(e)}")
            return None