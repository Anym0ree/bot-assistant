import logging
from datetime import datetime, timedelta
from database import db

logger = logging.getLogger(__name__)

# Базовые ачивки (коды, названия, описания, иконки)
ACHIEVEMENTS = {
    "first_sleep":      ("Первый сон", "Записать 1 сон", "🌙"),
    "first_checkin":    ("Первый чекин", "Сделать 1 чекин", "⚡"),
    "first_summary":    ("Первый итог", "Подвести итог дня", "📝"),
    "sleep_7_streak":   ("7 дней сна", "Записать сон 7 дней подряд", "😴"),
    "sleep_30_streak":  ("Месяц сна", "Записать сон 30 дней подряд", "🏆"),
    "checkin_7_streak": ("Неделя чекинов", "Делать чекин 7 дней подряд", "📈"),
    "checkin_30_streak":("Месяц чекинов", "Делать чекин 30 дней подряд", "🔥"),
    "perfect_day":      ("Идеальный день", "Сон + чекин + итог за один день", "🌟"),
    "notes_10":         ("10 заметок", "Создать 10 заметок", "📚"),
    "food_50":          ("Гурман", "Записать 50 приёмов пищи", "🍽"),
}

# Ограничения на начисление XP в день
DAILY_LIMITS = {
    "note": 3,
    "food": 3,
    "drink": 3,
}

async def track_action(user_id: int, action: str, bot=None):
    """
    Вызывается после каждого важного действия.
    action: 'sleep', 'checkin', 'summary', 'note', 'food', 'drink'
    Возвращает список строк-уведомлений для пользователя (достижения + повышение уровня).
    Если передан bot, сразу отправляет сообщение пользователю.
    """
    messages = []

    # Начисление XP
    xp_map = {
        "sleep": 10,
        "checkin": 5,
        "summary": 10,
        "note": 2,
        "food": 1,
        "drink": 1,
    }
    xp = xp_map.get(action, 0)

    # Проверка дневных лимитов для заметок и еды
    if action in DAILY_LIMITS:
        today_count = 0
        if action == "note":
            today_count = await db.count_today_notes(user_id)
        elif action == "food":
            today_count = await db.count_today_food(user_id)
        elif action == "drink":
            today_count = await db.count_today_drinks(user_id)

        if today_count >= DAILY_LIMITS[action] + 1:  # +1 потому что действие уже выполнено, но ещё не посчитано? Нужно считать до сохранения.
            # Чтобы избежать гонки, лучше вызывать track_action ДО сохранения в БД.
            # Но для простоты будем считать, что на момент вызова запись уже сделана, и today_count уже включает текущую.
            # Тогда условие: if today_count > DAILY_LIMITS[action]: пропустить XP.
            # Передадим параметр уже после сохранения, значит today_count включает текущую запись.
            # Поэтому ограничение: если today_count > DAILY_LIMITS[action], то XP не даём.
            pass  # Ниже поправим логику

    # Упростим: будем считать, что лимит превышен, если today_count > DAILY_LIMITS[action]
    # Но чтобы это работало, вызов track_action должен быть после сохранения в БД, что правильно.

    if xp > 0:
        # Проверяем лимит
        if action in DAILY_LIMITS:
            count_method = {
                "note": db.count_today_notes,
                "food": db.count_today_food,
                "drink": db.count_today_drinks,
            }[action]
            cnt = await count_method(user_id)
            if cnt > DAILY_LIMITS[action]:
                xp = 0  # превышен лимит, XP не начисляем

    if xp > 0:
        old_data = await db.get_user_xp(user_id)
        old_level = old_data['level']
        await db.add_xp(user_id, xp)
        new_data = await db.get_user_xp(user_id)
        if new_data['level'] > old_level:
            messages.append(f"🎉 Поздравляем! Ты достиг уровня {new_data['level']}!")
            if bot:
                try:
                    await bot.send_message(user_id, f"🎉 Поздравляем! Ты достиг уровня {new_data['level']}!")
                except:
                    pass

    # Проверка достижений
    new_achievements = []
    if action == "sleep":
        new_achievements.append(await db.award_achievement(user_id, "first_sleep"))
        # Проверка серий
        streak = await get_sleep_streak(user_id)
        if streak >= 7:
            new_achievements.append(await db.award_achievement(user_id, "sleep_7_streak"))
        if streak >= 30:
            new_achievements.append(await db.award_achievement(user_id, "sleep_30_streak"))

    elif action == "checkin":
        new_achievements.append(await db.award_achievement(user_id, "first_checkin"))
        streak = await get_checkin_streak(user_id)
        if streak >= 7:
            new_achievements.append(await db.award_achievement(user_id, "checkin_7_streak"))
        if streak >= 30:
            new_achievements.append(await db.award_achievement(user_id, "checkin_30_streak"))

    elif action == "summary":
        new_achievements.append(await db.award_achievement(user_id, "first_summary"))
        # Идеальный день
        if await is_perfect_day(user_id):
            new_achievements.append(await db.award_achievement(user_id, "perfect_day"))

    elif action == "note":
        total = await db.count_today_notes(user_id)  # уже с учётом новой
        # Но нам нужно общее количество за всё время, а не за сегодня.
        # Для ачивки "10 заметок" используем общее количество.
        async with db.pool.acquire() as conn:
            total_all = await conn.fetchval("SELECT COUNT(*) FROM notes WHERE user_id = $1", user_id)
        if total_all >= 10:
            new_achievements.append(await db.award_achievement(user_id, "notes_10"))

    elif action in ("food", "drink"):
        async with db.pool.acquire() as conn:
            total_food = await conn.fetchval("SELECT COUNT(*) FROM food WHERE user_id = $1", user_id)
        if total_food >= 50:
            new_achievements.append(await db.award_achievement(user_id, "food_50"))

    for ach in new_achievements:
        if ach:
            name, icon = ach
            msg = f"🏆 Достижение разблокировано: {icon} *{name}*"
            messages.append(msg)
            if bot:
                try:
                    await bot.send_message(user_id, msg, parse_mode="Markdown")
                except:
                    pass

    return messages


