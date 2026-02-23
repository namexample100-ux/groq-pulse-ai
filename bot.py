import asyncio
import logging
import sys
import os
from aiogram import Bot, Dispatcher, Router, F, BaseMiddleware
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    Message, CallbackQuery, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup, TelegramObject,
    BufferedInputFile
)
from aiohttp import web
from typing import Callable, Any, Awaitable

from config import BOT_TOKEN, ADMIN_ID
from groq_service import ai
from image_service import image_gen
import database as db

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
    await ai.clear_context(message.from_user.id)
    await message.answer("🧼 <b>Память диалога очищена.</b> Начнем с чистого листа!")

@router.message(F.text == "ℹ️ О модели")
async def model_info(message: Message):
    _, current_model = await db.get_user_data(message.from_user.id)
    from config import DEFAULT_MODEL
    model_to_show = current_model or DEFAULT_MODEL
    await message.answer(
        f"🧠 <b>Текущая конфигурация:</b>\n\n"
        f"• Модель: <code>{model_to_show}</code>\n"
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
    await ai.set_model(callback.from_user.id, model_name)
    
    await callback.answer(f"✅ Установлена модель {model_name}")
    await callback.message.edit_text(
        f"✅ <b>Модель успешно изменена!</b>\n"
        f"Теперь я использую: <code>{model_name}</code>\n\n"
        f"Вся память диалога сохранена."
    )

@router.message(Command("img"))
async def cmd_img(message: Message):
    # Получаем текст после команды /img
    prompt = message.text.replace("/img", "").strip()
    if not prompt:
        await message.answer("🖼 <b>Пожалуйста, введите описание картинки.</b>\nПример: <code>/img робот в космосе</code>")
        return

    await message.bot.send_chat_action(chat_id=message.chat.id, action="upload_photo")
    
    try:
        # 1. Улучшаем промпт через Groq (если он доступен)
        english_prompt = prompt # По умолчанию используем оригинал
        try:
            enhanced_prompt_query = f"Translate and enhance this image description for an AI generator. Be descriptive but keep it under 30 words. Prompt: {prompt}"
            ai_prompt = await ai.client.chat.completions.create(
                messages=[{"role": "user", "content": enhanced_prompt_query}],
                model="llama-3.1-8b-instant",
                temperature=0.7,
            )
            english_prompt = ai_prompt.choices[0].message.content.strip()
            log.info(f"✨ Enhanced prompt: {english_prompt}")
        except Exception as groq_err:
            log.warning(f"⚠️ Не удалось улучшить промпт через Groq (вероятно, блок): {groq_err}")
            # Продолжаем с оригинальным промптом

        # 2. Генерируем картинку через Hugging Face
        image_bytes = await image_gen.generate_image(english_prompt)
        
        await message.answer_photo(
            photo=BufferedInputFile(image_bytes, filename="art.png"),
            caption=f"🎨 <b>Ваш запрос:</b> {prompt}\n✨ <i>Модель: FLUX.1 (Hugging Face)</i>"
        )
    except Exception as e:
        log.error(f"Image Gen Error: {e}", exc_info=True)
        error_msg = str(e)
        if "HF_TOKEN" in error_msg:
            await message.answer("❌ <b>Ошибка: Отсутствует токен Hugging Face.</b>\nПожалуйста, добавьте <code>HF_TOKEN</code> в настройки бота.")
        elif "wait" in error_msg.lower():
            await message.answer("⏳ <b>Модель прогревается.</b>\nПожалуйста, попробуйте еще раз через несколько секунд.")
        else:
            await message.answer(f"⚠️ <b>Произошла ошибка:</b>\n<code>{error_msg}</code>")

@router.message(F.photo)
async def handle_photo(message: Message):
    """Обработка входящих фотографий (Зрение)."""
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        # Получаем фото самого высокого качества
        photo = message.photo[-1]
        
        # Скачиваем фото в память
        file = await message.bot.get_file(photo.file_id)
        image_bytes = await message.bot.download_file(file.file_path)
        
        # Передаем в ИИ-зрение
        response = await ai.get_vision_response(
            user_id=message.from_user.id,
            image_bytes=image_bytes.read(),
            caption=message.caption
        )
        
        await message.answer(response)
    except Exception as e:
        log.error(f"Vision Handler Error: {e}", exc_info=True)
        await message.answer(f"⚠️ Ошибка при обработке фото: {str(e)}")

@router.message()
async def chat_handler(message: Message):
    if not message.text:
        return

    # Проверка на запрос генерации картинки через текст
    if message.text.lower().startswith(("нарисуй", "начерти", "draw")):
        prompt = message.text.lower().replace("нарисуй", "").replace("начерти", "").replace("draw", "").strip()
        if prompt:
            await cmd_img(message) # Используем тот же хендлер, но с промптом
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
    # Инициализация БД
    await db.init_db()
    
    # Запуск веб-сервера
    asyncio.create_task(start_web_server())
    
    # Регистрация Middleware
    router.message.middleware(AccessMiddleware())
    
    dp.include_router(router)
    log.info("🚀 GroqPulse запущен!")
    try:
        await dp.start_polling(bot)
    finally:
        await db.close_db()
        await bot.session.close()

if __name__ == "__main__":
    asyncio.run(main())
