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
# Nilai-nilai ini akan menjadi default saat bot pertama kali dijalankan
# atau jika file state.json tidak ada.
OPENWRT_DEFAULTS = {
    "VERSION": "24.10.1",
    "TARGET": "x86",
    "SUBTARGET": "64",
    "DEVICE_PROFILE": "generic",
    "CUSTOM_PACKAGES": "luci nano kmod-usb-net-rndis",
    "OUTPUT_DIR": "FIRMWARE_BUILDS",
    "UPLOAD_FILENAME_CONTAINS": "combined-efi",
    "ROOTFS_SIZE": "512",
    "LEECH_DESTINATION_ID": "me" 
}

# --- Pengaturan Lainnya ---
BUILD_LOG_PATH = "build.log"
