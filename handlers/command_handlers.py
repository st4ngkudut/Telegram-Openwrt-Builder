# handlers/command_handlers.py

import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.ext import ContextTypes
from telegram.error import BadRequest
from telegram.helpers import escape_markdown

from config import BUILD_LOG_PATH
from core.build_manager import build_manager
from .utils import restricted, send_temporary_message

logger = logging.getLogger(__name__)

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengirim pesan selamat datang dan keyboard perintah."""
    user = update.effective_user
    chat_id = update.effective_chat.id
    
    stang_url = "https://t.me/ST4NGKUDUT"
    github_url = "https://github.com/st4ngkudut/Telegram-Openwrt-Builder/tree/main"
    
    message_text = (
        "👋 <b>Selamat Datang di Bot OpenWrt Builder!</b>\n\n"
        "Asisten pribadi Anda untuk membuat firmware OpenWrt khusus dengan mudah dan cepat.\n\n"
        "<b>Fitur Utama:</b>\n"
        "🔧 <code>/build</code> - Memulai proses build interaktif.\n"
        "⚙️ <code>/settings</code> - Mengonfigurasi semua parameter build.\n"
        "💽 <code>/upload_rootfs</code> - Mengunggah <code>rootfs</code> untuk Amlogic.\n"
        "📦 <code>/upload_ipk</code> - Mengunggah paket <code>.ipk</code> kustom.\n"
        "🗂️ <code>/arsip</code> - Melihat dan mengunduh ulang hasil build.\n"
        "🧹 <code>/cleanup</code> - Mengelola dan membersihkan file build.\n\n"
        "--- \n"
        f"Bot ini dikembangkan oleh <a href='{stang_url}'>ST4NGKUDUT</a> dengan bantuan Gemini AI."
    )

    inline_keyboard = [
        [
            InlineKeyboardButton("Pengembang", url=stang_url),
            InlineKeyboardButton("GitHub", url=github_url)
        ]
    ]
    
    await context.bot.send_message(
        chat_id=chat_id,
        text=message_text,
        parse_mode=ParseMode.HTML,
        reply_markup=InlineKeyboardMarkup(inline_keyboard),
        disable_web_page_preview=True
    )
    
    commands_keyboard = [
        [KeyboardButton("/build"), KeyboardButton("/settings")],
        [KeyboardButton("/upload_rootfs"), KeyboardButton("/upload_ipk")],
        [KeyboardButton("/arsip"), KeyboardButton("/cleanup")],
        [KeyboardButton("/status"), KeyboardButton("/cancel"), KeyboardButton("/getlog")],
    ]
    reply_markup = ReplyKeyboardMarkup(commands_keyboard, resize_keyboard=True)
    
    await context.bot.send_message(
        chat_id=chat_id,
        text="Gunakan tombol keyboard di bawah untuk akses cepat:",
        reply_markup=reply_markup
    )

@restricted
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menghapus panel status lama (jika ada) dan selalu mengirim yang baru."""
    if update.message:
        await update.message.delete()

    chat_id = update.effective_chat.id
    
    old_panel_id = context.chat_data.pop('status_panel_id', None)
    if old_panel_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=old_panel_id)
        except BadRequest:
            logger.info(f"Gagal hapus panel status lama (ID: {old_panel_id}), mungkin sudah dihapus.")
            pass

    bot_config = context.bot_data.get('config', {})
    active_mode_raw = bot_config.get('active_build_mode', 'official').title()
    
    safe_active_mode = escape_markdown(active_mode_raw, version=2)
    header = f"🔧 *Konfigurasi & Status \\(Mode: {safe_active_mode}\\)* 🔧\n\n"
    
    status_text = header
    
    active_config = bot_config.get(bot_config.get('active_build_mode', 'official'), {})
    
    for key, value in active_config.items():
        safe_key = escape_markdown(str(key), version=2)
        safe_value = escape_markdown(str(value) or 'Default', version=2)
        status_text += f"*{safe_key}*: `{safe_value}`\n"
        
    safe_build_status = escape_markdown(build_manager.status, version=2)
    status_text += f"\n*Build Status*: `{safe_build_status}`"

    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=status_text,
        parse_mode=ParseMode.MARKDOWN_V2
    )
    context.chat_data['status_panel_id'] = sent_message.message_id
    logger.info(f"Panel status baru dibuat dengan ID: {sent_message.message_id}")

@restricted
async def getlog_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.delete()
    if build_manager.status == "Building...":
        await send_temporary_message(context, update.effective_chat.id, "⚙️ Proses build sedang berjalan. Silakan coba lagi setelah selesai.")
        return
    
    if os.path.exists(BUILD_LOG_PATH):
        await context.bot.send_document(chat_id=update.effective_chat.id, document=open(BUILD_LOG_PATH, 'rb'))
    else:
        await send_temporary_message(context, update.effective_chat.id, "File log tidak ditemukan.")

@restricted
async def cancel_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.delete()
    if build_manager.status != "Building...":
        await send_temporary_message(context, update.effective_chat.id, "Tidak ada proses build yang sedang berjalan untuk dibatalkan.")
        return
    was_cancelled = await build_manager.cancel_current_build()
    if was_cancelled:
        await send_temporary_message(context, update.effective_chat.id, "✅ Mengirim sinyal pembatalan ke proses build...")
    else:
        await send_temporary_message(context, update.effective_chat.id, " Gagal membatalkan. Mungkin proses sudah selesai atau macet.")
