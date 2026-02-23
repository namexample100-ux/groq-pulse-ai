import os
import asyncio
import logging
import asyncpg
import json
from config import DATABASE_URL

log = logging.getLogger(__name__)

_pool = None

async def init_db():
    """Инициализация пула подключений и создание таблиц."""
    global _pool
    
    if not DATABASE_URL:
        log.error("❌ DATABASE_URL не задан!")
        return

    try:
        _pool = await asyncpg.create_pool(
            DATABASE_URL, 
            ssl='require', 
            min_size=2, 
            max_size=10,
            statement_cache_size=0 # Нужно для работы с PgBouncer (Supabase)
        )
        log.info("🐘 Пул подключений к БД (Supabase) создан.")
        
        async with _pool.acquire() as conn:
            # Таблица для хранения контекста (последние сообщения)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_history (
                    user_id BIGINT PRIMARY KEY,
                    messages JSONB DEFAULT '[]'::jsonb,
                    model_name TEXT DEFAULT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            log.info("✅ Таблица chat_history проверена/создана.")
            
    except Exception as e:
        log.error(f"❌ Ошибка БД: {e}")

async def get_user_data(user_id: int):
    """Получает историю и модель пользователя."""
    if not _pool: return [], None
    
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT messages, model_name FROM chat_history WHERE user_id = $1",
                user_id
            )
            if row:
                return json.loads(row['messages']), row['model_name']
            return [], None
    except Exception as e:
        log.error(f"❌ Ошибка получения данных: {e}")
        return [], None

async def save_user_data(user_id: int, messages: list, model_name: str = None):
    """Сохраняет историю и выбранную модель."""
    if not _pool: return
    
    try:
        messages_json = json.dumps(messages)
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO chat_history (user_id, messages, model_name, updated_at)
                VALUES ($1, $2, $3, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id) DO UPDATE 
                SET messages = $2, model_name = COALESCE($3, chat_history.model_name), updated_at = CURRENT_TIMESTAMP
            """, user_id, messages_json, model_name)
    except Exception as e:
        log.error(f"❌ Ошибка сохранения данных: {e}")

async def clear_user_history(user_id: int):
    """Очищает только историю сообщений, оставляя модель."""
    if not _pool: return
    
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "UPDATE chat_history SET messages = '[]'::jsonb, updated_at = CURRENT_TIMESTAMP WHERE user_id = $1",
                user_id
            )
    except Exception as e:
        log.error(f"❌ Ошибка очистки истории: {e}")

async def close_db():
    """Закрытие пула."""
    if _pool:
        await _pool.close()
        log.info("🐘 Пул подключений к БД закрыт.")
