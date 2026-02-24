import aiohttp
import logging
from config import HF_TOKEN

log = logging.getLogger(__name__)

class ImageService:
    def __init__(self):
        # По умолчанию используем FLUX
        from config import DEFAULT_IMAGE_MODEL
        self.default_model = DEFAULT_IMAGE_MODEL

    async def generate_image(self, prompt: str, model_id: str = None) -> (bytes, str):
        """Генерирует изображение через Hugging Face с авто-повтором и фоллбэком.
        Возвращает кортеж (image_bytes, used_model_id).
        """
        if not HF_TOKEN:
            raise Exception("HF_TOKEN is missing. Please add it to config.")

        target_model = model_id or self.default_model
        api_url = f"https://api-inference.huggingface.co/models/{target_model}"
        
        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": prompt}
        
        import asyncio
        max_retries = 3
        for attempt in range(max_retries):
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(api_url, json=payload, timeout=90) as response:
                    if response.status == 200:
                        img_data = await response.read()
                        return img_data, target_model
                    
                    error_data = await response.text()
                    log.warning(f"⚠️ HF Error ({target_model}) Status {response.status}: {error_data}")

                    # Fallback
                    if response.status in [400, 404, 501] and target_model != self.default_model:
                        log.warning(f"🔄 Модель {target_model} недоступна. Откат на {self.default_model}...")
                        return await self.generate_image(prompt, model_id=self.default_model)
                    
                    if response.status == 503 and attempt < max_retries - 1:
                        wait_time = (attempt + 1) * 5
                        log.info(f"⏳ Модель HF {target_model} загружается. Ждем {wait_time}с... (Попытка {attempt+1})")
                        await asyncio.sleep(wait_time)
                        continue
                    
                    raise Exception(f"Hugging Face Error {response.status}: {error_data}")

# Глобальный экземпляр
image_gen = ImageService()
