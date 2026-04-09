import asyncio
import os
import shutil
import tempfile
import logging
from aiogram import Dispatcher, types
from aiogram.dispatcher import FSMContext
from states import ConverterStates
from keyboards import get_converter_formats_keyboard, get_back_button, get_main_menu
from utils import edit_or_send, delete_dialog_message, send_temp_message, safe_finish, safe_remove_file

async def converter_menu(message: types.Message, state: FSMContext):
    await ConverterStates.file.set()
    m = await message.answer("Отправь мне файл (видео, аудио, изображение), который хочешь конвертировать.", reply_markup=get_back_button())
    await state.update_data(msg_id=m.message_id, chat_id=m.chat.id)

async def converter_file_text(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        return
    await send_temp_message(message.chat.id, "❌ Отправь файл или нажми «Назад».", 3)

async def converter_file(message: types.Message, state: FSMContext):
    if not (message.document or message.video or message.audio):
        await send_temp_message(message.chat.id, "❌ Неподдерживаемый тип файла. Пожалуйста, отправь документ, видео или аудио.", 3)
        return
    if message.document:
        file_id = message.document.file_id
        file_name = message.document.file_name or f"{message.document.file_unique_id}.bin"
    elif message.video:
        file_id = message.video.file_id
        file_name = f"{message.video.file_unique_id}.mp4"
    elif message.audio:
        file_id = message.audio.file_id
        file_name = f"{message.audio.file_unique_id}.mp3"
    else:
        await send_temp_message(message.chat.id, "❌ Неподдерживаемый тип файла.", 3)
        return

    try:
        file = await message.bot.get_file(file_id)
        downloaded_file = await message.bot.download_file(file.file_path)
        input_ext = os.path.splitext(file_name)[1] or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=input_ext, dir="/tmp") as tmp_file:
            tmp_file.write(downloaded_file.getvalue())
            temp_input = tmp_file.name
        await state.update_data(input_path=temp_input)
        await delete_dialog_message(state)
        m = await message.answer("Выбери целевой формат:", reply_markup=get_converter_formats_keyboard())
        await state.update_data(msg_id=m.message_id, chat_id=m.chat.id)
        await ConverterStates.format.set()
    except Exception as e:
        logging.error(f"Ошибка при получении файла: {e}")
        await send_temp_message(message.chat.id, "❌ Не удалось загрузить файл. Попробуй ещё раз.", 3)
        await safe_finish(state, message)

async def converter_format(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Назад":
        await safe_finish(state, message)
        return
    fmt = message.text.upper()
    allowed_formats = ["MP4", "GIF", "MP3", "WEBM"]
    if fmt not in allowed_formats:
        await send_temp_message(message.chat.id, f"❌ Неверный формат. Выбери из кнопок: {', '.join(allowed_formats)}", 3)
        return
    data = await state.get_data()
    input_path = data.get('input_path')
    if not input_path or not os.path.exists(input_path):
        await send_temp_message(message.chat.id, "❌ Файл не найден. Попробуй ещё раз.", 3)
        await safe_finish(state, message)
        return
    await delete_dialog_message(state)
    await state.finish()

    spinner = ['⠋', '⠙', '⠹', '⠸', '⠼', '⠴', '⠦', '⠧', '⠇', '⠏']
    progress_msg = await message.answer(f"⏳ Конвертирую... {spinner[0]}")
    async def update_spinner():
        i = 0
        while True:
            await asyncio.sleep(0.3)
            i = (i + 1) % len(spinner)
            try:
                await message.bot.edit_message_text(f"⏳ Конвертирую... {spinner[i]}", chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
            except:
                break
    spinner_task = asyncio.create_task(update_spinner())
    output_path = None
    try:
        ffmpeg_path = shutil.which('ffmpeg')
        if not ffmpeg_path:
            ffmpeg_path = os.path.join(os.getcwd(), 'ffmpeg')
            if not os.path.exists(ffmpeg_path):
                raise Exception("ffmpeg не найден в системе. Установите ffmpeg или поместите его в папку с ботом.")
        with tempfile.NamedTemporaryFile(delete=False, suffix=f".{fmt.lower()}", dir="/tmp") as tmp_out:
            output_path = tmp_out.name
        cmd = [ffmpeg_path, '-i', input_path, output_path]
        if fmt == "GIF":
            cmd = [ffmpeg_path, '-i', input_path, '-vf', 'scale=640:-1:flags=lanczos,fps=15,split[s0][s1];[s0]palettegen=max_colors=256[p];[s1][p]paletteuse', '-loop', '0', output_path]
        process = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        _, stderr = await process.communicate()
        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="ignore").strip()[:200]
            raise Exception(f"ffmpeg error: {error_msg}")
        file_size = os.path.getsize(output_path)
        max_size = 50 * 1024 * 1024
        if file_size > max_size:
            raise Exception(f"File too large: {file_size / (1024*1024):.1f} MB > 50 MB limit.")
        spinner_task.cancel()
        try:
            await spinner_task
        except asyncio.CancelledError:
            pass
        await message.bot.edit_message_text("✅ Конвертация завершена! Отправляю файл...", chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
        with open(output_path, 'rb') as f:
            await message.answer_document(f, caption=f"✅ Конвертировано в {fmt.upper()}")
    except Exception as e:
        logging.error(f"Ошибка конвертации: {e}")
        spinner_task.cancel()
        try:
            await spinner_task
        except asyncio.CancelledError:
            pass
        error_msg = str(e)
        if "File too large" in error_msg:
            await message.bot.edit_message_text(f"❌ {error_msg}", chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
        else:
            await message.bot.edit_message_text(f"❌ Ошибка конвертации: {error_msg}\nПопробуй другой файл или формат.", chat_id=progress_msg.chat.id, message_id=progress_msg.message_id)
        await asyncio.sleep(3)
        await safe_delete_message_obj(progress_msg)
    finally:
        safe_remove_file(input_path)
        safe_remove_file(output_path)
    await message.answer("Главное меню", reply_markup=get_main_menu())

def register(dp: Dispatcher):
    dp.register_message_handler(converter_menu, text="🔄 Конвертер", state="*")
    dp.register_message_handler(converter_file_text, state=ConverterStates.file, content_types=types.ContentTypes.TEXT)
    dp.register_message_handler(converter_file, content_types=['document', 'video', 'audio'], state=ConverterStates.file)
    dp.register_message_handler(converter_format, state=ConverterStates.format)
