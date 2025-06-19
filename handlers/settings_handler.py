# handlers/settings_handler.py

import logging
import os
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.error import BadRequest

from .constants import *
from .utils import restricted, send_temporary_message
from core.openwrt_api import (
    scrape_openwrt_versions,
    scrape_targets_for_version,
    scrape_subtargets_for_target,
    get_device_profiles,
    find_imagebuilder_url_and_name
)
from config import OPENWRT_DOWNLOAD_URL, IMMORTALWRT_DOWNLOAD_URL

logger = logging.getLogger(__name__)

# --- HELPER FUNCTIONS ---

def get_config(context: ContextTypes.DEFAULT_TYPE) -> dict:
    """Mengambil konfigurasi lengkap dari bot data."""
    return context.bot_data.get('config', {})

def save_config(context: ContextTypes.DEFAULT_TYPE, config: dict) -> None:
    """Menyimpan konfigurasi yang diperbarui."""
    context.bot_data['config'] = config
    if 'save_config' in context.bot_data:
        context.bot_data['save_config'](config)

async def _save_menu_message_id(message, context):
    """Menyimpan ID pesan menu untuk dihapus atau diedit nanti."""
    if message:
        context.user_data['settings_menu_id'] = message.message_id
        context.user_data['settings_chat_id'] = message.chat_id

async def _delete_old_menu(context: ContextTypes.DEFAULT_TYPE):
    """Menghapus pesan menu sebelumnya jika ada."""
    menu_id = context.user_data.pop('settings_menu_id', None)
    chat_id = context.user_data.pop('settings_chat_id', None)
    if menu_id and chat_id:
        try:
            await context.bot.delete_message(chat_id=chat_id, message_id=menu_id)
        except BadRequest:
            logger.warning(f"Gagal hapus menu lama (ID: {menu_id}), mungkin sudah dihapus.")
            pass

async def create_paginated_keyboard(items, page, callback_prefix, buttons_per_row=2, back_callback="back_to_official_menu"):
    items_per_page = buttons_per_row * 5; start = page * items_per_page; end = start + items_per_page; keyboard = []
    if not isinstance(items, list): items = list(items)
    paginated_items = items[start:end]
    row_buttons = []
    for item in paginated_items:
        row_buttons.append(InlineKeyboardButton(item, callback_data=f"{callback_prefix}{item}"))
        if len(row_buttons) == buttons_per_row: keyboard.append(row_buttons); row_buttons = []
    if row_buttons: keyboard.append(row_buttons)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("«", callback_data=f"{callback_prefix}page_{page-1}"))
    if end < len(items): nav_row.append(InlineKeyboardButton("»", callback_data=f"{callback_prefix}page_{page+1}"))
    if nav_row: keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("« Kembali", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)

def _get_official_menu_content(context: ContextTypes.DEFAULT_TYPE) -> tuple:
    config_data = get_config(context); config = config_data.get('official', {})
    text = f"⚙️ **Pengaturan Build Resmi** (Mode Aktif: `{config_data.get('active_build_mode', 'N/A').title()}`)"
    source_str = config.get("BUILD_SOURCE", "openwrt").title()
    ver_str = config.get("VERSION", "N/A"); tgt_str = f"{config.get('TARGET', 'N/A')}/{config.get('SUBTARGET', '')}".strip('/'); prof_str = config.get("DEVICE_PROFILE", "N/A"); rootfs_str = (config.get("ROOTFS_SIZE") or "Default"); leech_str = config.get("LEECH_DESTINATION_ID", "me")
    keyboard = [[InlineKeyboardButton(f"☁️ Sumber Build: {source_str}", callback_data="official_set_source")], [InlineKeyboardButton("🔧 Versi", callback_data="official_set_version")], [InlineKeyboardButton(f"🎯 Target: {tgt_str}", callback_data="official_set_target")], [InlineKeyboardButton(f"🆔 Profil: {prof_str[:25]}", callback_data="official_set_profile")], [InlineKeyboardButton(f"💾 RootFS: {rootfs_str}MB", callback_data="official_set_rootfs")], [InlineKeyboardButton("📦 Atur Paket Kustom", callback_data="official_set_packages")], [InlineKeyboardButton(f"🎯 Leech ke: {leech_str}", callback_data="official_set_leech")], [InlineKeyboardButton("🛠️ Kustomisasi Build", callback_data="official_set_customization")], [InlineKeyboardButton("« Kembali", callback_data="back_to_mode_select"), InlineKeyboardButton("✅ Simpan & Tutup", callback_data="settings_save")]]
    return text, InlineKeyboardMarkup(keyboard)

def _get_amlogic_menu_content(context: ContextTypes.DEFAULT_TYPE) -> tuple:
    config = get_config(context).get('amlogic', {}); text = "⚙️ **Pengaturan Amlogic Remake**"
    url_val = config.get("ROOTFS_URL", "Belum Diatur"); board_val = config.get("BOARD", "Belum Diatur"); rootfs_val = (config.get("ROOTFS_SIZE") or "Default"); leech_val = config.get("LEECH_DESTINATION_ID", "me")
    kernel_val = config.get("KERNEL_VERSION", "N/A"); tag_val = config.get("KERNEL_TAG", "stable"); auto_update_val = "ON ✅" if config.get("KERNEL_AUTO_UPDATE", True) else "OFF ❌"; builder_val = config.get("BUILDER_NAME") or "Default"
    keyboard = [[InlineKeyboardButton(f"🌐 URL RootFS: {url_val[:30]}...", callback_data="aml_set_url")], [InlineKeyboardButton(f"📦 Board: {board_val}", callback_data="aml_set_board")], [InlineKeyboardButton(f"💾 RootFS: {rootfs_val}MB", callback_data="aml_set_rootfs")], [InlineKeyboardButton(f"🐧 Versi Kernel: {kernel_val}", callback_data="aml_set_kernel")], [InlineKeyboardButton(f"🏷️ Tag Kernel: {tag_val}", callback_data="aml_set_kernel_tag")], [InlineKeyboardButton(f"⚙️ Auto Update Kernel: {auto_update_val}", callback_data="aml_toggle_auto_update")], [InlineKeyboardButton(f"✒️ Nama Builder: {builder_val}", callback_data="aml_set_builder_name")], [InlineKeyboardButton(f"🎯 Leech ke: {leech_val}", callback_data="aml_set_leech")], [InlineKeyboardButton("« Kembali", callback_data="back_to_mode_select"), InlineKeyboardButton("✅ Simpan & Tutup", callback_data="settings_save")]]
    return text, InlineKeyboardMarkup(keyboard)

def _get_customization_menu_content(context: ContextTypes.DEFAULT_TYPE) -> tuple:
    text = "🛠️ **Menu Kustomisasi Build Resmi**"
    keyboard = [[InlineKeyboardButton("🔗 Atur Custom Repo", callback_data="custom_set_repo")], [InlineKeyboardButton("📜 Upload Skrip uci-defaults", callback_data="custom_upload_uci")], [InlineKeyboardButton("« Kembali", callback_data="back_to_official_menu")]]
    return text, InlineKeyboardMarkup(keyboard)

# --- MENU UTAMA & PEMILIHAN MODE ---
@restricted
async def start_settings_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = [[InlineKeyboardButton("🔧 Build Resmi (Image Builder)", callback_data="mode_official")], [InlineKeyboardButton("💽 Amlogic Remake", callback_data="mode_amlogic")], [InlineKeyboardButton("Tutup", callback_data="action_close")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    message_text = "⚙️ **Mode Pengaturan**\n\nPilih jenis build yang ingin Anda konfigurasi:"
    sent_message = None
    if update.message:
        await _delete_old_menu(context); await update.message.delete()
        sent_message = await update.message.reply_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup, parse_mode='Markdown')
        sent_message = update.callback_query.message
    await _save_menu_message_id(sent_message, context)
    return SELECT_MODE

async def mode_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    mode = query.data.split('_')[1]
    config = get_config(context); config['active_build_mode'] = mode; save_config(context, config)
    if mode == 'official': return await display_official_settings_menu(update, context)
    elif mode == 'amlogic': return await display_amlogic_settings_menu(update, context)

# --- FUNGSI TAMPILAN MENU ---
async def display_official_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, new_message=False) -> int:
    text, reply_markup = _get_official_menu_content(context)
    sent_message = None
    if new_message:
        sent_message = await context.bot.send_message(update.effective_chat.id, text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        query = update.callback_query
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        sent_message = query.message
    await _save_menu_message_id(sent_message, context)
    return MENU

async def display_amlogic_settings_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, new_message=False) -> int:
    text, reply_markup = _get_amlogic_menu_content(context)
    sent_message = None
    if new_message:
        sent_message = await context.bot.send_message(update.effective_chat.id, text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        query = update.callback_query
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        sent_message = query.message
    await _save_menu_message_id(sent_message, context)
    return AML_MENU

async def display_customization_menu(update: Update, context: ContextTypes.DEFAULT_TYPE, new_message=False) -> int:
    text, reply_markup = _get_customization_menu_content(context)
    sent_message = None
    if new_message:
        sent_message = await context.bot.send_message(update.effective_chat.id, text, reply_markup=reply_markup, parse_mode='Markdown')
    else:
        query = update.callback_query
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode='Markdown')
        sent_message = query.message
    await _save_menu_message_id(sent_message, context)
    return CUSTOM_MENU

