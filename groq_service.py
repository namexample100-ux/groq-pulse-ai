import os
import logging
import httpx
from groq import AsyncGroq
from config import GROQ_API_KEY, DEFAULT_MODEL

log = logging.getLogger(__name__)

class GroqService:
    def __init__(self):
        # Проверяем наличие прокси в переменных окружения
        proxy = os.getenv("PROXY")
        
        if proxy:
            log.info(f"🌐 Используется прокси для Groq: {proxy}")
            # Создаем кастомный httpx клиент для работы через прокси
            http_client = httpx.AsyncClient(proxies=proxy)
            self.client = AsyncGroq(api_key=GROQ_API_KEY, http_client=http_client)
        else:
            self.client = AsyncGroq(api_key=GROQ_API_KEY)
            
        # Хранилище контекста: {user_id: [messages]}
        self.context = {}
        self.max_context = 10  # Храним последние 10 сообщений

    async def get_response(self, user_id: int, user_text: str) -> str:
        """Получает ответ от нейросети с учетом контекста."""
        if not GROQ_API_KEY:
            return "❌ GROQ_API_KEY не задан в настройках."

        # Инициализация контекста для нового пользователя
        if user_id not in self.context:
            self.context[user_id] = [
                {"role": "system", "content": "You are a helpful assistant. Answer in the language the user speaks to you."}
            ]

        # Добавляем сообщение пользователя
        self.context[user_id].append({"role": "user", "content": user_text})

        # Обрезаем контекст
        if len(self.context[user_id]) > self.max_context:
            self.context[user_id] = [self.context[user_id][0]] + self.context[user_id][-(self.max_context-1):]

        try:
            chat_completion = await self.client.chat.completions.create(
                messages=self.context[user_id],
                model=DEFAULT_MODEL,
                temperature=0.7,
            )
            
            ai_response = chat_completion.choices[0].message.content
            self.context[user_id].append({"role": "assistant", "content": ai_response})
            return ai_response
            
        except Exception as e:
            log.error(f"Groq API Error: {e}")
            if "Forbidden" in str(e) or "Access denied" in str(e):
                return "❌ **Ошибка доступа (403).**\nGroq блокирует запросы из вашего региона. Нужно либо использовать прокси, либо задеплоить бота на зарубежный хостинг (например, Render)."
            return f"⚠️ Ошибка нейросети: {str(e)}"

    def clear_context(self, user_id: int):
        """Очищает историю диалога."""
        if user_id in self.context:
            del self.context[user_id]

# Глобальный экземпляр
ai = GroqService()
