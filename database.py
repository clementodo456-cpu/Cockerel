import aiosqlite
import os
import logging
from datetime import datetime
import pytz

logger = logging.getLogger(__name__)

DB_PATH = os.getenv("DB_PATH", "planner.db")


async def init_db():
    db_dir = os.path.dirname(DB_PATH)
    if db_dir and not os.path.exists(db_dir):
        os.makedirs(db_dir, exist_ok=True)

    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("PRAGMA foreign_keys = ON;")
        
        # Users table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            timezone TEXT DEFAULT 'UTC',
            default_priority TEXT DEFAULT '🟡 Medium',
            reminders_enabled INTEGER DEFAULT 1
        );
        """)

        # Tasks table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            description TEXT,
            category TEXT DEFAULT '⭐ Other',
            priority TEXT DEFAULT '🟡 Medium',
            due_date TEXT NOT NULL,
            due_time TEXT NOT NULL,
            recurring TEXT DEFAULT 'None',
            status TEXT DEFAULT 'pending',
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)

        # Reminders table
        await db.execute("""
        CREATE TABLE IF NOT EXISTS reminders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id INTEGER NOT NULL,
            user_id INTEGER NOT NULL,
            offset_minutes INTEGER NOT NULL,
            remind_at_utc TEXT NOT NULL,
            sent INTEGER DEFAULT 0,
            FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
            FOREIGN KEY (user_id) REFERENCES users (user_id) ON DELETE CASCADE
        );
        """)
        await db.commit()
    logger.info("Database initialized successfully.")


async def get_or_create_user(user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            user = await cursor.fetchone()
            if not user:
                await db.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
                await db.commit()
                async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor2:
                    user = await cursor2.fetchone()
            return dict(user)


async def update_user_setting(user_id: int, key: str, value):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(f"UPDATE users SET {key} = ? WHERE user_id = ?", (value, user_id))
        await db.commit()


async def add_task(user_id: int, title: str, description: str, category: str, priority: str, due_date: str, due_time: str, recurring: str):
    created_at = datetime.now(pytz.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
        INSERT INTO tasks (user_id, title, description, category, priority, due_date, due_time, recurring, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (user_id, title, description, category, priority, due_date, due_time, recurring, created_at))
        await db.commit()
        return cursor.lastrowid


async def create_reminder(task_id: int, user_id: int, offset_minutes: int, remind_at_utc: str):
    async with aiosqlite.connect(DB_PATH) as db:
        cursor = await db.execute("""
        INSERT INTO reminders (task_id, user_id, offset_minutes, remind_at_utc, sent)
        VALUES (?, ?, ?, ?, 0)
        """, (task_id, user_id, offset_minutes, remind_at_utc))
        await db.commit()
        return cursor.lastrowid


async def get_task_by_id(task_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_user_tasks(user_id: int, filter_type: str = "all", date_str: str = None):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        query = "SELECT * FROM tasks WHERE user_id = ?"
        params = [user_id]

        if filter_type == "today" and date_str:
            query += " AND due_date = ?"
            params.append(date_str)
        elif filter_type == "upcoming" and date_str:
            query += " AND due_date >= ? AND status = 'pending'"
            params.append(date_str)
        elif filter_type == "completed":
            query += " AND status = 'completed'"
        elif filter_type == "pending":
            query += " AND status = 'pending'"

        query += " ORDER OR due_date ASC, due_time ASC"
        query = query.replace("ORDER OR", "ORDER BY")
        
        async with db.execute(query, params) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def set_task_status(task_id: int, user_id: int, status: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE tasks SET status = ? WHERE id = ? AND user_id = ?", (status, task_id, user_id))
        await db.commit()


async def delete_task(task_id: int, user_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("DELETE FROM tasks WHERE id = ? AND user_id = ?", (task_id, user_id))
        await db.commit()


async def get_pending_reminders():
    now_utc = datetime.now(pytz.utc).isoformat()
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
        SELECT r.id as reminder_id, r.user_id, r.task_id, t.title, t.due_time, t.priority, t.category
        FROM reminders r
        JOIN tasks t ON r.task_id = t.id
        WHERE r.sent = 0 AND r.remind_at_utc <= ? AND t.status = 'pending'
        """, (now_utc,)) as cursor:
            rows = await cursor.fetchall()
            return [dict(r) for r in rows]


async def mark_reminder_sent(reminder_id: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE reminders SET sent = 1 WHERE id = ?", (reminder_id,))
        await db.commit()


async def get_user_stats(user_id: int, today_str: str):
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ?", (user_id,)) as c:
            total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND status = 'completed'", (user_id,)) as c:
            completed_total = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND due_date = ? AND status = 'completed'", (user_id, today_str)) as c:
            completed_today = (await c.fetchone())[0]
        async with db.execute("SELECT COUNT(*) FROM tasks WHERE user_id = ? AND due_date = ?", (user_id, today_str)) as c:
            total_today = (await c.fetchone())[0]

        rate = round((completed_total / total * 100)) if total > 0 else 0
        return {
            "total": total,
            "completed_total": completed_total,
            "completed_today": completed_today,
            "total_today": total_today,
            "rate": rate
        }
