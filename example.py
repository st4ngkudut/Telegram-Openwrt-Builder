# config.py

# =====================================================================
# PENGATURAN BOT TERPUSAT
# Cukup edit file ini untuk mengubah perilaku bot.
# =====================================================================

# (WAJIB) Masukkan token bot yang Anda dapat dari @BotFather
TELEGRAM_TOKEN = "GANTI_DENGAN_TOKEN_BOT_ANDA"

# (WAJIB) Masukkan user ID Anda. Bot hanya akan merespon Anda.
# Bisa diisi lebih dari satu, pisahkan dengan koma. Contoh: [12345678, 87654321]
AUTHORIZED_USER_IDS = [GANTI_DENGAN_USER_ID_ANDA]

# --- Pengaturan OpenWrt Default ---
# Nilai-nilai ini akan menjadi default saat bot pertama kali dijalankan.
OPENWRT_DEFAULTS = {
    "VERSION": "23.05.3",
    "TARGET": "ramips",
    "SUBTARGET": "mt7621",
    "DEVICE_PROFILE": "xiaomi_mi-router-3g",
    "CUSTOM_PACKAGES": "luci luci-ssl luci-theme-argon luci-app-ddns nano",
    "OUTPUT_DIR": "FIRMWARE_BUILDS",
}

# --- Pengaturan Lainnya ---
BUILD_LOG_PATH = "build.log"
