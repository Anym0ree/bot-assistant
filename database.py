import json
import os
import logging
from datetime import datetime, timedelta
import asyncpg
from config import DATABASE_URL

logging.basicConfig(level=logging.INFO)

class Database:
    def __init__(self):
        self.pool = None

    async def init_pool(self):
        self.pool = await asyncpg.create_pool(
            DATABASE_URL,
            min_size=1,
            max_size=10,
            command_timeout=60
        )
        await self._init_tables()
        await self._migrate_reminder_settings()
        logging.info("✅ PostgreSQL подключён!")

    async def close(self):
        if self.pool:
            await self.pool.close()

    async def _init_tables(self):
        async with self.pool.acquire() as conn:
            # users
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    timezone_offset INTEGER DEFAULT 0,
                    created_at TIMESTAMP,
                    age INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    weight INTEGER DEFAULT 0,
                    city TEXT,
                    nickname TEXT,
                    status_text TEXT DEFAULT '',
                    current_track TEXT,
                    xp INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1
                )
            ''')
            # sleep
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS sleep (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    date TEXT,
                    timestamp TIMESTAMP,
                    bed_time TEXT,
                    wake_time TEXT,
                    quality INTEGER,
                    woke_night INTEGER,
                    note TEXT
                )
            ''')
            # checkins
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS checkins (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    date TEXT,
                    time TEXT,
                    timestamp TIMESTAMP,
                    time_slot TEXT,
                    energy INTEGER,
                    stress INTEGER,
                    emotions TEXT,
                    note TEXT
                )
            ''')
            # day_summary
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS day_summary (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    date TEXT,
                    timestamp TIMESTAMP,
                    score INTEGER,
                    best TEXT,
                    worst TEXT,
                    gratitude TEXT,
                    note TEXT
                )
            ''')
            # food
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS food (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    date TEXT,
                    time TEXT,
                    timestamp TIMESTAMP,
                    meal_type TEXT,
                    food_text TEXT
                )
            ''')
            # drinks
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS drinks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    date TEXT,
                    time TEXT,
                    timestamp TIMESTAMP,
                    drink_type TEXT,
                    amount TEXT
                )
            ''')
            # notes (старая таблица для простых заметок)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    text TEXT,
                    date TEXT,
                    time TEXT,
                    timestamp TIMESTAMP
                )
            ''')
            # notes_v2 (новая таблица с разделами - не используем пока)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS notes_v2 (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    section_id INTEGER NOT NULL,
                    title TEXT,
                    content TEXT,
                    created_at TIMESTAMP DEFAULT NOW(),
                    updated_at TIMESTAMP
                )
            ''')
            # note_sections
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS note_sections (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name TEXT NOT NULL,
                    icon TEXT DEFAULT '📝',
                    sort_order INTEGER DEFAULT 0,
                    UNIQUE(user_id, name)
                )
            ''')
            # reminders
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS reminders (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT,
                    text TEXT,
                    date TEXT,
                    time TEXT,
                    advance_type TEXT,
                    parent_id INTEGER,
                    is_custom INTEGER DEFAULT 0,
                    is_active INTEGER DEFAULT 1,
                    created_at TIMESTAMP,
                    remind_utc TIMESTAMP
                )
            ''')
            # user_locations
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_locations (
                    user_id BIGINT PRIMARY KEY,
                    city TEXT,
                    lat REAL,
                    lon REAL,
                    updated_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            # ai_history
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS ai_history (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_history_user_id ON ai_history(user_id)')
            await conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_history_created_at ON ai_history(created_at)')
            # user_reminder_settings
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_reminder_settings (
                    user_id BIGINT NOT NULL,
                    setting_type TEXT NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    times TEXT[] DEFAULT '{}',
                    PRIMARY KEY (user_id, setting_type)
                )
            ''')
            # user_settings
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_settings (
                    user_id BIGINT PRIMARY KEY,
                    ai_enabled INTEGER DEFAULT 1,
                    reminders_enabled INTEGER DEFAULT 1,
                    daily_surveys_enabled INTEGER DEFAULT 1,
                    weekly_report_enabled INTEGER DEFAULT 1,
                    do_not_disturb_start TEXT,
                    do_not_disturb_end TEXT,
                    weather_notify INTEGER DEFAULT 0
                )
            ''')
            # tasks
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS tasks (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT NOT NULL,
                    recurrence_type TEXT,
                    recurrence_interval INTEGER,
                    recurrence_days INTEGER[],
                    start_date DATE,
                    start_time TIME,
                    remind_before_minutes INTEGER DEFAULT 45,
                    next_due TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE,
                    created_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            # task_logs
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS task_logs (
                    id SERIAL PRIMARY KEY,
                    task_id INTEGER,
                    user_id BIGINT,
                    due_date DATE,
                    completed BOOLEAN DEFAULT FALSE,
                    skipped BOOLEAN DEFAULT FALSE,
                    cancelled BOOLEAN DEFAULT FALSE,
                    completed_at TIMESTAMP
                )
            ''')
            logging.info("✅ Все таблицы созданы")

    async def _migrate_reminder_settings(self):
        pass

    # ========== МЕТОДЫ ДЛЯ ЗАДАЧ И РУТИНЫ ==========
    async def add_task(self, user_id, title, task_type, **kwargs):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO tasks (user_id, title, task_type, recurrence_type, recurrence_interval, recurrence_days, start_date, start_time, remind_before_minutes, next_due)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING id
            """, user_id, title, task_type,
                kwargs.get('recurrence_type'),
                kwargs.get('recurrence_interval'),
                kwargs.get('recurrence_days'),
                kwargs.get('start_date'),
                kwargs.get('start_time'),
                kwargs.get('remind_before_minutes', 45),
                kwargs.get('next_due'))
            return row['id'] if row else None

    async def get_upcoming_tasks(self, user_id, limit=20):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id, title, start_date, start_time, remind_before_minutes, next_due
                FROM tasks
                WHERE user_id = $1 AND task_type = 'once' AND is_active = TRUE AND next_due > NOW()
                ORDER BY next_due LIMIT $2
            """, user_id, limit)

    async def complete_task(self, task_id, user_id, completed=True, skipped=False, cancelled=False):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO task_logs (task_id, user_id, due_date, completed, skipped, cancelled, completed_at)
                VALUES ($1, $2, CURRENT_DATE, $3, $4, $5, NOW())
            """, task_id, user_id, completed, skipped, cancelled)
            await conn.execute("UPDATE tasks SET is_active = FALSE WHERE id = $1 AND task_type = 'once'", task_id)

    async def postpone_task(self, task_id, minutes=60):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET next_due = NOW() + ($1 || ' minutes')::INTERVAL WHERE id = $2", str(minutes), task_id)

    async def get_tasks_due_now(self, now_utc):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id, user_id, title, start_date, start_time
                FROM tasks
                WHERE task_type = 'once' AND is_active = TRUE AND next_due <= $1
            """, now_utc)

    async def get_recurring_tasks_by_user(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id, title, recurrence_type, recurrence_interval, recurrence_days, start_time, remind_before_minutes, is_active, created_at
                FROM tasks WHERE user_id = $1 AND task_type = 'recurring' AND is_active = TRUE
            """, user_id)

    async def deactivate_task(self, task_id, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE tasks SET is_active = FALSE WHERE id = $1 AND user_id = $2", task_id, user_id)

    # ========== МЕТОДЫ ДЛЯ ЗАМЕТОК С РАЗДЕЛАМИ ==========
    async def add_section(self, user_id, name, icon='📝'):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                INSERT INTO note_sections (user_id, name, icon) VALUES ($1, $2, $3)
                ON CONFLICT (user_id, name) DO NOTHING
                RETURNING id
            """, user_id, name, icon)
            return row['id'] if row else None

    async def get_sections(self, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT id, name, icon, sort_order FROM note_sections WHERE user_id = $1 ORDER BY sort_order, name", user_id)

    async def get_notes_by_section(self, section_id, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetch("SELECT id, title, content, created_at, updated_at FROM notes_v2 WHERE section_id = $1 AND user_id = $2 ORDER BY created_at DESC", section_id, user_id)

    async def get_note_by_id(self, note_id, user_id):
        async with self.pool.acquire() as conn:
            return await conn.fetchrow("SELECT * FROM notes_v2 WHERE id = $1 AND user_id = $2", note_id, user_id)

    async def add_note_v2(self, user_id, section_id, title=None, content=None):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("INSERT INTO notes_v2 (user_id, section_id, title, content) VALUES ($1, $2, $3, $4) RETURNING id", user_id, section_id, title, content)
            return row['id'] if row else None

    async def update_note(self, note_id, user_id, title=None, content=None):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE notes_v2 SET title = COALESCE($1, title), content = COALESCE($2, content), updated_at = NOW() WHERE id = $3 AND user_id = $4", title, content, note_id, user_id)

    async def delete_note_v2(self, note_id, user_id):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM notes_v2 WHERE id = $1 AND user_id = $2", note_id, user_id)

    # ========== МЕТОДЫ ДЛЯ НАПОМИНАНИЙ ==========
    async def get_reminder_setting(self, user_id, setting_type):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT enabled, times FROM user_reminder_settings WHERE user_id = $1 AND setting_type = $2", user_id, setting_type)
        if row: return {"enabled": row['enabled'], "times": row['times']}
        defaults = {
            "sleep": {"enabled": True, "times": ["22:00"]},
            "checkins": {"enabled": True, "times": ["12:00", "16:00", "20:00"]},
            "summary": {"enabled": True, "times": ["21:00"]},
            "water": {"enabled": True, "times": ["10:00", "14:00", "18:00"]},
            "meals": {"enabled": True, "times": ["09:00", "13:00", "19:00"]}
        }
        return defaults.get(setting_type, {"enabled": False, "times": []})

    async def set_reminder_setting(self, user_id, setting_type, enabled, times):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_reminder_settings (user_id, setting_type, enabled, times)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, setting_type) DO UPDATE SET enabled = $3, times = $4
            """, user_id, setting_type, enabled, times)

    # ========== БАЗОВЫЕ МЕТОДЫ ==========
    async def get_user_profile(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT age, height, weight FROM users WHERE user_id = $1", user_id)
        return {"age": row['age'], "height": row['height'], "weight": row['weight']} if row else {"age": 0, "height": 0, "weight": 0}

    async def update_user_profile(self, user_id, age=None, height=None, weight=None):
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO users (user_id, timezone_offset, created_at) VALUES ($1, 0, NOW()) ON CONFLICT (user_id) DO NOTHING", user_id)
            if age is not None: await conn.execute("UPDATE users SET age = $1 WHERE user_id = $2", age, user_id)
            if height is not None: await conn.execute("UPDATE users SET height = $1 WHERE user_id = $2", height, user_id)
            if weight is not None: await conn.execute("UPDATE users SET weight = $1 WHERE user_id = $2", weight, user_id)

    async def get_user_timezone(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT timezone_offset FROM users WHERE user_id = $1", user_id)
            return row['timezone_offset'] if row else 0

    async def set_user_timezone(self, user_id, timezone_offset):
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO users (user_id, timezone_offset, created_at) VALUES ($1, $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET timezone_offset = $2", user_id, timezone_offset)

    async def get_user_local_datetime(self, user_id):
        offset = await self.get_user_timezone(user_id)
        return datetime.utcnow() + timedelta(hours=offset)

    async def get_user_local_date(self, user_id):
        dt = await self.get_user_local_datetime(user_id)
        return dt.strftime("%Y-%m-%d")

    async def get_user_local_hour(self, user_id):
        dt = await self.get_user_local_datetime(user_id)
        return dt.hour

    async def has_sleep_today(self, user_id):
        today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM sleep WHERE user_id = $1 AND date = $2", user_id, today)
        return row is not None

    async def add_sleep(self, user_id, bed_time, wake_time, quality, woke_night, note=""):
        if await self.has_sleep_today(user_id):
            return False
        date_today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO sleep (user_id, date, timestamp, bed_time, wake_time, quality, woke_night, note) VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)", user_id, date_today, bed_time, wake_time, quality, 1 if woke_night else 0, note)
        return True

    async def add_checkin(self, user_id, time_slot, energy, stress, emotions, note=""):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO checkins (user_id, date, time, timestamp, time_slot, energy, stress, emotions, note) VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8)", user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), time_slot, energy, stress, json.dumps(emotions, ensure_ascii=False), note)
        return True

    async def get_target_date_for_summary(self, user_id):
        local_hour = await self.get_user_local_hour(user_id)
        if local_hour >= 18:
            return await self.get_user_local_date(user_id)
        elif local_hour < 6:
            offset = await self.get_user_timezone(user_id)
            yesterday = datetime.utcnow() - timedelta(days=1)
            return (yesterday + timedelta(hours=offset)).strftime("%Y-%m-%d")
        return None

    async def has_day_summary_for_date(self, user_id, date_str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM day_summary WHERE user_id = $1 AND date = $2", user_id, date_str)
        return row is not None

    async def add_day_summary(self, user_id, score, best, worst, gratitude, note=""):
        target_date = await self.get_target_date_for_summary(user_id)
        if target_date is None or await self.has_day_summary_for_date(user_id, target_date):
            return False
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO day_summary (user_id, date, timestamp, score, best, worst, gratitude, note) VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)", user_id, target_date, score, best, worst, gratitude, note)
        return True

    async def add_food(self, user_id, meal_type, food_text):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO food (user_id, date, time, timestamp, meal_type, food_text) VALUES ($1, $2, $3, NOW(), $4, $5)", user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), meal_type, food_text)
        return True

    async def add_drink(self, user_id, drink_type, amount):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO drinks (user_id, date, time, timestamp, drink_type, amount) VALUES ($1, $2, $3, NOW(), $4, $5)", user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), drink_type, amount)
        return True

    async def add_note(self, user_id, text):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("INSERT INTO notes (user_id, text, date, time, timestamp) VALUES ($1, $2, $3, $4, NOW()) RETURNING id", user_id, text, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"))
            return row['id'] if row else None

    async def get_notes(self, user_id):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, text, date, time FROM notes WHERE user_id = $1 ORDER BY id DESC", user_id)
        return [{"id": r['id'], "text": r['text'], "date": r['date'], "time": r['time']} for r in rows]

    async def delete_note_by_id(self, user_id, note_id):
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM notes WHERE user_id = $1 AND id = $2", user_id, note_id)
            return result != "DELETE 0"

    async def get_stats(self, user_id):
        async with self.pool.acquire() as conn:
            sleep_count = (await conn.fetchval("SELECT COUNT(*) FROM sleep WHERE user_id = $1", user_id)) or 0
            checkins_count = (await conn.fetchval("SELECT COUNT(*) FROM checkins WHERE user_id = $1", user_id)) or 0
        return f"📊 Статистика\n😴 Сон: {sleep_count} записей\n⚡️ Чек-ины: {checkins_count} записей"

    async def get_reminders_due_now(self):
        result = []
        now_utc = datetime.utcnow()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, user_id, text FROM reminders WHERE is_active = 1 AND remind_utc <= $1", now_utc)
            for r in rows: result.append((r['user_id'], {"id": r['id'], "text": r['text']}))
        return result

    async def mark_reminder_sent(self, user_id, reminder_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE reminders SET is_active = 0 WHERE id = $1", reminder_id)

    async def _load_json(self, user_id, filename):
        async with self.pool.acquire() as conn:
            if filename == "checkins.json":
                rows = await conn.fetch("SELECT date, time, energy, stress, emotions, note FROM checkins WHERE user_id = $1", user_id)
                return [{"date": r['date'], "time": r['time'], "energy": r['energy'], "stress": r['stress'], "emotions": json.loads(r['emotions']) if r['emotions'] else [], "note": r['note']} for r in rows]
        return []

    async def get_today_food_and_drinks(self, user_id):
        today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            food_rows = await conn.fetch("SELECT time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2", user_id, today)
            drink_rows = await conn.fetch("SELECT time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2", user_id, today)
        combined = []
        for r in food_rows: combined.append({"type": "🍽 Еда", "time": r['time'], "text": f"{r['meal_type']}: {r['food_text']}"})
        for r in drink_rows: combined.append({"type": "🥤 Напитки", "time": r['time'], "text": f"{r['drink_type']}: {r['amount']}"})
        return sorted(combined, key=lambda x: x['time'])

    async def add_note_simple(self, user_id, text):
        """Добавляет заметку в старую таблицу notes"""
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "INSERT INTO notes (user_id, text, date, time, timestamp) VALUES ($1, $2, $3, $4, NOW()) RETURNING id",
                user_id, text,
                local_dt.strftime("%Y-%m-%d"),
                local_dt.strftime("%H:%M")
            )
            return row['id'] if row else None

db = Database()
