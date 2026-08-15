import logging
import os
import asyncio
from datetime import datetime, timedelta
import pytz
from dotenv import load_dotenv

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)

import database as db
from scheduler import setup_scheduler

load_dotenv()

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# Conversation states
TITLE, DESC, CATEGORY, DATE, TIME, PRIORITY, REMINDER, RECURRING = range(8)
SET_TZ = 9

TIMEZONES = ["UTC", "US/Eastern", "US/Pacific", "Europe/London", "Europe/Berlin", "Asia/Dubai", "Asia/Kolkata", "Asia/Singapore", "Asia/Tokyo", "Australia/Sydney"]
CATEGORIES = ["💼 Work", "📚 Study", "🏠 Personal", "🏃 Health", "💰 Finance", "⭐ Other"]
PRIORITIES = ["🔴 High", "🟡 Medium", "🟢 Low"]
REMINDERS = [("At task time", 0), ("5 min before", 5), ("15 min before", 15), ("30 min before", 30), ("1 hour before", 60), ("No reminder", -1)]


def get_main_keyboard():
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="btn_add"), InlineKeyboardButton("📋 My Tasks", callback_data="btn_tasks")],
        [InlineKeyboardButton("📅 Today's Plan", callback_data="btn_today"), InlineKeyboardButton("🔔 Reminders", callback_data="btn_reminders")],
        [InlineKeyboardButton("📊 Progress", callback_data="btn_stats"), InlineKeyboardButton("⚙️ Settings", callback_data="btn_settings")]
    ]
    return InlineKeyboardMarkup(keyboard)


async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await db.get_or_create_user(user.id)
    text = (
        f"👋 Welcome, *{user.first_name}*!\n\n"
        f"I am your *Daily Planner Bot* (@CockerelKnaeTanSBS24bot).\n"
        f"Organize tasks, set reminders, and maintain your schedule easily."
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = (
        "📖 *Daily Planner Bot Help*\n\n"
        "*Commands:*\n"
        "/start - Main Menu\n"
        "/help - How to use\n"
        "/add - Create a new task\n"
        "/tasks - View all tasks\n"
        "/today - View today's schedule\n"
        "/upcoming - View pending upcoming tasks\n"
        "/completed - View finished tasks\n"
        "/stats - Productivity metrics\n"
        "/settings - Adjust timezone & preferences\n"
        "/cancel - Abort current form"
    )
    if update.message:
        await update.message.reply_text(text, parse_mode="Markdown")
    else:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=get_main_keyboard())


async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    text = "📝 *Step 1/7: Enter Task Title*\n\nSend a short name for your task (or /cancel):"
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.message.edit_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")
    return TITLE


async def add_title(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data["title"] = update.message.text
    text = "📝 *Step 2/7: Description*\n\nSend a detail/note, or click *Skip*:"
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("Skip ⏩", callback_data="skip_desc")]])
    await update.message.reply_text(text, parse_mode="Markdown", reply_markup=kb)
    return DESC


async def add_desc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        context.user_data["desc"] = update.message.text
    else:
        query = update.callback_query
        await query.answer()
        context.user_data["desc"] = ""

    keyboard = [[InlineKeyboardButton(c, callback_data=f"cat_{c}")] for c in CATEGORIES]
    text = "🏷 *Step 3/7: Choose Category*"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    else:
        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(keyboard))
    return CATEGORY


