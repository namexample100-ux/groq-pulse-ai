import logging
import asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
import database as db

log = logging.getLogger(__name__)

class ReminderService:
    def __init__(self, bot=None):
        self.scheduler = AsyncIOScheduler()
        self.bot = bot

    def set_bot(self, bot):
        self.bot = bot

    async def check_reminders(self):
        """Проверяет базу на наличие просроченных напоминаний и отправляет их."""
        if not self.bot:
            return

        reminders = await db.get_pending_reminders()
        for rem in reminders:
            try:
                msg = f"🔔 <b>НАПОМИНАНИЕ!</b>\n\n📝 {rem['text']}"
                await self.bot.send_message(chat_id=rem['user_id'], text=msg)
                await db.mark_reminder_done(rem['id'])
                log.info(f"✅ Напоминание {rem['id']} отправлено пользователю {rem['user_id']}")
            except Exception as e:
                log.error(f"❌ Ошибка отправки напоминания {rem['id']}: {e}")

    def start(self):
        """Запускает планировщик."""
        self.scheduler.add_job(self.check_reminders, 'interval', seconds=60)
        self.scheduler.start()
        log.info("📅 Планировщик напоминаний запущен (интервал 60с).")

reminder_manager = ReminderService()
