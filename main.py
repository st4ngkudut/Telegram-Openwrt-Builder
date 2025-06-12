# main.py

import logging
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
    setpackages_command,
    setoutputdir_command
)
from handlers.callback_handlers import main_callback_handler
from handlers.conversation_handlers import (
    SET_PACKAGES, SET_OUTPUT_DIR,
    receive_packages,
    receive_output_dir,
    cancel_conversation
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

def main() -> None:
    if config.TELEGRAM_TOKEN == "GANTI_DENGAN_TOKEN_BOT_ANDA" or not config.AUTHORIZED_USER_IDS:
        logger.error("TOKEN atau USER ID belum diatur di dalam config.py! Bot tidak akan berjalan.")
        return

    application = Application.builder().token(config.TELEGRAM_TOKEN).build()
    application.bot_data['config'] = config.OPENWRT_DEFAULTS.copy()

    conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("setpackages", setpackages_command),
            CommandHandler("setoutputdir", setoutputdir_command),
        ],
        states={
            SET_PACKAGES: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_packages)],
            SET_OUTPUT_DIR: [MessageHandler(filters.TEXT & ~filters.COMMAND, receive_output_dir)],
        },
        fallbacks=[CommandHandler("cancel", cancel_conversation)],
    )

    application.add_handler(conv_handler)
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("settings", settings_command))
    application.add_handler(CommandHandler("build", build_command))
    application.add_handler(CommandHandler("getlog", getlog_command))
    application.add_handler(CallbackQueryHandler(main_callback_handler))

    logger.info("Bot dengan struktur modular final siap dijalankan...")
    application.run_polling()

if __name__ == "__main__":
    main()
