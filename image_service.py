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
        """Генерирует изображение через Hugging Face с авто-повтором."""
        if not HF_TOKEN:
            raise Exception("HF_TOKEN is missing. Please add it to config.")

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": prompt}
        
        import asyncio
        max_retries = 3
        for attempt in range(max_retries):
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(self.hf_api_url, json=payload, timeout=90) as response:
                    if response.status == 200:
                        return await response.read()
                    
                    error_data = await response.text()
                    
                    # Если модель загружается (503), ждем и пробуем снова
                    if response.status == 503 and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        log.info(f"⏳ Модель HF загружается. Ждем {wait_time}с... (Попытка {attempt+1})")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    raise Exception(f"Hugging Face Error {response.status}: {error_data}")

# Глобальный экземпляр
image_gen = ImageService()
