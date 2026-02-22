import aiohttp
import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        self.base_url = "https://image.pollinations.ai/prompt/"

    async def generate_image_url(self, prompt: str) -> str:
        """Генерирует URL для изображения на основе промпта."""
        # Кодируем промпт для URL
        encoded_prompt = quote(prompt)
        # Добавляем параметры (nologo, enhance и seed для уникальности)
        import random
        seed = random.randint(1, 1000000)
        url = f"{self.base_url}{encoded_prompt}?width=1024&height=1024&nologo=true&enhance=true&seed={seed}"
        return url

    async def download_image(self, url: str) -> bytes:
        """Скачивает изображение по URL и возвращает байты."""
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    raise Exception(f"Failed to download image: status {response.status}")

# Глобальный экземпляр
image_gen = ImageService()
