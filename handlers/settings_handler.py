# handlers/settings_handler.py

import logging
import os
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from .utils import restricted
from core.openwrt_api import (
    scrape_openwrt_versions,
    scrape_targets_for_version,
    scrape_subtargets_for_target,
    get_device_profiles,
    find_imagebuilder_url_and_name
)

logger = logging.getLogger(__name__)

(
    MENU,
    AWAITING_PACKAGES, AWAITING_ROOTFS_SIZE, AWAITING_LEECH_DEST,
    SELECT_VERSION_MAJOR, SELECT_VERSION_MINOR,
    SELECT_TARGET, SELECT_SUBTARGET,
    SELECT_PROFILE,
    SELECT_UPLOAD_PATTERN
) = range(10)


async def create_main_settings_keyboard():
    keyboard = [
        [
            InlineKeyboardButton("🔧 Ubah Versi", callback_data="settings_version"),
            InlineKeyboardButton("🎯 Ubah Target/Subtarget", callback_data="settings_target")
        ],
        [
            InlineKeyboardButton("🆔 Ubah Profil Perangkat", callback_data="settings_profile"),
            InlineKeyboardButton("💾 Ukuran RootFS", callback_data="settings_rootfs")
        ],
        [
            InlineKeyboardButton("📦 Ubah Paket Kustom", callback_data="settings_packages"),
            InlineKeyboardButton("📄 Pola File Upload", callback_data="settings_filename_pattern")
        ],
        [
            InlineKeyboardButton("🎯 Tujuan Leech", callback_data="settings_leech_dest"),
            InlineKeyboardButton("Tutup", callback_data="settings_close")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def create_paginated_keyboard(items, page, callback_prefix, buttons_per_row=2, back_callback="back_to_main_menu"):
    items_per_page = buttons_per_row * 5; start = page * items_per_page; end = start + items_per_page; keyboard = []; row = []
    for item in items[start:end]:
        button = InlineKeyboardButton(item, callback_data=f"{callback_prefix}{item}"); row.append(button)
        if len(row) == buttons_per_row: keyboard.append(row); row = []
    if row: keyboard.append(row)
    nav_row = []
    if page > 0: nav_row.append(InlineKeyboardButton("«", callback_data=f"{callback_prefix}page_{page-1}"))
    if end < len(items): nav_row.append(InlineKeyboardButton("»", callback_data=f"{callback_prefix}page_{page+1}"))
    if nav_row: keyboard.append(nav_row)
    keyboard.append([InlineKeyboardButton("« Kembali ke Menu", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)

@restricted
async def start_settings_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    keyboard = await create_main_settings_keyboard()
    message_text = "⚙️ **Menu Pengaturan**\nPilih parameter yang ingin diubah:"
    if update.message:
        await update.message.reply_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
    elif update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(message_text, reply_markup=keyboard, parse_mode='Markdown')
        except Exception as e:
            logger.warning(f"Gagal edit pesan kembali ke menu utama: {e}")
            await context.bot.send_message(chat_id=update.effective_chat.id, text=message_text, reply_markup=keyboard, parse_mode='Markdown')
            
    return MENU

@restricted
async def menu_router(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    route = query.data; bot_config = context.bot_data.get('config', {})
    if route == 'back_to_main_menu': return await start_settings_conversation(update, context)
    if route == 'settings_close': await query.edit_message_text("Mode pengaturan ditutup."); return ConversationHandler.END
    if route == 'settings_packages': await query.edit_message_text("Silakan tempel (paste) daftar paket kustom Anda.\nKetik /cancel untuk batal."); return AWAITING_PACKAGES
    if route == 'settings_rootfs': await query.edit_message_text("Silakan kirim ukuran RootFS baru dalam MB.\nKetik /cancel untuk batal."); return AWAITING_ROOTFS_SIZE
    if route == 'settings_leech_dest': await query.edit_message_text("Silakan kirim ID Grup/Channel atau 'me'.\nKetik /cancel untuk batal."); return AWAITING_LEECH_DEST
    if route == "settings_filename_pattern":
        keyboard = [[InlineKeyboardButton("squashfs", callback_data="set_pattern_squashfs"), InlineKeyboardButton("ext4", callback_data="set_pattern_ext4")],[InlineKeyboardButton("combined", callback_data="set_pattern_combined"), InlineKeyboardButton("combined-efi", callback_data="set_pattern_combined-efi")],[InlineKeyboardButton("« Kembali", callback_data="back_to_main_menu")]]; await query.edit_message_text("Pilih kata kunci nama file:", reply_markup=InlineKeyboardMarkup(keyboard)); return SELECT_UPLOAD_PATTERN
    if route == "settings_version":
        await query.edit_message_text("Mengambil daftar versi..."); versions = await scrape_openwrt_versions()
        if not versions: await query.edit_message_text("❌ Gagal Mengambil Data"); return await start_settings_conversation(update, context)
        keyboard = []; row = [];
        for v in versions.keys():
            row.append(InlineKeyboardButton(v, callback_data=f"v_major_{v}"))
            if len(row) == 2: keyboard.append(row); row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("« Kembali", callback_data="back_to_main_menu")]); await query.edit_message_text("Pilih seri rilis utama:", reply_markup=InlineKeyboardMarkup(keyboard)); return SELECT_VERSION_MAJOR
    if route == "settings_target":
        version = bot_config.get("VERSION"); await query.edit_message_text(f"Mengambil target untuk v{version}..."); targets = await scrape_targets_for_version(version)
        if not targets: await query.edit_message_text(f"Tidak ada target untuk versi {version}."); return await start_settings_conversation(update, context)
        keyboard = await create_paginated_keyboard(targets, 0, "t_select_", 3, "back_to_main_menu"); await query.edit_message_text(f"Pilih Target untuk v{version} (Hal 1):", reply_markup=keyboard); return SELECT_TARGET
    if route == "settings_profile":
        await query.edit_message_text("Mencari direktori Image Builder..."); _, ib_filename = await find_imagebuilder_url_and_name(bot_config.get("VERSION"), bot_config.get("TARGET"), bot_config.get("SUBTARGET"))
        if not ib_filename or not os.path.isdir(ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")): await query.edit_message_text("Image Builder belum diunduh. Jalankan /build sekali.", reply_markup=await create_main_settings_keyboard()); return MENU
        ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", ""); profiles = await get_device_profiles(ib_dir)
        if not profiles: await query.edit_message_text("Gagal mendapatkan daftar profil."); return await start_settings_conversation(update, context)
        keyboard = await create_paginated_keyboard(profiles, 0, "p_select_"); await query.edit_message_text("Pilih Profil Perangkat (Hal 1):", reply_markup=keyboard); return SELECT_PROFILE
    return MENU

@restricted
async def select_version_major_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    if query.data == 'settings_version':
        versions = await scrape_openwrt_versions(); keyboard = []; row = []
        for v in versions.keys():
            row.append(InlineKeyboardButton(v, callback_data=f"v_major_{v}"));
            if len(row) == 2: keyboard.append(row); row = []
        if row: keyboard.append(row)
        keyboard.append([InlineKeyboardButton("« Kembali", callback_data="back_to_main_menu")]);
        await query.edit_message_text("Pilih seri rilis utama:", reply_markup=InlineKeyboardMarkup(keyboard)); return SELECT_VERSION_MAJOR
    major_series = query.data.replace("v_major_", ""); versions = await scrape_openwrt_versions(); buttons = []; row = []
    for v in versions.get(major_series, []):
        row.append(InlineKeyboardButton(v, callback_data=f"v_minor_{v}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("« Kembali", callback_data="settings_version")])
    await query.edit_message_text(f"Pilih versi spesifik untuk seri {major_series}:", reply_markup=InlineKeyboardMarkup(buttons)); return SELECT_VERSION_MINOR

@restricted
async def select_version_minor_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); bot_config = context.bot_data.get('config', {})
    bot_config["VERSION"] = query.data.replace("v_minor_", ""); context.bot_data['config'] = bot_config
    if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
    await query.edit_message_text(f"✅ Versi diatur ke: *{bot_config['VERSION']}*", parse_mode='Markdown'); return await start_settings_conversation(update, context)

@restricted
async def select_target_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); bot_config = context.bot_data.get('config', {})
    data = query.data; version = bot_config.get("VERSION")
    if data.startswith("t_select_page_"):
        page = int(data.split('_')[-1]); targets = await scrape_targets_for_version(version)
        keyboard = await create_paginated_keyboard(targets, page, "t_select_", 3, "back_to_main_menu")
        await query.edit_message_text(f"Pilih Target untuk v{version} (Halaman {page + 1}):", reply_markup=keyboard); return SELECT_TARGET
    selected_target = data.replace("t_select_", ""); bot_config["TARGET"] = selected_target; context.bot_data['config'] = bot_config
    subtargets = await scrape_subtargets_for_target(version, selected_target)
    if not subtargets:
        if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
        await query.edit_message_text(f"✅ Target diatur ke: *{selected_target}* (tidak ada subtarget).", parse_mode='Markdown'); return await start_settings_conversation(update, context)
    buttons = []; row = []
    for st in subtargets:
        row.append(InlineKeyboardButton(st, callback_data=f"st_select_{st}"))
        if len(row) == 2: buttons.append(row); row = []
    if row: buttons.append(row)
    buttons.append([InlineKeyboardButton("« Kembali", callback_data="settings_target")]); await query.edit_message_text(f"Target: *{selected_target}*. Pilih Subtarget:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons)); return SELECT_SUBTARGET
    
@restricted
async def select_subtarget_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); bot_config = context.bot_data.get('config', {})
    bot_config["SUBTARGET"] = query.data.replace("st_select_", ""); context.bot_data['config'] = bot_config
    if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
    await query.edit_message_text(f"✅ Target diatur ke: *{bot_config['TARGET']}/{bot_config['SUBTARGET']}*", parse_mode='Markdown'); return await start_settings_conversation(update, context)

@restricted
async def select_profile_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); bot_config = context.bot_data.get('config', {})
    data = query.data
    if data.startswith("p_select_page_"):
        page = int(data.split('_')[-1]); _, ib_filename = await find_imagebuilder_url_and_name(bot_config.get("VERSION"), bot_config.get("TARGET"), bot_config.get("SUBTARGET"))
        ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", ""); profiles = await get_device_profiles(ib_dir)
        keyboard = await create_paginated_keyboard(profiles, page, "p_select_"); await query.edit_message_text(f"Pilih Profil Perangkat (Halaman {page + 1}):", reply_markup=keyboard); return SELECT_PROFILE
    else:
        profile = data.replace("p_select_", ""); bot_config["DEVICE_PROFILE"] = profile; context.bot_data['config'] = bot_config
        if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
        await query.edit_message_text(f"✅ Profil diatur ke: *{profile}*", parse_mode='Markdown'); return await start_settings_conversation(update, context)

@restricted
async def select_upload_pattern_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer(); bot_config = context.bot_data.get('config', {})
    selected_pattern = query.data.replace("set_pattern_", ""); bot_config["UPLOAD_FILENAME_CONTAINS"] = selected_pattern; context.bot_data['config'] = bot_config
    if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
    await query.edit_message_text(f"✅ Pola nama file diatur ke: *{selected_pattern}*", parse_mode='Markdown'); return await start_settings_conversation(update, context)
    
@restricted
async def receive_packages(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    raw_input = update.message.text; sanitized_input = raw_input.replace('\n', ' ').replace('\\', ' '); package_list = sanitized_input.split(' '); unique_packages = list(dict.fromkeys(filter(None, package_list))); final_packages_string = ' '.join(unique_packages)
    bot_config = context.bot_data.get('config', {}); bot_config['CUSTOM_PACKAGES'] = final_packages_string; context.bot_data['config'] = bot_config
    if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
    await update.message.reply_text(f"✅ Paket kustom berhasil diatur dan dinormalkan menjadi:\n\n`{final_packages_string}`", parse_mode='Markdown'); return await start_settings_conversation(update, context)

@restricted
async def receive_rootfs_size(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip().lower()
    if user_input in ['0', 'default', '']: new_size, reply_text = "", "✅ Ukuran RootFS diatur kembali ke default."
    elif not user_input.isdigit(): await update.message.reply_text("❌ Input tidak valid. Coba lagi."); return AWAITING_ROOTFS_SIZE
    else: new_size, reply_text = user_input, f"✅ Ukuran RootFS berhasil diatur ke: `{user_input}MB`"
    bot_config = context.bot_data.get('config', {}); bot_config['ROOTFS_SIZE'] = new_size; context.bot_data['config'] = bot_config
    if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
    await update.message.reply_text(reply_text, parse_mode='Markdown'); return await start_settings_conversation(update, context)

@restricted
async def receive_leech_dest(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_input = update.message.text.strip()
    if user_input.lower() == 'me': dest_id, reply_text = 'me', "✅ Destinasi Leech diatur ke: `Saved Messages`."
    else:
        try: int(user_input); dest_id, reply_text = user_input, f"✅ Destinasi Leech diatur ke ID: `{user_input}`"
        except ValueError: await update.message.reply_text("❌ Input tidak valid. Coba lagi."); return AWAITING_LEECH_DEST
    bot_config = context.bot_data.get('config', {}); bot_config['LEECH_DESTINATION_ID'] = dest_id; context.bot_data['config'] = bot_config
    if 'save_config' in context.bot_data: context.bot_data['save_config'](bot_config)
    await update.message.reply_text(reply_text, parse_mode='Markdown'); return await start_settings_conversation(update, context)

@restricted
async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    if query: await query.answer(); await query.edit_message_text("Mode pengaturan dibatalkan.")
    else: await update.message.reply_text("Mode pengaturan dibatalkan.")
    return ConversationHandler.END
