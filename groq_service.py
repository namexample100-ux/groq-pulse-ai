import os
import logging
import httpx
import json
import base64
import re
import datetime
from groq import AsyncGroq
from config import GROQ_API_KEY, DEFAULT_MODEL
import database as db
from search_service import search_tool
from doc_service import doc_tool

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
    },
    {
        "type": "function",
        "function": {
            "name": "add_reminder",
            "description": "Sets a reminder for the user. Example: text='Meeting', time_str='in 15 minutes' or 'at 18:00'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "The content of the reminder (e.g. 'Buy milk')"},
                    "time_str": {"type": "string", "description": "Time description (e.g. 'in 5 minutes', 'tomorrow at 10:00', 'at 15:00')"}
                },
                "required": ["text", "time_str"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_doc",
            "description": "Analyze the content of a previously uploaded document.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the document file."},
                    "query": {"type": "string", "description": "What to look for or analyze in the document."}
                },
                "required": ["path", "query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "save_memory",
            "description": "Saves a fact or preference about the user for long-term memory. Example: content='User prefers dark mode'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "The fact to remember."}
                },
                "required": ["content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "summarize_channel",
            "description": "Fetch and summarize the latest posts from a public Telegram channel. Example: channel_name='durov'.",
            "parameters": {
                "type": "object",
                "properties": {
                    "channel_name": {"type": "string", "description": "The telegram channel username/ID (without @)."}
                },
                "required": ["channel_name"]
            }
        }
    }
]

