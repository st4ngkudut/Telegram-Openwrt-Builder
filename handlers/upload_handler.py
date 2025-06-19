# handlers/upload_handler.py

import logging
import os
import shutil
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler

from .constants import UPLOAD_ROOTFS, UPLOAD_IPK
from .utils import restricted, send_temporary_message
from .settings_handler import _save_menu_message_id, _delete_old_menu, get_config
from core.openwrt_api import find_imagebuilder_url_and_name
from config import AML_BUILD_SCRIPT_DIR, OPENWRT_DOWNLOAD_URL, IMMORTALWRT_DOWNLOAD_URL

logger = logging.getLogger(__name__)

# --- UPLOAD ROOTFS (FOR AMLOGIC) ---

@restricted
async def start_rootfs_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai sesi upload rootfs."""
    await update.message.delete()
    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Silakan kirim file `rootfs` Anda sebagai dokumen.",
        parse_mode='Markdown'
    )
    # Simpan ID pesan prompt untuk dihapus nanti
    await _save_menu_message_id(sent_message, context)
    return UPLOAD_ROOTFS

@restricted
async def handle_rootfs_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangani file rootfs yang diunggah oleh pengguna."""
    await _delete_old_menu(context) # Hapus pesan prompt
    await update.message.delete() # Hapus pesan pengguna yang berisi file

    document = update.message.document
    if not document:
        await send_temporary_message(context, update.effective_chat.id, "Ini bukan file. Mohon kirim file rootfs.")
        return UPLOAD_ROOTFS

    rootfs_dest_dir = os.path.join(AML_BUILD_SCRIPT_DIR, "openwrt-armsr")
    os.makedirs(rootfs_dest_dir, exist_ok=True)
    file_path = os.path.join(rootfs_dest_dir, document.file_name)

    try:
        status_message = await context.bot.send_message(chat_id=update.effective_chat.id, text=f"📥 Mengunduh `{document.file_name}`...")
        file_obj = await document.get_file()
        await file_obj.download_to_drive(file_path)
        
        await status_message.delete()
        await send_temporary_message(context, update.effective_chat.id, f"✅ File `{document.file_name}` berhasil diunggah ke pustaka Amlogic.")
        logger.info(f"Rootfs {document.file_name} diunggah ke {file_path}")

    except Exception as e:
        logger.error(f"Gagal mengunduh rootfs: {e}", exc_info=True)
        if status_message: await status_message.delete()
        await send_temporary_message(context, update.effective_chat.id, f"❌ Terjadi kesalahan saat mengunduh file: {e}")

    return ConversationHandler.END

# --- UPLOAD IPK (FOR OFFICIAL BUILD) ---

@restricted
async def start_ipk_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai sesi upload file .ipk."""
    await update.message.delete()
    
    official_config = get_config(context).get('official', {})
    source = official_config.get("BUILD_SOURCE", "openwrt")
    base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL

    _, ib_filename = await find_imagebuilder_url_and_name(
        official_config.get("VERSION"), official_config.get("TARGET"), official_config.get("SUBTARGET"), base_url
    )
    if not ib_filename:
        await send_temporary_message(context, update.effective_chat.id, "❌ Tidak dapat menentukan direktori Image Builder. Pastikan konfigurasi Build Resmi Anda valid.")
        return ConversationHandler.END
    
    ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")
    
    upload_path = os.path.join(ib_dir, "packages")
    context.user_data['ipk_upload_path'] = upload_path

    sent_message = await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=f"Silakan kirim satu atau beberapa file `.ipk`.\nFile akan disimpan di `{upload_path}`\n\nKirim /cancel untuk selesai.",
        parse_mode='Markdown'
    )
    await _save_menu_message_id(sent_message, context)
    return UPLOAD_IPK

@restricted
async def handle_ipk_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangani file .ipk yang diunggah."""
    # Hapus pesan pengguna yang berisi file
    await update.message.delete()
    
    # Cek apakah ini album atau file tunggal
    attachments = update.message.document or []
    if not isinstance(attachments, list):
        attachments = [attachments]

    if not attachments:
        await send_temporary_message(context, update.effective_chat.id, "Ini bukan file. Mohon kirim file .ipk.")
        return UPLOAD_IPK
        
    upload_path = context.user_data.get('ipk_upload_path')
    if not upload_path:
        await send_temporary_message(context, update.effective_chat.id, "❌ Sesi upload kedaluwarsa. Silakan mulai ulang /upload_ipk.")
        await _delete_old_menu(context)
        return ConversationHandler.END
        
    os.makedirs(upload_path, exist_ok=True)
    
    successful_uploads = []
    failed_uploads = []

    for doc in attachments:
        if not doc.file_name.endswith('.ipk'):
            failed_uploads.append(doc.file_name)
            continue
        
        file_path = os.path.join(upload_path, doc.file_name)
        try:
            file_obj = await doc.get_file()
            await file_obj.download_to_drive(file_path)
            successful_uploads.append(doc.file_name)
            logger.info(f"IPK {doc.file_name} diunggah ke {file_path}")
        except Exception as e:
            failed_uploads.append(doc.file_name)
            logger.error(f"Gagal mengunduh IPK {doc.file_name}: {e}", exc_info=True)

    report_text = ""
    if successful_uploads:
        report_text += f"✅ Berhasil mengunggah: " + ", ".join(successful_uploads)
    if failed_uploads:
        report_text += f"\n\n❌ Gagal mengunggah: " + ", ".join(failed_uploads)
    
    await send_temporary_message(context, update.effective_chat.id, report_text.strip())
    
    # Jangan akhiri sesi, biarkan pengguna mengirim lebih banyak file
    # Sesi akan berakhir via /cancel atau timeout
    return UPLOAD_IPK

# --- CANCEL HANDLER ---

@restricted
async def cancel_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan sesi upload."""
    await _delete_old_menu(context) # Hapus pesan prompt
    if update.message:
        await update.message.delete()
    await send_temporary_message(context, update.effective_chat.id, "Proses upload selesai.")
    context.user_data.pop('ipk_upload_path', None)
    return ConversationHandler.END
