import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")
WEATHER_API_KEY = os.environ.get("WEATHER_API_KEY")
OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY")
DATABASE_URL = os.environ.get("DATABASE_URL")
DATA_FOLDER = "data"

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не задан")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY не задан")
