import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from telegram.ext import Application
import database as db

logger = logging.getLogger(__name__)


async def check_and_send_reminders(app: Application):
    try:
        reminders = await db.get_pending_reminders()
        for r in reminders:
            text = (
                f"🔔 *REMINDER*\n"
                f"━━━━━━━━━━━━\n"
                f"📌 *Task:* {r['title']}\n"
                f"⏰ *Time:* {r['due_time']}\n"
                f"🎯 *Priority:* {r['priority']}\n"
                f"🏷 *Category:* {r['category']}"
            )
            try:
                await app.bot.send_message(chat_id=r['user_id'], text=text, parse_mode='Markdown')
                await db.mark_reminder_sent(r['reminder_id'])
            except Exception as e:
                logger.error(f"Failed to send reminder {r['reminder_id']} to user {r['user_id']}: {e}")
    except Exception as e:
        logger.error(f"Error checking reminders: {e}")


def setup_scheduler(app: Application) -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler()
    scheduler.add_job(
        check_and_send_reminders,
        'interval',
        seconds=30,
        args=[app],
        id='reminder_job',
        replace_existing=True
    )
    return scheduler
