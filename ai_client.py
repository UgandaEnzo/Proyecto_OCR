import os
import re
import json
import base64
import io
import logging
from openai import AsyncOpenAI
from PIL import Image as PILImage
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger("ocr_api")


class OpenRouterClient:

    BASE_URL = "https://openrouter.ai/api/v1"
    TEXT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
    VISION_MODEL = "google/gemma-4-26b-a4b-it:free"

    def __init__(self):
        api_key = os.getenv("OPENROUTER_API_KEY", "").strip()
        self.client = AsyncOpenAI(api_key=api_key, base_url=self.BASE_URL) if api_key else None
        self.api_key = api_key

    def is_available(self):
        return self.client is not None and bool(self.api_key)

    async def chat(self, messages, temperature=0.0, max_tokens=None):
        if not self.is_available():
            return None
        kwargs = dict(model=self.TEXT_MODEL, messages=messages, temperature=temperature)
        if max_tokens:
            kwargs["max_tokens"] = max_tokens
        response = await self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

    async def extract_json(self, text, system_prompt):
        if not self.is_available():
            return None
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": text},
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.TEXT_MODEL,
                messages=messages,
                temperature=0.0,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content
            encontrado = re.search(r"\{.*\}", content, re.DOTALL)
            if encontrado:
                return json.loads(encontrado.group(0))
            return json.loads(content)
        except Exception as e:
            logger.warning("OpenRouter extract_json fallo: %s", e)
            return None

    async def analyze_image(self, image_bytes, prompt_text):
        if not self.is_available():
            return None
        try:
            img = PILImage.open(io.BytesIO(image_bytes))
            img = img.convert("RGB")
            max_dim = 800
            if max(img.width, img.height) > max_dim:
                scale = max_dim / max(img.width, img.height)
                img = img.resize((int(img.width * scale), int(img.height * scale)))
            buffer = io.BytesIO()
            img.save(buffer, format="JPEG", quality=70)
            compressed = buffer.getvalue()
            image_b64 = base64.b64encode(compressed).decode("utf-8")
        except Exception as e:
            logger.debug("Compresion imagen fallo: %s", e)
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{image_b64}"}},
                    {"type": "text", "text": prompt_text},
                ],
            }
        ]
        try:
            response = await self.client.chat.completions.create(
                model=self.VISION_MODEL, messages=messages, temperature=0.0, max_tokens=4096
            )
            content = response.choices[0].message.content or ""
            encontrado = re.search(r"\{.*\}", content, re.DOTALL)
            if encontrado:
                try:
                    return json.loads(encontrado.group(0))
                except json.JSONDecodeError:
                    pass
            return None
        except Exception as e:
            logger.warning("OpenRouter analyze_image fallo: %s", e)
            return None

    async def verify_connection(self):
        if not self.api_key:
            return (False, "No se ha configurado la clave OpenRouter.")
        try:
            await self.client.chat.completions.create(
                messages=[{"role": "user", "content": "Responde con pong"}],
                model=self.TEXT_MODEL,
                temperature=0.0,
                max_tokens=1,
            )
            return (True, "Clave OpenRouter verificada correctamente.")
        except Exception as e:
            logger.warning("No se pudo verificar OpenRouter: %s", e)
            return (False, "No se puede conectar a OpenRouter. Comprueba tu conexion y clave API.")


openrouter = OpenRouterClient()
