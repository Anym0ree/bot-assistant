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

from database_pg import db
from states import ExportStates
from keyboards import get_export_menu, get_download_formats_keyboard, get_back_button, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, download_media_with_ytdlp, safe_remove_file, safe_delete_message_obj

# ========== Функция извлечения URL ==========
def extract_url(text: str) -> str:
    match = re.search(r'https?://[^\s]+', text)
    return match.group(0) if match else None

# ========== ГРАФИКИ ==========
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
    tz = await db.get_user_timezone(user_id)
    if tz == 0:
        tz = 3
    now_local = datetime.utcnow() + timedelta(hours=tz)
    start_date = (now_local - timedelta(days=days)).date()
    async with db.pool.acquire() as conn:
        sleep_rows = await conn.fetch(
            "SELECT date, bed_time, wake_time FROM sleep WHERE user_id = $1 AND date >= $2",
            user_id, start_date.strftime("%Y-%m-%d")
        )
        checkin_rows = await conn.fetch(
            "SELECT date, energy, stress FROM checkins WHERE user_id = $1 AND date >= $2",
            user_id, start_date.strftime("%Y-%m-%d")
        )
        summary_rows = await conn.fetch(
            "SELECT date, score FROM day_summary WHERE user_id = $1 AND date >= $2",
            user_id, start_date.strftime("%Y-%m-%d")
        )
    sleep_data = []
    for r in sleep_rows:
        bed = datetime.strptime(r['bed_time'], "%H:%M")
        wake = datetime.strptime(r['wake_time'], "%H:%M")
        hours = (wake - bed).seconds / 3600
        if hours < 0:
            hours += 24
        sleep_data.append({'date': r['date'], 'sleep_hours': hours})
    checkin_data = [{'date': r['date'], 'energy': r['energy'], 'stress': r['stress']} for r in checkin_rows]
    summary_data = [{'date': r['date'], 'day_score': r['score']} for r in summary_rows]
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

# ========== СТАТИСТИКА (с обычными кнопками) ==========
async def stats_menu(message: types.Message):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add("📅 Неделя", "📆 Месяц")
    kb.add("📄 Текстовая статистика", "⬅️ Назад")
    await message.answer("📊 Выбери период для графика или текстовую статистику:", reply_markup=kb)

async def stats_week(message: types.Message):
    await send_graph(message, days=7, period_name="неделю")

async def stats_month(message: types.Message):
    await send_graph(message, days=30, period_name="месяц")

async def send_graph(message: types.Message, days: int, period_name: str):
    user_id = message.from_user.id
    await message.answer("⏳ Загружаю данные, строю график...")
    df = await get_stats_data(user_id, days=days)
    if df.empty:
        await message.answer("❌ Недостаточно данных для построения графика за этот период.")
        return
    avg_sleep = df['sleep_hours'].mean()
    avg_energy = df['energy'].mean()
    avg_stress = df['stress'].mean()
    avg_score = df['day_score'].mean()
    text = (
        f"📈 *Анализ за {period_name}*:\n"
        f"🛌 Сон: {avg_sleep:.1f} часов в среднем\n"
        f"⚡️ Энергия: {avg_energy:.1f}/10\n"
        f"😰 Стресс: {avg_stress:.1f}/10\n"
        f"📝 Оценка дня: {avg_score:.1f}/10\n"
    )
    if avg_sleep < 7:
        text += "😴 Ты мало спишь. Постарайся спать не менее 7-8 часов.\n"
    if avg_energy < 5:
        text += "🔋 Энергия низкая. Возможно, нужен отдых или пересмотр питания.\n"
    if avg_stress > 6:
        text += "🧘‍♂️ Уровень стресса высок. Попробуй техники релаксации.\n"
    buf = plot_stats(df, period_name)
    if buf:
        await message.answer_photo(photo=buf, caption=text, parse_mode="Markdown")
    else:
        await message.answer(text, parse_mode="Markdown")

async def stats_text(message: types.Message):
    user_id = message.from_user.id
    old_stats = await db.get_stats(user_id)
    async with db.pool.acquire() as conn:
        avg_score = await conn.fetchval("SELECT AVG(score) FROM day_summary WHERE user_id = $1", user_id)
        total_summaries = await conn.fetchval("SELECT COUNT(*) FROM day_summary WHERE user_id = $1", user_id)
        best_day = await conn.fetchrow(
            "SELECT date, score FROM day_summary WHERE user_id = $1 ORDER BY score DESC LIMIT 1",
            user_id
        )
        worst_day = await conn.fetchrow(
            "SELECT date, score FROM day_summary WHERE user_id = $1 ORDER BY score ASC LIMIT 1",
            user_id
        )
    summary_stats = "\n📝 *Итоги дня:*\n"
    if total_summaries and total_summaries > 0:
        summary_stats += f"• Всего подведено итогов: {total_summaries}\n"
        if avg_score:
            summary_stats += f"• Средняя оценка дня: {avg_score:.1f}/10\n"
        if best_day:
            summary_stats += f"• Лучший день: {best_day['date']} (оценка {best_day['score']}/10)\n"
        if worst_day:
            summary_stats += f"• Худший день: {worst_day['date']} (оценка {worst_day['score']}/10)\n"
    else:
        summary_stats += "• Нет ни одного подведённого итога дня.\n"
    full_stats = old_stats + summary_stats
    await message.answer(full_stats, parse_mode="Markdown", reply_markup=get_main_menu())

async def back_to_main(message: types.Message):
    await message.answer("Главное меню", reply_markup=get_main_menu())

# ========== ЭКСПОРТ (без изменений) ==========
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
                           get_back_button(), edit=False)
    else:
        await edit_or_send(state, message.chat.id,
                           f"📎 Отправь ссылку на трек или плейлист {message.text}.\n"
                           "Можно просто скопировать ссылку из приложения — я сам найду её в тексте.",
                           get_back_button(), edit=False)

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
                           get_back_button(), edit=True)
        return
    await state.update_data(url=url)
    await ExportStates.format.set()
    await edit_or_send(state, message.chat.id,
                       "🎵 Выбери формат:",
                       reply_markup=get_download_formats_keyboard(source="unknown"),
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
        await edit_or_send(state, message.chat.id, "Выбери формат:", get_download_formats_keyboard(), edit=True)
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

# ========== РЕГИСТРАЦИЯ ==========
def register(dp: Dispatcher):
    dp.register_message_handler(stats_menu, text="📊 Статистика", state="*")
    dp.register_message_handler(stats_week, text="📅 Неделя", state="*")
    dp.register_message_handler(stats_month, text="📆 Месяц", state="*")
    dp.register_message_handler(stats_text, text="📄 Текстовая статистика", state="*")
    dp.register_message_handler(back_to_main, text="⬅️ Назад", state="*")
    dp.register_message_handler(export_menu, text="📤 Экспорт", state="*")
    dp.register_message_handler(export_all_data, text="📥 Экспорт всех данных", state="*")
    dp.register_message_handler(export_any_start, text=["🎵 SoundCloud", "📌 Pinterest (видео)", "🌐 Другой URL"], state="*")
    dp.register_message_handler(export_any_url, state=ExportStates.url)
    dp.register_message_handler(export_any_format, state=ExportStates.format)
