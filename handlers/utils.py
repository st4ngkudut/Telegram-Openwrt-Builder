# handlers/utils.py

import logging
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes

from config import AUTHORIZED_USER_IDS

logger = logging.getLogger(__name__)

def restricted(func):
    """Decorator untuk membatasi akses ke pengguna yang diizinkan."""
    @wraps(func)
    async def wrapped(update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        if not user:
            return
        
        user_id = user.id

        if user_id not in AUTHORIZED_USER_IDS:
            logger.warning(f"Akses ditolak untuk user ID: {user_id}")
            if update.callback_query:
                await update.callback_query.answer("⛔ Anda tidak diizinkan melakukan aksi ini.", show_alert=True)
            elif update.message:
                await update.message.reply_text("⛔ Maaf, Anda tidak diizinkan menggunakan bot ini.")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapped
