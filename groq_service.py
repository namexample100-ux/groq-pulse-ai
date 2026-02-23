import os
import logging
import httpx
import json
from groq import AsyncGroq
from config import GROQ_API_KEY, DEFAULT_MODEL
import database as db
from search_service import search_tool

log = logging.getLogger(__name__)

# Определение инструментов (Tools) для агента
TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the internet for real-time information, news, facts, current events, weather, and specific data not present in your training data.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query."
                    }
                },
                "required": ["query"]
            }
        }
    }
]

class GroqService:
    def __init__(self):
        proxy = os.getenv("PROXY")
        if proxy:
            log.info(f"🌐 Используется прокси для Groq: {proxy}")
            http_client = httpx.AsyncClient(proxies=proxy)
            self.client = AsyncGroq(api_key=GROQ_API_KEY, http_client=http_client)
        else:
            self.client = AsyncGroq(api_key=GROQ_API_KEY)
            
        self.max_context = 10

    async def get_response(self, user_id: int, user_text: str) -> str:
        """Получает ответ от ИИ-агента с поддержкой инструментов (поиск)."""
        if not GROQ_API_KEY:
            return "❌ GROQ_API_KEY не задан в настройках."
        
        history, user_model = await db.get_user_data(user_id)
        current_model = user_model or DEFAULT_MODEL

        # Системный промпт для Агента
        system_prompt = {
            "role": "system", 
            "content": (
                "You are GroqPulse, an advanced AI Agent. You have access to real-time web search. "
                "If the user asks about current events, news, or something you are not sure about, "
                "use the 'search_web' tool. Always answer in the language the user speaks to you. "
                "CRITICAL: When using search results, ALWAYS provide clickable links (URLs) to the sources at the end of your response."
            )
        }

        if not history:
            history = [system_prompt]
        else:
            # Убеждаемся, что системный промпт всегда актуальный
            history[0] = system_prompt

        history.append({"role": "user", "content": user_text})

        # Ограничение контекста
        if len(history) > self.max_context + 1:
            history = [history[0]] + history[-self.max_context:]

        try:
            # ПЕРВЫЙ ЗАПРОС: Может содержать вызов инструмента
            response = await self.client.chat.completions.create(
                messages=history,
                model=current_model,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.7,
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            # Если ИИ решил использовать поиск
            if tool_calls:
                # Превращаем сообщение со звонками в словарь для сохранения
                history.append({
                    "role": "assistant",
                    "content": response_message.content,
                    "tool_calls": [
                        {
                            "id": tool.id,
                            "type": "function",
                            "function": {
                                "name": tool.function.name,
                                "arguments": tool.function.arguments
                            }
                        } for tool in tool_calls
                    ]
                })
                
                for tool_call in tool_calls:
                    function_name = tool_call.function.name
                    function_args = json.loads(tool_call.function.arguments)
                    
                    if function_name == "search_web":
                        query = function_args.get("query")
                        log.info(f"🔍 Агент ищет в сети: {query}")
                        
                        # Выполняем поиск
                        search_result = await search_tool.search(query)
                        
                        # Добавляем результат поиска в историю
                        history.append({
                            "tool_call_id": tool_call.id,
                            "role": "tool",
                            "name": function_name,
                            "content": search_result,
                        })

                # ВТОРОЙ ЗАПРОС: Получаем финальный ответ на основе данных поиска
                second_response = await self.client.chat.completions.create(
                    messages=history,
                    model=current_model,
                )
                ai_response = second_response.choices[0].message.content
            else:
                ai_response = response_message.content

            # Обновляем историю в памяти и БД (превращаем в дикт)
            history.append({"role": "assistant", "content": ai_response})
            await db.save_user_data(user_id, history)
            
            return ai_response
            
        except Exception as e:
            log.error(f"Groq Agent Error: {e}", exc_info=True)
            if "Forbidden" in str(e) or "Access denied" in str(e):
                return "❌ **Ошибка доступа (403).**\nGroq блокирует запросы из вашего региона."
            return f"⚠️ Ошибка ИИ-агента: {str(e)}"

    async def clear_context(self, user_id: int):
        await db.clear_user_history(user_id)

    async def set_model(self, user_id: int, model_name: str):
        history, _ = await db.get_user_data(user_id)
        await db.save_user_data(user_id, history or [], model_name)

# Глобальный экземпляр
ai = GroqService()
