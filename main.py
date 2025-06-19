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
from core.build_manager import build_manager, FILES_PER_PAGE
from core.history_manager import (
    load_history, 
    remove_build_entry,
    remove_ib_directory_and_entries
)
from handlers.command_handlers import (
    start_command, 
    status_command, 
    getlog_command,
    cancel_command as general_cancel_command 
)
from handlers.constants import *
from handlers.settings_handler import *
from handlers.build_handler import *
from handlers.upload_handler import *
from handlers.cleanup_handler import *
from handlers.chain_handler import *
from handlers.utils import send_temporary_message

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

ITEMS_PER_PAGE_HISTORY = 5

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
    history = load_history()
    if mode == 'arsip': text = f"📖 **Arsip Build (Halaman {page + 1})**\n\nPilih build untuk melihat file."
    else: text = f"🗑️ **Kelola Arsip (Halaman {page + 1})**\n\nPilih build untuk dihapus satu per satu."
    keyboard = []
    if not history:
        text = "Arsip build Anda masih kosong."
    else:
        start_index = page * ITEMS_PER_PAGE_HISTORY; end_index = start_index + ITEMS_PER_PAGE_HISTORY
        paginated_history = history[start_index:end_index]
        for entry in paginated_history:
            dt_object = datetime.fromtimestamp(entry['timestamp']); date_str = dt_object.strftime('%d-%b-%Y %H:%M')
            if entry.get('build_mode') == 'amlogic': profile_str = f"Amlogic {entry.get('BOARD', 'N/A')}"
            else: profile_str = entry.get('profile', 'N/A').replace('_', ' ').title()
            button_text = f"[{date_str}] {entry.get('version', 'Amlogic')} - {profile_str}"; callback_data = f"{mode}_select_{entry['id']}"
            keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])
        nav_row = []
        if page > 0: nav_row.append(InlineKeyboardButton("« Sebelumnya", callback_data=f"{mode}_page_{page - 1}"))
        if end_index < len(history): nav_row.append(InlineKeyboardButton("Berikutnya »", callback_data=f"{mode}_page_{page + 1}"))
        if nav_row: keyboard.append(nav_row)
    if mode == 'cleanup': keyboard.append([InlineKeyboardButton("💥 HAPUS SEMUA DATA BUILD 💥", callback_data="cleanup_all_start")])
    keyboard.append([InlineKeyboardButton("Tutup", callback_data="action_close")])
    if update.message: await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    else:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')

async def history_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); data = query.data.split('_'); mode, action = data[0], data[1]
    if action == "page": await _show_history_page(update, context, page=int(data[2]), mode=mode); return
    build_id = data[2]; history = load_history()
    selected_build = next((item for item in history if item['id'] == build_id), None)
    if not selected_build: await query.edit_message_text("❌ Error: Build tidak ditemukan."); return
    if mode == 'arsip': await _show_archive_files_page(update, context, build_id, page=0)
    elif mode == 'cleanup':
        keyboard = [[InlineKeyboardButton("🗑️ Hapus Hasil Saja", callback_data=f"cleanup_del-res_{build_id}")],[InlineKeyboardButton("💥 Hapus Semua (Source & Hasil)", callback_data=f"cleanup_del-all_{build_id}")],[InlineKeyboardButton("« Kembali", callback_data="cleanup_page_0")]]
        await query.edit_message_text("Pilih aksi untuk build ini:", reply_markup=InlineKeyboardMarkup(keyboard))

