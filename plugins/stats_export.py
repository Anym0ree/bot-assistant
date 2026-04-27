import os
import re
import asyncio
import logging
from datetime import datetime, timedelta
from io import BytesIO

import matplotlib.pyplot as plt
import pandas as pd
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from database import db
from states import ExportStates
from keyboards import get_export_menu, get_download_formats_keyboard, get_back_button, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, download_media_with_ytdlp, safe_remove_file, safe_delete_message_obj

def extract_url(text: str) -> str:
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

def plot_stats(data_df, period_name):
    if data_df.empty:
        return None
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    fig.suptitle(f'📊 Ваша статистика за {period_name}', fontsize=16)
    if 'sleep_hours' in data_df.columns:
        ax = axes[0, 0]
        ax.bar(data_df['date'], data_df['sleep_hours'], color='skyblue')
        ax.set_title('🛌 Длительность сна (часы)')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Часы')
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    if 'energy' in data_df.columns:
        ax = axes[0, 1]
        ax.plot(data_df['date'], data_df['energy'], marker='o', color='green')
        ax.set_title('⚡️ Энергия (1-10)')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Уровень')
        ax.set_ylim(0, 10)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    if 'stress' in data_df.columns:
        ax = axes[1, 0]
        ax.plot(data_df['date'], data_df['stress'], marker='o', color='red')
        ax.set_title('😰 Стресс (1-10)')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Уровень')
        ax.set_ylim(0, 10)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    if 'day_score' in data_df.columns:
        ax = axes[1, 1]
        ax.bar(data_df['date'], data_df['day_score'], color='orange')
        ax.set_title('📝 Оценка дня (1-10)')
        ax.set_xlabel('Дата')
        ax.set_ylabel('Оценка')
        ax.set_ylim(0, 10)
        plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')
    plt.tight_layout(rect=[0, 0, 1, 0.96])
    buf = BytesIO()
    plt.savefig(buf, format='png', dpi=100)
    buf.seek(0)
    plt.close(fig)
    return buf

async def get_stats_data(user_id, days=30):
    """Получает данные за указанное количество дней без использования pool"""
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    start_date = (now_local - timedelta(days=days)).date()
    start_date_str = start_date.strftime("%Y-%m-%d")
    
    # Запросы через прямые вызовы db.conn.execute
    sleep_rows = await db.conn.execute_fetchall(
        "SELECT date, bed_time, wake_time FROM sleep WHERE user_id = ? AND date >= ?",
        (user_id, start_date_str)
    )
    checkin_rows = await db.conn.execute_fetchall(
        "SELECT date, energy, stress FROM checkins WHERE user_id = ? AND date >= ?",
        (user_id, start_date_str)
    )
    summary_rows = await db.conn.execute_fetchall(
        "SELECT date, score FROM day_summary WHERE user_id = ? AND date >= ?",
        (user_id, start_date_str)
    )
    
    sleep_data = []
    for r in sleep_rows:
        bed = datetime.strptime(r[1], "%H:%M")
        wake = datetime.strptime(r[2], "%H:%M")
        hours = (wake - bed).seconds / 3600
        if hours < 0:
            hours += 24
        sleep_data.append({'date': r[0], 'sleep_hours': hours})
    checkin_data = [{'date': r[0], 'energy': r[1], 'stress': r[2]} for r in checkin_rows]
    summary_data = [{'date': r[0], 'day_score': r[1]} for r in summary_rows]
    
    df_sleep = pd.DataFrame(sleep_data)
    df_check = pd.DataFrame(checkin_data)
    df_sum = pd.DataFrame(summary_data)
    
    all_dates = set()
    for df in [df_sleep, df_check, df_sum]:
        if not df.empty:
            all_dates.update(df['date'])
    if not all_dates:
        return pd.DataFrame()
    df_all = pd.DataFrame(sorted(all_dates), columns=['date'])
    df_all = df_all.sort_values('date')
    if not df_sleep.empty:
        df_all = df_all.merge(df_sleep, on='date', how='left')
    else:
        df_all['sleep_hours'] = None
    if not df_check.empty:
        df_all = df_all.merge(df_check, on='date', how='left')
    else:
        df_all['energy'] = None
        df_all['stress'] = None
    if not df_sum.empty:
        df_all = df_all.merge(df_sum, on='date', how='left')
    else:
        df_all['day_score'] = None
    return df_all

