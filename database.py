import json
import os
import logging
from datetime import datetime, timedelta
import aiosqlite

logging.basicConfig(level=logging.INFO)

class Database:
    def __init__(self, db_path="bot.db"):
        self.db_path = db_path
        self.conn = None

    async def init_pool(self):
        """Инициализация соединения с SQLite (аналог init_pool)"""
        self.conn = await aiosqlite.connect(self.db_path)
        self.conn.row_factory = aiosqlite.Row  # чтобы возвращал словари
        await self._init_tables()
        await self._migrate_reminder_settings()
        logging.info("✅ SQLite подключён!")

    async def close(self):
        if self.conn:
            await self.conn.close()

    async def _init_tables(self):
        """Создаёт все таблицы, если их нет"""
        # Старые таблицы (твои)
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                timezone_offset INTEGER DEFAULT 0,
                created_at TIMESTAMP,
                age INTEGER DEFAULT 0,
                height INTEGER DEFAULT 0,
                weight INTEGER DEFAULT 0
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS sleep (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                timestamp TIMESTAMP,
                bed_time TEXT,
                wake_time TEXT,
                quality INTEGER,
                woke_night INTEGER,
                note TEXT
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS checkins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS day_summary (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                timestamp TIMESTAMP,
                score INTEGER,
                best TEXT,
                worst TEXT,
                gratitude TEXT,
                note TEXT
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS food (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                time TEXT,
                timestamp TIMESTAMP,
                meal_type TEXT,
                food_text TEXT
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS drinks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                date TEXT,
                time TEXT,
                timestamp TIMESTAMP,
                drink_type TEXT,
                amount TEXT
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                text TEXT,
                date TEXT,
                time TEXT,
                timestamp TIMESTAMP
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
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
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS ai_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await self.conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_history_user_id ON ai_history(user_id)')
        await self.conn.execute('CREATE INDEX IF NOT EXISTS idx_ai_history_created_at ON ai_history(created_at)')

        # Новые таблицы (геймификация, цели, настройки напоминаний)
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_reminder_settings (
                user_id INTEGER NOT NULL,
                setting_type TEXT NOT NULL,
                enabled INTEGER DEFAULT 1,
                times TEXT DEFAULT '[]',
                PRIMARY KEY (user_id, setting_type)
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_goals (
                user_id INTEGER PRIMARY KEY,
                goal TEXT,
                set_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS achievements (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                description TEXT,
                icon TEXT
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_achievements (
                user_id INTEGER NOT NULL,
                achievement_code TEXT NOT NULL,
                awarded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (user_id, achievement_code)
            )
        ''')
        await self.conn.execute('''
            CREATE TABLE IF NOT EXISTS user_stats (
                user_id INTEGER PRIMARY KEY,
                sleep_streak INTEGER DEFAULT 0,
                checkin_streak INTEGER DEFAULT 0,
                total_checkins INTEGER DEFAULT 0,
                total_sleeps INTEGER DEFAULT 0,
                last_checkin_date TEXT,
                last_sleep_date TEXT
            )
        ''')

        # Вставка достижений по умолчанию, если таблица пуста
        await self.conn.execute('''
            INSERT OR IGNORE INTO achievements (code, name, description, icon)
            VALUES
            ('first_sleep', 'Первый сон', 'Записать первый сон', '🌙'),
            ('first_checkin', 'Первый чек-ин', 'Сделать первый чек-ин', '⚡️'),
            ('sleep_3_days', 'Три ночи подряд', 'Записать сон 3 дня подряд', '😴'),
            ('sleep_7_days', 'Семь спящих', 'Спать ≥7 часов 7 ночей подряд', '🏆'),
            ('checkin_7_days', 'Неделя чек-инов', 'Делать чек-ин 7 дней подряд', '📊')
        ''')
        await self.conn.commit()

    async def _migrate_reminder_settings(self):
        """Если есть старый JSON-файл с настройками напоминаний – переносим в БД"""
        if not os.path.exists("reminder_settings.json"):
            return
        try:
            with open("reminder_settings.json", "r") as f:
                data = json.load(f)
            for user_id_str, settings in data.items():
                user_id = int(user_id_str)
                # sleep
                sleep = settings.get("sleep", {})
                await self.set_reminder_setting(user_id, "sleep", sleep.get("enabled", True), [sleep.get("time", "09:00")])
                # checkins
                ch = settings.get("checkins", {})
                await self.set_reminder_setting(user_id, "checkins", ch.get("enabled", True), ch.get("times", ["12:00", "16:00", "20:00"]))
                # summary
                summ = settings.get("summary", {})
                await self.set_reminder_setting(user_id, "summary", summ.get("enabled", True), [summ.get("time", "22:30")])
                # water
                water = settings.get("water", {})
                await self.set_reminder_setting(user_id, "water", water.get("enabled", True), water.get("times", ["10:00", "14:00", "18:00", "22:00"]))
                # meals
                meals = settings.get("meals", {})
                await self.set_reminder_setting(user_id, "meals", meals.get("enabled", True), meals.get("times", ["09:00", "13:00", "19:00"]))
            os.rename("reminder_settings.json", "reminder_settings.json.bak")
            logging.info("✅ Настройки напоминаний перенесены из JSON в SQLite")
        except Exception as e:
            logging.error(f"Ошибка миграции reminder_settings: {e}")

    # ========== НОВЫЕ МЕТОДЫ ДЛЯ НАПОМИНАНИЙ (БД) ==========
    async def get_reminder_setting(self, user_id: int, setting_type: str):
        async with self.conn.execute(
            "SELECT enabled, times FROM user_reminder_settings WHERE user_id = ? AND setting_type = ?",
            (user_id, setting_type)
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            enabled = bool(row[0])
            times = json.loads(row[1]) if row[1] else []
            return {"enabled": enabled, "times": times}
        defaults = {
            "sleep": {"enabled": True, "times": ["09:00"]},
            "checkins": {"enabled": True, "times": ["12:00", "16:00", "20:00"]},
            "summary": {"enabled": True, "times": ["22:30"]},
            "water": {"enabled": True, "times": ["10:00", "14:00", "18:00", "22:00"]},
            "meals": {"enabled": True, "times": ["09:00", "13:00", "19:00"]}
        }
        return defaults.get(setting_type, {"enabled": False, "times": []})

    async def set_reminder_setting(self, user_id: int, setting_type: str, enabled: bool, times: list):
        times_json = json.dumps(times)
        await self.conn.execute("""
            INSERT INTO user_reminder_settings (user_id, setting_type, enabled, times)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, setting_type) DO UPDATE SET enabled = ?, times = ?
        """, (user_id, setting_type, 1 if enabled else 0, times_json,
              1 if enabled else 0, times_json))
        await self.conn.commit()

    # ========== ЦЕЛИ ПОЛЬЗОВАТЕЛЯ ==========
    async def set_user_goal(self, user_id: int, goal: str):
        await self.conn.execute("""
            INSERT INTO user_goals (user_id, goal, set_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET goal = ?, set_at = ?
        """, (user_id, goal, datetime.now(), goal, datetime.now()))
        await self.conn.commit()

    async def get_user_goal(self, user_id: int) -> str:
        cursor = await self.conn.execute("SELECT goal FROM user_goals WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else ""

    # ========== ДОСТИЖЕНИЯ ==========
    async def award_achievement(self, user_id: int, code: str):
        """Возвращает (name, icon) если выдано впервые, иначе None"""
        cursor = await self.conn.execute(
            "SELECT 1 FROM user_achievements WHERE user_id = ? AND achievement_code = ?",
            (user_id, code)
        )
        exists = await cursor.fetchone()
        if exists:
            return None
        await self.conn.execute(
            "INSERT INTO user_achievements (user_id, achievement_code) VALUES (?, ?)",
            (user_id, code)
        )
        cursor = await self.conn.execute("SELECT name, icon FROM achievements WHERE code = ?", (code,))
        ach = await cursor.fetchone()
        await self.conn.commit()
        return (ach[0], ach[1]) if ach else (code, "🏆")

    async def get_user_achievements(self, user_id: int) -> list:
        async with self.conn.execute("""
            SELECT a.code, a.name, a.icon, ua.awarded_at
            FROM user_achievements ua
            JOIN achievements a ON a.code = ua.achievement_code
            WHERE ua.user_id = ?
            ORDER BY ua.awarded_at
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [{"code": r[0], "name": r[1], "icon": r[2], "awarded_at": r[3]} for r in rows]

    # ========== СЕРИИ И ПРОГРЕСС ==========
    async def update_sleep_streak(self, user_id: int, hours_slept: float = None):
        cursor = await self.conn.execute(
            "SELECT date FROM sleep WHERE user_id = ? ORDER BY date DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        if not rows:
            await self.conn.execute(
                "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
                (user_id,)
            )
            await self.conn.commit()
            return 0
        streak = 1
        prev_date = datetime.strptime(rows[0][0], "%Y-%m-%d").date()
        for row in rows[1:]:
            cur_date = datetime.strptime(row[0], "%Y-%m-%d").date()
            if (prev_date - cur_date).days == 1:
                streak += 1
                prev_date = cur_date
            else:
                break
        total = len(rows)
        await self.conn.execute("""
            INSERT INTO user_stats (user_id, sleep_streak, total_sleeps, last_sleep_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                sleep_streak = excluded.sleep_streak,
                total_sleeps = excluded.total_sleeps,
                last_sleep_date = excluded.last_sleep_date
        """, (user_id, streak, total, rows[0][0]))
        # Проверка достижений
        if total == 1:
            await self.award_achievement(user_id, "first_sleep")
        if streak >= 3:
            await self.award_achievement(user_id, "sleep_3_days")
        if streak >= 7 and hours_slept and hours_slept >= 7:
            await self.award_achievement(user_id, "sleep_7_days")
        await self.conn.commit()
        return streak

    async def update_checkin_streak(self, user_id: int):
        cursor = await self.conn.execute(
            "SELECT date FROM checkins WHERE user_id = ? ORDER BY date DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        if not rows:
            await self.conn.execute(
                "INSERT OR IGNORE INTO user_stats (user_id) VALUES (?)",
                (user_id,)
            )
            await self.conn.commit()
            return 0
        streak = 1
        prev_date = datetime.strptime(rows[0][0], "%Y-%m-%d").date()
        for row in rows[1:]:
            cur_date = datetime.strptime(row[0], "%Y-%m-%d").date()
            if (prev_date - cur_date).days == 1:
                streak += 1
                prev_date = cur_date
            else:
                break
        total = len(rows)
        await self.conn.execute("""
            INSERT INTO user_stats (user_id, checkin_streak, total_checkins, last_checkin_date)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                checkin_streak = excluded.checkin_streak,
                total_checkins = excluded.total_checkins,
                last_checkin_date = excluded.last_checkin_date
        """, (user_id, streak, total, rows[0][0]))
        if total == 1:
            await self.award_achievement(user_id, "first_checkin")
        if streak >= 7:
            await self.award_achievement(user_id, "checkin_7_days")
        await self.conn.commit()
        return streak

    # ========== СТАРЫЕ МЕТОДЫ (сохранены все, но с SQLite) ==========
    async def get_user_profile(self, user_id):
        cursor = await self.conn.execute(
            "SELECT age, height, weight FROM users WHERE user_id = ?",
            (user_id,)
        )
        row = await cursor.fetchone()
        if row:
            return {"age": row[0], "height": row[1], "weight": row[2]}
        return {"age": 0, "height": 0, "weight": 0}

    async def update_user_profile(self, user_id, age=None, height=None, weight=None):
        if age is not None:
            await self.conn.execute("UPDATE users SET age = ? WHERE user_id = ?", (age, user_id))
        if height is not None:
            await self.conn.execute("UPDATE users SET height = ? WHERE user_id = ?", (height, user_id))
        if weight is not None:
            await self.conn.execute("UPDATE users SET weight = ? WHERE user_id = ?", (weight, user_id))
        await self.conn.commit()

    async def save_ai_message(self, user_id: int, role: str, content: str):
        await self.conn.execute(
            "INSERT INTO ai_history (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, datetime.now())
        )
        await self.conn.commit()

    async def get_ai_history(self, user_id: int, limit: int = 10) -> list:
        cursor = await self.conn.execute(
            "SELECT role, content FROM ai_history WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        rows = await cursor.fetchall()
        rows_rev = list(reversed(rows))
        return [{"role": r[0], "content": r[1]} for r in rows_rev]

    async def clear_ai_history(self, user_id: int):
        await self.conn.execute("DELETE FROM ai_history WHERE user_id = ?", (user_id,))
        await self.conn.commit()

    async def get_user_timezone(self, user_id):
        cursor = await self.conn.execute("SELECT timezone_offset FROM users WHERE user_id = ?", (user_id,))
        row = await cursor.fetchone()
        return row[0] if row else 0

    async def set_user_timezone(self, user_id, timezone_offset):
        await self.conn.execute('''
            INSERT INTO users (user_id, timezone_offset, created_at)
            VALUES (?, ?, COALESCE((SELECT created_at FROM users WHERE user_id = ?), ?))
            ON CONFLICT(user_id) DO UPDATE SET timezone_offset = ?
        ''', (user_id, timezone_offset, user_id, datetime.now(), timezone_offset))
        await self.conn.commit()

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
        cursor = await self.conn.execute(
            "SELECT 1 FROM sleep WHERE user_id = ? AND date = ? LIMIT 1",
            (user_id, today)
        )
        row = await cursor.fetchone()
        return row is not None

    async def add_sleep(self, user_id, bed_time, wake_time, quality, woke_night, note=""):
        if await self.has_sleep_today(user_id):
            return False
        date_today = await self.get_user_local_date(user_id)
        await self.conn.execute('''
            INSERT INTO sleep (user_id, date, timestamp, bed_time, wake_time, quality, woke_night, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, date_today, datetime.now(), bed_time, wake_time, quality, 1 if woke_night else 0, note))
        await self.conn.commit()
        # Рассчёт часов сна для достижения sleep_7_days
        try:
            bed = datetime.strptime(bed_time, "%H:%M")
            wake = datetime.strptime(wake_time, "%H:%M")
            hours = (wake - bed).seconds / 3600
            if hours < 0:
                hours += 24
        except:
            hours = 0
        await self.update_sleep_streak(user_id, hours)
        return True

    async def add_checkin(self, user_id, time_slot, energy, stress, emotions, note=""):
        local_dt = await self.get_user_local_datetime(user_id)
        await self.conn.execute('''
            INSERT INTO checkins (user_id, date, time, timestamp, time_slot, energy, stress, emotions, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"),
              datetime.now(), time_slot, energy, stress, json.dumps(emotions, ensure_ascii=False), note))
        await self.conn.commit()
        await self.update_checkin_streak(user_id)
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
        cursor = await self.conn.execute(
            "SELECT 1 FROM day_summary WHERE user_id = ? AND date = ? LIMIT 1",
            (user_id, date_str)
        )
        row = await cursor.fetchone()
        return row is not None

    async def add_day_summary(self, user_id, score, best, worst, gratitude, note=""):
        target_date = await self.get_target_date_for_summary(user_id)
        if target_date is None or await self.has_day_summary_for_date(user_id, target_date):
            return False
        await self.conn.execute('''
            INSERT INTO day_summary (user_id, date, timestamp, score, best, worst, gratitude, note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (user_id, target_date, datetime.now(), score, best, worst, gratitude, note))
        await self.conn.commit()
        return True

    async def add_food(self, user_id, meal_type, food_text):
        local_dt = await self.get_user_local_datetime(user_id)
        await self.conn.execute('''
            INSERT INTO food (user_id, date, time, timestamp, meal_type, food_text)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"),
              datetime.now(), meal_type, food_text))
        await self.conn.commit()
        return True

    async def add_drink(self, user_id, drink_type, amount):
        local_dt = await self.get_user_local_datetime(user_id)
        await self.conn.execute('''
            INSERT INTO drinks (user_id, date, time, timestamp, drink_type, amount)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (user_id, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"),
              datetime.now(), drink_type, amount))
        await self.conn.commit()
        return True

    async def add_note(self, user_id, text):
        local_dt = await self.get_user_local_datetime(user_id)
        cursor = await self.conn.execute('''
            INSERT INTO notes (user_id, text, date, time, timestamp)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id
        ''', (user_id, text, local_dt.strftime("%Y-%m-%d"), local_dt.strftime("%H:%M"), datetime.now()))
        row = await cursor.fetchone()
        await self.conn.commit()
        return row[0] if row else None

    async def get_notes(self, user_id):
        cursor = await self.conn.execute(
            "SELECT id, text, date, time FROM notes WHERE user_id = ? ORDER BY id DESC",
            (user_id,)
        )
        rows = await cursor.fetchall()
        return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3]} for r in rows]

    async def delete_note_by_id(self, user_id, note_id):
        cursor = await self.conn.execute(
            "DELETE FROM notes WHERE user_id = ? AND id = ?",
            (user_id, note_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def add_reminder(self, user_id, text, target_date, target_time, advance_type=None, parent_id=None, is_custom=False, remind_utc=None):
        if remind_utc is None:
            local_dt = await self.get_user_local_datetime(user_id)
            target_local = datetime.strptime(f"{target_date} {target_time}", "%Y-%m-%d %H:%M")
            if target_local < local_dt:
                return None
            tz_offset = await self.get_user_timezone(user_id)
            remind_utc = target_local - timedelta(hours=tz_offset)
        cursor = await self.conn.execute('''
            INSERT INTO reminders (user_id, text, date, time, advance_type, parent_id, is_custom, created_at, remind_utc)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
        ''', (user_id, text, target_date, target_time, advance_type, parent_id, 1 if is_custom else 0, datetime.now(), remind_utc))
        row = await cursor.fetchone()
        await self.conn.commit()
        return row[0] if row else None

    async def get_active_reminders(self, user_id):
        cursor = await self.conn.execute('''
            SELECT id, text, date, time, advance_type, parent_id, is_custom, remind_utc
            FROM reminders WHERE user_id = ? AND is_active = 1
            ORDER BY remind_utc
        ''', (user_id,))
        rows = await cursor.fetchall()
        return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3],
                 "advance_type": r[4], "parent_id": r[5], "is_custom": r[6], "remind_utc": r[7]} for r in rows]

    async def delete_reminder(self, user_id, reminder_id):
        await self.conn.execute(
            "UPDATE reminders SET is_active = 0 WHERE user_id = ? AND (id = ? OR parent_id = ?)",
            (user_id, reminder_id, reminder_id)
        )
        await self.conn.commit()
        return True

    async def get_reminders_due_now(self):
        result = []
        now_utc = datetime.utcnow()
        cursor = await self.conn.execute('''
            SELECT id, user_id, text FROM reminders
            WHERE is_active = 1 AND remind_utc <= ?
        ''', (now_utc,))
        rows = await cursor.fetchall()
        for r in rows:
            result.append((r[1], {"id": r[0], "text": r[2]}))
        return result

    async def mark_reminder_sent(self, user_id, reminder_id):
        await self.conn.execute("UPDATE reminders SET is_active = 0 WHERE id = ?", (reminder_id,))
        await self.conn.commit()

    async def get_today_food_and_drinks(self, user_id):
        today = await self.get_user_local_date(user_id)
        food_rows = await self.conn.execute_fetchall(
            "SELECT time, meal_type, food_text FROM food WHERE user_id = ? AND date = ?",
            (user_id, today)
        )
        drink_rows = await self.conn.execute_fetchall(
            "SELECT time, drink_type, amount FROM drinks WHERE user_id = ? AND date = ?",
            (user_id, today)
        )
        combined = []
        for r in food_rows:
            combined.append({"type": "🍽 Еда", "time": r[0], "text": f"{r[1]}: {r[2]}"})
        for r in drink_rows:
            combined.append({"type": "🥤 Напитки", "time": r[0], "text": f"{r[1]}: {r[2]}"})
        combined.sort(key=lambda x: x["time"])
        return combined

    async def get_today_food_and_drinks_with_ids(self, user_id):
        today = await self.get_user_local_date(user_id)
        food_rows = await self.conn.execute_fetchall(
            "SELECT id, time, meal_type, food_text FROM food WHERE user_id = ? AND date = ?",
            (user_id, today)
        )
        drink_rows = await self.conn.execute_fetchall(
            "SELECT id, time, drink_type, amount FROM drinks WHERE user_id = ? AND date = ?",
            (user_id, today)
        )
        combined = []
        for r in food_rows:
            combined.append({"id": r[0], "type": "food", "time": r[1], "text": f"{r[2]}: {r[3]}"})
        for r in drink_rows:
            combined.append({"id": r[0], "type": "drink", "time": r[1], "text": f"{r[2]}: {r[3]}"})
        combined.sort(key=lambda x: x["time"])
        return combined

    async def delete_food_by_id(self, user_id, food_id):
        cursor = await self.conn.execute(
            "DELETE FROM food WHERE user_id = ? AND id = ?",
            (user_id, food_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def delete_drink_by_id(self, user_id, drink_id):
        cursor = await self.conn.execute(
            "DELETE FROM drinks WHERE user_id = ? AND id = ?",
            (user_id, drink_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def get_stats(self, user_id):
        # counts
        sleep_count = (await self.conn.execute_fetchone("SELECT COUNT(*) FROM sleep WHERE user_id = ?", (user_id,)))[0] or 0
        checkins_count = (await self.conn.execute_fetchone("SELECT COUNT(*) FROM checkins WHERE user_id = ?", (user_id,)))[0] or 0
        food_count = (await self.conn.execute_fetchone("SELECT COUNT(*) FROM food WHERE user_id = ?", (user_id,)))[0] or 0
        drinks_count = (await self.conn.execute_fetchone("SELECT COUNT(*) FROM drinks WHERE user_id = ?", (user_id,)))[0] or 0
        notes_count = (await self.conn.execute_fetchone("SELECT COUNT(*) FROM notes WHERE user_id = ?", (user_id,)))[0] or 0
        reminders_count = (await self.conn.execute_fetchone("SELECT COUNT(*) FROM reminders WHERE user_id = ? AND is_active = 1", (user_id,)))[0] or 0
        # last sleep
        cursor = await self.conn.execute(
            "SELECT bed_time, wake_time, quality FROM sleep WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        last_sleep = await cursor.fetchone()
        # last checkin
        cursor = await self.conn.execute(
            "SELECT energy, stress, emotions FROM checkins WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,)
        )
        last_checkin = await cursor.fetchone()

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
        # sleep
        cursor = await self.conn.execute("SELECT date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["sleep"].append({"date": r[0], "bed_time": r[1], "wake_time": r[2], "quality": r[3], "woke_night": bool(r[4]), "note": r[5]})
        # checkins
        cursor = await self.conn.execute("SELECT date, time, time_slot, energy, stress, emotions, note FROM checkins WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["checkins"].append({"date": r[0], "time": r[1], "time_slot": r[2], "energy": r[3], "stress": r[4], "emotions": json.loads(r[5]) if r[5] else [], "note": r[6]})
        # day_summary
        cursor = await self.conn.execute("SELECT date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["day_summary"].append({"date": r[0], "score": r[1], "best": r[2], "worst": r[3], "gratitude": r[4], "note": r[5]})
        # food
        cursor = await self.conn.execute("SELECT date, time, meal_type, food_text FROM food WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["food"].append({"date": r[0], "time": r[1], "meal_type": r[2], "food_text": r[3]})
        # drinks
        cursor = await self.conn.execute("SELECT date, time, drink_type, amount FROM drinks WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["drinks"].append({"date": r[0], "time": r[1], "drink_type": r[2], "amount": r[3]})
        # notes
        cursor = await self.conn.execute("SELECT text, date, time FROM notes WHERE user_id = ?", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["notes"].append({"text": r[0], "date": r[1], "time": r[2]})
        # reminders (active only)
        cursor = await self.conn.execute("SELECT text, date, time, advance_type, parent_id, is_custom FROM reminders WHERE user_id = ? AND is_active = 1", (user_id,))
        rows = await cursor.fetchall()
        for r in rows:
            export_data["reminders"].append({"text": r[0], "date": r[1], "time": r[2], "advance_type": r[3], "parent_id": r[4], "is_custom": bool(r[5])})

        file_path = os.path.join("data", str(user_id), "export_all.json")
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, ensure_ascii=False, indent=2)
        return file_path

    # Вспомогательный метод для _load_json (используется в ai_advice.py и др.)
    async def _load_json(self, user_id, filename):
        if filename == "sleep.json":
            cursor = await self.conn.execute("SELECT date, bed_time, wake_time, quality, woke_night, note FROM sleep WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"date": r[0], "bed_time": r[1], "wake_time": r[2], "quality": r[3], "woke_night": bool(r[4]), "note": r[5]} for r in rows]
        elif filename == "checkins.json":
            cursor = await self.conn.execute("SELECT date, time, energy, stress, emotions, note FROM checkins WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"date": r[0], "time": r[1], "energy": r[2], "stress": r[3], "emotions": json.loads(r[4]) if r[4] else [], "note": r[5]} for r in rows]
        elif filename == "day_summary.json":
            cursor = await self.conn.execute("SELECT date, score, best, worst, gratitude, note FROM day_summary WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"date": r[0], "score": r[1], "best": r[2], "worst": r[3], "gratitude": r[4], "note": r[5]} for r in rows]
        elif filename == "notes.json":
            cursor = await self.conn.execute("SELECT id, text, date, time FROM notes WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3]} for r in rows]
        elif filename == "reminders.json":
            cursor = await self.conn.execute("SELECT id, text, date, time, advance_type, parent_id, is_custom, is_active, remind_utc FROM reminders WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"id": r[0], "text": r[1], "date": r[2], "time": r[3], "advance_type": r[4], "parent_id": r[5], "is_custom": bool(r[6]), "is_active": bool(r[7]), "remind_utc": r[8]} for r in rows]
        elif filename == "food.json":
            cursor = await self.conn.execute("SELECT date, time, meal_type, food_text FROM food WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"date": r[0], "time": r[1], "meal_type": r[2], "food_text": r[3]} for r in rows]
        elif filename == "drinks.json":
            cursor = await self.conn.execute("SELECT date, time, drink_type, amount FROM drinks WHERE user_id = ?", (user_id,))
            rows = await cursor.fetchall()
            return [{"date": r[0], "time": r[1], "drink_type": r[2], "amount": r[3]} for r in rows]
        return []

db = Database()
