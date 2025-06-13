# handlers/command_handlers.py

import os
import logging
import subprocess
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from config import BUILD_LOG_PATH
from core.build_manager import build_manager
from .settings_handler import start_settings_conversation
from .utils import restricted

logger = logging.getLogger(__name__)

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    keyboard = [
        [KeyboardButton("/status"), KeyboardButton("/settings")],
        [KeyboardButton("/build"), KeyboardButton("/cancel")],
        [KeyboardButton("/getlog")]
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
    if build_manager.status in ["Building...", "Preparing"]:
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
    if build_manager.status == "Building...":
        await update.message.reply_text("⚙️ Proses build sedang berjalan. Silakan coba lagi setelah selesai untuk mendapatkan log lengkap.")
        return
    if os.path.exists(BUILD_LOG_PATH):
        await update.message.reply_document(document=open(BUILD_LOG_PATH, 'rb'))
    else:
        await update.message.reply_text("File log tidak ditemukan.")

@restricted
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if build_manager.status != "Building...":
        await update.message.reply_text("Tidak ada proses build yang sedang berjalan untuk dibatalkan.")
        return
    was_cancelled = await build_manager.cancel_current_build()
    if was_cancelled:
        await update.message.reply_text("Mengirim sinyal pembatalan ke proses build...")
    else:
        await update.message.reply_text("Gagal membatalkan. Mungkin proses sudah selesai.")

settings_command = start_settings_conversation
