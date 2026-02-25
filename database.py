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
                    image_model TEXT DEFAULT NULL,
                    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
            
            # Попытка добавить колонку если она не существует (Миграция)
            try:
                await conn.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS image_model TEXT DEFAULT NULL")
                await conn.execute("ALTER TABLE chat_history ADD COLUMN IF NOT EXISTS character TEXT DEFAULT 'default'")
            except:
                pass
            
            # Таблица для напоминаний
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    text TEXT NOT NULL,
                    remind_at TIMESTAMP WITH TIME ZONE NOT NULL,
                    status TEXT DEFAULT 'pending',
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
                
            # Таблица для "Вечной Памяти" (Eternal Memory)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS user_memories (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)
                
            log.info("✅ Таблицы БД проверены/созданы.")
            
    except Exception as e:
        log.error(f"❌ Ошибка БД: {e}")

async def get_user_data(user_id: int):
    """Получает историю и модель пользователя."""
    if not _pool: return [], None
    
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT messages, model_name, image_model, character FROM chat_history WHERE user_id = $1",
                user_id
            )
            if row:
                return json.loads(row['messages']), row['model_name'], row['image_model'], row['character']
            return [], None, None, 'default'
    except Exception as e:
        log.error(f"❌ Ошибка получения данных: {e}")
        return [], None, None

async def save_user_data(user_id: int, messages: list = None, model_name: str = None, image_model: str = None, character: str = None):
    """Сохраняет историю, чат-модель, image-модель или персонажа."""
    if not _pool: return
    
    try:
        async with _pool.acquire() as conn:
            # Сначала проверяем существование записи
            exists = await conn.fetchval("SELECT 1 FROM chat_history WHERE user_id = $1", user_id)
            if not exists:
                await conn.execute("INSERT INTO chat_history (user_id) VALUES ($1)", user_id)

            if messages is not None:
                messages_json = json.dumps(messages)
                await conn.execute("UPDATE chat_history SET messages = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2", messages_json, user_id)
            
            if model_name is not None:
                await conn.execute("UPDATE chat_history SET model_name = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2", model_name, user_id)

            if image_model is not None:
                await conn.execute("UPDATE chat_history SET image_model = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2", image_model, user_id)
            
            if character is not None:
                await conn.execute("UPDATE chat_history SET character = $1, updated_at = CURRENT_TIMESTAMP WHERE user_id = $2", character, user_id)
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

async def add_reminder(user_id: int, text: str, remind_at):
    """Добавляет напоминание в БД."""
    if not _pool: return
    try:
        import datetime
        # Если пришла строка, конвертируем в datetime
        if isinstance(remind_at, str):
            from dateutil import parser
            remind_at = parser.parse(remind_at)

        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO reminders (user_id, text, remind_at) VALUES ($1, $2, $3)",
                user_id, text, remind_at
            )
    except Exception as e:
        log.error(f"❌ Ошибка добавления напоминания: {e}")

async def get_pending_reminders():
    """Получает напоминания, время которых пришло."""
    if not _pool: return []
    try:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        async with _pool.acquire() as conn:
            return await conn.fetch(
                "SELECT id, user_id, text FROM reminders WHERE status = 'pending' AND remind_at <= $1",
                now
            )
    except Exception as e:
        log.error(f"❌ Ошибка получения напоминаний: {e}")
        return []

async def mark_reminder_done(reminder_id: int):
    """Помечает напоминание как выполненное."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "UPDATE reminders SET status = 'completed' WHERE id = $1",
                reminder_id
            )
    except Exception as e:
        log.error(f"❌ Ошибка обновления статуса напоминания: {e}")

async def add_memory(user_id: int, content: str):
    """Добавляет факт в вечную память."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO user_memories (user_id, content) VALUES ($1, $2)",
                user_id, content
            )
    except Exception as e:
        log.error(f"❌ Ошибка добавления памяти: {e}")

async def get_memories(user_id: int):
    """Получает все факты из вечной памяти пользователя."""
    if not _pool: return []
    try:
        async with _pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT content FROM user_memories WHERE user_id = $1 ORDER BY created_at ASC",
                user_id
            )
            return [row['content'] for row in rows]
    except Exception as e:
        log.error(f"❌ Ошибка получения памяти: {e}")
        return []

async def clear_memories(user_id: int):
    """Очищает всю вечную память пользователя."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM user_memories WHERE user_id = $1",
                user_id
            )
    except Exception as e:
        log.error(f"❌ Ошибка очистки памяти: {e}")

async def get_stats():
    """Получает общую статистику по базе."""
    if not _pool: return {}
    try:
        async with _pool.acquire() as conn:
            users_count = await conn.fetchval("SELECT COUNT(*) FROM chat_history")
            reminders_count = await conn.fetchval("SELECT COUNT(*) FROM reminders")
            memories_count = await conn.fetchval("SELECT COUNT(*) FROM user_memories")
            return {
                "users": users_count,
                "reminders": reminders_count,
                "memories": memories_count
            }
    except Exception as e:
        log.error(f"❌ Ошибка получения статистики: {e}")
        return {}

async def close_db():
    """Закрытие пула."""
    if _pool:
        await _pool.close()
        log.info("🐘 Пул подключений к БД закрыт.")
