import os
import logging
import httpx
import json
import base64
import datetime
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
            "description": "Search the internet for real-time information, news, facts, and events.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The search query."}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_current_time",
            "description": "Get the current date and time.",
            "parameters": {
                "type": "object",
                "properties": {}
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "calculate_math",
            "description": "Perform complex mathematical calculations.",
            "parameters": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "description": "The math expression to evaluate (e.g., '2 + 2 * 5')."}
                },
                "required": ["expression"]
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
        """Получает ответ от ИИ-агента с поддержкой инструментов."""
        if not GROQ_API_KEY:
            return "❌ GROQ_API_KEY не задан в настройках."
        
        history, user_model = await db.get_user_data(user_id)
        current_model = user_model or DEFAULT_MODEL

        # Системный промпт для Агента
        system_prompt = {
            "role": "system", 
            "content": (
                "You are GroqPulse, an advanced AI Agent. You have access to real-time tools. "
                "1. If the user asks about current events, use 'search_web'. "
                "2. If the user asks for time/date, use 'get_current_time'. "
                "3. For complex math, use 'calculate_math'. "
                "Always answer in the language the user speaks to you. "
                "CRITICAL: When using search results, ALWAYS provide clickable links (URLs) to the sources."
            )
        }

        if not history:
            history = [system_prompt]
        else:
            history[0] = system_prompt

        history.append({"role": "user", "content": user_text})

        if len(history) > self.max_context + 1:
            history = [history[0]] + history[-self.max_context:]

        try:
            response = await self.client.chat.completions.create(
                messages=history,
                model=current_model,
                tools=TOOLS,
                tool_choice="auto",
                temperature=0.7,
            )
            
            response_message = response.choices[0].message
            tool_calls = response_message.tool_calls

            if tool_calls:
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
                    tool_content = ""

                    if function_name == "search_web":
                        query = function_args.get("query")
                        log.info(f"🔍 Агент ищет в сети: {query}")
                        tool_content = await search_tool.search(query)
                    
                    elif function_name == "get_current_time":
                        now = datetime.datetime.now()
                        tool_content = f"Текущее время и дата: {now.strftime('%Y-%m-%d %H:%M:%S')}"
                        log.info(f"🕒 Агент запрашивает время")

                    elif function_name == "calculate_math":
                        expr = function_args.get("expression")
                        try:
                            # Простая и безопасная оценка (для демки)
                            # В проде лучше использовать специализированную либу
                            result = eval(expr, {"__builtins__": None}, {})
                            tool_content = f"Результат вычисления '{expr}': {result}"
                        except Exception as math_err:
                            tool_content = f"Ошибка вычисления: {math_err}"
                        log.info(f"🔢 Агент считает: {expr}")
                    
                    history.append({
                        "tool_call_id": tool_call.id,
                        "role": "tool",
                        "name": function_name,
                        "content": tool_content,
                    })

                second_response = await self.client.chat.completions.create(
                    messages=history,
                    model=current_model,
                )
                ai_response = second_response.choices[0].message.content
            else:
                ai_response = response_message.content

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

    async def get_vision_response(self, user_id: int, image_bytes: bytes, caption: str = None) -> str:
        """Анализирует изображение через Llama 3.2 Vision."""
        if not GROQ_API_KEY:
            return "❌ GROQ_API_KEY не задан."

        # Превращаем картинку в base64
        base64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Получаем контекст, чтобы бот помнил, о чем говорили раньше
        history, _ = await db.get_user_data(user_id)
        if not history:
            history = [{"role": "system", "content": "You are GroqPulse, a helpful AI with vision capabilities. Describe images accurately and answer questions about them."}]

        prompt = caption or "Опиши, что ты видишь на этом изображении?"
        
        # Формируем сообщение с картинкой
        vision_message = {
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{base64_image}",
                    },
                },
            ],
        }

        # Добавляем в историю (но не храним саму тяжелую картинку в БД, только текст)
        temp_history = history + [vision_message]

        try:
            response = await self.client.chat.completions.create(
                messages=temp_history,
                model="meta-llama/llama-4-scout-17b-16e-instruct",
            )
            ai_response = response.choices[0].message.content
            
            # Сохраняем в историю только текст (без картинки, чтобы не раздувать БД)
            history.append({"role": "user", "content": f"[Фото]: {prompt}"})
            history.append({"role": "assistant", "content": ai_response})
            await db.save_user_data(user_id, history)
            
            return ai_response
        except Exception as e:
            log.error(f"Vision Error: {e}")
            return f"⚠️ Ошибка при анализе фото: {str(e)}"

    async def get_doc_response(self, user_id: int, doc_text: str, file_name: str) -> str:
        """Обрабатывает контент из документа."""
        if not GROQ_API_KEY:
            return "❌ GROQ_API_KEY не задан."

        history, _ = await db.get_user_data(user_id)
        
        # Системная вставка про документ
        doc_info = f"Пользователь прислал документ: {file_name}.\n\nСодержимое документа:\n\"\"\"\n{doc_text}\n\"\"\"\n\nПроанализируй этот текст и приготовься отвечать на вопросы по нему. Если текст слишком длинный, сфокусируйся на главных тезах."
        
        if not history:
            history = [{"role": "system", "content": "You are GroqPulse, a helpful AI. You can analyze documents. Answer in the language of the user."}]

        # Добавляем инфу о документе в ИИ (через системное сообщение или user-вставку)
        history.append({"role": "user", "content": f"Я загрузил файл '{file_name}'. Прочитай его."})
        history.append({"role": "system", "content": doc_info})

        try:
            response = await self.client.chat.completions.create(
                messages=history,
                model="llama-3.3-70b-versatile", # Для документов берем самую умную модель
            )
            ai_response = response.choices[0].message.content
            
            # Сохраняем в историю подтверждение прочтения
            history.append({"role": "assistant", "content": ai_response})
            await db.save_user_data(user_id, history)
            
            return ai_response
        except Exception as e:
            log.error(f"Doc Analysis Error: {e}")
            return f"⚠️ Ошибка при анализе документа: {str(e)}"

    async def set_model(self, user_id: int, model_name: str):
        history, _ = await db.get_user_data(user_id)
        await db.save_user_data(user_id, history or [], model_name)

# Глобальный экземпляр
ai = GroqService()
