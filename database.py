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
                    weight INTEGER DEFAULT 0
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
            # notes
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
            # reminders (добавим snooze_until)
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
                    remind_utc TIMESTAMP,
                    snooze_until TIMESTAMP
                )
            ''')

                        # reminders (добавим snooze_until)
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_locations (
                    user_id BIGINT PRIMARY KEY,
                    city TEXT,
                    lat REAL,
                    lon REAL,
                    updated_at TIMESTAMP DEFAULT NOW()
                );
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
            # user_goals
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_goals (
                    user_id BIGINT PRIMARY KEY,
                    goal TEXT,
                    set_at TIMESTAMP DEFAULT NOW()
                )
            ''')
            # achievements
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS achievements (
                    id SERIAL PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    description TEXT,
                    icon TEXT
                )
            ''')
            # user_achievements
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_achievements (
                    user_id BIGINT NOT NULL,
                    achievement_code TEXT NOT NULL,
                    awarded_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (user_id, achievement_code)
                )
            ''')
            # user_stats
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS user_stats (
                    user_id BIGINT PRIMARY KEY,
                    sleep_streak INTEGER DEFAULT 0,
                    checkin_streak INTEGER DEFAULT 0,
                    total_checkins INTEGER DEFAULT 0,
                    total_sleeps INTEGER DEFAULT 0,
                    last_checkin_date DATE,
                    last_sleep_date DATE
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
                    do_not_disturb_end TEXT
                )
            ''')
            # Вставка достижений по умолчанию
            await conn.execute('''
                INSERT INTO achievements (code, name, description, icon)
                VALUES
                ('first_sleep', 'Первый сон', 'Записать первый сон', '🌙'),
                ('first_checkin', 'Первый чек-ин', 'Сделать первый чек-ин', '⚡️'),
                ('sleep_3_days', 'Три ночи подряд', 'Записать сон 3 дня подряд', '😴'),
                ('sleep_7_days', 'Семь спящих', 'Спать ≥7 часов 7 ночей подряд', '🏆'),
                ('checkin_7_days', 'Неделя чек-инов', 'Делать чек-ин 7 дней подряд', '📊')
                ON CONFLICT (code) DO NOTHING
            ''')
            logging.info("✅ Все таблицы созданы")

    async def _migrate_reminder_settings(self):
        # Можно пропустить, если нет старого JSON
        pass

    # ========== МЕТОДЫ ДЛЯ НАПОМИНАНИЙ ==========
    async def get_reminder_setting(self, user_id: int, setting_type: str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT enabled, times FROM user_reminder_settings WHERE user_id = $1 AND setting_type = $2",
                user_id, setting_type
            )
        if row:
            return {"enabled": row['enabled'], "times": row['times']}
        defaults = {
            "sleep": {"enabled": True, "times": ["09:00"]},
            "checkins": {"enabled": True, "times": ["12:00", "16:00", "20:00"]},
            "summary": {"enabled": True, "times": ["22:30"]},
            "water": {"enabled": True, "times": ["10:00", "14:00", "18:00", "22:00"]},
            "meals": {"enabled": True, "times": ["09:00", "13:00", "19:00"]}
        }
        return defaults.get(setting_type, {"enabled": False, "times": []})

    async def set_reminder_setting(self, user_id: int, setting_type: str, enabled: bool, times: list):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_reminder_settings (user_id, setting_type, enabled, times)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id, setting_type) DO UPDATE
                SET enabled = $3, times = $4
            """, user_id, setting_type, enabled, times)

    # ========== ЦЕЛИ ==========
    async def set_user_goal(self, user_id: int, goal: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO user_goals (user_id, goal, set_at)
                VALUES ($1, $2, NOW())
                ON CONFLICT (user_id) DO UPDATE SET goal = $2, set_at = NOW()
            """, user_id, goal)

    async def get_user_goal(self, user_id: int) -> str:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT goal FROM user_goals WHERE user_id = $1", user_id)
            return row['goal'] if row else ""

    # ========== ДОСТИЖЕНИЯ ==========
    async def award_achievement(self, user_id: int, code: str):
        async with self.pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM user_achievements WHERE user_id = $1 AND achievement_code = $2", user_id, code)
            if exists:
                return None
            await conn.execute("INSERT INTO user_achievements (user_id, achievement_code) VALUES ($1, $2)", user_id, code)
            ach = await conn.fetchrow("SELECT name, icon FROM achievements WHERE code = $1", code)
            return (ach['name'], ach['icon']) if ach else (code, "🏆")

    async def get_user_achievements(self, user_id: int) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT a.code, a.name, a.icon, ua.awarded_at
                FROM user_achievements ua
                JOIN achievements a ON a.code = ua.achievement_code
                WHERE ua.user_id = $1
                ORDER BY ua.awarded_at
            """, user_id)
        return [{"code": r['code'], "name": r['name'], "icon": r['icon'], "awarded_at": r['awarded_at']} for r in rows]

    # ========== СЕРИИ ==========
    async def update_sleep_streak(self, user_id: int, hours_slept: float = None):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT date FROM sleep WHERE user_id = $1 ORDER BY date DESC", user_id)
            if not rows:
                await conn.execute("INSERT INTO user_stats (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", user_id)
                return 0
            streak = 1
            prev_date = rows[0]['date']
            for row in rows[1:]:
                cur_date = row['date']
                if (datetime.strptime(prev_date, "%Y-%m-%d") - datetime.strptime(cur_date, "%Y-%m-%d")).days == 1:
                    streak += 1
                    prev_date = cur_date
                else:
                    break
            total = len(rows)
            await conn.execute("""
                INSERT INTO user_stats (user_id, sleep_streak, total_sleeps, last_sleep_date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET sleep_streak = $2, total_sleeps = $3, last_sleep_date = $4
            """, user_id, streak, total, rows[0]['date'])
            if total == 1:
                await self.award_achievement(user_id, "first_sleep")
            if streak >= 3:
                await self.award_achievement(user_id, "sleep_3_days")
            if streak >= 7 and hours_slept and hours_slept >= 7:
                await self.award_achievement(user_id, "sleep_7_days")
            return streak

    async def update_checkin_streak(self, user_id: int):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT date FROM checkins WHERE user_id = $1 ORDER BY date DESC", user_id)
            if not rows:
                await conn.execute("INSERT INTO user_stats (user_id) VALUES ($1) ON CONFLICT (user_id) DO NOTHING", user_id)
                return 0
            streak = 1
            prev_date = rows[0]['date']
            for row in rows[1:]:
                cur_date = row['date']
                if (datetime.strptime(prev_date, "%Y-%m-%d") - datetime.strptime(cur_date, "%Y-%m-%d")).days == 1:
                    streak += 1
                    prev_date = cur_date
                else:
                    break
            total = len(rows)
            await conn.execute("""
                INSERT INTO user_stats (user_id, checkin_streak, total_checkins, last_checkin_date)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (user_id) DO UPDATE
                SET checkin_streak = $2, total_checkins = $3, last_checkin_date = $4
            """, user_id, streak, total, rows[0]['date'])
            if total == 1:
                await self.award_achievement(user_id, "first_checkin")
            if streak >= 7:
                await self.award_achievement(user_id, "checkin_7_days")
            return streak

    # ========== БАЗОВЫЕ МЕТОДЫ (user, sleep, checkin и т.д.) ==========
    async def get_user_profile(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT age, height, weight FROM users WHERE user_id = $1", user_id)
        if row:
            return {"age": row['age'], "height": row['height'], "weight": row['weight']}
        return {"age": 0, "height": 0, "weight": 0}

    async def update_user_profile(self, user_id, age=None, height=None, weight=None):
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO users (user_id, timezone_offset, created_at) VALUES ($1, 0, NOW()) ON CONFLICT (user_id) DO NOTHING", user_id)
            if age is not None:
                await conn.execute("UPDATE users SET age = $1 WHERE user_id = $2", age, user_id)
            if height is not None:
                await conn.execute("UPDATE users SET height = $1 WHERE user_id = $2", height, user_id)
            if weight is not None:
                await conn.execute("UPDATE users SET weight = $1 WHERE user_id = $2", weight, user_id)

    async def save_ai_message(self, user_id: int, role: str, content: str):
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO ai_history (user_id, role, content, created_at) VALUES ($1, $2, $3, NOW())", user_id, role, content)

    async def get_ai_history(self, user_id: int, limit: int = 10) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT role, content FROM ai_history WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2", user_id, limit)
        return [{"role": r['role'], "content": r['content']} for r in rows[::-1]]

    async def clear_ai_history(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM ai_history WHERE user_id = $1", user_id)

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
        try:
            bed = datetime.strptime(bed_time, "%H:%M")
            wake = datetime.strptime(wake_time, "%H:%M")
            hours = (wake - bed).seconds / 3600
            if hours < 0:
                hours += 24
            await self.update_sleep_streak(user_id, hours)
        except:
            pass
        return True

    async def add_checkin(self, user_id, time_slot, energy, stress, emotions, note=""):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute("INSERT INTO checkins (user_id, date, time, timestamp, time_slot, energy, stress, emotions, note) VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8)", user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), time_slot, energy, stress, json.dumps(emotions, ensure_ascii=False), note)
        await self.update_checkin_streak(user_id)
        return True

    async def get_target_date_for_summary(self, user_id):
        local_hour = await self.get_user_local_hour(user_id)
        if local_hour >= 18:
            return await self.get_user_local_date(user_id)
        elif local_hour < 6:
            offset = await self.get_user_timezone(user_id)
            yesterday = datetime.utcnow() - timedelta(days=1)
            local_yesterday = yesterday + timedelta(hours=offset)
            return local_yesterday.strftime("%Y-%m-%d")
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

    async def add_reminder(self, user_id, text, target_date, target_time, advance_type=None, parent_id=None, is_custom=False, remind_utc=None):
        if remind_utc is None:
            local_dt = await self.get_user_local_datetime(user_id)
            target_local = datetime.strptime(f"{target_date} {target_time}", "%Y-%m-%d %H:%M")
            if target_local < local_dt:
                return None
            tz_offset = await self.get_user_timezone(user_id)
            remind_utc = target_local - timedelta(hours=tz_offset)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("INSERT INTO reminders (user_id, text, date, time, advance_type, parent_id, is_custom, created_at, remind_utc) VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8) RETURNING id", user_id, text, target_date, target_time, advance_type, parent_id, 1 if is_custom else 0, remind_utc)
            return row['id'] if row else None

    async def get_active_reminders(self, user_id):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, text, date, time, advance_type, parent_id, is_custom, remind_utc FROM reminders WHERE user_id = $1 AND is_active = 1 ORDER BY remind_utc", user_id)
        return [{"id": r['id'], "text": r['text'], "date": r['date'], "time": r['time'], "advance_type": r['advance_type'], "parent_id": r['parent_id'], "is_custom": r['is_custom'], "remind_utc": r['remind_utc']} for r in rows]

    async def delete_reminder(self, user_id, reminder_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE reminders SET is_active = 0 WHERE user_id = $1 AND (id = $2 OR parent_id = $2)", user_id, reminder_id)
        return True

    async def get_reminders_due_now(self):
        result = []
        now_utc = datetime.utcnow()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, user_id, text FROM reminders WHERE is_active = 1 AND remind_utc <= $1", now_utc)
            for r in rows:
                result.append((r['user_id'], {"id": r['id'], "text": r['text']}))
        return result

    async def mark_reminder_sent(self, user_id, reminder_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE reminders SET is_active = 0 WHERE id = $1", reminder_id)

    async def get_today_food_and_drinks(self, user_id):
        today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            food_rows = await conn.fetch("SELECT time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2", user_id, today)
            drink_rows = await conn.fetch("SELECT time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2", user_id, today)
        combined = []
        for r in food_rows:
            combined.append({"type": "🍽 Еда", "time": r['time'], "text": f"{r['meal_type']}: {r['food_text']}"})
        for r in drink_rows:
            combined.append({"type": "🥤 Напитки", "time": r['time'], "text": f"{r['drink_type']}: {r['amount']}"})
        combined.sort(key=lambda x: x['time'])
        return combined

    async def get_today_food_and_drinks_with_ids(self, user_id):
        today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            food_rows = await conn.fetch("SELECT id, time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2", user_id, today)
            drink_rows = await conn.fetch("SELECT id, time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2", user_id, today)
        combined = []
        for r in food_rows:
            combined.append({"id": r['id'], "type": "food", "time": r['time'], "text": f"{r['meal_type']}: {r['food_text']}"})
        for r in drink_rows:
            combined.append({"id": r['id'], "type": "drink", "time": r['time'], "text": f"{r['drink_type']}: {r['amount']}"})
        combined.sort(key=lambda x: x['time'])
        return combined

    async def delete_food_by_id(self, user_id, food_id):
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM food WHERE user_id = $1 AND id = $2", user_id, food_id)
            return result != "DELETE 0"

    async def delete_drink_by_id(self, user_id, drink_id):
        async with self.pool.acquire() as conn:
            result = await conn.execute("DELETE FROM drinks WHERE user_id = $1 AND id = $2", user_id, drink_id)
            return result != "DELETE 0"

    async def get_stats(self, user_id):
        async with self.pool.acquire() as conn:
            sleep_count = (await conn.fetchval("SELECT COUNT(*) FROM sleep WHERE user_id = $1", user_id)) or 0
            checkins_count = (await conn.fetchval("SELECT COUNT(*) FROM checkins WHERE user_id = $1", user_id)) or 0
            food_count = (await conn.fetchval("SELECT COUNT(*) FROM food WHERE user_id = $1", user_id)) or 0
            drinks_count = (await conn.fetchval("SELECT COUNT(*) FROM drinks WHERE user_id = $1", user_id)) or 0
            notes_count = (await conn.fetchval("SELECT COUNT(*) FROM notes WHERE user_id = $1", user_id)) or 0
            reminders_count = (await conn.fetchval("SELECT COUNT(*) FROM reminders WHERE user_id = $1 AND is_active = 1", user_id)) or 0
            last_sleep = await conn.fetchrow("SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = $1 ORDER BY id DESC LIMIT 1", user_id)
            last_checkin = await conn.fetchrow("SELECT energy, stress, emotions FROM checkins WHERE user_id = $1 ORDER BY id DESC LIMIT 1", user_id)
        text = f"📊 ТВОЯ СТАТИСТИКА\n\n"
        text += f"😴 Сон: {sleep_count} записей\n"
        text += f"⚡️ Чек-ины: {checkins_count} записей\n"
        text += f"🍽 Еда: {food_count} записей\n"
        text += f"🥤 Напитки: {drinks_count} записей\n"
        text += f"📝 Заметки: {notes_count} записей\n"
        text += f"⏰ Активных напоминаний: {reminders_count}\n"
        if last_sleep:
            text += f"\n😴 Последний сон:\n   Лег: {last_sleep['bed_time']}, встал: {last_sleep['wake_time']}\n   Качество: {last_sleep['quality']}/10"
        if last_checkin:
            emotions = json.loads(last_checkin['emotions']) if last_checkin['emotions'] else []
            emotions_str = ", ".join(emotions) or "не указаны"
            text += f"\n\n⚡️ Последний чек-ин:\n   Энергия: {last_checkin['energy']}/10, стресс: {last_checkin['stress']}/10\n   Эмоции: {emotions_str}"
        return text

    async def export_all(self, user_id):
        export_data = {
            "user_id": user_id,
            "export_date": datetime.utcnow().isoformat(),
            "sleep": [],
            "checkins": [],
            "day_summary": [],
            "food": [],
            "drinks": [],
            "notes": [],
            "reminders": []
        }
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1", user_id)
            for r in rows:
                export_data["sleep"].append({"date": r['date'], "bed_time": r['bed_time'], "wake_time": r['wake_time'], "quality": r['quality'], "woke_night": bool(r['woke_night']), "note": r['note']})
            rows = await conn.fetch("SELECT date, time, time_slot, energy, stress, emotions, note FROM checkins WHERE user_id = $1", user_id)
            for r in rows:
                export_data["checkins"].append({"date": r['date'], "time": r['time'], "time_slot": r['time_slot'], "energy": r['energy'], "stress": r['stress'], "emotions": json.loads(r['emotions']) if r['emotions'] else [], "note": r['note']})
            rows = await conn.fetch("SELECT date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1", user_id)
            for r in rows:
                export_data["day_summary"].append({"date": r['date'], "score": r['score'], "best": r['best'], "worst": r['worst'], "gratitude": r['gratitude'], "note": r['note']})
            rows = await conn.fetch("SELECT date, time, meal_type, food_text FROM food WHERE user_id = $1", user_id)
            for r in rows:
                export_data["food"].append({"date": r['date'], "time": r['time'], "meal_type": r['meal_type'], "food_text": r['food_text']})
            rows = await conn.fetch("SELECT date, time, drink_type, amount FROM drinks WHERE user_id = $1", user_id)
            for r in rows:
                export_data["drinks"].append({"date": r['date'], "time": r['time'], "drink_type": r['drink_type'], "amount": r['amount']})
            rows = await conn.fetch("SELECT text, date, time FROM notes WHERE user_id = $1", user_id)
            for r in rows:
                export_data["notes"].append({"text": r['text'], "date": r['date'], "time": r['time']})
            rows = await conn.fetch("SELECT text, date, time, advance_type, parent_id, is_custom FROM reminders WHERE user_id = $1 AND is_active = 1", user_id)
            for r in rows:
                export_data["reminders"].append({"text": r['text'], "date": r['date'], "time": r['time'], "advance_type": r['advance_type'], "parent_id": r['parent_id'], "is_custom": bool(r['is_custom'])})
        file_path = os.path.join("data", str(user_id), "export_all.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return file_path

    async def _load_json(self, user_id, filename):
        async with self.pool.acquire() as conn:
            if filename == "sleep.json":
                rows = await conn.fetch("SELECT date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1", user_id)
                return [{"date": r['date'], "bed_time": r['bed_time'], "wake_time": r['wake_time'], "quality": r['quality'], "woke_night": bool(r['woke_night']), "note": r['note']} for r in rows]
            elif filename == "checkins.json":
                rows = await conn.fetch("SELECT date, time, energy, stress, emotions, note FROM checkins WHERE user_id = $1", user_id)
                return [{"date": r['date'], "time": r['time'], "energy": r['energy'], "stress": r['stress'], "emotions": json.loads(r['emotions']) if r['emotions'] else [], "note": r['note']} for r in rows]
            elif filename == "day_summary.json":
                rows = await conn.fetch("SELECT date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1", user_id)
                return [{"date": r['date'], "score": r['score'], "best": r['best'], "worst": r['worst'], "gratitude": r['gratitude'], "note": r['note']} for r in rows]
            elif filename == "notes.json":
                rows = await conn.fetch("SELECT id, text, date, time FROM notes WHERE user_id = $1", user_id)
                return [{"id": r['id'], "text": r['text'], "date": r['date'], "time": r['time']} for r in rows]
            elif filename == "reminders.json":
                rows = await conn.fetch("SELECT id, text, date, time, advance_type, parent_id, is_custom, is_active, remind_utc FROM reminders WHERE user_id = $1", user_id)
                return [{"id": r['id'], "text": r['text'], "date": r['date'], "time": r['time'], "advance_type": r['advance_type'], "parent_id": r['parent_id'], "is_custom": bool(r['is_custom']), "is_active": bool(r['is_active']), "remind_utc": r['remind_utc']} for r in rows]
            elif filename == "food.json":
                rows = await conn.fetch("SELECT date, time, meal_type, food_text FROM food WHERE user_id = $1", user_id)
                return [{"date": r['date'], "time": r['time'], "meal_type": r['meal_type'], "food_text": r['food_text']} for r in rows]
            elif filename == "drinks.json":
                rows = await conn.fetch("SELECT date, time, drink_type, amount FROM drinks WHERE user_id = $1", user_id)
                return [{"date": r['date'], "time": r['time'], "drink_type": r['drink_type'], "amount": r['amount']} for r in rows]
        return []

db = Database()
