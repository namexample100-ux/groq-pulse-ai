import aiohttp
import logging
import random
from urllib.parse import quote
from config import HF_TOKEN

log = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        # Модели Hugging Face
        self.hf_model = "black-forest-labs/FLUX.1-schnell"
        self.hf_api_url = f"https://api-inference.huggingface.co/models/{self.hf_model}"
        
        # Провайдеры-агрегаторы (запасные)
        self.pollinations_url = "https://pollinations.ai/p/"
        self.airforce_url = "https://api.airforce/imagine2?prompt="

    async def generate_hf_image(self, prompt: str) -> bytes:
        """Генерирует изображение через Hugging Face Inference API."""
        if not HF_TOKEN:
            raise Exception("HF_TOKEN is missing")

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": prompt}

        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(self.hf_api_url, json=payload, timeout=60) as response:
                if response.status == 200:
                    return await response.read()
                elif response.status == 503:
                    raise Exception("Model is loading at Hugging Face. Please wait.")
                else:
                    error_data = await response.text()
                    raise Exception(f"HF Error {response.status}: {error_data}")

    async def generate_image_url(self, prompt: str, provider: str = "pollinations") -> str:
        """Генерирует URL для запасных провайдеров."""
        encoded_prompt = quote(prompt)
        seed = random.randint(1, 1000000)
        
        if provider == "airforce":
            return f"{self.airforce_url}{encoded_prompt}&model=flux&width=1024&height=1024&seed={seed}"
        else:
            return f"{self.pollinations_url}{encoded_prompt}?width=1024&height=1024&seed={seed}&model=flux"

    async def download_image(self, url: str) -> bytes:
        """Скачивает изображение по URL (для запасных провайдеров)."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    raise Exception(f"Failed to download image: status {response.status}")

# Глобальный экземпляр
image_gen = ImageService()
