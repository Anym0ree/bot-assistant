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
        # Добавляем колонку remind_utc, если её нет
        async with self.pool.acquire() as conn:
            await conn.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='reminders' AND column_name='remind_utc') THEN
                        ALTER TABLE reminders ADD COLUMN remind_utc TIMESTAMP;
                    END IF;
                END $$;
            ''')
            # Добавляем колонки для профиля пользователя
            await conn.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='users' AND column_name='age') THEN
                        ALTER TABLE users ADD COLUMN age INTEGER DEFAULT 0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='users' AND column_name='height') THEN
                        ALTER TABLE users ADD COLUMN height INTEGER DEFAULT 0;
                    END IF;
                    IF NOT EXISTS (SELECT 1 FROM information_schema.columns 
                                   WHERE table_name='users' AND column_name='weight') THEN
                        ALTER TABLE users ADD COLUMN weight INTEGER DEFAULT 0;
                    END IF;
                END $$;
            ''')
        logging.info("✅ PostgreSQL подключён!")

    async def _init_tables(self):
        async with self.pool.acquire() as conn:
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
                    created_at TIMESTAMP
                )
            ''')
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

    # ========== МЕТОДЫ ПРОФИЛЯ ==========
    async def get_user_profile(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT age, height, weight FROM users WHERE user_id = $1",
                user_id
            )
            if row:
                return {"age": row[0], "height": row[1], "weight": row[2]}
            return {"age": 0, "height": 0, "weight": 0}

    async def update_user_profile(self, user_id, age=None, height=None, weight=None):
        async with self.pool.acquire() as conn:
            if age is not None:
                await conn.execute("UPDATE users SET age = $1 WHERE user_id = $2", age, user_id)
            if height is not None:
                await conn.execute("UPDATE users SET height = $1 WHERE user_id = $2", height, user_id)
            if weight is not None:
                await conn.execute("UPDATE users SET weight = $1 WHERE user_id = $2", weight, user_id)

    # ========== МЕТОДЫ ДЛЯ AI ИСТОРИИ ==========
    async def save_ai_message(self, user_id: int, role: str, content: str):
        async with self.pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO ai_history (user_id, role, content, created_at) VALUES ($1, $2, $3, NOW())",
                user_id, role, content
            )

    async def get_ai_history(self, user_id: int, limit: int = 10) -> list:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT role, content FROM ai_history WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2",
                user_id, limit
            )
        return [{"role": row[0], "content": row[1]} for row in reversed(rows)]

    async def clear_ai_history(self, user_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM ai_history WHERE user_id = $1", user_id)

    # ========== ОСТАЛЬНЫЕ МЕТОДЫ (БЕЗ ИЗМЕНЕНИЙ) ==========
    async def get_user_timezone(self, user_id):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT timezone_offset FROM users WHERE user_id = $1", user_id)
            return row[0] if row else 0

    async def set_user_timezone(self, user_id, timezone_offset):
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (user_id, timezone_offset, created_at)
                VALUES ($1, $2, COALESCE((SELECT created_at FROM users WHERE user_id = $1), NOW()))
                ON CONFLICT (user_id) DO UPDATE SET timezone_offset = $2
            ''', user_id, timezone_offset)

    async def get_user_local_datetime(self, user_id):
        offset = await self.get_user_timezone(user_id)
        utc_now = datetime.utcnow()
        return utc_now + timedelta(hours=offset)

    async def get_user_local_date(self, user_id):
        dt = await self.get_user_local_datetime(user_id)
        return dt.strftime("%Y-%m-%d")

    async def get_user_local_hour(self, user_id):
        dt = await self.get_user_local_datetime(user_id)
        return dt.hour

    async def has_sleep_today(self, user_id):
        today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM sleep WHERE user_id = $1 AND date = $2 LIMIT 1", user_id, today)
            return row is not None

    async def add_sleep(self, user_id, bed_time, wake_time, quality, woke_night, note=""):
        if await self.has_sleep_today(user_id):
            return False
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO sleep (user_id, date, timestamp, bed_time, wake_time, quality, woke_night, note)
                VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)
            ''', user_id, await self.get_user_local_date(user_id), bed_time, wake_time, quality, 1 if woke_night else 0, note)
        return True

    async def add_checkin(self, user_id, time_slot, energy, stress, emotions, note=""):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO checkins (user_id, date, time, timestamp, time_slot, energy, stress, emotions, note)
                VALUES ($1, $2, $3, NOW(), $4, $5, $6, $7, $8)
            ''', user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"),
               time_slot, energy, stress, json.dumps(emotions, ensure_ascii=False), note)
        return True

    async def get_target_date_for_summary(self, user_id):
        local_hour = await self.get_user_local_hour(user_id)
        if local_hour >= 18:
            return await self.get_user_local_date(user_id)
        elif local_hour < 6:
            offset = await self.get_user_timezone(user_id)
            utc_now = datetime.utcnow()
            yesterday = utc_now - timedelta(days=1)
            local_yesterday = yesterday + timedelta(hours=offset)
            return local_yesterday.strftime("%Y-%m-%d")
        return None

    async def has_day_summary_for_date(self, user_id, date_str):
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT 1 FROM day_summary WHERE user_id = $1 AND date = $2 LIMIT 1", user_id, date_str)
            return row is not None

    async def add_day_summary(self, user_id, score, best, worst, gratitude, note=""):
        target_date = await self.get_target_date_for_summary(user_id)
        if target_date is None or await self.has_day_summary_for_date(user_id, target_date):
            return False
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO day_summary (user_id, date, timestamp, score, best, worst, gratitude, note)
                VALUES ($1, $2, NOW(), $3, $4, $5, $6, $7)
            ''', user_id, target_date, score, best, worst, gratitude, note)
        return True

    async def add_food(self, user_id, meal_type, food_text):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO food (user_id, date, time, timestamp, meal_type, food_text)
                VALUES ($1, $2, $3, NOW(), $4, $5)
            ''', user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), meal_type, food_text)
        return True

    async def add_drink(self, user_id, drink_type, amount):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO drinks (user_id, date, time, timestamp, drink_type, amount)
                VALUES ($1, $2, $3, NOW(), $4, $5)
            ''', user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), drink_type, amount)
        return True

    async def add_note(self, user_id, text):
        local_dt = await self.get_user_local_datetime(user_id)
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                INSERT INTO notes (user_id, text, date, time, timestamp)
                VALUES ($1, $2, $3, $4, NOW())
                RETURNING id
            ''', user_id, text, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"))
            return row[0]

    async def get_notes(self, user_id):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("SELECT id, text, date, time FROM notes WHERE user_id = $1 ORDER BY id DESC", user_id)
            return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3]} for r in rows]

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
            row = await conn.fetchrow('''
                INSERT INTO reminders (user_id, text, date, time, advance_type, parent_id, is_custom, created_at, remind_utc)
                VALUES ($1, $2, $3, $4, $5, $6, $7, NOW(), $8)
                RETURNING id
            ''', user_id, text, target_date, target_time, advance_type, parent_id, 1 if is_custom else 0, remind_utc)
            return row[0]

    async def get_active_reminders(self, user_id):
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, text, date, time, advance_type, parent_id, is_custom, remind_utc
                FROM reminders WHERE user_id = $1 AND is_active = 1
                ORDER BY remind_utc
            ''', user_id)
            return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3],
                     "advance_type": r[4], "parent_id": r[5], "is_custom": r[6], "remind_utc": r[7]} for r in rows]

    async def delete_reminder(self, user_id, reminder_id):
        async with self.pool.acquire() as conn:
            await conn.execute("UPDATE reminders SET is_active = 0 WHERE user_id = $1 AND (id = $2 OR parent_id = $2)", user_id, reminder_id)
        return True

    async def get_reminders_due_now(self):
        result = []
        now_utc = datetime.utcnow()
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT id, user_id, text FROM reminders
                WHERE is_active = 1 AND remind_utc <= $1
            ''', now_utc)
            for r in rows:
                result.append((r[1], {"id": r[0], "text": r[2]}))
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
            combined.append({"type": "🍽 Еда", "time": r[0], "text": f"{r[1]}: {r[2]}"})
        for r in drink_rows:
            combined.append({"type": "🥤 Напитки", "time": r[0], "text": f"{r[1]}: {r[2]}"})
        combined.sort(key=lambda x: x["time"])
        return combined

    async def get_today_food_and_drinks_with_ids(self, user_id):
        today = await self.get_user_local_date(user_id)
        async with self.pool.acquire() as conn:
            food_rows = await conn.fetch("SELECT id, time, meal_type, food_text FROM food WHERE user_id = $1 AND date = $2", user_id, today)
            drink_rows = await conn.fetch("SELECT id, time, drink_type, amount FROM drinks WHERE user_id = $1 AND date = $2", user_id, today)
        combined = []
        for r in food_rows:
            combined.append({"id": r[0], "type": "food", "time": r[1], "text": f"{r[2]}: {r[3]}"})
        for r in drink_rows:
            combined.append({"id": r[0], "type": "drink", "time": r[1], "text": f"{r[2]}: {r[3]}"})
        combined.sort(key=lambda x: x["time"])
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
            text += f"\n😴 Последний сон:\n   Лег: {last_sleep[0]}, встал: {last_sleep[1]}\n   Качество: {last_sleep[2]}/10"
        if last_checkin:
            emotions = json.loads(last_checkin[2]) if last_checkin[2] else []
            emotions_str = ", ".join(emotions) or "не указаны"
            text += f"\n\n⚡️ Последний чек-ин:\n   Энергия: {last_checkin[0]}/10, стресс: {last_checkin[1]}/10\n   Эмоции: {emotions_str}"
        return text

    async def export_all(self, user_id):
        async with self.pool.acquire() as conn:
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
            rows = await conn.fetch("SELECT date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1", user_id)
            for r in rows:
                export_data["sleep"].append({"date": r[0], "bed_time": r[1], "wake_time": r[2], "quality": r[3], "woke_night": bool(r[4]), "note": r[5]})
            rows = await conn.fetch("SELECT date, time, time_slot, energy, stress, emotions, note FROM checkins WHERE user_id = $1", user_id)
            for r in rows:
                export_data["checkins"].append({"date": r[0], "time": r[1], "time_slot": r[2], "energy": r[3], "stress": r[4], "emotions": json.loads(r[5]) if r[5] else [], "note": r[6]})
            rows = await conn.fetch("SELECT date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1", user_id)
            for r in rows:
                export_data["day_summary"].append({"date": r[0], "score": r[1], "best": r[2], "worst": r[3], "gratitude": r[4], "note": r[5]})
            rows = await conn.fetch("SELECT date, time, meal_type, food_text FROM food WHERE user_id = $1", user_id)
            for r in rows:
                export_data["food"].append({"date": r[0], "time": r[1], "meal_type": r[2], "food_text": r[3]})
            rows = await conn.fetch("SELECT date, time, drink_type, amount FROM drinks WHERE user_id = $1", user_id)
            for r in rows:
                export_data["drinks"].append({"date": r[0], "time": r[1], "drink_type": r[2], "amount": r[3]})
            rows = await conn.fetch("SELECT text, date, time FROM notes WHERE user_id = $1", user_id)
            for r in rows:
                export_data["notes"].append({"text": r[0], "date": r[1], "time": r[2]})
            rows = await conn.fetch("SELECT text, date, time, advance_type, parent_id, is_custom FROM reminders WHERE user_id = $1 AND is_active = 1", user_id)
            for r in rows:
                export_data["reminders"].append({"text": r[0], "date": r[1], "time": r[2], "advance_type": r[3], "parent_id": r[4], "is_custom": bool(r[5])})
        file_path = os.path.join("data", str(user_id), "export_all.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return file_path

    async def _load_json(self, user_id, filename):
        async with self.pool.acquire() as conn:
            if filename == "sleep.json":
                rows = await conn.fetch("SELECT date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = $1", user_id)
                return [{"date": r[0], "bed_time": r[1], "wake_time": r[2], "quality": r[3], "woke_night": bool(r[4]), "note": r[5]} for r in rows]
            elif filename == "checkins.json":
                rows = await conn.fetch("SELECT date, time, energy, stress, emotions, note FROM checkins WHERE user_id = $1", user_id)
                return [{"date": r[0], "time": r[1], "energy": r[2], "stress": r[3], "emotions": json.loads(r[4]) if r[4] else [], "note": r[5]} for r in rows]
            elif filename == "day_summary.json":
                rows = await conn.fetch("SELECT date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = $1", user_id)
                return [{"date": r[0], "score": r[1], "best": r[2], "worst": r[3], "gratitude": r[4], "note": r[5]} for r in rows]
            elif filename == "notes.json":
                rows = await conn.fetch("SELECT id, text, date, time FROM notes WHERE user_id = $1", user_id)
                return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3]} for r in rows]
            elif filename == "reminders.json":
                rows = await conn.fetch("SELECT id, text, date, time, advance_type, parent_id, is_custom, is_active, remind_utc FROM reminders WHERE user_id = $1", user_id)
                return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3], "advance_type": r[4], "parent_id": r[5], "is_custom": bool(r[6]), "is_active": bool(r[7]), "remind_utc": r[8]} for r in rows]
            elif filename == "food.json":
                rows = await conn.fetch("SELECT date, time, meal_type, food_text FROM food WHERE user_id = $1", user_id)
                return [{"date": r[0], "time": r[1], "meal_type": r[2], "food_text": r[3]} for r in rows]
            elif filename == "drinks.json":
                rows = await conn.fetch("SELECT date, time, drink_type, amount FROM drinks WHERE user_id = $1", user_id)
                return [{"date": r[0], "time": r[1], "drink_type": r[2], "amount": r[3]} for r in rows]
        return []

db = Database()
