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
    BufferedInputFile, InputFile
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
import io
from aiohttp import web
from typing import Callable, Any, Awaitable

from config import BOT_TOKEN, ADMIN_ID
from groq_service import ai
from image_service import image_gen
from doc_service import doc_tool
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
        [KeyboardButton(text="🧠 Chat-модели"), KeyboardButton(text="🖼 Image-модели")],
        [KeyboardButton(text="🧹 Очистить память"), KeyboardButton(text="ℹ️ О модели")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def models_keyboard():
    buttons = [
        [InlineKeyboardButton(text="💎 Llama 3.3 70B (Smartest)", callback_data="set_model_llama-3.3-70b-versatile")],
        [InlineKeyboardButton(text="⚡ Llama 3.1 8B (Instant)", callback_data="set_model_llama-3.1-8b-instant")],
        [InlineKeyboardButton(text="🌀 Qwen 3 32B (Balanced)", callback_data="set_model_qwen/qwen3-32b")],
        [InlineKeyboardButton(text="🚀 Llama 4 Maverick (New Gen)", callback_data="set_model_meta-llama/llama-4-maverick-17b-128e-instruct")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)

def image_models_keyboard():
    buttons = [
        [InlineKeyboardButton(text="🎨 FLUX.1 [schnell] (Best)", callback_data="set_img_black-forest-labs/FLUX.1-schnell")],
        [InlineKeyboardButton(text="📸 Stable Diffusion 3.5", callback_data="set_img_stabilityai/stable-diffusion-3.5-large")],
        [InlineKeyboardButton(text="🏮 Kolors (Ultra Phoreal)", callback_data="set_img_Kwai-Kolors/Kolors")],
        [InlineKeyboardButton(text="⚡ SDXL Turbo (Instant)", callback_data="set_img_stabilityai/sdxl-turbo")],
        [InlineKeyboardButton(text="🌸 Animagine (Anime Style)", callback_data="set_img_cagliostrolab/animagine-xl-3.1")]
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
    _, current_model, img_model = await db.get_user_data(message.from_user.id)
    from config import DEFAULT_MODEL, DEFAULT_IMAGE_MODEL
    chat_m = current_model or DEFAULT_MODEL
    img_m = (img_model or DEFAULT_IMAGE_MODEL).split('/')[-1]
    
    await message.answer(
        f"🤖 <b>Ваш статус: GroqPulse v4.5</b>\n\n"
        f"💬 <b>Chat Model:</b> <code>{chat_m}</code>\n"
        f"🖼 <b>Image Model:</b> <code>{img_m}</code>\n"
        f"⚡ <b>Inference:</b> Groq + HF"
    )

@router.message(F.text == "🧠 Chat-модели")
async def show_models(message: Message):
    await message.answer(
        "🎭 <b>Выберите модель для общения:</b>\n\n"
        "• <b>Llama 3.3 70B</b> — самая умная.\n"
        "• <b>Qwen / Llama 4</b> — новые горизонты.\n"
        "• <b>8B</b> — быстрая для чата.",
        reply_markup=models_keyboard()
    )

@router.message(F.text == "🖼 Image-модели")
async def show_image_models(message: Message):
    await message.answer(
        "🎨 <b>Выберите модель для рисования:</b>\n\n"
        "• <b>FLUX</b> — лидер фотореализма.\n"
        "• <b>SD 3.5</b> — понимает сложные промпты.\n"
        "• <b>Kolors</b> — идеальный свет и кожа.\n"
        "• <b>Animagine</b> — лучший аниме-арт.",
        reply_markup=image_models_keyboard()
    )

@router.callback_query(F.data.startswith("set_model_"))
async def process_model_selection(callback: CallbackQuery):
    model_name = callback.data.replace("set_model_", "")
    await db.save_user_data(callback.from_user.id, model_name=model_name)
    
    await callback.answer(f"✅ Чат: {model_name}")
    await callback.message.edit_text(f"✅ <b>Чат-модель изменена на:</b> <code>{model_name}</code>")

@router.callback_query(F.data.startswith("set_img_"))
async def process_image_model_selection(callback: CallbackQuery):
    img_model = callback.data.replace("set_img_", "")
    await db.save_user_data(callback.from_user.id, image_model=img_model)
    
    short_name = img_model.split('/')[-1]
    await callback.answer(f"✅ Фото: {short_name}")
    await callback.message.edit_text(f"✅ <b>Image-модель изменена на:</b> <code>{short_name}</code>")

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
        # Получаем выбранную модель пользователя
        _, _, user_img_model = await db.get_user_data(message.from_user.id)
        
        image_bytes = await image_gen.generate_image(english_prompt, model_id=user_img_model)
        
        model_display = (user_img_model or "FLUX.1").split('/')[-1]
        await message.answer_photo(
            photo=BufferedInputFile(image_bytes, filename="art.png"),
            caption=f"🎨 <b>Ваш запрос:</b> {prompt}\n✨ <i>Модель: {model_display}</i>"
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

@router.message(F.document)
async def handle_document(message: Message):
    """Обработка входящих документов (PDF/TXT)."""
    file_name = message.document.file_name
    if not (file_name.lower().endswith('.pdf') or file_name.lower().endswith('.txt')):
        await message.answer("❌ Я пока умею читать только <b>PDF</b> и <b>TXT</b> файлы.")
        return

    wait_msg = await message.answer(f"⏳ Читаю документ <code>{file_name}</code>...")
    await message.bot.send_chat_action(chat_id=message.chat.id, action="typing")
    
    try:
        # Скачиваем файл
        file = await message.bot.get_file(message.document.file_id)
        file_bytes = await message.bot.download_file(file.file_path)
        
        # Извлекаем текст
        doc_text = await doc_tool.get_document_content(file_bytes.read(), file_name)
        
        if doc_text.startswith("⚠️") or doc_text.startswith("❌"):
            await wait_msg.edit_text(doc_text)
            return

        # Отправляем в ИИ для анализа
        response = await ai.get_doc_response(
            user_id=message.from_user.id,
            doc_text=doc_text,
            file_name=file_name
        )
        
        await wait_msg.edit_text(response)
    except Exception as e:
        log.error(f"Doc Handler Error: {e}", exc_info=True)
        await wait_msg.edit_text(f"⚠️ Ошибка при чтении файла: {str(e)}")

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
