import aiohttp
import logging
from config import HF_TOKEN

log = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        # Модель Hugging Face (профессиональный стандарт)
        self.hf_model = "black-forest-labs/FLUX.1-schnell"
        self.hf_api_url = f"https://router.huggingface.co/hf-inference/models/{self.hf_model}"

    async def generate_image(self, prompt: str) -> bytes:
        """Генерирует изображение через Hugging Face Inference API."""
        if not HF_TOKEN:
            raise Exception("HF_TOKEN is missing. Please add it to your environment variables.")

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": prompt}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(self.hf_api_url, json=payload, timeout=60) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 503:
                    # Модель часто "спит" на бесплатном тарифе, нужно подождать
                    raise Exception("Model is loading at Hugging Face. Please wait a few seconds and try again.")
                else:
                    error_data = await response.text()
                    raise Exception(f"Hugging Face Error {response.status}: {error_data}")

# Глобальный экземпляр
image_gen = ImageService()
