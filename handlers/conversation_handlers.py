# handlers/conversation_handlers.py (Versi Lengkap dan Benar)

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

# Definisikan state untuk ConversationHandler
# Penamaan yang jelas membantu saat debugging
SET_PACKAGES, SET_OUTPUT_DIR = range(2)

async def setpackages_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai percakapan untuk mengatur paket. Ini adalah entry_point."""
    await update.message.reply_text(
        "Silakan kirimkan daftar paket baru dalam satu pesan (pisahkan dengan spasi).\n"
        "Ketik /cancel untuk membatalkan."
    )
    # Kembalikan state berikutnya
    return SET_PACKAGES

async def receive_packages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menerima dan menyimpan daftar paket baru."""
    packages = update.message.text
    context.bot_data['config']['CUSTOM_PACKAGES'] = packages
    await update.message.reply_text(f"✅ Paket kustom berhasil diatur ke:\n`{packages}`", parse_mode='Markdown')
    # Akhiri percakapan
    return ConversationHandler.END

async def setoutputdir_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai percakapan untuk mengatur direktori output. Ini adalah entry_point."""
    await update.message.reply_text(
        "Silakan kirimkan nama direktori output yang baru.\n"
        "Ketik /cancel untuk membatalkan."
    )
    # Kembalikan state berikutnya
    return SET_OUTPUT_DIR

async def receive_output_dir(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menerima dan menyimpan nama direktori output baru."""
    # Menghapus spasi dan menggantinya dengan underscore untuk nama direktori yang valid
    output_dir = update.message.text.strip().replace(" ", "_")
    context.bot_data['config']['OUTPUT_DIR'] = output_dir
    await update.message.reply_text(f"✅ Direktori output berhasil diatur ke: `{output_dir}`", parse_mode='Markdown')
    # Akhiri percakapan
    return ConversationHandler.END

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan percakapan saat ini (fallback)."""
    await update.message.reply_text("Operasi dibatalkan.")
    # Akhiri percakapan
    return ConversationHandler.END
