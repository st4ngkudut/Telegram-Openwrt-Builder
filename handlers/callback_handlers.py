# handlers/callback_handlers.py (Versi Final dengan Tombol Kesamping)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

# Impor semua fungsi yang kita butuhkan dari modul lain
from core.openwrt_api import (
    scrape_openwrt_versions,
    scrape_targets_for_version,
    scrape_subtargets_for_target,
    get_device_profiles,
    find_imagebuilder_url_and_name
)
from core.build_manager import build_manager
from .command_handlers import restricted

# --- FUNGSI PEMBUAT KEYBOARD ---

async def create_main_settings_keyboard():
    """Membuat keyboard untuk menu pengaturan utama dengan tata letak 2 kolom."""
    # --- PERUBAHAN DI SINI ---
    # Tombol dikelompokkan berpasangan dalam satu baris
    keyboard = [
        [
            InlineKeyboardButton("🔧 Ubah Versi", callback_data="settings_version"),
            InlineKeyboardButton("🎯 Ubah Target/Subtarget", callback_data="settings_target")
        ],
        [
            InlineKeyboardButton("🆔 Ubah Profil Perangkat", callback_data="settings_profile"),
            InlineKeyboardButton("📦 Ubah Paket Kustom", callback_data="settings_packages")
        ],
        [
            InlineKeyboardButton("📂 Ubah Direktori Output", callback_data="settings_output"),
            InlineKeyboardButton("Tutup", callback_data="settings_close")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

async def create_paginated_keyboard(items, page, callback_prefix, buttons_per_row=2, back_callback="back_to_settings"):
    """Membuat keyboard dengan paginasi untuk daftar yang panjang."""
    # Fungsi ini sudah mendukung tata letak menyamping, tidak perlu diubah.
    items_per_page = buttons_per_row * 5
    start = page * items_per_page
    end = start + items_per_page
    
    keyboard = []
    row = []
    for item in items[start:end]:
        button = InlineKeyboardButton(item, callback_data=f"{callback_prefix}{item}")
        row.append(button)
        if len(row) == buttons_per_row:
            keyboard.append(row)
            row = []
    if row:
        keyboard.append(row)

    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("« Sebelumnya", callback_data=f"{callback_prefix}page_{page-1}"))
    if end < len(items):
        nav_row.append(InlineKeyboardButton("Berikutnya »", callback_data=f"{callback_prefix}page_{page+1}"))
    if nav_row:
        keyboard.append(nav_row)
    
    keyboard.append([InlineKeyboardButton("« Kembali ke Menu", callback_data=back_callback)])
    return InlineKeyboardMarkup(keyboard)

# --- HANDLER UTAMA UNTUK SEMUA CALLBACK ---

@restricted
async def main_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Satu handler untuk menangani semua callback query dalam urutan yang benar."""
    query = update.callback_query
    await query.answer()
    
    callback_data = query.data
    bot_config = context.bot_data.get('config', {})
    
    # --- Handler untuk alur build otomatis ---
    if callback_data.startswith("build_with_profile_"):
        # (Logika ini tetap sama)
        selected_profile = callback_data.replace("build_with_profile_", "")
        bot_config["DEVICE_PROFILE"] = selected_profile; context.bot_data['config'] = bot_config
        await query.edit_message_text(f"✅ Profil diperbarui menjadi: `{selected_profile}`. Melanjutkan proses build...", parse_mode='Markdown')
        chat_id = query.message.chat_id
        context.application.job_queue.run_once(lambda ctx: build_manager.run_build_task(ctx, chat_id, bot_config), 0); return
        
    if callback_data == "cancel_build":
        build_manager.status = "Idle"; await query.edit_message_text("Proses build dibatalkan."); return

    # --- Handler untuk menu pengaturan utama ---
    if callback_data == "settings_close":
        await query.edit_message_text("Pengaturan ditutup."); return

    if callback_data == "back_to_settings":
        keyboard = await create_main_settings_keyboard(); await query.edit_message_text("⚙️ **Menu Pengaturan**", reply_markup=keyboard, parse_mode='Markdown'); return

    # --- AKSI DARI MENU PENGATURAN ---
    if callback_data == "settings_version" or callback_data == "back_to_version_select":
        await query.edit_message_text("Mengambil daftar versi..."); versions = await scrape_openwrt_versions()
        if not versions:
            await query.edit_message_text("❌ **Gagal Mengambil Data**", reply_markup=await create_main_settings_keyboard()); return

        # --- PERUBAHAN DI SINI ---
        # Membuat tombol versi menjadi 2 kolom
        keyboard = []; row = []
        for v in versions.keys():
            row.append(InlineKeyboardButton(v, callback_data=f"ver_major_{v}"))
            if len(row) == 2:
                keyboard.append(row); row = []
        if row: keyboard.append(row)
        
        await query.edit_message_text("Pilih seri rilis utama:", reply_markup=InlineKeyboardMarkup(keyboard)); return

    if callback_data == "settings_target" or callback_data == "back_to_target_select":
        version = bot_config.get("VERSION")
        await query.edit_message_text(f"Mengambil target untuk versi {version}...")
        targets = await scrape_targets_for_version(version)
        if not targets:
            await query.edit_message_text(f"Tidak ada target untuk versi {version}.", reply_markup=await create_main_settings_keyboard()); return
            
        # --- PERUBAHAN DI SINI ---
        # Membuat tombol target menjadi 2-3 kolom
        keyboard = []; row = []
        for t in targets:
            row.append(InlineKeyboardButton(t, callback_data=f"target_select_{t}"))
            if len(row) == 3: # 3 tombol per baris untuk target
                keyboard.append(row); row = []
        if row: keyboard.append(row)

        await query.edit_message_text(f"Pilih Target untuk versi {version}:", reply_markup=InlineKeyboardMarkup(keyboard)); return

    if callback_data.startswith("settings_profile") or callback_data.startswith("profile_select_page_"):
        # (Logika ini tetap sama, karena sudah menggunakan create_paginated_keyboard yang mendukung kolom)
        page = int(callback_data.split('_')[-1]) if callback_data.startswith("profile_select_page_") else 0
        await query.edit_message_text("Mencari direktori Image Builder...")
        _, ib_filename = await find_imagebuilder_url_and_name(
            bot_config.get("VERSION"), bot_config.get("TARGET"), bot_config.get("SUBTARGET")
        )
        if not ib_filename:
            await query.edit_message_text("Gagal menemukan file Image Builder.", reply_markup=await create_main_settings_keyboard()); return
        ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")
        profiles = await get_device_profiles(ib_dir)
        if profiles:
            keyboard = await create_paginated_keyboard(profiles, page, "profile_select_")
            await query.edit_message_text(f"Pilih Profil Perangkat (Halaman {page + 1}):", reply_markup=keyboard)
        else:
            await query.edit_message_text("Gagal mendapatkan daftar profil. Jalankan /build untuk mengunduh Image Builder.", reply_markup=await create_main_settings_keyboard())
        return

    if callback_data in ["settings_packages", "settings_output"]:
        # (Logika ini tetap sama)
        action = "paket kustom" if callback_data == "settings_packages" else "direktori output"
        command = "/setpackages" if callback_data == "settings_packages" else "/setoutputdir"
        await query.edit_message_text(f"Untuk mengubah {action}, silakan kirim perintah `{command}`", parse_mode='Markdown', reply_markup=await create_main_settings_keyboard()); return

    # --- Lanjutan dari Pemilihan (Sub-Menu) ---
    if callback_data.startswith("ver_major_"):
        major_series = callback_data.replace("ver_major_", ""); versions = await scrape_openwrt_versions()
        buttons = []; row = []
        for v in versions.get(major_series, []):
            row.append(InlineKeyboardButton(v, callback_data=f"ver_select_{v}"))
            if len(row) == 2:
                buttons.append(row); row = []
        if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("« Kembali", callback_data="settings_version")])
        await query.edit_message_text(f"Pilih versi spesifik untuk seri {major_series}:", reply_markup=InlineKeyboardMarkup(buttons)); return

    if callback_data.startswith("ver_select_"):
        bot_config["VERSION"] = callback_data.replace("ver_select_", ""); context.bot_data['config'] = bot_config
        await query.edit_message_text(f"✅ Versi diatur ke: *{bot_config['VERSION']}*", parse_mode='Markdown', reply_markup=await create_main_settings_keyboard()); return
    
    if callback_data.startswith("target_select_"):
        selected_target = callback_data.replace("target_select_", ""); bot_config["TARGET"] = selected_target; context.bot_data['config'] = bot_config
        version = bot_config.get("VERSION")
        subtargets = await scrape_subtargets_for_target(version, selected_target)
        buttons = []; row = []
        for st in subtargets:
            row.append(InlineKeyboardButton(st, callback_data=f"subtarget_select_{st}"))
            if len(row) == 2:
                buttons.append(row); row = []
        if row: buttons.append(row)
        buttons.append([InlineKeyboardButton("« Kembali", callback_data="settings_target")])
        await query.edit_message_text(f"Target: *{selected_target}*. Pilih Subtarget:", parse_mode='Markdown', reply_markup=InlineKeyboardMarkup(buttons)); return

    if callback_data.startswith("subtarget_select_"):
        bot_config["SUBTARGET"] = callback_data.replace("subtarget_select_", ""); context.bot_data['config'] = bot_config
        await query.edit_message_text(f"✅ Target diatur ke: *{bot_config['TARGET']}/{bot_config['SUBTARGET']}*", parse_mode='Markdown', reply_markup=await create_main_settings_keyboard()); return

    if callback_data.startswith("profile_select_"):
        bot_config["DEVICE_PROFILE"] = callback_data.replace("profile_select_", "")
        await query.edit_message_text(f"✅ Profil diatur ke: *{bot_config['DEVICE_PROFILE']}*", parse_mode='Markdown', reply_markup=await create_main_settings_keyboard()); return
