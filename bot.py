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
        # 1. Улучшаем промпт через Groq (перевод + детализация)
        enhanced_prompt_query = f"Translate and enhance this image description for an AI generator. Be descriptive but keep it under 30 words. Prompt: {prompt}"
        # Используем быструю 8B модель для перевода
        ai_prompt = await ai.client.chat.completions.create(
            messages=[{"role": "user", "content": enhanced_prompt_query}],
            model="llama-3.1-8b-instant",
            temperature=0.7,
        )
        english_prompt = ai_prompt.choices[0].message.content.strip()
        log.info(f"✨ Enhanced prompt: {english_prompt}")

        # 2. Генерируем картинку (Провайдер 1: Pollinations)
        try:
            image_url = await image_gen.generate_image_url(english_prompt, provider="pollinations")
            log.info(f"🎨 Trying Pollinations for prompt: {english_prompt}")
            image_bytes = await image_gen.download_image(image_url)
            
            await message.answer_photo(
                photo=BufferedInputFile(image_bytes, filename="art.png"),
                caption=f"🎨 <b>Ваш запрос:</b> {prompt}\n✨ <i>Модель: Flux (Pollinations)</i>"
            )
            return
        except Exception as e:
            log.warn(f"⚠️ Провайдер Pollinations недоступен: {e}. Пробую запасной вариант...")

        # 3. Генерируем картинку (Провайдер 2: Airforce)
        try:
            image_url = await image_gen.generate_image_url(english_prompt, provider="airforce")
            log.info(f"🎨 Trying Airforce for prompt: {english_prompt}")
            image_bytes = await image_gen.download_image(image_url)
            
            await message.answer_photo(
                photo=BufferedInputFile(image_bytes, filename="art.png"),
                caption=f"🎨 <b>Ваш запрос:</b> {prompt}\n✨ <i>Модель: Flux (Airforce)</i>"
            )
        except Exception as e:
            log.error(f"❌ Оба провайдера не справились: {e}")
            await message.answer(
                f"❌ <b>К сожалению, все сервисы генерации сейчас перегружены.</b>\n"
                f"Попробуйте позже или используйте другой запрос.\n\n"
                f"<i>(Ошибка: {str(e)})</i>"
            )
    except Exception as e:
        log.error(f"Image Gen Error for prompt '{prompt}': {e}", exc_info=True)
        error_msg = str(e)
        
        # Если скачивание не удалось (блокада), пробуем отправить просто ссылку
        # Telegram сам "развернет" (preview) картинку по ссылке
        try:
            log.info("⚠️ Falling back to direct URL due to download error.")
            image_url = await image_gen.generate_image_url(prompt) # Генерируем еще раз на всякий случай
            await message.answer(
                f"🎨 <b>Не удалось загрузить файл, вот прямая ссылка:</b>\n"
                f"<a href='{image_url}'>🖼 Открыть изображение</a>\n\n"
                f"<i>(Telegram должен показать превью ниже)</i>",
                disable_web_page_preview=False
            )
        except Exception as fallback_e:
            is_render = os.getenv("RENDER") == "true"
            if "530" in error_msg or "Forbidden" in error_msg:
                if is_render:
                    await message.answer(f"❌ <b>Сервис Pollinations временно недоступен (Error {error_msg}).</b>\nПопробуйте позже или используйте другой промпт.")
                else:
                    await message.answer("❌ <b>Ошибка доступа (530/403).</b>\nЛокальный запуск заблокирован. Пожалуйста, **залейте изменения на Render**!")
            else:
                await message.answer(f"⚠️ Ошибка: {error_msg}")

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
