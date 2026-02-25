import logging
import datetime
import database as db

log = logging.getLogger(__name__)

class CalendarService:
    """Внутренний сервис календаря (на базе БД Supabase)."""

    async def list_events(self, user_id: int, max_results: int = 5):
        """Список ближайших событий из БД."""
        try:
            events = await db.get_calendar_events(user_id, max_results)

            if not events:
                return "📅 На ближайшее время событий не найдено."

            res = "📅 **Ваше расписание (Внутренний календарь):**\n"
            for event in events:
                # Форматируем время
                start = event['start_time'].strftime("%d.%m %H:%M")
                res += f"- **{start}**: {event['summary']}\n"
                if event.get('description'):
                    res += f"  └ ℹ️ {event['description']}\n"
            return res

        except Exception as e:
            log.error(f"Internal Calendar List Error: {e}")
            return f"❌ Ошибка при чтении календаря: {str(e)}"

    async def create_event(self, user_id: int, summary: str, start_time: str, end_time: str = None, description: str = ""):
        """Создает событие в базе данных."""
        try:
            from dateutil import parser
            import datetime
            
            # Парсим время начала
            dt_start = parser.parse(start_time)
            
            # Если время конца не задано, ставим +1 час
            if not end_time:
                dt_end = dt_start + datetime.timedelta(hours=1)
            else:
                dt_end = parser.parse(end_time)

            success = await db.add_calendar_event(
                user_id=user_id,
                summary=summary,
                start_time=dt_start,
                end_time=dt_end,
                description=description
            )
            
            if success:
                start_str = dt_start.strftime("%d.%m в %H:%M")
                return f"✅ Событие «{summary}» успешно добавлено во внутренний календарь на {start_str}!"
            else:
                return "❌ Не удалось сохранить событие в базу данных."

        except Exception as e:
            log.error(f"Internal Calendar Create Error: {e}")
            return f"❌ Ошибка при создании события: {str(e)}"

calendar_service = CalendarService()
