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
        # Добавляем параметры (например, ширина и высота)
        url = f"{self.base_url}{encoded_prompt}?width=1024&height=1024&nologo=true&enhance=true"
        return url

# Глобальный экземпляр
image_gen = ImageService()