async def add_category(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    category = query.data.replace("cat_", "")
    context.user_data["category"] = category

    user_data = await db.get_or_create_user(query.from_user.id)
    tz = pytz.timezone(user_data["timezone"])
    today = datetime.now(tz).date()
    tomorrow = today + timedelta(days=1)

    kb = [
        [InlineKeyboardButton(f"Today ({today.strftime('%Y-%m-%d')})", callback_data=f"date_{today.strftime('%Y-%m-%d')}")],
        [InlineKeyboardButton(f"Tomorrow ({tomorrow.strftime('%Y-%m-%d')})", callback_data=f"date_{tomorrow.strftime('%Y-%m-%d')}")],
    ]
    await query.message.edit_text("📅 *Step 4/7: Select Date*\n\nOr reply with format `YYYY-MM-DD`:", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return DATE


async def add_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        query = update.callback_query
        await query.answer()
        date_str = query.data.replace("date_", "")
    else:
        date_str = update.message.text.strip()
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            await update.message.reply_text("❌ Invalid format! Please enter date as `YYYY-MM-DD`:")
            return DATE

    context.user_data["date"] = date_str
    text = "⏰ *Step 5/7: Enter Time*\n\nSend time in 24-hour format `HH:MM` (e.g. `09:00` or `18:30`):"
    
    if update.callback_query:
        await update.callback_query.message.edit_text(text, parse_mode="Markdown")
    else:
        await update.message.reply_text(text, parse_mode="Markdown")
    return TIME


async def add_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    time_str = update.message.text.strip()
    try:
        datetime.strptime(time_str, "%H:%M")
    except ValueError:
        await update.message.reply_text("❌ Invalid time format! Send in 24-hour format `HH:MM` (e.g., `14:30`):")
        return TIME

    context.user_data["time"] = time_str
    kb = [[InlineKeyboardButton(p, callback_data=f"prio_{p}")] for p in PRIORITIES]
    await update.message.reply_text("🔴 *Step 6/7: Select Priority*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return PRIORITY


async def add_priority(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    context.user_data["priority"] = query.data.replace("prio_", "")

    kb = [[InlineKeyboardButton(lbl, callback_data=f"rem_{off}")] for lbl, off in REMINDERS]
    await query.message.edit_text("🔔 *Step 7/7: Set Reminder Notification*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return REMINDER


async def add_reminder_and_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    offset = int(query.data.replace("rem_", ""))
    user_id = query.from_user.id

    data = context.user_data
    user = await db.get_or_create_user(user_id)
    user_tz = pytz.timezone(user["timezone"])

    task_id = await db.add_task(
        user_id=user_id,
        title=data["title"],
        description=data.get("desc", ""),
        category=data.get("category", "⭐ Other"),
        priority=data.get("priority", "🟡 Medium"),
        due_date=data["date"],
        due_time=data["time"],
        recurring="None"
    )

    if offset >= 0:
        naive_dt = datetime.strptime(f"{data['date']} {data['time']}", "%Y-%m-%d %H:%M")
        local_dt = user_tz.localize(naive_dt)
        remind_dt_local = local_dt - timedelta(minutes=offset)
        remind_dt_utc = remind_dt_local.astimezone(pytz.utc)

        if remind_dt_utc > datetime.now(pytz.utc):
            await db.create_reminder(task_id, user_id, offset, remind_dt_utc.isoformat())

    await query.message.edit_text(
        f"✅ *Task Created Successfully!*\n\n"
        f"📌 *{data['title']}*\n"
        f"📅 Date: {data['date']} | ⏰ Time: {data['time']}\n"
        f"🏷 {data['category']} | {data['priority']}",
        parse_mode="Markdown",
        reply_markup=get_main_keyboard()
    )
    return ConversationHandler.END


async def cancel_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = "❌ Operation cancelled."
    if update.message:
        await update.message.reply_text(text, reply_markup=get_main_keyboard())
    elif update.callback_query:
        await update.callback_query.message.edit_text(text, reply_markup=get_main_keyboard())
    return ConversationHandler.END


async def show_today_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_or_create_user(user_id)
    tz = pytz.timezone(user["timezone"])
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    tasks = await db.get_user_tasks(user_id, filter_type="today", date_str=today_str)
    
    if not tasks:
        msg = f"📅 *Today's Plan ({today_str})*\n━━━━━━━━━━━━\n🎉 No tasks scheduled for today!"
        kb = []
    else:
        completed = sum(1 for t in tasks if t["status"] == "completed")
        pending = len(tasks) - completed
        lines = [f"📅 *Today's Plan ({today_str})*\n━━━━━━━━━━━━"]
        kb = []

        for t in tasks:
            status_icon = "✅" if t["status"] == "completed" else t["priority"].split()[0]
            lines.append(f"{status_icon} `{t['due_time']}` — *{t['title']}* ({t['category']})")
            
            btn_txt = f"❌ Delete #{t['id']}" if t['status'] == "completed" else f"✅ Complete #{t['id']}"
            action = f"del_{t['id']}" if t['status'] == "completed" else f"done_{t['id']}"
            kb.append([InlineKeyboardButton(btn_txt, callback_data=action)])

        lines.append("━━━━━━━━━━━━")
        lines.append(f"✅ {completed} completed | ⏳ {pending} pending")
        msg = "\n".join(lines)

    kb.append([InlineKeyboardButton("🔙 Main Menu", callback_data="btn_main")])
    reply_markup = InlineKeyboardMarkup(kb)

    if update.callback_query:
        await update.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)


async def show_tasks(update: Update, context: ContextTypes.DEFAULT_TYPE, filter_type="all"):
    user_id = update.effective_user.id
    user = await db.get_or_create_user(user_id)
    tz = pytz.timezone(user["timezone"])
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    tasks = await db.get_user_tasks(user_id, filter_type=filter_type, date_str=today_str)
    
    title_map = {"all": "📋 All Tasks", "upcoming": "📅 Upcoming Tasks", "completed": "✅ Completed Tasks"}
    header = title_map.get(filter_type, "📋 Tasks")

    if not tasks:
        msg = f"*{header}*\n\nNo tasks found."
        kb = [[InlineKeyboardButton("🔙 Main Menu", callback_data="btn_main")]]
    else:
        lines = [f"*{header}*\n━━━━━━━━━━━━"]
        kb = []
        for t in tasks:
            icon = "✅" if t["status"] == "completed" else t["priority"].split()[0]
            lines.append(f"{icon} *{t['title']}* — `{t['due_date']} {t['due_time']}`")
            if t["status"] == "pending":
                kb.append([
                    InlineKeyboardButton(f"✅ #{t['id']}", callback_data=f"done_{t['id']}"),
                    InlineKeyboardButton(f"🗑 #{t['id']}", callback_data=f"del_{t['id']}")
                ])
            else:
                kb.append([InlineKeyboardButton(f"🗑 Delete #{t['id']}", callback_data=f"del_{t['id']}")])

        kb.append([InlineKeyboardButton("🔙 Main Menu", callback_data="btn_main")])
        msg = "\n".join(lines)

    reply_markup = InlineKeyboardMarkup(kb)
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=reply_markup)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=reply_markup)


async def task_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = query.from_user.id

    if data.startswith("done_"):
        task_id = int(data.replace("done_", ""))
        await db.set_task_status(task_id, user_id, "completed")
        await show_today_plan(update, context)
    elif data.startswith("del_"):
        task_id = int(data.replace("del_", ""))
        await db.delete_task(task_id, user_id)
        await show_today_plan(update, context)


async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_or_create_user(user_id)
    tz = pytz.timezone(user["timezone"])
    today_str = datetime.now(tz).strftime("%Y-%m-%d")

    s = await db.get_user_stats(user_id, today_str)

    msg = (
        "📊 *Your Progress Dashboard*\n"
        "━━━━━━━━━━━━\n"
        f"📅 *Today's Completed:* {s['completed_today']} / {s['total_today']}\n"
        f"🏆 *Total Completed:* {s['completed_total']}\n"
        f"📦 *Total Tasks Created:* {s['total']}\n"
        f"📈 *Completion Rate:* {s['rate']}%\n"
        "━━━━━━━━━━━━"
    )
    kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Main Menu", callback_data="btn_main")]])
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)


async def settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await db.get_or_create_user(user_id)

    msg = (
        "⚙️ *User Settings*\n\n"
        f"🌐 *Timezone:* `{user['timezone']}`\n"
        f"🔴 *Default Priority:* `{user['default_priority']}`\n"
    )
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🌐 Change Timezone", callback_data="btn_change_tz")],
        [InlineKeyboardButton("🔙 Main Menu", callback_data="btn_main")]
    ])
    if update.callback_query:
        await update.callback_query.message.edit_text(msg, parse_mode="Markdown", reply_markup=kb)
    else:
        await update.message.reply_text(msg, parse_mode="Markdown", reply_markup=kb)


