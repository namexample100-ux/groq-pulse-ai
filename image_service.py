import aiohttp
import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        # Меняем на основной домен, он бывает стабильнее при ошибках 1033
        self.base_url = "https://pollinations.ai/p/"

    async def generate_image_url(self, prompt: str) -> str:
        """Генерирует URL для изображения с использованием модели Flux."""
        import random
        encoded_prompt = quote(prompt)
        seed = random.randint(1, 1000000)
        # Упрощаем параметры: убираем лишнее, оставляем суть
        url = f"{self.base_url}{encoded_prompt}?width=1024&height=1024&seed={seed}&model=flux"
        return url

    async def download_image(self, url: str) -> bytes:
        """Скачивает изображение по URL и возвращает байты (с эмуляцией браузера)."""
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=30) as response:
                if response.status == 200:
                    return await response.read()
                else:
                    raise Exception(f"Failed to download image: status {response.status}")

# Глобальный экземпляр
image_gen = ImageService()