# Пресеты персонажей
CHARACTERS = {
    "default": "You are GroqPulse, an advanced AI Agent. You are helpful, polite, and efficient.",
    "coder": "You are GroqPulse Coder. You are an expert senior software engineer. Focus on clean code, best practices, and detailed technical explanations. Use markdown for code blocks.",
    "teacher": "You are GroqPulse Teacher. Your goal is to explain complex concepts in simple terms. Use analogies, step-by-step guides, and encourage the user to ask questions.",
    "friend": "You are GroqPulse Friend. You are a friendly, informal, and supportive companion. Use a relaxed tone and be empathetic."
}

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
        
        # Получаем данные пользователя
        history, user_model, _, character = await db.get_user_data(user_id)
        current_model = user_model or DEFAULT_MODEL
        current_char = character or "default"

        # Получаем Вечную Память
        memories = await db.get_memories(user_id)
        memory_context = ""
        if memories:
            memory_context = "\n\n[USER ETERNAL MEMORY]:\n" + "\n".join([f"- {m}" for m in memories])

        # Системный промпт для Агента
        char_prompt = CHARACTERS.get(current_char, CHARACTERS["default"])
        system_content = (
            f"{char_prompt}\n\n"
            "You have access to real-time tools:\n"
            "1. If the user asks about current events, use 'search_web'.\n"
            "2. If the user asks for time/date, use 'get_current_time'.\n"
            "3. For complex math, use 'calculate_math'.\n"
            "4. To set a reminder, use 'add_reminder'.\n"
            "5. To save a fact about user, use 'save_memory'.\n"
            "Always answer in the language the user speaks to you. "
            "CRITICAL: When using search results, ALWAYS provide clickable links (URLs) to the sources."
            f"{memory_context}"
        )

        system_prompt = {"role": "system", "content": system_content}

        if not history:
            history = [system_prompt]
        else:
            history[0] = system_prompt

        history.append({"role": "user", "content": user_text})

        if len(history) > self.max_context + 1:
            history = [history[0]] + history[-self.max_context:]

        try:
            try:
                response = await self.client.chat.completions.create(
                    messages=history,
                    model=current_model,
                    tools=TOOLS,
                    tool_choice="auto",
                    temperature=0.7,
                )
            except Exception as e:
                if "rate_limit_exceeded" in str(e).lower() and current_model != "llama-3.1-8b-instant":
                    log.warning(f"⚠️ Лимит {current_model} исчерпан. Переключаюсь на 8b-instant...")
                    response = await self.client.chat.completions.create(
                        messages=history,
                        model="llama-3.1-8b-instant",
                        tools=TOOLS,
                        tool_choice="auto",
                        temperature=0.7,
                    )
                else:
                    raise e
            
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
                        tool_content = await self.tool_get_current_time()
                        log.info(f"🕒 Агент запрашивает время")

                    elif function_name == "calculate_math":
                        tool_content = await self.tool_calculate_math(function_args.get("expression"))
                        log.info(f"🔢 Агент вычисляет математику")
                    
                    elif function_name == "add_reminder":
                        tool_content = await self.tool_add_reminder(user_id, **function_args)
                        log.info(f"📅 Агент ставит напоминание")
                    
                    elif function_name == "summarize_channel":
                        tool_content = await self.tool_summarize_channel(function_args.get("channel_name"))
                        log.info(f"🔗 Агент читает канал: {function_args.get('channel_name')}")

                    elif function_name == "analyze_doc":
                        path = function_args.get("path")
                        query = function_args.get("query")
                        log.info(f"📄 Агент анализирует файл: {path}")
                        tool_content = await doc_tool.analyze(path, query)

                    history.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": function_name,
                        "content": tool_content,
                    })

                # Второй запрос тоже с фоллбэком
                try:
                    second_response = await self.client.chat.completions.create(
                        messages=history,
                        model=current_model,
                    )
                except Exception as e:
                    if "rate_limit_exceeded" in str(e).lower() and current_model != "llama-3.1-8b-instant":
                        second_response = await self.client.chat.completions.create(
                            messages=history,
                            model="llama-3.1-8b-instant",
                        )
                    else:
                        raise e
                ai_response = second_response.choices[0].message.content
            else:
                ai_response = response_message.content

            # Очистка ответа перед сохранением и возвратом
            ai_response = self._clean_response(ai_response)

            history.append({"role": "assistant", "content": ai_response})
            await db.save_user_data(user_id, history)
            return ai_response
            
        except Exception as e:
            log.error(f"Groq Agent Error: {e}", exc_info=True)
            err_str = str(e).lower()
            if "forbidden" in err_str or "access denied" in err_str:
                return "❌ **Ошибка доступа (403).**\nGroq блокирует запросы из вашего региона."
            if "rate_limit_exceeded" in err_str:
                return "🚨 **Лимит запросов исчерпан.**\nВсе доступные модели Groq сейчас перегружены. Пожалуйста, подождите 15-20 минут."
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
        history, _, _, _ = await db.get_user_data(user_id)
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

        history, _, _, _ = await db.get_user_data(user_id)
        
        # Системная вставка про документ
        doc_info = f"Пользователь прислал документ: {file_name}.\n\nСодержимое документа:\n\"\"\"\n{doc_text}\n\"\"\"\n\nПроанализируй этот текст и приготовься отвечать на вопросы по нему. Если текст слишком длинный, сфокусируйся на главных тезах."
        
        if not history:
            history = [{"role": "system", "content": "You are GroqPulse, a helpful AI. You can analyze documents. Answer in the language of the user."}]

        # Добавляем инфу о документе в ИИ (через системное сообщение или user-вставку)
        history.append({"role": "user", "content": f"Я загрузил файл '{file_name}'. Прочитай его."})
        history.append({"role": "system", "content": doc_info})

        try:
            try:
                response = await self.client.chat.completions.create(
                    messages=history,
                    model="llama-3.3-70b-versatile", # Для документов берем самую умную модель
                )
            except Exception as e:
                if "rate_limit_exceeded" in str(e).lower():
                    # Фоллбэк на более легкую модель
                    response = await self.client.chat.completions.create(
                        messages=history,
                        model="llama-3.1-8b-instant",
                    )
                else:
                    raise e
            
            ai_response = response.choices[0].message.content
            
            # Сохраняем в историю подтверждение прочтения
            history.append({"role": "assistant", "content": ai_response})
            await db.save_user_data(user_id, history)
            
            return ai_response
        except Exception as e:
            log.error(f"Doc Analysis Error: {e}")
            return f"⚠️ Ошибка при анализе документа: {str(e)}"

    async def set_model(self, user_id: int, model_name: str):
        await db.save_user_data(user_id, model_name=model_name)

    async def tool_get_current_time(self) -> str:
        """Инструмент для получения текущего времени."""
        import datetime
        now = datetime.datetime.now()
        return f"🕒 Текущее время: {now.strftime('%H:%M:%S')}. Дата: {now.strftime('%d.%m.%Y')}."

    async def tool_calculate_math(self, expression: str) -> str:
        """Инструмент для вычисления математических выражений."""
        try:
            # Безопасное вычисление (ограниченное)
            result = eval(expression, {"__builtins__": None}, {})
            return f"🔢 Результат: {result}"
        except Exception as e:
            return f"❌ Ошибка вычисления: {str(e)}"

    async def tool_add_reminder(self, user_id: int, text: str, time_str: str) -> str:
        """Инструмент для добавления напоминания."""
        try:
            from dateutil import parser
            import datetime
            
            now = datetime.datetime.now()
            
            # Попытка парсинга относительного времени (упрощенно)
            remind_at = None
            ts = time_str.lower()
            
            if "через" in ts or "in " in ts:
                number = int(''.join(filter(str.isdigit, ts)))
                if "мин" in ts or "min" in ts:
                    remind_at = now + datetime.timedelta(minutes=number)
                elif "час" in ts or "hour" in ts:
                    remind_at = now + datetime.timedelta(hours=number)
                elif "сек" in ts or "sec" in ts:
                    remind_at = now + datetime.timedelta(seconds=number)
                elif "день" in ts or "day" in ts:
                    remind_at = now + datetime.timedelta(days=number)
            
            if not remind_at:
                # Универсальный парсер для форматов типа "18:00" или "tomorrow at 10:00"
                remind_at = parser.parse(time_str, fuzzy=True, default=now)
                # Если время в прошлом (например, указано 09:00, а сейчас 10:00), прибавляем день
                if remind_at < now:
                    remind_at += datetime.timedelta(days=1)

            # Сохраняем в БД (передаем объект datetime)
            await db.add_reminder(user_id, text, remind_at)
            
            pretty_time = remind_at.strftime("%H:%M %d.%m.%Y")
            return f"✅ Напоминание установлено: '{text}' на {pretty_time}"
            
        except Exception as e:
            log.error(f"Add Reminder Tool Error: {e}")
            return f"❌ Ошибка при установке напоминания: {str(e)}"

    async def tool_summarize_channel(self, channel_name: int | str) -> str:
        """Инструмент для суммаризации Telegram-канала."""
        try:
            url = f"https://t.me/s/{channel_name}"
            async with httpx.AsyncClient(follow_redirects=True) as client:
                resp = await client.get(url, timeout=10)
                if resp.status_code != 200:
                    return f"❌ Не удалось получить доступ к каналу @{channel_name} (Status: {resp.status_code})"
                
                html = resp.text
                # Извлекаем текст сообщений (упрощенно через регулярки)
                # Сообщения обычно в дивах с классом tgme_widget_message_text
                messages = re.findall(r'<div class="tgme_widget_message_text[^>]*>(.*?)</div>', html, re.DOTALL)
                
                if not messages:
                    return f"⚠️ В канале @{channel_name} не найдено текстовых сообщений (или канал приватный)."
                
                # Очищаем от HTML-тегов каждое сообщение
                clean_messages = []
                for msg in messages[-5:]: # Берем последние 5
                    # Убираем теги <br/> и другие
                    clean_text = re.sub(r'<[^>]+>', ' ', msg)
                    clean_messages.append(clean_text.strip())
                
                context = "\n---\n".join(clean_messages)
                return f"📝 Последние посты из канала @{channel_name}:\n\n{context}\n\nПожалуйста, проанализируй и кратко перескажи суть этих постов."

        except Exception as e:
            log.error(f"Summarize Channel Tool Error: {e}")
            return f"❌ Ошибка при чтению канала: {str(e)}"

    async def tool_save_memory(self, user_id: int, content: str) -> str:
        """Инструмент для сохранения фактов в вечную память."""
        try:
            await db.add_memory(user_id, content)
            return f"✅ Я запомнил: {content}"
        except Exception as e:
            log.error(f"Save Memory Tool Error: {e}")
            return f"❌ Ошибка сохранения памяти: {str(e)}"

    async def transcribe_audio(self, audio_file_path: str) -> str:
        """Транскрибирует аудио через Groq Whisper."""
        try:
            with open(audio_file_path, "rb") as file:
                transcription = await self.client.audio.transcriptions.create(
                    file=(audio_file_path, file.read()),
                    model="whisper-large-v3",
                    response_format="text",
                )
            return transcription
        except Exception as e:
            log.error(f"Transcription Error: {e}")
            return f"❌ Ошибка транскрипции: {str(e)}"

    def _clean_response(self, text: str) -> str:
        """Очищает ответ от служебных тегов типа <think> и лишних переносов."""
        if not text:
            return ""
        # Убираем содержимое тегов <think>...</think>
        text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)
        # Убираем множественные переносы строк
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

# Глобальный экземпляр
ai = GroqService()
