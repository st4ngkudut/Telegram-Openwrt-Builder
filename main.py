# main.py

import logging
import os
import json
import asyncio
from telethon import TelegramClient
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters
)

import config
from handlers.command_handlers import (
    start_command, 
    status_command, 
    build_command, 
    getlog_command,
    settings_command,
    cancel_command
)
from handlers.settings_handler import (
    MENU,
    AWAITING_PACKAGES, AWAITING_OUTPUT_DIR, AWAITING_ROOTFS_SIZE, AWAITING_LEECH_DEST,
    SELECT_VERSION_MAJOR, SELECT_VERSION_MINOR,
    SELECT_TARGET, SELECT_SUBTARGET,
    SELECT_PROFILE,
    SELECT_UPLOAD_PATTERN,
    start_settings_conversation,
    menu_router,
    receive_packages, receive_output_dir, receive_rootfs_size, receive_leech_dest,
    select_version_major_handler, select_version_minor_handler,
    select_target_handler, select_subtarget_handler,
    select_profile_handler,
    select_upload_pattern_handler,
    cancel_conversation
)


logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("telethon").setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

def save_config(data):
    """Menyimpan dictionary konfigurasi ke state.json"""
    try:
        with open('state.json', 'w') as f: json.dump(data, f, indent=4)
        logger.info("Konfigurasi berhasil disimpan ke state.json")
    except Exception as e: logger.error(f"Gagal menyimpan konfigurasi: {e}")

async def main() -> None:
    """Fungsi utama yang menjalankan pengecekan sesi dan bot."""
    
    logger.info("Memulai pengecekan sesi Telethon...")
    telethon_client = TelegramClient('telegram_user_session', config.API_ID, config.API_HASH)
    try:
        await telethon_client.start()
        me = await telethon_client.get_me()
        logger.info(f"Pengecekan sesi Telethon berhasil. Login sebagai: {me.first_name}")
        await telethon_client.disconnect()
        logger.info("Koneksi Telethon untuk pengecekan ditutup.")
    except Exception as e:
        logger.error(f"Gagal melakukan pengecekan sesi Telethon: {e}")
        print(f"\n!!! GAGAL MENGHUBUNGKAN TELETHON: {e} !!!")
        print("Pastikan API_ID, API_HASH, dan input login (nomor telp/kode) sudah benar.")
        print("Fitur upload file besar mungkin tidak akan berjalan. Bot akan berhenti.")
        if telethon_client.is_connected():
            await telethon_client.disconnect()
        return
    
    logger.info("="*30)
    logger.info("MEMULAI BOT UTAMA (PYTHON-TELEGRAM-BOT)")
    logger.info("="*30)
    
    if not config.TELEGRAM_TOKEN or not config.AUTHORIZED_USER_IDS:
        logger.error("TOKEN atau USER ID belum diatur di dalam config.py! Bot tidak akan berjalan.")
        return
    
    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    
    if os.path.exists('state.json'):
        logger.info("Membaca konfigurasi dari state.json...")
        try:
            with open('state.json', 'r') as f: user_config = json.load(f)
            base_config = config.OPENWRT_DEFAULTS.copy()
            base_config.update(user_config)
            application.bot_data['config'] = base_config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Gagal membaca state.json: {e}. Menggunakan konfigurasi default.")
            application.bot_data['config'] = config.OPENWRT_DEFAULTS.copy()
    else:
        logger.info("state.json tidak ditemukan, menggunakan konfigurasi default.")
        application.bot_data['config'] = config.OPENWRT_DEFAULTS.copy()

    application.bot_data['save_config'] = save_config
    
    settings_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("settings", start_settings_conversation)],
        states={
            MENU: [CallbackQueryHandler(menu_router)],
            AWAITING_PACKAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_packages)],
            AWAITING_OUTPUT_DIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_output_dir)],
            AWAITING_ROOTFS_SIZE: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_rootfs_size)],
            AWAITING_LEECH_DEST: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_leech_dest)],
            SELECT_UPLOAD_PATTERN: [CallbackQueryHandler(select_upload_pattern_handler, pattern="^set_pattern_")],
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

    logger.info("Bot dengan handler pengaturan baru siap dijalankan...")
    
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
