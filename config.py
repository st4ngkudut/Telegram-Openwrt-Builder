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

# --- URL DASAR UNTUK SUMBER BUILD ---
OPENWRT_DOWNLOAD_URL = "https://downloads.openwrt.org"
IMMORTALWRT_DOWNLOAD_URL = "https://downloads.immortalwrt.org"

# --- PENGATURAN KONFIGURASI DEFAULT ---
DEFAULT_CONFIGS = {
    "active_build_mode": "official",

    "official": {
        "BUILD_SOURCE": "openwrt",
        "VERSION": "23.05.3",
        "TARGET": "ramips",
        "SUBTARGET": "mt7621",
        "DEVICE_PROFILE": "xiaomi_mi-router-3g",
        "CUSTOM_PACKAGES": "luci luci-ssl nano",
        "CUSTOM_REPOS": {}, 
        "ROOTFS_SIZE": "",
        "LEECH_DESTINATION_ID": "me"
    },

    "amlogic": {
        "ROOTFS_URL": "",
        "BOARD": "hk1box",
        "ROOTFS_SIZE": "512",
        "KERNEL_VERSION": "5.15.y",
        "KERNEL_TAG": "stable",
        "KERNEL_AUTO_UPDATE": True,
        "BUILDER_NAME": "",
        "LEECH_DESTINATION_ID": "me"
    }
}

# --- Pengaturan Lainnya ---
BUILD_LOG_PATH = "build.log"
HISTORY_DB_PATH = "history.json"
TEMP_MESSAGE_DURATION = 15
CONFIRMATION_PHRASE = "hapus semua data build saya"

AML_BUILD_SCRIPT_REPO = "https://github.com/ophub/amlogic-s9xxx-openwrt.git"
AML_BUILD_SCRIPT_DIR = "amlogic-s9xxx-openwrt"
