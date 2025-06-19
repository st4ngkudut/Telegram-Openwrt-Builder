# handlers/build_handler.py

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .constants import *
from .utils import restricted, send_temporary_message
from core.build_manager import build_manager
from core.openwrt_api import get_device_profiles, find_imagebuilder_url_and_name
from config import OPENWRT_DOWNLOAD_URL, IMMORTALWRT_DOWNLOAD_URL

logger = logging.getLogger(__name__)

# --- Helper Functions ---
def get_config(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.bot_data.get('config', {})

def save_config(context: ContextTypes.DEFAULT_TYPE, config: dict) -> None:
    context.bot_data['config'] = config
    if 'save_config' in context.bot_data:
        context.bot_data['save_config'](config)

async def _display_preflight_check(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    """Menampilkan layar konfirmasi sebelum build dimulai, dengan validasi proaktif."""
    query = update.callback_query
    config_full = get_config(context)
    config = config_full.get(mode, {})

    await query.edit_message_text(f"Mengecek konfigurasi untuk mode: {mode.title()}...")
    
    text = f"🚨 **Konfirmasi Build (Mode: {mode.title()})** 🚨\n\n"
    keyboard = []
    
    if mode == 'official':
        conf = config
        source = conf.get("BUILD_SOURCE", "openwrt"); base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL
        _, ib_filename = await find_imagebuilder_url_and_name(conf.get("VERSION"), conf.get("TARGET"), conf.get("SUBTARGET"), base_url)
        
        is_valid = True
        if ib_filename and os.path.isdir(ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")):
            ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")
            valid_profiles = await get_device_profiles(ib_dir)
            if conf.get("DEVICE_PROFILE") not in valid_profiles:
                is_valid = False
                text = f"⚠️ **Profil `{conf.get('DEVICE_PROFILE')}` tidak valid!**\n\nPilih profil yang benar dari daftar di bawah untuk melanjutkan:"
                keyboard = [[InlineKeyboardButton(p, callback_data=f"build_fix_profile_{p}")] for p in valid_profiles[:20]]
                keyboard.append([InlineKeyboardButton("❌ Batal", callback_data="build_cancel")])
                await query.edit_message_text(text, parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(keyboard))
                return AWAITING_PROFILE_FIX
        
        if is_valid:
            text += "Bot akan memulai proses build dengan pengaturan berikut:\n\n"
            text += f"*Sumber:* `{conf.get('BUILD_SOURCE', 'N/A').title()}`\n"
            text += f"*Versi:* `{conf.get('VERSION', 'N/A')}`\n"
            text += f"*Profil:* `{conf.get('DEVICE_PROFILE', 'N/A')}`\n"
            text += f"*Paket:* `{conf.get('CUSTOM_PACKAGES', 'N/A')[:50]}...`\n"
    elif mode == 'amlogic':
        conf = config
        text += "Bot akan memulai proses Amlogic Remake dengan pengaturan berikut:\n\n"
        text += f"*URL RootFS:* `{conf.get('ROOTFS_URL', 'N/A')[:50]}...`\n"
        text += f"*Board:* `{conf.get('BOARD', 'N/A')}`\n"
        text += f"*Ukuran RootFS:* `{conf.get('ROOTFS_SIZE', 'Default')}MB`\n"

    text += "\nAnda yakin ingin melanjutkan?"
    
    if not keyboard:
        keyboard = [
            [InlineKeyboardButton("✅ Ya, Mulai Build", callback_data=f"build_confirm_{mode}")],
            [InlineKeyboardButton("✏️ Ubah Pengaturan", callback_data=f"build_goto_settings_{mode}")],
            [InlineKeyboardButton("❌ Batal", callback_data="build_cancel")]
        ]
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
    return CONFIRM_BUILD

# --- Conversation Handlers for /build ---

@restricted
async def start_build_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Titik masuk untuk percakapan /build."""
    await update.message.delete()
    
    if build_manager.is_starting_build or build_manager.status not in ["Idle", "Success", "Failed", "Cancelled"]:
        await send_temporary_message(context, update.effective_chat.id, "❌ Harap selesaikan atau batalkan permintaan build sebelumnya.")
        return ConversationHandler.END
    
    # Kunci sistem
    build_manager.is_starting_build = True

    keyboard = [
        [InlineKeyboardButton("🔧 Build Resmi", callback_data="build_mode_official")],
        [InlineKeyboardButton("💽 Amlogic Remake", callback_data="build_mode_amlogic")],
        [InlineKeyboardButton("Batal", callback_data="build_cancel")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Pilih mode build yang ingin Anda jalankan:",
        reply_markup=reply_markup
    )
    return SELECT_BUILD_MODE

@restricted
async def select_build_mode_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangani pemilihan mode dan menampilkan pre-flight check."""
    query = update.callback_query
    await query.answer()
    mode = query.data.split('_')[-1]
    
    context.user_data['build_mode'] = mode
    
    return await _display_preflight_check(update, context, mode)

@restricted
async def confirm_build_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai proses build setelah konfirmasi."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("✅ Permintaan build diterima. Mempersiapkan job...", reply_markup=None)

    mode = context.user_data.get('build_mode')
    config = get_config(context)
    build_config = config.get(mode, {})
    
    chat_id = query.message.chat_id
    
    panel_id = context.chat_data.pop('status_panel_id', None)
    if panel_id:
        try: await context.bot.delete_message(chat_id=chat_id, message_id=panel_id)
        except Exception: pass

    context.application.job_queue.run_once(
        lambda ctx: build_manager.run_build_task(ctx, chat_id, build_config, mode),
        0,
        name=f"build_job_{chat_id}"
    )
    
    # Buka kunci setelah job berhasil dimulai
    build_manager.is_starting_build = False
    return ConversationHandler.END

@restricted
async def fix_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangani saat pengguna memilih profil yang benar setelah error."""
    query = update.callback_query
    await query.answer()
    
    new_profile = query.data.replace("build_fix_profile_", "")
    
    config_full = get_config(context)
    config_full['official']['DEVICE_PROFILE'] = new_profile
    save_config(context, config_full)
    
    await query.edit_message_text(f"✅ Profil diperbarui ke `{new_profile}`. Mengulangi konfirmasi build...", parse_mode='Markdown')
    
    # Kembali ke layar konfirmasi dengan profil yang sudah benar
    return await _display_preflight_check(update, context, 'official')

@restricted
async def request_settings_change_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan build dan memberi instruksi untuk menjalankan /settings."""
    query = update.callback_query
    await query.answer()

    await query.edit_message_text(
        "Permintaan build dibatalkan.\n\n"
        "Silakan jalankan `/settings` untuk mengubah konfigurasi, lalu mulai `/build` kembali.",
        reply_markup=None
    )
    # Buka kunci saat dibatalkan
    build_manager.is_starting_build = False
    return ConversationHandler.END

@restricted
async def cancel_build_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan percakapan build."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("Permintaan build dibatalkan.")
    context.user_data.pop('build_mode', None)
    # Buka kunci saat dibatalkan
    build_manager.is_starting_build = False
    return ConversationHandler.END
