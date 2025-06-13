# config.py

import os

# =====================================================================
# PENGATURAN BOT TERPUSAT
# =====================================================================

# (WAJIB) Masukkan token bot yang Anda dapat dari @BotFather
TELEGRAM_TOKEN = "GANTI_DENGAN_TOKEN_BOT_ANDA"

# (WAJIB) Masukkan user ID Anda. Bot hanya akan merespon Anda.
AUTHORIZED_USER_IDS = [GANTI_DENGAN_USER_ID_ANDA]

# --- KREDENSIAL UNTUK TELETHON ---
# Masukkan nilai yang Anda dapat dari my.telegram.org
API_ID = 12345678 # GANTI DENGAN API_ID ANDA (harus integer, bukan string)
API_HASH = "GANTI_DENGAN_API_HASH_ANDA"

# --- Pengaturan OpenWrt Default ---
OPENWRT_DEFAULTS = {
    "VERSION": "23.05.3",
    "TARGET": "ramips",
    "SUBTARGET": "mt7621",
    "DEVICE_PROFILE": "xiaomi_mi-router-3g",
    "CUSTOM_PACKAGES": "luci luci-ssl luci-theme-argon luci-app-ddns nano",
    "UPLOAD_FILENAME_CONTAINS": "combined-efi",
    "ROOTFS_SIZE": "",
    "LEECH_DESTINATION_ID": "me" 
}

# --- Pengaturan Lainnya ---
BUILD_LOG_PATH = "build.log"