async def tz_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    kb = [[InlineKeyboardButton(tz, callback_data=f"settz_{tz}")] for tz in TIMEZONES]
    kb.append([InlineKeyboardButton("❌ Cancel", callback_data="btn_main")])
    await query.message.edit_text("🌐 *Select your Timezone:*", parse_mode="Markdown", reply_markup=InlineKeyboardMarkup(kb))
    return SET_TZ


async def tz_save(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    tz_str = query.data.replace("settz_", "")
    await db.update_user_setting(query.from_user.id, "timezone", tz_str)
    await query.message.edit_text(f"✅ Timezone updated to *{tz_str}*!", parse_mode="Markdown", reply_markup=get_main_keyboard())
    return ConversationHandler.END


async def post_init(application: Application):
    """Initialize database and start background scheduler after event loop starts."""
    await db.init_db()
    scheduler = setup_scheduler(application)
    scheduler.start()
    logger.info("Database initialized and scheduler started.")


def main():
    token = os.getenv("BOT_TOKEN")
    if not token:
        logger.error("BOT_TOKEN environment variable missing!")
        return

    app = Application.builder().token(token).post_init(post_init).build()

    # Conversation Handler for Add Task
    add_conv = ConversationHandler(
        entry_points=[
            CommandHandler("add", add_start),
            CallbackQueryHandler(add_start, pattern="^btn_add$")
        ],
        states={
            TITLE: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_title)],
            DESC: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_desc),
                CallbackQueryHandler(add_desc, pattern="^skip_desc$")
            ],
            CATEGORY: [CallbackQueryHandler(add_category, pattern="^cat_")],
            DATE: [
                CallbackQueryHandler(add_date, pattern="^date_"),
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_date)
            ],
            TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, add_time)],
            PRIORITY: [CallbackQueryHandler(add_priority, pattern="^prio_")],
            REMINDER: [CallbackQueryHandler(add_reminder_and_save, pattern="^rem_")],
        },
        fallbacks=[CommandHandler("cancel", cancel_add)],
        per_message=False
    )

    # Conversation Handler for Timezone Settings
    tz_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(tz_start, pattern="^btn_change_tz$")],
        states={
            SET_TZ: [CallbackQueryHandler(tz_save, pattern="^settz_")]
        },
        fallbacks=[CommandHandler("cancel", cancel_add), CallbackQueryHandler(start_cmd, pattern="^btn_main$")],
        per_message=False
    )

    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("today", show_today_plan))
    app.add_handler(CommandHandler("tasks", lambda u, c: show_tasks(u, c, "all")))
    app.add_handler(CommandHandler("upcoming", lambda u, c: show_tasks(u, c, "upcoming")))
    app.add_handler(CommandHandler("completed", lambda u, c: show_tasks(u, c, "completed")))
    app.add_handler(CommandHandler("stats", show_stats))
    app.add_handler(CommandHandler("settings", settings_menu))

    app.add_handler(add_conv)
    app.add_handler(tz_conv)

    # General navigation callbacks
    app.add_handler(CallbackQueryHandler(start_cmd, pattern="^btn_main$"))
    app.add_handler(CallbackQueryHandler(show_today_plan, pattern="^btn_today$"))
    app.add_handler(CallbackQueryHandler(lambda u, c: show_tasks(u, c, "all"), pattern="^btn_tasks$"))
    app.add_handler(CallbackQueryHandler(show_stats, pattern="^btn_stats$"))
    app.add_handler(CallbackQueryHandler(settings_menu, pattern="^btn_settings$"))
    app.add_handler(CallbackQueryHandler(help_cmd, pattern="^btn_reminders$"))
    app.add_handler(CallbackQueryHandler(task_action_handler, pattern="^(done_|del_)"))

    logger.info("Bot is starting polling...")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
