import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, TelegramObject, KeyboardButton, ReplyKeyboardMarkup
from aiohttp import web
from typing import Callable, Any, Awaitable

from config import BOT_TOKEN, ADMIN_ID
from groq_service import ai

# Логирование
logging.basicConfig(level=logging.INFO, stream=sys.stdout)
log = logging.getLogger(__name__)

# Сервисы
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()

class AccessMiddleware(BaseMiddleware):
    """Ограничение доступа: бот отвечает только админу."""
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if not ADMIN_ID:
            return await handler(event, data)

        user = data.get("event_from_user")
        if user:
            if str(user.id) != str(ADMIN_ID):
                if isinstance(event, Message) and event.text == "/start":
                    await event.answer("🔒 <b>Доступ ограничен.</b>\nЭтот AI-ассистент является приватным.")
                return 
        
        return await handler(event, data)

# ── Веб-сервер (Anti-sleep для Render) ────────────────────────────────

async def handle_ping(request):
    return web.Response(text="GroqPulse is alive and thinking!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle_ping)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", 8080))
    site = web.TCPSite(runner, "0.0.0.0", port)
    log.info(f"🌐 Server started on port {port}")
    await site.start()

# ── Клавиатуры ──────────────────────────────────────────────────────────

def main_keyboard():
    kb = [
        [KeyboardButton(text="🧠 Выбор модели")],
        [KeyboardButton(text="🧹 Очистить память"), KeyboardButton(text="ℹ️ О модели")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def models_keyboard():
    buttons = [
        [InlineKeyboardButton(text="💎 Llama 3.3 70B (Smartest)", callback_data="set_model_llama-3.3-70b-versatile")],
        [InlineKeyboardButton(text="⚡ Llama 3.1 8B (Instant)", callback_data="set_model_llama-3.1-8b-instant")],
        [InlineKeyboardButton(text="🌀 Mixtral 8x7b (Balanced)", callback_data="set_model_mixtral-8x7b-32768")],
        [InlineKeyboardButton(text="🐥 Gemma 2 9b (Light)", callback_data="set_model_gemma2-9b-it")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ── Хендлеры ────────────────────────────────────────────────────────────

@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "🤖 <b>Привет! Я GroqPulse.</b>\n\n"
        "Я работаю на базе сверхбыстрых моделей Llama 3 через Groq API.\n"
        "Просто напиши мне что-нибудь, и я отвечу почти мгновенно.",
        reply_markup=main_keyboard()
    )

@router.message(F.text == "🧹 Очистить память")
async def clear_memory(message: Message):
    ai.clear_context(message.from_user.id)
    await message.answer("🧼 <b>Память диалога очищена.</b> Начнем с чистого листа!")

@router.message(F.text == "ℹ️ О модели")
async def model_info(message: Message):
    from groq_service import ai
    current_model = ai.user_models.get(message.from_user.id, "Default")
    await message.answer(
        f"🧠 <b>Текущая конфигурация:</b>\n\n"
        f"• Модель: <code>{current_model}</code>\n"
        f"• Инференс: Groq LPU (Ultra Fast)"
    )

@router.message(F.text == "🧠 Выбор модели")
async def show_models(message: Message):
    await message.answer(
        "🎭 <b>Выберите модель для общения:</b>\n\n"
        "• <b>70B</b> — самая умная, подходит для сложных задач.\n"
        "• <b>8B / Gemma</b> — самые быстрые, идеальны для чата.\n"
        "• <b>Mixtral</b> — отличный баланс логики и скорости.",
        reply_markup=models_keyboard()
    )

@router.callback_query(F.data.startswith("set_model_"))
async def process_model_selection(callback: CallbackQuery):
    model_name = callback.data.replace("set_model_", "")
    ai.set_model(callback.from_user.id, model_name)
    
    await callback.answer(f"✅ Установлена модель {model_name}")
    await callback.message.edit_text(
        f"✅ <b>Модель успешно изменена!</b>\n"
        f"Теперь я использую: <code>{model_name}</code>\n\n"
        f"Вся память диалога сохранена."
    )

@router.message()
async def chat_handler(message: Message):
    if not message.text:
        return

    # Показываем статус "печатает"
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    # Получаем ответ от AI
    response = await ai.get_response(message.from_user.id, message.text)
    
    # Отправляем ответ частями, если он слишком длинный (лимит TG ~4000 символов)
    if len(response) > 4000:
        for i in range(0, len(response), 4000):
            await message.answer(response[i:i+4000])
    else:
        await message.answer(response)

async def main():
    # Запуск веб-сервера
    asyncio.create_task(start_web_server())
    
    # Регистрация Middleware
    router.message.middleware(AccessMiddleware())
    
    dp.include_router(router)
    log.info("🚀 GroqPulse запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
