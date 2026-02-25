import aiohttp
import logging
import os
from config import HF_TOKEN

log = logging.getLogger(__name__)

class VoiceService:
    def __init__(self):
        # Возвращаемся к проверенной MMS модели, так как MeloTTS вернула 404
        self.model_id = "facebook/mms-tts-rus"
        # Используем актуальный Router API
        self.api_url = f"https://router.huggingface.co/hf-inference/models/{self.model_id}"

    async def text_to_speech(self, text: str) -> bytes:
        """Преобразует текст в речь через Hugging Face."""
        if not HF_TOKEN:
            raise Exception("HF_TOKEN is missing for TTS.")

        headers = {"Authorization": f"Bearer {HF_TOKEN}"}
        payload = {"inputs": text}

        try:
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.post(self.api_url, json=payload, timeout=60) as response:
                    if response.status == 200:
                        return await response.read()
                    
                    error_msg = await response.text()
                    log.error(f"HF TTS Error {response.status}: {error_msg}")
                    
                    # Если модель загружается, можно добавить ретрай (по аналогии с ImageService)
                    if response.status == 503:
                        import asyncio
                        log.info("⏳ TTS модель загружается, ждем 20 секунд...")
                        await asyncio.sleep(20)
                        return await self.text_to_speech(text)
                        
                    raise Exception(f"TTS Failed: {response.status} - {error_msg}")
        except Exception as e:
            log.error(f"VoiceService Error: {e}")
            raise e

voice_service = VoiceService()