# --- ROUTER & HANDLER UNTUK BUILD RESMI ---
@restricted
async def official_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    route = query.data.split('_', 2)[-1]
    if route == 'source': return await prompt_build_source(update, context)
    if route == 'customization': return await display_customization_menu(update, context)
    await _delete_old_menu(context)
    prompt_message = await query.message.reply_text("Memuat...", reply_markup=None)
    await _save_menu_message_id(prompt_message, context) 
    bot_config = get_config(context).get('official', {}); source = bot_config.get("BUILD_SOURCE", "openwrt"); base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL
    if route == 'version':
        versions = await scrape_openwrt_versions(base_url)
        if not versions: await prompt_message.edit_text("❌ Gagal mengambil data versi."); await asyncio.sleep(2); return await display_official_settings_menu(update, context)
        keyboard = []; row = []
        for v in versions.keys():
            row.append(InlineKeyboardButton(v, callback_data=f"official_vmajor_{v}"))
            if len(row) == 2: keyboard.append(row); row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("« Kembali", callback_data="back_to_official_menu")]); await prompt_message.edit_text("Pilih seri rilis utama:", reply_markup=InlineKeyboardMarkup(keyboard)); return SELECT_VERSION_MAJOR
    elif route == 'target':
        version = bot_config.get("VERSION")
        if not version: await prompt_message.edit_text("Versi belum diatur!"); await asyncio.sleep(2); return await display_official_settings_menu(update, context)
        targets = await scrape_targets_for_version(version, base_url)
        keyboard = await create_paginated_keyboard(targets, 0, "official_tselect_", 3, "back_to_official_menu"); await prompt_message.edit_text(f"Pilih Target untuk v{version} (Hal 1):", reply_markup=keyboard); return SELECT_TARGET
    elif route == 'profile':
        _, ib_filename = await find_imagebuilder_url_and_name(bot_config.get("VERSION"), bot_config.get("TARGET"), bot_config.get("SUBTARGET"), base_url)
        if not ib_filename or not os.path.isdir(ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")):
            await prompt_message.delete(); await send_temporary_message(context, query.message.chat_id, "Image Builder belum diunduh. Jalankan `/build` mode 'Resmi' sekali."); return ConversationHandler.END
        ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", ""); context.user_data['current_ib_dir'] = ib_dir
        profiles = await get_device_profiles(ib_dir)
        keyboard = await create_paginated_keyboard(profiles, 0, "official_pselect_", back_callback="back_to_official_menu"); await prompt_message.edit_text("Pilih Profil Perangkat (Hal 1):", reply_markup=keyboard); return SELECT_PROFILE
    elif route == 'packages':
        await prompt_message.edit_text("Tempel daftar paket untuk Build Resmi:"); return AWAITING_PACKAGES
    elif route == 'rootfs':
        await prompt_message.edit_text("Kirim ukuran RootFS baru dalam MB (angka saja):"); return AWAITING_ROOTFS_SIZE
    elif route == 'leech':
        await prompt_message.edit_text("Kirim ID Grup/Channel atau 'me' untuk Leech Build Resmi:"); return AWAITING_LEECH_DEST_OFFICIAL
    await prompt_message.delete(); return MENU

async def back_to_official_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    return await display_official_settings_menu(update, context)

async def prompt_build_source(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    keyboard = [[InlineKeyboardButton("OpenWrt (Resmi)", callback_data="select_source_openwrt")], [InlineKeyboardButton("ImmortalWrt", callback_data="select_source_immortalwrt")], [InlineKeyboardButton("« Kembali", callback_data="back_to_official_menu")]]
    await query.edit_message_text("Pilih sumber unduhan untuk Image Builder:", reply_markup=InlineKeyboardMarkup(keyboard))
    return SELECT_BUILD_SOURCE

async def select_build_source_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); source = query.data.split('_')[-1]
    config = get_config(context)
    config['official']['BUILD_SOURCE'] = source; config['official']['VERSION'] = ""; config['official']['TARGET'] = ""; config['official']['SUBTARGET'] = ""; config['official']['DEVICE_PROFILE'] = ""
    save_config(context, config)
    await send_temporary_message(context, query.message.chat_id, f"✅ Sumber build diatur ke {source.title()}. Konfigurasi Versi/Target direset.")
    return await display_official_settings_menu(update, context)

@restricted
async def select_version_major_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    major_series = query.data.replace("official_vmajor_", ""); bot_config = get_config(context).get('official', {})
    source = bot_config.get("BUILD_SOURCE", "openwrt"); base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL
    versions = await scrape_openwrt_versions(base_url)
    buttons = [[InlineKeyboardButton(v, callback_data=f"official_vminor_{v}")] for v in versions.get(major_series, [])]
    buttons.append([InlineKeyboardButton("« Kembali", callback_data="official_set_version")])
    await query.edit_message_text(f"Pilih versi spesifik untuk seri {major_series}:", reply_markup=InlineKeyboardMarkup(buttons)); return SELECT_VERSION_MINOR

@restricted
async def select_version_minor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); config = get_config(context)
    config['official']['VERSION'] = query.data.replace("official_vminor_", ""); save_config(context, config)
    return await display_official_settings_menu(update, context)

