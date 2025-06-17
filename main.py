# main.py

import logging
import os
import json
import asyncio
import time
from datetime import datetime
from telethon import TelegramClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    ContextTypes,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

import config
from core.build_manager import build_manager
from core.history_manager import (
    load_history, 
    remove_build_entry,
    remove_ib_directory_and_entries
)
from handlers.command_handlers import (
    start_command, 
    status_command, 
    build_command, 
    getlog_command,
    cancel_command
)
from handlers.constants import *
from handlers.settings_handler import (
    start_settings_conversation,
    menu_router,
    receive_packages,
    receive_rootfs_size,
    receive_leech_dest,
    select_version_major_handler,
    select_version_minor_handler,
    select_target_handler,
    select_subtarget_handler,
    select_profile_handler,
    cancel_conversation
)
from handlers.utils import send_temporary_message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE = 5

def save_config(data):
    try:
        with open('state.json', 'w') as f: json.dump(data, f, indent=4)
        logger.info("Konfigurasi berhasil disimpan ke state.json")
    except Exception as e: logger.error(f"Gagal menyimpan konfigurasi: {e}")

async def archive_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message: await update.message.delete()
    await _show_history_page(update, context, page=0, mode='arsip')

async def cleanup_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message: await update.message.delete()
    await _show_history_page(update, context, page=0, mode='cleanup')

