# handlers/command_handlers.py

import os
import logging
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from config import BUILD_LOG_PATH
from core.build_manager import build_manager
from .utils import restricted, send_temporary_message

logger = logging.getLogger(__name__)

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user

    keyboard = [
        [KeyboardButton("/build"), KeyboardButton("/settings")],
        [KeyboardButton("/arsip"), KeyboardButton("/cleanup")],
        [KeyboardButton("/status"), KeyboardButton("/cancel"), KeyboardButton("/getlog")]
    ]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    await update.message.reply_html(
        f"Halo {user.mention_html()}!\n\nBot OpenWrt siap digunakan. Gunakan /settings untuk memulai konfigurasi.",
        reply_markup=reply_markup
    )

@restricted
async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Mengirim atau mengedit 'Panel Status' yang persisten.
    """
    if update.message:
        await update.message.delete()

    chat_id = update.effective_chat.id
    bot_config = context.bot_data.get('config', {})
    status_text = "🔧 **Konfigurasi & Status** 🔧\n\n"
    for key, value in bot_config.items():
        status_text += f"*{key}*: `{value or 'Default'}`\n"
    status_text += f"\n*Build Status*: `{build_manager.status}`"

    panel_id = context.chat_data.get('status_panel_id')

    if panel_id:
        try:
            await context.bot.edit_message_text(
                chat_id=chat_id,
                message_id=panel_id,
                text=status_text,
                parse_mode='Markdown'
            )
            return
        except BadRequest as e:
            if "Message to edit not found" in str(e):
                logger.info("Panel status lama tidak ditemukan, membuat yang baru.")
                panel_id = None
            else:
                logger.error(f"Gagal edit panel status: {e}")
                await send_temporary_message(context, chat_id, f"Gagal update panel status: {e}")
                return
    
    sent_message = await context.bot.send_message(
        chat_id=chat_id,
        text=status_text,
        parse_mode='Markdown'
    )
    context.chat_data['status_panel_id'] = sent_message.message_id
    logger.info(f"Panel status baru dibuat dengan ID: {sent_message.message_id}")

@restricted
async def build_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.delete()
    if build_manager.status in ["Building...", "Preparing"]:
        await send_temporary_message(context, update.effective_chat.id, "❌ Proses build lain sedang berjalan.")
        return
    
    panel_id = context.chat_data.get('status_panel_id')
    if panel_id:
        try:
            await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=panel_id)
            del context.chat_data['status_panel_id']
            logger.info("Panel status lama dihapus karena build baru dimulai.")
        except BadRequest as e:
            if "Message to delete not found" in str(e):
                del context.chat_data['status_panel_id']
            else:
                logger.warning(f"Gagal hapus panel status lama: {e}")

    chat_id = update.effective_message.chat_id
    current_config = context.bot_data.get('config', {})
    context.application.job_queue.run_once(
        lambda ctx: build_manager.run_build_task(ctx, chat_id, current_config),
        0,
        name=f"build_job_{chat_id}"
    )

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