@restricted
async def select_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); config = get_config(context)
    bot_config = config.get('official', {}); data = query.data; version = bot_config.get("VERSION")
    source = bot_config.get("BUILD_SOURCE", "openwrt"); base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL
    if data.startswith("official_tselect_page_"):
        page = int(data.split('_')[-1]); targets = await scrape_targets_for_version(version, base_url)
        keyboard = await create_paginated_keyboard(targets, page, "official_tselect_", 3, "back_to_official_menu")
        await query.edit_message_text(f"Pilih Target untuk v{version} (Halaman {page + 1}):", reply_markup=keyboard); return SELECT_TARGET
    selected_target = data.replace("official_tselect_", ""); config['official']['TARGET'] = selected_target
    subtargets = await scrape_subtargets_for_target(version, selected_target, base_url)
    if not subtargets:
        config['official']['SUBTARGET'] = ""; save_config(context, config)
        await query.edit_message_text(f"✅ Target diatur ke: *{selected_target}* (tidak ada subtarget).", parse_mode='Markdown'); await asyncio.sleep(1)
        return await display_official_settings_menu(update, context)
    buttons = [[InlineKeyboardButton(st, callback_data=f"official_stselect_{st}")] for st in subtargets]
    buttons.append([InlineKeyboardButton("« Kembali", callback_data="official_set_target")])
    await query.edit_message_text(f"Target: *{selected_target}*. Pilih Subtarget:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons))
    save_config(context, config); return SELECT_SUBTARGET

@restricted
async def select_subtarget_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); config = get_config(context)
    config['official']['SUBTARGET'] = query.data.replace("official_stselect_", ""); save_config(context, config)
    await query.edit_message_text(f"✅ Subtarget diatur.", parse_mode='Markdown'); await asyncio.sleep(1)
    return await display_official_settings_menu(update, context)

@restricted
async def select_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); config = get_config(context); data = query.data
    if data.startswith("official_pselect_page_"):
        page = int(data.split('_')[-1]); ib_dir = context.user_data.get('current_ib_dir')
        if not ib_dir: return await start_settings_conversation(update, context)
        profiles = await get_device_profiles(ib_dir)
        keyboard = await create_paginated_keyboard(profiles, page, "official_pselect_", back_callback="back_to_official_menu")
        await query.edit_message_text(f"Pilih Profil Perangkat (Halaman {page + 1}):", reply_markup=keyboard); return SELECT_PROFILE
    profile = data.replace("official_pselect_", ""); config['official']['DEVICE_PROFILE'] = profile
    save_config(context, config); context.user_data.pop('current_ib_dir', None)
    await query.edit_message_text(f"✅ Profil diatur ke: *{profile}*", parse_mode='Markdown'); await asyncio.sleep(1)
    return await display_official_settings_menu(update, context)

