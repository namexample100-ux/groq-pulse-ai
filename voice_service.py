import logging
import io
from gtts import gTTS

log = logging.getLogger(__name__)

class VoiceService:
    def __init__(self):
        # Настройка языка по умолчанию
        self.lang = 'ru'

    async def text_to_speech(self, text: str) -> bytes:
        """Преобразует текст в речь через gTTS (Google TTS)."""
        try:
            # gTTS выполняет запрос к Google и возвращает аудио
            tts = gTTS(text=text, lang=self.lang)
            
            # Сохраняем в байты в памяти
            fp = io.BytesIO()
            tts.write_to_fp(fp)
            fp.seek(0)
            
            return fp.read()
            
        except Exception as e:
            log.error(f"gTTS Service Error: {e}")
            raise e

voice_service = VoiceService()