async def _show_archive_files_page(update: Update, context: ContextTypes.DEFAULT_TYPE, build_id: str, page: int):
    query = update.callback_query; history = load_history()
    selected_build = next((item for item in history if item['id'] == build_id), None)
    if not selected_build: await query.edit_message_text("❌ Error: Build tidak ditemukan."); return
    firmware_files_dict = selected_build.get('firmware_files', {}); firmware_filenames = sorted(list(firmware_files_dict.keys()))
    total_files = len(firmware_filenames); total_pages = -(-total_files // FILES_PER_PAGE) if FILES_PER_PAGE > 0 else 1
    start_index = page * FILES_PER_PAGE; end_index = start_index + FILES_PER_PAGE
    paginated_filenames = firmware_filenames[start_index:end_index]
    keyboard = []
    for filename in paginated_filenames:
        try:
            global_index = list(firmware_files_dict.keys()).index(filename)
            keyboard.append([InlineKeyboardButton(f"📥 {filename}", callback_data=f"arsip_dl_{build_id}_{global_index}")])
        except ValueError: continue
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("«", callback_data=f"arsip_files_page_{build_id}_{page - 1}"))
    if end_index < total_files: nav_row.append(InlineKeyboardButton("»", callback_data=f"arsip_files_page_{build_id}_{page + 1}"))
    if nav_row: keyboard.append(nav_row)
    if "rootfs" in str(selected_build.get('firmware_files', {}).values()) and selected_build.get('build_mode') == 'official':
        keyboard.append([InlineKeyboardButton("💽 Gunakan untuk Amlogic Remake", callback_data=f"arsip_remake_{build_id}")])
    keyboard.append([InlineKeyboardButton("« Kembali ke Arsip", callback_data="arsip_page_0")])
    text = f"Pilih file dari arsip (Halaman {page + 1}/{total_pages}):"
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_archive_file_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try:
        _, _, _, build_id, page_str = query.data.split('_'); page = int(page_str)
    except ValueError: await query.edit_message_text("❌ Error: Data paginasi arsip tidak valid."); return
    await _show_archive_files_page(update, context, build_id, page)

async def archive_download_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try:
        _, _, build_id, file_index_str = query.data.split('_', 2); file_index = int(file_index_str)
    except ValueError: await send_temporary_message(context, update.effective_chat.id, "❌ Error: Data tombol tidak valid."); return
    history = load_history(); selected_build = next((item for item in history if item['id'] == build_id), None)
    if not selected_build: await query.edit_message_text("❌ Error: Build tidak ditemukan."); return
    firmware_dict = selected_build.get('firmware_files', {})
    if not firmware_dict or file_index >= len(list(firmware_dict.keys())): await query.edit_message_text("❌ Error: Indeks file tidak valid."); return
    filename = sorted(list(firmware_dict.keys()))[file_index]; file_path = firmware_dict[filename]
    if not os.path.exists(file_path): await query.edit_message_text(f"❌ Error: File fisik `{filename}` tidak ditemukan."); return
    edited_message = await query.edit_message_text(f"Mempersiapkan pengunduhan `{filename}`...", parse_mode='Markdown')
    await build_manager.perform_upload(context, update.effective_chat.id, file_path, edited_message)

async def cleanup_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer(); _, action, build_id = query.data.split('_')
    if action == 'del-res': text_to_send = "✅ Hasil compile dan catatan dihapus." if remove_build_entry(build_id) else "❌ Gagal menghapus entri."
    elif action == 'del-all':
        history = load_history(); selected_build = next((item for item in history if item['id'] == build_id), None)
        if selected_build and selected_build.get('ib_dir'):
            text_to_send = "✅ Direktori IB dan arsip terkait dihapus." if remove_ib_directory_and_entries(selected_build['ib_dir']) else "❌ Gagal hapus direktori."
        else: text_to_send = "❌ Gagal mendapatkan path direktori."
    await query.message.delete(); await send_temporary_message(context, update.effective_chat.id, text_to_send)