async def _return_from_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE, mode: str):
    await update.message.delete(); await _delete_old_menu(context)
    await send_temporary_message(context, update.effective_chat.id, "✅ Pengaturan disimpan.")
    if mode == 'official': text, reply_markup = _get_official_menu_content(context); next_state = MENU
    elif mode == 'amlogic': text, reply_markup = _get_amlogic_menu_content(context); next_state = AML_MENU
    elif mode == 'customization': text, reply_markup = _get_customization_menu_content(context); next_state = CUSTOM_MENU
    else: return ConversationHandler.END
    sent_message = await context.bot.send_message(update.effective_chat.id, text=text, reply_markup=reply_markup, parse_mode='Markdown')
    await _save_menu_message_id(sent_message, context)
    return next_state

@restricted
async def receive_official_packages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['official']['CUSTOM_PACKAGES'] = ' '.join(update.message.text.split()); save_config(context, config)
    return await _return_from_message_handler(update, context, 'official')

@restricted
async def receive_official_rootfs(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip(); config = get_config(context)
    if user_input in ['0', 'default', '']: config['official']['ROOTFS_SIZE'] = ""
    elif user_input.isdigit(): config['official']['ROOTFS_SIZE'] = user_input
    else:
        await update.message.delete(); await send_temporary_message(context, update.effective_chat.id, "Input tidak valid, harus angka.")
        prompt_message = await context.bot.send_message(update.effective_chat.id, "Kirim ukuran RootFS baru dalam MB (angka saja):")
        await _save_menu_message_id(prompt_message, context); return AWAITING_ROOTFS_SIZE
    save_config(context, config); return await _return_from_message_handler(update, context, 'official')

@restricted
async def receive_official_leech_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['official']['LEECH_DESTINATION_ID'] = update.message.text.strip(); save_config(context, config)
    return await _return_from_message_handler(update, context, 'official')

@restricted
async def aml_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); route = query.data.split('_', 2)[-1]
    if route == 'auto_update': return await toggle_aml_auto_update(update, context)
    await _delete_old_menu(context)
    prompt_message = await query.message.reply_text("Memuat...")
    await _save_menu_message_id(prompt_message, context)
    prompts = {'url': "Kirim URL ke `rootfs.img.gz` atau `.xz`.", 'board': "Kirim nama `BOARD` (contoh: hk1box).", 'rootfs': "Kirim ukuran RootFS baru dalam MB:", 'leech': "Kirim ID Grup/Channel atau 'me':", 'kernel': "Kirim Versi Kernel (contoh: 5.15.y):", 'kernel_tag': "Kirim Tag Kernel (e.g., stable, flippy):", 'builder_name': "Kirim Nama Builder Anda:"}
    states = {'url': AWAITING_AML_ROOTFS_URL, 'board': AWAITING_AML_BOARD, 'rootfs': AWAITING_AML_ROOTFS_SIZE, 'leech': AWAITING_LEECH_DEST_AML, 'kernel': AWAITING_AML_KERNEL, 'kernel_tag': AWAITING_AML_KERNEL_TAG, 'builder_name': AWAITING_AML_BUILDER_NAME}
    if route in prompts:
        await prompt_message.edit_message_text(prompts[route], parse_mode='Markdown'); return states[route]
    await prompt_message.delete(); return AML_MENU

async def toggle_aml_auto_update(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); config = get_config(context)
    current_state = config.get('amlogic', {}).get('KERNEL_AUTO_UPDATE', True)
    config['amlogic']['KERNEL_AUTO_UPDATE'] = not current_state; save_config(context, config)
    return await display_amlogic_settings_menu(update, context)