async def stats_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        InlineKeyboardButton("📅 Неделя", callback_data="stats_week"),
        InlineKeyboardButton("📆 Месяц", callback_data="stats_month"),
        InlineKeyboardButton("📄 Текстовая статистика", callback_data="stats_text"),
        InlineKeyboardButton("⬅️ Назад", callback_data="stats_back")
    )
    await message.answer("📊 Выбери период для графиков или текстовую статистику:", reply_markup=keyboard)

async def stats_callback_handler(callback_query: types.CallbackQuery):
    user_id = callback_query.from_user.id
    data = callback_query.data
    if data == "stats_back":
        await callback_query.message.delete()
        await callback_query.message.answer("Главное меню", reply_markup=get_main_menu())
        await callback_query.answer()
        return
    if data == "stats_text":
        text = await db.get_stats(user_id)
        await callback_query.message.answer(text, reply_markup=get_main_menu())
        await callback_query.message.delete()
        await callback_query.answer()
        return
    if data == "stats_week":
        days = 7
        period_name = "неделю"
    elif data == "stats_month":
        days = 30
        period_name = "месяц"
    else:
        await callback_query.answer("Неизвестный выбор")
        return
    await callback_query.answer("Загружаю данные...")
    df = await get_stats_data(user_id, days=days)
    if df.empty:
        await callback_query.message.answer("❌ Недостаточно данных для построения графика за этот период.")
        return
    avg_sleep = df['sleep_hours'].mean()
    avg_energy = df['energy'].mean()
    avg_stress = df['stress'].mean()
    avg_score = df['day_score'].mean()
    text_analysis = (
        f"📈 *Анализ за {period_name}*:\n"
        f"🛌 Сон: {avg_sleep:.1f} часов в среднем\n"
        f"⚡️ Энергия: {avg_energy:.1f}/10\n"
        f"😰 Стресс: {avg_stress:.1f}/10\n"
        f"📝 Оценка дня: {avg_score:.1f}/10\n"
    )
    if avg_sleep < 7:
        text_analysis += "😴 Ты мало спишь. Постарайся спать не менее 7-8 часов.\n"
    if avg_energy < 5:
        text_analysis += "🔋 Энергия низкая. Возможно, нужен отдых или пересмотр питания.\n"
    if avg_stress > 6:
        text_analysis += "🧘‍♂️ Уровень стресса высок. Попробуй техники релаксации.\n"
    buf = plot_stats(df, period_name)
    if buf:
        await callback_query.message.answer_photo(photo=buf, caption=text_analysis, parse_mode="Markdown")
    else:
        await callback_query.message.answer(text_analysis, parse_mode="Markdown")
    await callback_query.message.delete()
    await callback_query.answer()

async def stats(message: types.Message):
    await stats_menu(message)

async def export_menu(message: types.Message):
    await message.answer("📤 Выбери, что хочешь экспортировать:", reply_markup=get_export_menu())

async def export_all_data(message: types.Message):
    file_path = await db.export_all(message.from_user.id)
    with open(file_path, 'rb') as f:
        await message.answer_document(f, caption="📁 Вот все твои данные")
    await message.answer("Главное меню", reply_markup=get_main_menu())

async def export_any_start(message: types.Message, state: FSMContext):
    await ExportStates.url.set()
    if message.text == "🌐 Другой URL":
        await edit_or_send(state, message.chat.id,
                           "📎 Отправь ссылку на трек или плейлист (YouTube, SoundCloud, VK, Spotify и др.).\n"
                           "Можно просто скопировать ссылку из приложения — я сам найду её в тексте.",
                           keyboard=get_back_button(), edit=False)
    else:
        await edit_or_send(state, message.chat.id,
                           f"📎 Отправь ссылку на трек или плейлист {message.text}.\n"
                           "Можно просто скопировать ссылку из приложения — я сам найду её в тексте.",
                           keyboard=get_back_button(), edit=False)

