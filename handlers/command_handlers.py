# handlers/command_handlers.py

import os
import logging
from functools import wraps
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from config import AUTHORIZED_USER_IDS, BUILD_LOG_PATH
from core.build_manager import build_manager
from .conversation_handlers import setpackages_command, setoutputdir_command

logger = logging.getLogger(__name__)

def restricted(func):
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user_id = update.effective_user.id
        if update.callback_query:
            user_id = update.callback_query.from_user.id
        if user_id not in AUTHORIZED_USER_IDS:
            if update.callback_query:
                await update.callback_query.answer("Akses ditolak.", show_alert=True)
            else:
                await update.message.reply_text("Maaf, Anda tidak diizinkan menggunakan bot ini.")
            logger.warning(f"Akses ditolak untuk user ID: {user_id}")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [KeyboardButton("/status"), KeyboardButton("/settings")],
        [KeyboardButton("/build"), KeyboardButton("/getlog")],
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
    await update.message.reply_html(
        f"Halo {user.mention_html()}!\n\nBot OpenWrt siap digunakan. Gunakan /settings untuk memulai konfigurasi.",
        reply_markup=reply_markup
    )

@restricted
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    bot_config = context.bot_data.get('config', {})
    status_text = "🔧 **Konfigurasi Saat Ini** 🔧\n\n"
    for key, value in bot_config.items():
        status_text += f"*{key}*: `{value}`\n"
    status_text += f"\n*Build Status*: `{build_manager.status}`"
    await update.message.reply_markdown(status_text)

@restricted
async def build_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if build_manager.status == "Building...":
        await update.message.reply_text("❌ Proses build lain sedang berjalan.")
        return
    
    chat_id = update.effective_message.chat_id
    current_config = context.bot_data.get('config', {})
    context.application.job_queue.run_once(
        lambda ctx: build_manager.run_build_task(ctx, chat_id, current_config),
        0,
        name=f"build_job_{chat_id}"
    )

@restricted
async def getlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if os.path.exists(BUILD_LOG_PATH):
        await update.message.reply_document(document=open(BUILD_LOG_PATH, 'rb'))
    else:
        await update.message.reply_text("File log tidak ditemukan.")

@restricted
async def settings_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    from .callback_handlers import create_main_settings_keyboard
    keyboard = await create_main_settings_keyboard()
    await update.message.reply_text("⚙️ **Menu Pengaturan**\n\nPilih parameter yang ingin diubah:", reply_markup=keyboard, parse_mode='Markdown')
