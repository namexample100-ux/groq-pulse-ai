import aiohttp
import logging
from urllib.parse import quote

log = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        # Основной провайдер
        self.pollinations_url = "https://pollinations.ai/p/"
        # Запасной провайдер (Airforce AI)
        self.airforce_url = "https://api.airforce/imagine2?prompt="

    async def generate_image_url(self, prompt: str, provider: str = "pollinations") -> str:
        """Генерирует URL для изображения."""
        encoded_prompt = quote(prompt)
        import random
        seed = random.randint(1, 1000000)
        
        if provider == "airforce":
            # Airforce AI (Stable Diffusion/Flux)
            return f"{self.airforce_url}{encoded_prompt}&model=flux&width=1024&height=1024&seed={seed}"
        else:
            # Pollinations AI (Primary)
            return f"{self.pollinations_url}{encoded_prompt}?width=1024&height=1024&seed={seed}&model=flux"

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