async def handle_upload_selection(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try:
        data_part = query.data.replace('upload_choice_', ''); build_id, file_index_str = data_part.rsplit('_', 1)
        file_index = int(file_index_str); history = load_history()
        selected_build = next((item for item in history if item['id'] == build_id), None)
        if not selected_build: await query.message.edit_text("❌ Error: Catatan build tidak ditemukan."); return
        firmware_dict = selected_build.get('firmware_files', {})
        firmware_paths = sorted(list(firmware_dict.values()))
        if not firmware_dict or file_index >= len(firmware_paths): await query.message.edit_text("❌ Error: Indeks file tidak valid."); return
        selected_file_path = firmware_paths[file_index]
        if not os.path.exists(selected_file_path): await query.message.edit_message_text("❌ Error: File fisik tidak ditemukan."); return
        await build_manager.perform_upload(context, update.effective_chat.id, selected_file_path, query.message)
    except Exception as e:
        logger.error(f"Error tak terduga di handle_upload_selection: {e}", exc_info=True)
        if query.message: await query.message.edit_text("❌ Terjadi kesalahan tak terduga.")

async def handle_build_file_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    try: _, build_id, page_str = query.data.split('_', 2); page = int(page_str)
    except ValueError: await query.edit_message_text("❌ Error: Data paginasi tidak valid."); return
    history = load_history()
    selected_build = next((item for item in history if item['id'] == build_id), None)
    if not selected_build: await query.edit_message_text("❌ Error: Catatan build tidak ditemukan."); return
    firmware_files = sorted(list(selected_build.get('firmware_files', {}).values()))
    total_files = len(firmware_files); total_pages = -(-total_files // FILES_PER_PAGE) if FILES_PER_PAGE > 0 else 1
    start_index = page * FILES_PER_PAGE; end_index = start_index + FILES_PER_PAGE
    paginated_files = firmware_files[start_index:end_index]
    keyboard = []
    for file_path in paginated_files:
        try:
            global_index = firmware_files.index(file_path)
            keyboard.append([InlineKeyboardButton(os.path.basename(file_path), callback_data=f"upload_choice_{build_id}_{global_index}")])
        except ValueError: continue
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("«", callback_data=f"build_page_{build_id}_{page - 1}"))
    if end_index < total_files: nav_row.append(InlineKeyboardButton("»", callback_data=f"build_page_{build_id}_{page + 1}"))
    if nav_row: keyboard.append(nav_row)
    if selected_build.get('build_mode') == 'official' and any("rootfs" in f for f in firmware_files):
        keyboard.append([InlineKeyboardButton("➡️ Lanjutkan ke Amlogic Remake", callback_data=f"chain_relic_{build_id}")])
    await query.edit_message_text(f"✅ **Build Selesai!** (Hal {page + 1}/{total_pages})\n\nDisimpan ke `/arsip`.\n👇 Pilih file untuk diunggah:", reply_markup=InlineKeyboardMarkup(keyboard))

async def close_message_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try: await update.callback_query.message.delete()
    except Exception as e: logger.warning(f"Gagal menghapus pesan: {e}")

async def main() -> None:
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    if os.path.exists('state.json'):
        try:
            with open('state.json', 'r') as f: user_config = json.load(f)
            base_config = config.DEFAULT_CONFIGS.copy()
            for key, value in user_config.items():
                if isinstance(value, dict) and key in base_config: base_config[key].update(value)
                else: base_config[key] = value
            application.bot_data['config'] = base_config
        except (json.JSONDecodeError, IOError): application.bot_data['config'] = config.DEFAULT_CONFIGS.copy()
    else: application.bot_data['config'] = config.DEFAULT_CONFIGS.copy()
    application.bot_data['save_config'] = save_config
    
    master_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("settings", start_settings_conversation),
            CommandHandler("build", start_build_conversation),
            CommandHandler("upload_rootfs", start_rootfs_upload),
            CommandHandler("upload_ipk", start_ipk_upload),
            CallbackQueryHandler(start_full_cleanup, pattern="^cleanup_all_start$"),
            CallbackQueryHandler(start_chain_build, pattern="^chain_relic_"),
            CallbackQueryHandler(start_chain_build, pattern="^arsip_remake_")
        ],
        states={
            # States untuk /settings
            SELECT_MODE: [CallbackQueryHandler(mode_router, pattern="^mode_")],
            MENU: [CallbackQueryHandler(official_menu_router, pattern="^official_set_"), CallbackQueryHandler(save_and_exit_handler, pattern="^settings_save$")],
            SELECT_BUILD_SOURCE: [CallbackQueryHandler(select_build_source_handler, pattern="^select_source_")],
            SELECT_VERSION_MAJOR: [CallbackQueryHandler(select_version_major_handler, pattern="^official_vmajor_")],
            SELECT_VERSION_MINOR: [CallbackQueryHandler(select_version_minor_handler, pattern="^official_vminor_")],
            SELECT_TARGET: [CallbackQueryHandler(select_target_handler, pattern="^official_tselect_")],
            SELECT_SUBTARGET: [CallbackQueryHandler(select_subtarget_handler, pattern="^official_stselect_")],
            SELECT_PROFILE: [CallbackQueryHandler(select_profile_handler, pattern="^official_pselect_")],
            AWAITING_PACKAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_official_packages)],
            AWAITING_ROOTFS_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_official_rootfs)],
            AWAITING_LEECH_DEST_OFFICIAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_official_leech_dest)],
            CUSTOM_MENU: [CallbackQueryHandler(customization_menu_router, pattern="^custom_")],
            AWAITING_CUSTOM_REPOS: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_custom_repos)],
            AWAITING_UCI_SCRIPT: [MessageHandler(filters.Document.ALL, handle_uci_script_upload)],
            AML_MENU: [CallbackQueryHandler(aml_menu_router, pattern="^aml_set_"), CallbackQueryHandler(toggle_aml_auto_update, pattern="^aml_toggle_auto_update$"), CallbackQueryHandler(save_and_exit_handler, pattern="^settings_save$")],
            AWAITING_AML_ROOTFS_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_rootfs_url)],
            AWAITING_AML_BOARD: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_board)],
            AWAITING_AML_ROOTFS_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_rootfs_size)],
            AWAITING_AML_KERNEL: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_kernel)],
            AWAITING_AML_KERNEL_TAG: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_kernel_tag)],
            AWAITING_AML_BUILDER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_builder_name)],
            AWAITING_LEECH_DEST_AML: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_aml_leech_dest)],

            # States untuk /build
            SELECT_BUILD_MODE: [CallbackQueryHandler(select_build_mode_handler, pattern="^build_mode_")],
            CONFIRM_BUILD: [CallbackQueryHandler(confirm_build_handler, pattern="^build_confirm_"), CallbackQueryHandler(request_settings_change_handler, pattern="^build_goto_settings_")],
            AWAITING_PROFILE_FIX: [CallbackQueryHandler(fix_profile_handler, pattern="^build_fix_profile_")],

            # States untuk /upload
            UPLOAD_ROOTFS: [MessageHandler(filters.Document.ALL, handle_rootfs_upload)],
            UPLOAD_IPK: [MessageHandler(filters.Document.ALL, handle_ipk_upload)],

            # States untuk /cleanup all
            CLEANUP_ALL_CONFIRM_1: [CallbackQueryHandler(prompt_for_final_confirmation, pattern="^cleanup_all_confirm_yes$")],
            AWAITING_DELETION_PHRASE: [MessageHandler(filters.Text(config.CONFIRMATION_PHRASE), execute_full_cleanup), MessageHandler(filters.TEXT & ~filters.COMMAND, invalid_confirmation_phrase)],
        
            # States untuk Build Berantai
            CHAIN_CONFIRM_AML: [CallbackQueryHandler(confirm_chain_build, pattern="^chain_confirm_start$"), CallbackQueryHandler(chain_goto_settings, pattern="^chain_goto_settings$")]
        },
        fallbacks=[
            CommandHandler("cancel", cancel_conversation),
            CallbackQueryHandler(start_settings_conversation, pattern="^back_to_mode_select$"),
            CallbackQueryHandler(back_to_official_menu_handler, pattern="^back_to_official_menu$"),
            CallbackQueryHandler(cancel_full_cleanup, pattern="^cleanup_all_cancel$"),
            CallbackQueryHandler(cancel_chain_build, pattern="^chain_cancel$"),
        ],
        conversation_timeout=600, per_user=True, per_chat=True, allow_reentry=True
    )
    
    # --- Semua Handler ---
    application.add_handler(master_conv_handler)
    
    application.add_handler(CommandHandler("start", start_command)); application.add_handler(CommandHandler("status", status_command)); application.add_handler(CommandHandler("getlog", getlog_command)); application.add_handler(CommandHandler("cancel", general_cancel_command)); application.add_handler(CommandHandler("arsip", archive_command)); application.add_handler(CommandHandler("cleanup", cleanup_command))
    application.add_handler(CallbackQueryHandler(handle_upload_selection, pattern="^upload_choice_"))
    application.add_handler(CallbackQueryHandler(handle_build_file_pagination, pattern="^build_page_"))
    application.add_handler(CallbackQueryHandler(handle_archive_file_pagination, pattern="^arsip_files_page_"))
    application.add_handler(CallbackQueryHandler(history_menu_callback, pattern="^(arsip|cleanup)_select_"))
    application.add_handler(CallbackQueryHandler(history_menu_callback, pattern="^(arsip|cleanup)_page_"))
    application.add_handler(CallbackQueryHandler(archive_download_callback, pattern="^arsip_dl_"))
    application.add_handler(CallbackQueryHandler(cleanup_action_callback, pattern="^cleanup_del-"))
    application.add_handler(CallbackQueryHandler(close_message_callback, pattern="^action_close$"))
    
    logger.info("Bot dengan arsitektur final siap dijalankan..."); await application.initialize(); await application.start(); await application.updater.start_polling(); logger.info("Bot telah dimulai dan sedang polling.")
    
    while True: await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot dihentikan.")
