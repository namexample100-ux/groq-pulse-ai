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
            
            # Таблица для напоминаний (текущая система)
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

            # Таблица для Календаря (события с длительностью)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS calendar_events (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    summary TEXT NOT NULL,
                    description TEXT,
                    start_time TIMESTAMP WITH TIME ZONE NOT NULL,
                    end_time TIMESTAMP WITH TIME ZONE NOT NULL,
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

            # Таблица для Экономиста (подсчет токенов и стоимости)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS token_usage (
                    user_id BIGINT PRIMARY KEY,
                    prompt_tokens BIGINT DEFAULT 0,
                    completion_tokens BIGINT DEFAULT 0,
                    total_cost NUMERIC(10, 6) DEFAULT 0,
                    last_update TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
                );
            """)

            # Таблица для Google OAuth токенов
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS google_tokens (
                    user_id BIGINT PRIMARY KEY,
                    access_token TEXT NOT NULL,
                    refresh_token TEXT,
                    token_uri TEXT,
                    client_id TEXT,
                    client_secret TEXT,
                    scopes TEXT,
                    expiry TIMESTAMP WITH TIME ZONE
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
            total_tokens = await conn.fetchval("SELECT SUM(prompt_tokens + completion_tokens) FROM token_usage") or 0
            total_cost = await conn.fetchval("SELECT SUM(total_cost) FROM token_usage") or 0
            return {
                "users": users_count,
                "reminders": reminders_count,
                "memories": memories_count,
                "tokens": total_tokens,
                "cost": float(total_cost)
            }
    except Exception as e:
        log.error(f"❌ Ошибка получения статистики: {e}")
        return {}

async def update_token_usage(user_id: int, p_tokens: int, c_tokens: int, cost: float):
    """Обновляет статистику использования токенов."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO token_usage (user_id, prompt_tokens, completion_tokens, total_cost)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE SET
                    prompt_tokens = token_usage.prompt_tokens + EXCLUDED.prompt_tokens,
                    completion_tokens = token_usage.completion_tokens + EXCLUDED.completion_tokens,
                    total_cost = token_usage.total_cost + EXCLUDED.total_cost,
                    last_update = CURRENT_TIMESTAMP
            """, user_id, p_tokens, c_tokens, cost)
    except Exception as e:
        log.error(f"❌ Ошибка обновления лимитов: {e}")

async def get_user_usage(user_id: int):
    """Получает статистику пользователя."""
    if not _pool: return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * FROM token_usage WHERE user_id = $1", user_id)
            if row: return dict(row)
            return {"prompt_tokens": 0, "completion_tokens": 0, "total_cost": 0}
    except Exception as e:
        log.error(f"❌ Ошибка получения статистики пользователя: {e}")
        return None

async def save_google_token(user_id: int, token_data: dict):
    """Сохраняет Google OAuth токен в БД."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO google_tokens (user_id, access_token, refresh_token, token_uri, client_id, client_secret, scopes, expiry)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                ON CONFLICT (user_id) DO UPDATE SET
                    access_token = EXCLUDED.access_token,
                    refresh_token = COALESCE(EXCLUDED.refresh_token, google_tokens.refresh_token),
                    expiry = EXCLUDED.expiry
            """, 
            user_id, 
            token_data['token'], 
            token_data.get('refresh_token'),
            token_data.get('token_uri'),
            token_data.get('client_id'),
            token_data.get('client_secret'),
            ",".join(token_data.get('scopes', [])),
            token_data.get('expiry')
            )
    except Exception as e:
        log.error(f"❌ Ошибка сохранения Google токена: {e}")

async def get_google_token(user_id: int):
    # (Оставляем для совместимости, если нужно, но не используем для нового календаря)
    if not _pool: return None
    try:
        async with _pool.acquire() as conn:
            row = await conn.fetchrow("SELECT * google_tokens WHERE user_id = $1", user_id)
            if row: return dict(row)
            return None
    except Exception as e:
        log.error(f"❌ Ошибка получения Google токена: {e}")
        return None

# --- Функции Внутреннего Календаря ---

async def add_calendar_event(user_id: int, summary: str, start_time, end_time, description: str = ""):
    """Добавляет событие в календарь."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO calendar_events (user_id, summary, start_time, end_time, description)
                VALUES ($1, $2, $3, $4, $5)
            """, user_id, summary, start_time, end_time, description)
            return True
    except Exception as e:
        log.error(f"❌ Ошибка добавления события в календарь: {e}")
        return False

async def get_calendar_events(user_id: int, limit: int = 10):
    """Получает предстоящие события пользователя."""
    if not _pool: return []
    try:
        import datetime
        now = datetime.datetime.now(datetime.timezone.utc)
        async with _pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT * FROM calendar_events 
                WHERE user_id = $1 AND start_time >= $2 
                ORDER BY start_time ASC 
                LIMIT $3
            """, user_id, now, limit)
            return [dict(r) for r in rows]
    except Exception as e:
        log.error(f"❌ Ошибка получения событий календаря: {e}")
        return []

async def delete_calendar_event(user_id: int, event_id: int):
    """Удаляет событие."""
    if not _pool: return
    try:
        async with _pool.acquire() as conn:
            await conn.execute("DELETE FROM calendar_events WHERE user_id = $1 AND id = $2", user_id, event_id)
            return True
    except Exception as e:
        log.error(f"❌ Ошибка удаления события: {e}")
        return False

async def close_db():
    """Закрытие пула."""
    if _pool:
        await _pool.close()
        log.info("🐘 Пул подключений к БД закрыт.")