async def get_sleep_streak(user_id: int) -> int:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT date FROM sleep WHERE user_id = $1 ORDER BY date DESC", user_id)
    if not rows:
        return 0
    streak = 1
    prev = datetime.strptime(rows[0]['date'], "%Y-%m-%d")
    for r in rows[1:]:
        cur = datetime.strptime(r['date'], "%Y-%m-%d")
        if (prev - cur).days == 1:
            streak += 1
            prev = cur
        else:
            break
    return streak

async def get_checkin_streak(user_id: int) -> int:
    async with db.pool.acquire() as conn:
        rows = await conn.fetch("SELECT DISTINCT date FROM checkins WHERE user_id = $1 ORDER BY date DESC", user_id)
    if not rows:
        return 0
    streak = 1
    prev = datetime.strptime(rows[0]['date'], "%Y-%m-%d")
    for r in rows[1:]:
        cur = datetime.strptime(r['date'], "%Y-%m-%d")
        if (prev - cur).days == 1:
            streak += 1
            prev = cur
        else:
            break
    return streak

async def is_perfect_day(user_id: int) -> bool:
    today = await db.get_user_local_date(user_id)
    async with db.pool.acquire() as conn:
        sleep = await conn.fetchval("SELECT 1 FROM sleep WHERE user_id = $1 AND date = $2", user_id, today)
        checkin = await conn.fetchval("SELECT 1 FROM checkins WHERE user_id = $1 AND date = $2", user_id, today)
        summary = await conn.fetchval("SELECT 1 FROM day_summary WHERE user_id = $1 AND date = $2", user_id, today)
    return bool(sleep and checkin and summary)