async def export_any_url(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await export_menu(message)
        return
    url = extract_url(message.text.strip())
    if not url:
        await send_temp_message(message.chat.id,
                                "❌ Не удалось найти ссылку в сообщении. Пожалуйста, отправь корректный URL (начинающийся с http:// или https://).",
                                4)
        await edit_or_send(state, message.chat.id,
                           "📎 Отправь ссылку на трек или плейлист:",
                           keyboard=get_back_button(), edit=True)
        return
    await state.update_data(url=url)
    await ExportStates.format.set()
    await edit_or_send(state, message.chat.id,
                       "🎵 Выбери формат:",
                       keyboard=get_download_formats_keyboard(source="unknown"),
                       edit=True)

async def export_any_format(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        await export_menu(message)
        return
    fmt = message.text
    allowed_formats = {"MP3 (аудио)", "WAV (аудио)", "MP4 (видео)", "Лучшее качество (оригинал)"}
    if fmt not in allowed_formats:
        await send_temp_message(message.chat.id, "❌ Выбери формат только кнопками.", 3)
        await edit_or_send(state, message.chat.id, "Выбери формат:", keyboard=get_download_formats_keyboard(), edit=True)
        return
    data = await state.get_data()
    url = data.get('url')
    if not url:
        await safe_finish(state, message, "Ошибка: ссылка не найдена. Начни заново.")
        return
    await delete_dialog_message(state)
    await state.finish()
    progress_msg = await message.answer("⏳ Начинаю скачивание...")
    filename = None
    try:
        filename, title = await download_media_with_ytdlp(url, fmt, progress_msg)
        if not filename or not os.path.exists(filename):
            raise Exception("Скачанный файл не найден после завершения загрузки.")
        await message.bot.edit_message_text("✅ Скачивание завершено! Отправляю файл...",
                                            chat_id=progress_msg.chat.id,
                                            message_id=progress_msg.message_id)
        file_size = os.path.getsize(filename)
        if file_size > 50 * 1024 * 1024:
            raise Exception("Файл слишком большой для отправки в Telegram (более 50 MB).")
        with open(filename, 'rb') as f:
            await message.answer_document(f, caption=f"🎵 {title}")
    except Exception as e:
        logging.error(f"Ошибка загрузки: {e}")
        error_msg = str(e)
        if "Sign in to confirm you’re not a bot" in error_msg:
            await message.bot.edit_message_text(
                "❌ YouTube временно блокирует запросы. Попробуйте:\n"
                "• Подождать 10–15 минут\n"
                "• Использовать другой источник (SoundCloud, VK)\n"
                "• Скачать позже, когда нагрузка снизится",
                chat_id=progress_msg.chat.id, message_id=progress_msg.message_id
            )
        else:
            await message.bot.edit_message_text(
                f"❌ Ошибка: {error_msg[:200]}\nПроверь ссылку и попробуй снова.",
                chat_id=progress_msg.chat.id, message_id=progress_msg.message_id
            )
        await asyncio.sleep(3)
        await safe_delete_message_obj(progress_msg)
    finally:
        safe_remove_file(filename)
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(stats, text="📊 Статистика", state="*")
    dp.register_message_handler(export_menu, text="📤 Экспорт", state="*")
    dp.register_message_handler(export_all_data, text="📥 Экспорт всех данных", state="*")
    dp.register_message_handler(export_any_start, text=["🎵 SoundCloud", "📌 Pinterest (видео)", "🌐 Другой URL"], state="*")
    dp.register_message_handler(export_any_url, state=ExportStates.url)
    dp.register_message_handler(export_any_format, state=ExportStates.format)
    dp.register_callback_query_handler(stats_callback_handler, lambda c: c.data.startswith('stats_'))