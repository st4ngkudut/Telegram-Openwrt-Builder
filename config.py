# config.py

import os

# (WAJIB) Masukkan token bot yang Anda dapat dari @BotFather
TELEGRAM_TOKEN = ""

# (WAJIB) Masukkan user ID Anda.
AUTHORIZED_USER_IDS = [123456789]

# --- KREDENSIAL UNTUK TELETHON ---
# Masukkan nilai yang Anda dapat dari my.telegram.org
API_ID = 1234567 # GANTI DENGAN API_ID ANDA (harus integer, bukan string)
API_HASH = ""

# --- Pengaturan OpenWrt Default ---
OPENWRT_DEFAULTS = {
    "VERSION": "24.10.1",
    "TARGET": "x86",
    "SUBTARGET": "64",
    "DEVICE_PROFILE": "generic",
    "CUSTOM_PACKAGES": "luci luci-ssl nano kmod-usb-net-rndis ntfs-3g-utils block-mount",
    "ROOTFS_SIZE": "512",
    "LEECH_DESTINATION_ID": "me" 
}

# --- Pengaturan Lainnya ---
BUILD_LOG_PATH = "build.log"
HISTORY_DB_PATH = "history.json"
TEMP_MESSAGE_DURATION = 5
