import logging
import aiohttp
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.dispatcher.filters.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

from database import db
from keyboards import get_main_menu
from config import WEATHER_API_KEY
import ai_advisor

logger = logging.getLogger(__name__)

class WeatherState(StatesGroup):
    waiting_for_city = State()

# ========== КЛАВИАТУРЫ ==========
def get_weather_keyboard():
    buttons = [
        [KeyboardButton("📍 Обновить гео"), KeyboardButton("🏙️ Ввести город")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

def get_location_keyboard():
    buttons = [
        [KeyboardButton("📍 Отправить геопозицию", request_location=True)],
        [KeyboardButton("🏙️ Ввести город вручную")],
        [KeyboardButton("⬅️ Назад")]
    ]
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# ========== ПОЛУЧЕНИЕ ПОГОДЫ ==========
async def get_weather_by_city(city):
    if not WEATHER_API_KEY:
        logger.error("WEATHER_API_KEY не задан")
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    logger.error(f"Погода: ошибка {resp.status}")
                    return None
        except Exception as e:
            logger.error(f"Погода: исключение {e}")
            return None

async def get_weather_by_coords(lat, lon):
    if not WEATHER_API_KEY:
        return None
    url = f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&appid={WEATHER_API_KEY}&units=metric&lang=ru"
    headers = {"User-Agent": "Mozilla/5.0"}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get(url, headers=headers, timeout=10) as resp:
                if resp.status == 200:
                    return await resp.json()
                else:
                    return None
        except Exception:
            return None

# ========== AI-СОВЕТ ПО ПОГОДЕ ==========
async def get_ai_weather_advice(user_id, weather_desc, temp):
    """Получает короткий совет по погоде от AI"""
    if not weather_desc or not ai_advisor.ai_advisor:
        return ""
    try:
        prompt = (
            f"Сейчас на улице: {weather_desc}, температура {temp:.0f}°C. "
            f"Дай ОДИН короткий совет (до 15 слов) что надеть или взять с собой. "
            f"Только совет, без приветствий."
        )
        advice = await ai_advisor.ai_advisor.get_advice(user_id, prompt, history=None)
        if advice and len(advice) > 5:
            return advice[:150].strip()
        return ""
    except Exception as e:
        logger.error(f"AI совет по погоде: {e}")
        return ""

# ========== ФОРМАТИРОВАНИЕ ==========
def format_weather(data):
    if not data:
        return "❌ Не удалось получить погоду.", None, None

    city = data.get('name', 'Неизвестно')
    temp = data['main']['temp']
    feels_like = data['main']['feels_like']
    humidity = data['main']['humidity']
    pressure = data['main']['pressure']
    wind = data['wind']['speed']
    desc = data['weather'][0]['description']
    icon_code = data['weather'][0]['icon']

    icon_map = {
        '01d': '☀️', '01n': '🌙', '02d': '⛅', '02n': '☁️',
        '03d': '☁️', '03n': '☁️', '04d': '☁️', '04n': '☁️',
        '09d': '🌧️', '09n': '🌧️', '10d': '🌦️', '10n': '🌧️',
        '11d': '⛈️', '11n': '⛈️', '13d': '❄️', '13n': '❄️',
        '50d': '🌫️', '50n': '🌫️'
    }
    emoji = icon_map.get(icon_code, '🌡️')

    text = (
        f"{emoji} *{city}*\n"
        f"🌡️ {temp:.1f}°C (ощущается как {feels_like:.1f}°C)\n"
        f"🌬️ {desc.capitalize()}\n"
        f"💧 Влажность: {humidity}%\n"
        f"🌪️ Ветер: {wind} м/с\n"
        f"📈 Давление: {pressure} гПа"
    )
    return text, desc, temp

# ========== СОХРАНЕНИЕ ЛОКАЦИИ ==========
async def save_location(user_id, city=None, lat=None, lon=None):
    async with db.pool.acquire() as conn:
        if city:
            await conn.execute(
                "INSERT INTO user_locations (user_id, city, updated_at) VALUES ($1, $2, NOW()) ON CONFLICT (user_id) DO UPDATE SET city = $2, updated_at = NOW()",
                user_id, city
            )
        elif lat and lon:
            await conn.execute(
                "INSERT INTO user_locations (user_id, lat, lon, updated_at) VALUES ($1, $2, $3, NOW()) ON CONFLICT (user_id) DO UPDATE SET lat = $2, lon = $3, updated_at = NOW()",
                user_id, lat, lon
            )

# ========== ОТОБРАЖЕНИЕ ПОГОДЫ ==========
async def show_weather_by_location(user_id, message, lat=None, lon=None, city=None):
    if not city and not lat:
        async with db.pool.acquire() as conn:
            row = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)
            if row:
                city = row['city']
                lat = row['lat']
                lon = row['lon']

    if city:
        data = await get_weather_by_city(city)
    elif lat and lon:
        data = await get_weather_by_coords(lat, lon)
    else:
        await message.answer(
            "📍 Я не знаю твоё местоположение.\n\nОтправь геопозицию или введи город:",
            reply_markup=get_location_keyboard()
        )
        return

    if not data:
        await message.answer(
            "❌ Не удалось получить погоду.\n\nПроверь название города или отправь геопозицию.",
            reply_markup=get_weather_keyboard()
        )
        return

    weather_text, desc, temp = format_weather(data)

    # AI-совет
    advice = await get_ai_weather_advice(user_id, desc, temp)
    if advice:
        weather_text += f"\n\n🧥 *Совет:* {advice}"

    await message.answer(weather_text, reply_markup=get_weather_keyboard(), parse_mode="Markdown")

# ========== ОБРАБОТЧИКИ ==========
async def weather_start(message: types.Message, state: FSMContext):
    """Кнопка 🌤️ Погода в главном меню"""
    await state.finish()
    user_id = message.from_user.id
    async with db.pool.acquire() as conn:
        row = await conn.fetchrow("SELECT city, lat, lon FROM user_locations WHERE user_id = $1", user_id)

    if row and (row['city'] or (row['lat'] and row['lon'])):
        await show_weather_by_location(user_id, message, city=row['city'], lat=row['lat'], lon=row['lon'])
    else:
        await message.answer(
            "📍 Чтобы узнавать погоду, укажи местоположение:\n\n• Отправь геопозицию\n• Или введи название города",
            reply_markup=get_location_keyboard()
        )
        await WeatherState.waiting_for_city.set()

async def refresh_geo(message: types.Message, state: FSMContext):
    """Кнопка 📍 Обновить гео"""
    await state.finish()
    await message.answer(
        "📍 Отправь новую геопозицию или введи город:",
        reply_markup=get_location_keyboard()
    )
    await WeatherState.waiting_for_city.set()

async def enter_city_prompt(message: types.Message, state: FSMContext):
    """Кнопка 🏙️ Ввести город"""
    await state.finish()
    await message.answer("🏙️ Введи название города (например, Москва):", reply_markup=ReplyKeyboardMarkup(resize_keyboard=True).add(KeyboardButton("⬅️ Назад")))
    await WeatherState.waiting_for_city.set()

async def process_city_input(message: types.Message, state: FSMContext):
    """Обработка ввода города"""
    if message.text == "⬅️ Назад":
        await state.finish()
        await message.answer("Главное меню", reply_markup=get_main_menu())
        return
    if message.text == "🏙️ Ввести город вручную":
        await message.answer("Введи название города:")
        return

    city = message.text.strip()
    if not city:
        await message.answer("Введи название города.")
        return

    # Проверяем, существует ли город
    data = await get_weather_by_city(city)
    if not data:
        await message.answer(
            f"❌ Город «{city}» не найден.\n\nПопробуй ещё раз или отправь геопозицию.",
            reply_markup=get_location_keyboard()
        )
        return

    user_id = message.from_user.id
    await save_location(user_id, city=city)
    await state.finish()
    await show_weather_by_location(user_id, message, city=city)

async def handle_location(message: types.Message, state: FSMContext):
    """Обработка геопозиции"""
    if not message.location:
        return

    lat = message.location.latitude
    lon = message.location.longitude
    user_id = message.from_user.id

    await save_location(user_id, lat=lat, lon=lon)
    await state.finish()
    await show_weather_by_location(user_id, message, lat=lat, lon=lon)

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(weather_start, text="🌤️ Погода", state="*")
    dp.register_message_handler(refresh_geo, text="📍 Обновить гео", state="*")
    dp.register_message_handler(enter_city_prompt, text="🏙️ Ввести город", state="*")
    dp.register_message_handler(process_city_input, state=WeatherState.waiting_for_city)
    dp.register_message_handler(handle_location, content_types=types.ContentTypes.LOCATION, state="*")
