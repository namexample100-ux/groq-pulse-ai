import os
import logging
import httpx
from groq import AsyncGroq
from config import GROQ_API_KEY, DEFAULT_MODEL
import database as db

log = logging.getLogger(__name__)

class GroqService:
    def __init__(self):
        proxy = os.getenv("PROXY")
        if proxy:
            log.info(f"🌐 Используется прокси для Groq: {proxy}")
            http_client = httpx.AsyncClient(proxies=proxy)
            self.client = AsyncGroq(api_key=GROQ_API_KEY, http_client=http_client)
        else:
            self.client = AsyncGroq(api_key=GROQ_API_KEY)
            
        self.max_context = 10  # Храним последние 10 сообщений

    async def get_response(self, user_id: int, user_text: str) -> str:
        """Получает ответ от нейросети с учетом истории из БД."""
        if not GROQ_API_KEY:
            return "❌ GROQ_API_KEY не задан в настройках."
        
        # Загружаем историю и модель из БД
        history, user_model = await db.get_user_data(user_id)
        current_model = user_model or DEFAULT_MODEL

        # Если истории нет, добавляем системный промпт
        if not history:
            history = [
                {"role": "system", "content": "You are a helpful assistant. Answer in the language the user speaks to you."}
            ]

        # Добавляем сообщение пользователя
        history.append({"role": "user", "content": user_text})

        # Обрезаем контекст (системный промпт + последние N сообщений)
        if len(history) > self.max_context + 1:
            history = [history[0]] + history[-self.max_context:]

        try:
            chat_completion = await self.client.chat.completions.create(
                messages=history,
                model=current_model,
                temperature=0.7,
            )
            
            ai_response = chat_completion.choices[0].message.content
            history.append({"role": "assistant", "content": ai_response})
            
            # Сохраняем обновленную историю в БД
            await db.save_user_data(user_id, history)
            
            return ai_response
            
        except Exception as e:
            log.error(f"Groq API Error: {e}")
            if "Forbidden" in str(e) or "Access denied" in str(e):
                return "❌ **Ошибка доступа (403).**\nGroq блокирует запросы из вашего региона."
            return f"⚠️ Ошибка нейросети: {str(e)}"

    async def clear_context(self, user_id: int):
        """Очищает историю диалога в БД."""
        await db.clear_user_history(user_id)

    async def set_model(self, user_id: int, model_name: str):
        """Устанавливает модель для пользователя в БД."""
        # Получаем текущую историю, чтобы сохранить её при смене модели
        history, _ = await db.get_user_data(user_id)
        await db.save_user_data(user_id, history or [], model_name)

# Глобальный экземпляр
ai = GroqService()