@restricted
async def receive_aml_rootfs_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    url = update.message.text.strip()
    if not (url.startswith('http') and (url.endswith('.gz') or url.endswith('.xz'))): await send_temporary_message(context, update.effective_chat.id, "URL tidak valid.")
    else: config = get_config(context); config['amlogic']['ROOTFS_URL'] = url; save_config(context, config)
    return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def receive_aml_board(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['amlogic']['BOARD'] = update.message.text.strip().lower(); save_config(context, config)
    return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def receive_aml_rootfs_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip(); config = get_config(context)
    if user_input in ['0', 'default', '']: config['amlogic']['ROOTFS_SIZE'] = ""
    elif user_input.isdigit(): config['amlogic']['ROOTFS_SIZE'] = user_input
    else:
        await update.message.delete(); await send_temporary_message(context, update.effective_chat.id, "Input tidak valid, harus angka.")
        prompt_message = await context.bot.send_message(update.effective_chat.id, "Kirim ukuran RootFS baru dalam MB (angka saja):")
        await _save_menu_message_id(prompt_message, context); return AWAITING_AML_ROOTFS_SIZE
    save_config(context, config); return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def receive_aml_leech_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['amlogic']['LEECH_DESTINATION_ID'] = update.message.text.strip(); save_config(context, config)
    return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def receive_aml_kernel_tag(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['amlogic']['KERNEL_TAG'] = update.message.text.strip().lower(); save_config(context, config)
    return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def receive_aml_builder_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['amlogic']['BUILDER_NAME'] = update.message.text.strip(); save_config(context, config)
    return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def receive_aml_kernel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); config['amlogic']['KERNEL_VERSION'] = update.message.text.strip().lower(); save_config(context, config)
    return await _return_from_message_handler(update, context, 'amlogic')

@restricted
async def customization_menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); route = query.data.split('_', 2)[-1]
    await _delete_old_menu(context)
    prompt_message = await query.message.reply_text("Memuat...")
    await _save_menu_message_id(prompt_message, context)
    if route == 'repo':
        await prompt_message.edit_message_text("Tempel satu atau beberapa URL custom repo, pisahkan dengan baris baru (enter).")
        return AWAITING_CUSTOM_REPOS
    elif route == 'uci':
        await prompt_message.edit_text("Kirim file skrip `.sh` untuk uci-defaults sebagai dokumen.")
        return AWAITING_UCI_SCRIPT
    await prompt_message.delete(); return CUSTOM_MENU

@restricted
async def receive_custom_repos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    config = get_config(context); official_config = config.get('official', {})
    arch_key = f"{official_config.get('BUILD_SOURCE', 'openwrt')}_{official_config.get('TARGET', 'na')}_{official_config.get('SUBTARGET', 'na')}"
    if 'CUSTOM_REPOS' not in config['official'] or not isinstance(config['official']['CUSTOM_REPOS'], dict):
        config['official']['CUSTOM_REPOS'] = {}
    config['official']['CUSTOM_REPOS'][arch_key] = update.message.text
    save_config(context, config)
    return await _return_from_message_handler(update, context, 'customization')

@restricted
async def handle_uci_script_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    document = update.message.document
    if not document or not document.file_name.endswith('.sh'):
        await send_temporary_message(context, update.effective_chat.id, "File tidak valid. Harap kirim skrip `.sh`."); return await _return_from_message_handler(update, context, 'customization')
    bot_config = get_config(context).get('official', {}); source = bot_config.get("BUILD_SOURCE", "openwrt"); base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL
    _, ib_filename = await find_imagebuilder_url_and_name(bot_config.get("VERSION"), bot_config.get("TARGET"), bot_config.get("SUBTARGET"), base_url)
    if not ib_filename:
        await send_temporary_message(context, update.effective_chat.id, "❌ Tidak dapat menentukan direktori Image Builder."); return await _return_from_message_handler(update, context, 'customization')
    ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", ""); uci_path = os.path.join(ib_dir, "files", "etc", "uci-defaults")
    os.makedirs(uci_path, exist_ok=True); file_obj = await document.get_file()
    await file_obj.download_to_drive(os.path.join(uci_path, document.file_name))
    return await _return_from_message_handler(update, context, 'customization')

@restricted
async def save_and_exit_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); save_config(context, get_config(context))
    await _delete_old_menu(context)
    await send_temporary_message(context, query.message.chat_id, "✅ Semua pengaturan telah disimpan.")
    return ConversationHandler.END

@restricted
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    await _delete_old_menu(context)
    chat_id = update.effective_chat.id
    if update.message: await update.message.delete()
    await send_temporary_message(context, chat_id, "Pengaturan dibatalkan.")
    return ConversationHandler.END
