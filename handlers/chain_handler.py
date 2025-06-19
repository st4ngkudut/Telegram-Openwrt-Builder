# handlers/chain_handler.py

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .constants import *
from .utils import restricted, send_temporary_message
from core.build_manager import build_manager
from .settings_handler import start_settings_conversation, get_config, save_config # Impor fungsi yang relevan
from core.history_manager import load_history

logger = logging.getLogger(__name__)

# --- Helper untuk menampilkan konfirmasi ---
async def display_chain_preflight_check(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan layar konfirmasi untuk Amlogic Remake dari sumber lokal."""
    query = update.callback_query
    await query.answer()

    aml_config = get_config(context).get('amlogic', {})
    local_rootfs_path = context.user_data.get('local_rootfs_path')
    
    if not local_rootfs_path:
        await query.edit_message_text("❌ Error: Path rootfs lokal tidak ditemukan di sesi.")
        return ConversationHandler.END

    text = (
        f"🚨 **Konfirmasi Amlogic Remake** 🚨\n\n"
        f"Akan menggunakan `rootfs` dari file lokal:\n`{os.path.basename(local_rootfs_path)}`\n\n"
        "Dengan pengaturan Amlogic berikut:\n"
        f"- *Board:* `{aml_config.get('BOARD', 'N/A')}`\n"
        f"- *Ukuran RootFS:* `{aml_config.get('ROOTFS_SIZE', 'Default')}MB`\n"
        f"- *Kernel:* `{aml_config.get('KERNEL_VERSION', 'N/A')}-{aml_config.get('KERNEL_TAG', 'stable')}`\n\n"
        "Anda yakin ingin melanjutkan?"
    )

    keyboard = [
        [InlineKeyboardButton("✅ Ya, Lanjutkan Remake", callback_data="chain_confirm_start")],
        [InlineKeyboardButton("✏️ Ubah Pengaturan Amlogic", callback_data="chain_goto_settings")],
        [InlineKeyboardButton("❌ Batal", callback_data="chain_cancel")]
    ]

    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown')
    return CHAIN_CONFIRM_AML

# --- Entry Point untuk alur build berantai ---
@restricted
async def start_chain_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai alur dari tombol 'Lanjutkan ke Remake' atau 'Gunakan dari Arsip'."""
    query = update.callback_query
    await query.answer()
    
    try:
        build_id = query.data.split('_')[-1]
    except (ValueError, IndexError):
        await query.edit_message_text("❌ Error: Build ID tidak valid."); return ConversationHandler.END

    history = load_history()
    source_build = next((item for item in history if item['id'] == build_id), None)
    if not source_build:
        await query.edit_message_text("❌ Error: Build sumber tidak ditemukan di histori."); return ConversationHandler.END
        
    # Cari file rootfs di dalam build sumber
    rootfs_path = None
    for path in source_build.get('firmware_files', {}).values():
        if 'rootfs' in path:
            rootfs_path = path
            break
    
    if not rootfs_path or not os.path.exists(rootfs_path):
        await query.edit_message_text("❌ Error: File `rootfs` tidak ditemukan di dalam arsip build ini."); return ConversationHandler.END
        
    context.user_data['local_rootfs_path'] = rootfs_path
    
    return await display_chain_preflight_check(update, context)

# --- Handler untuk tombol-tombol di layar konfirmasi ---
@restricted
async def confirm_chain_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mengkonfirmasi dan memulai Amlogic Remake dengan rootfs lokal."""
    query = update.callback_query
    await query.answer()
    
    local_rootfs_path = context.user_data.get('local_rootfs_path')
    if not local_rootfs_path:
        await query.edit_message_text("❌ Sesi kedaluwarsa, path rootfs tidak ditemukan."); return ConversationHandler.END

    await query.edit_message_text("✅ Permintaan Amlogic Remake diterima. Mempersiapkan job...", reply_markup=None)

    # Siapkan config khusus untuk job ini
    config_full = get_config(context)
    build_config = config_full.get('amlogic', {}).copy() # Salin agar tidak mengubah config asli
    build_config['local_rootfs_path'] = local_rootfs_path # Suntikkan path rootfs lokal

    chat_id = query.message.chat_id
    
    # Hapus panel status lama jika ada
    panel_id = context.chat_data.pop('status_panel_id', None)
    if panel_id:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=panel_id)
        except Exception: pass

    # Jalankan tugas build dengan config yang sudah disuntik path lokal
    context.application.job_queue.run_once(
        lambda ctx: build_manager.run_build_task(ctx, chat_id, build_config, 'amlogic'),
        0,
        name=f"build_job_{chat_id}"
    )
    
    context.user_data.pop('local_rootfs_path', None)
    return ConversationHandler.END

@restricted
async def chain_goto_settings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan chain build dan mengarahkan ke menu settings."""
    query = update.callback_query
    await query.answer()

    # Set mode aktif ke amlogic agar langsung masuk ke menu yang benar
    config = get_config(context)
    config['active_build_mode'] = 'amlogic'
    save_config(context, config)

    await query.edit_message_text("Membuka menu pengaturan Amlogic...")
    await start_settings_conversation(update, context)

    return ConversationHandler.END

@restricted
async def cancel_chain_build(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan proses chain build."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Proses remake dibatalkan.")
    context.user_data.pop('local_rootfs_path', None)
    return ConversationHandler.END