async def _show_history_page(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int, mode: str):
    chat_id = update.effective_chat.id
    history = load_history()
    
    if mode == 'arsip': text = f"📖 **Arsip Build (Halaman {page + 1})**\n\nPilih build untuk melihat file."
    else: text = f"🗑️ **Kelola Arsip (Halaman {page + 1})**\n\nPilih build untuk dihapus."
    
    if not history:
        await send_temporary_message(context, chat_id, "Arsip build Anda masih kosong.")
        if update.callback_query:
            await update.callback_query.message.delete()
        return

    start_index = page * ITEMS_PER_PAGE
    end_index = start_index + ITEMS_PER_PAGE
    paginated_history = history[start_index:end_index]
    keyboard = []
    for entry in paginated_history:
        dt_object = datetime.fromtimestamp(entry['timestamp'])
        date_str = dt_object.strftime('%d-%b-%Y %H:%M')
        profile_str = entry['profile'].replace('_', ' ').title()
        button_text = f"[{date_str}] {entry['version']} - {profile_str}"
        callback_data = f"{mode}_select_{entry['id']}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("« Sebelumnya", callback_data=f"{mode}_page_{page - 1}"))
    if end_index < len(history): nav_row.append(InlineKeyboardButton("Berikutnya »", callback_data=f"{mode}_page_{page + 1}"))
    if nav_row: keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("Tutup Menu", callback_data="action_close")])

    if update.message: 
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def history_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data.split('_')
    mode, action = data[0], data[1]
    if action == "page":
        page = int(data[2])
        await _show_history_page(update, context, page=page, mode=mode)
        return
    build_id = data[2]
    history = load_history()
    selected_build = next((item for item in history if item['id'] == build_id), None)
    if not selected_build:
        await query.edit_message_text("❌ Error: Build tidak ditemukan. Mungkin sudah dihapus.")
        return
    
    if mode == 'arsip':
        keyboard = []
        firmware_dict = selected_build.get('firmware_files', {})
        for i, filename in enumerate(firmware_dict.keys()):
            callback_data = f"arsip_dl_{build_id}_{i}"
            keyboard.append([InlineKeyboardButton(f"📥 {filename}", callback_data=callback_data)])
        keyboard.append([InlineKeyboardButton("« Kembali", callback_data="arsip_page_0")])
        profile_str = selected_build['profile'].replace('_', ' ').title()
        await query.edit_message_text(f"Anda memilih:\n*Build: {profile_str}*\n\nPilih file untuk diunduh:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    
    elif mode == 'cleanup':
        keyboard = [
            [InlineKeyboardButton("🗑️ Hapus Hasil Saja", callback_data=f"cleanup_del-res_{build_id}")],
            [InlineKeyboardButton("💥 Hapus Semua", callback_data=f"cleanup_del-all_{build_id}")],
            [InlineKeyboardButton("« Kembali", callback_data="cleanup_page_0")]
        ]
        profile_str = selected_build['profile'].replace('_', ' ').title()
        await query.edit_message_text(f"Anda memilih:\n*Build: {profile_str}*\n\nPilih aksi yang diinginkan:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def archive_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        prefix, data_part = query.data.split('_', 1)
        _, build_id, file_index_str = data_part.split('_', 2)
        file_index = int(file_index_str)
    except ValueError:
        await send_temporary_message(context, update.effective_chat.id, "❌ Error: Data tombol tidak valid.")
        return
    
    history = load_history()
    selected_build = next((item for item in history if item['id'] == build_id), None)
    if not selected_build:
        await query.edit_message_text("❌ Error: Build tidak ditemukan.")
        return

    firmware_dict = selected_build.get('firmware_files', {})
    if not firmware_dict or file_index >= len(firmware_dict):
        await query.edit_message_text("❌ Error: Indeks file tidak valid.")
        return
        
    file_path = list(firmware_dict.values())[file_index]
    filename = list(firmware_dict.keys())[file_index]

    if not os.path.exists(file_path):
        await query.edit_message_text(f"❌ Error: File fisik `{filename}` tidak ditemukan di server.")
        return
        
    edited_message = await query.edit_message_text(f"Mempersiapkan pengunduhan `{filename}` dari arsip...", parse_mode='Markdown')
    await build_manager.perform_upload(context, update.effective_chat.id, file_path, edited_message)

async def cleanup_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    _, action, build_id = query.data.split('_')
    
    text_to_send = "" 
    if action == 'del-res':
        if remove_build_entry(build_id):
            text_to_send = "✅ Hasil compile dan catatannya telah dihapus dari arsip."
        else:
            text_to_send = "❌ Gagal menghapus entri build."
    
    elif action == 'del-all':
        history = load_history()
        selected_build = next((item for item in history if item['id'] == build_id), None)
        if not selected_build:
            await query.edit_message_text("❌ Error: Build tidak ditemukan, mungkin sudah dihapus.")
            return

        ib_dir = selected_build.get('ib_dir')
        if ib_dir and remove_ib_directory_and_entries(ib_dir):
            text_to_send = f"✅ Direktori Image Builder dan semua arsip terkait telah dihapus."
        else:
            text_to_send = "❌ Gagal menghapus direktori atau path tidak ditemukan."

    await query.message.delete()
    await send_temporary_message(context, update.effective_chat.id, text_to_send)

async def handle_upload_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    try:
        selection_message = query.message
        data_part = query.data.replace('upload_choice_', '')
        build_id, file_index_str = data_part.rsplit('_', 1)
        file_index = int(file_index_str)
        history = load_history()
        selected_build = next((item for item in history if item['id'] == build_id), None)
        if not selected_build:
            await selection_message.edit_text("❌ Terjadi kesalahan: Catatan build tidak ditemukan di histori.")
            return
        firmware_dict = selected_build.get('firmware_files', {})
        if not firmware_dict or file_index >= len(firmware_dict):
            await selection_message.edit_text("❌ Terjadi kesalahan: Indeks file tidak valid.")
            return
        selected_file_path = list(firmware_dict.values())[file_index]
        if not os.path.exists(selected_file_path):
             await selection_message.edit_text("❌ Terjadi kesalahan: File fisik tidak ditemukan di server.")
             return
        await build_manager.perform_upload(context, update.effective_chat.id, selected_file_path, selection_message)
    except Exception as e:
        logger.error(f"Error tak terduga di handle_upload_selection: {e}", exc_info=True)
        if query.message:
            await query.message.edit_text("❌ Terjadi kesalahan tak terduga saat memproses pilihan Anda.")

async def close_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Callback untuk menghapus pesan saat tombol 'Tutup' ditekan."""
    query = update.callback_query
    await query.answer()
    await query.message.delete()

async def main() -> None:
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    if os.path.exists('state.json'):
        try:
            with open('state.json', 'r') as f: user_config = json.load(f)
            base_config = config.OPENWRT_DEFAULTS.copy()
            base_config.update(user_config)
            application.bot_data['config'] = base_config
        except (json.JSONDecodeError, IOError):
            application.bot_data['config'] = config.OPENWRT_DEFAULTS.copy()
    else:
        application.bot_data['config'] = config.OPENWRT_DEFAULTS.copy()

    application.bot_data['save_config'] = save_config
    
    settings_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("settings", start_settings_conversation)],
        states={
            MENU: [CallbackQueryHandler(menu_router)],
            AWAITING_PACKAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_packages)],
            AWAITING_ROOTFS_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rootfs_size)],
            AWAITING_LEECH_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_leech_dest)],
            SELECT_VERSION_MAJOR: [CallbackQueryHandler(select_version_major_handler, pattern="^v_major_")],
            SELECT_VERSION_MINOR: [CallbackQueryHandler(select_version_minor_handler, pattern="^v_minor_")],
            SELECT_TARGET: [CallbackQueryHandler(select_target_handler, pattern="^t_select_")],
            SELECT_SUBTARGET: [CallbackQueryHandler(select_subtarget_handler, pattern="^st_select_")],
            SELECT_PROFILE: [CallbackQueryHandler(select_profile_handler, pattern="^p_select_")],
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(start_settings_conversation, pattern="^back_to_main_menu$"),
            CallbackQueryHandler(select_version_major_handler, pattern="^settings_version$"),
        ],
        conversation_timeout=600
    )
    
    application.add_handler(settings_conv_handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("build", build_command))
    application.add_handler(CommandHandler("getlog", getlog_command))
    application.add_handler(CommandHandler("cancel", cancel_command))
    application.add_handler(CommandHandler("arsip", archive_command))
    application.add_handler(CommandHandler("cleanup", cleanup_command))
    application.add_handler(CallbackQueryHandler(handle_upload_selection, pattern="^upload_choice_"))
    application.add_handler(CallbackQueryHandler(history_menu_callback, pattern="^(arsip|cleanup)_select_"))
    application.add_handler(CallbackQueryHandler(history_menu_callback, pattern="^(arsip|cleanup)_page_"))
    application.add_handler(CallbackQueryHandler(archive_download_callback, pattern="^arsip_dl_"))
    application.add_handler(CallbackQueryHandler(cleanup_action_callback, pattern="^cleanup_del-"))
    application.add_handler(CallbackQueryHandler(close_message_callback, pattern="^action_close$"))

    
    logger.info("Bot dengan semua fitur baru siap dijalankan...")
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    logger.info("Bot telah dimulai dan sedang polling.")
    
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot dihentikan.")
