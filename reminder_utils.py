from database import db

async def load_reminder_settings(user_id):
    """Возвращает dict в старом формате для совместимости"""
    settings = {}
    for key in ["sleep", "checkins", "summary", "water", "meals"]:
        s = await db.get_reminder_setting(user_id, key)
        if key in ["sleep", "summary"]:
            settings[key] = {"enabled": s["enabled"], "time": s["times"][0] if s["times"] else "09:00"}
        else:
            settings[key] = {"enabled": s["enabled"], "times": s["times"]}
    return settings

async def save_reminder_settings(user_id, settings):
    for key, val in settings.items():
        if key in ["sleep", "summary"]:
            await db.set_reminder_setting(user_id, key, val["enabled"], [val.get("time", "09:00")])
        else:
            await db.set_reminder_setting(user_id, key, val["enabled"], val.get("times", []))

def get_default_reminders():
    return {
        "sleep": {"enabled": True, "time": "09:00"},
        "checkins": {"enabled": True, "times": ["12:00", "16:00", "20:00"]},
        "summary": {"enabled": True, "time": "22:30"},
        "water": {"enabled": True, "times": ["10:00", "14:00", "18:00", "22:00"]},
        "meals": {"enabled": True, "times": ["09:00", "13:00", "19:00"]}
    }
