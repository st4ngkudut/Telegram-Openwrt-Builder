# handlers/utils.py

import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes
from telegram.error import BadRequest

from config import AUTHORIZED_USER_IDS, TEMP_MESSAGE_DURATION

logger = logging.getLogger(__name__)

def restricted(func):
    """Decorator untuk membatasi akses ke pengguna yang diizinkan."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user or user.id not in AUTHORIZED_USER_IDS:
            logger.warning(f"Akses ditolak untuk user ID: {user.id if user else 'Unknown'}")
            if update.callback_query:
                await update.callback_query.answer("⛔ Anda tidak diizinkan.", show_alert=True)
            elif update.message:
                await update.message.reply_text("⛔ Maaf, Anda tidak diizinkan menggunakan bot ini.")
            return
        return await func(update, context, *args, **kwargs)
    return wrapped

async def delete_message_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Tugas yang dijadwalkan untuk menghapus pesan."""
    try:
        await context.bot.delete_message(
            chat_id=context.job.chat_id,
            message_id=context.job.data['message_id']
        )
    except BadRequest as e:
        if "Message to delete not found" not in str(e):
            logger.warning(f"Gagal menghapus pesan terjadwal: {e}")

async def send_temporary_message(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str, **kwargs):
    """Mengirim pesan yang akan hilang otomatis setelah durasi tertentu."""
    try:
        sent_message = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            **kwargs
        )
        context.job_queue.run_once(
            delete_message_job,
            TEMP_MESSAGE_DURATION,
            data={'message_id': sent_message.message_id},
            chat_id=chat_id
        )
    except Exception as e:
        logger.error(f"Gagal mengirim pesan temporer: {e}")
