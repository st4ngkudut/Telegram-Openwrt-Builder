# Telegram OpenWrt Builder Bot

Sebuah bot Telegram canggih untuk mengelola, mengonfigurasi, dan memulai proses *build* OpenWrt Image Builder secara remote langsung dari chat Telegram. Bot ini dirancang untuk menjadi asisten pribadi Anda dalam membuat *firmware* OpenWrt kustom dengan mudah dan efisien.

---

## ✨ Fitur Utama

- **Menu Pengaturan Interaktif:** Kontrol semua parameter build melalui menu `/settings` berbasis tombol yang intuitif, tanpa perlu menghafal perintah.
- **Kustomisasi Build Penuh:**
    - Pilih Versi, Target, dan Subtarget OpenWrt.
    - Pilih Profil Perangkat yang spesifik.
    - Tentukan daftar Paket Kustom yang ingin disertakan.
    - Atur Ukuran Partisi RootFS secara dinamis.
- **Metode "Leech & Forward":** File besar diunggah terlebih dahulu ke "Saved Messages" atau grup/channel pribadi.
- **Kontrol Proses Build:**
    - `/build`: Memulai proses kompilasi.
    - `/cancel`: Menghentikan paksa proses `make` yang sedang berjalan.
    - `/getlog`: Mengambil file log dari build terakhir untuk debugging.

---

## 🏗️ Struktur Proyek

```
.
├── core/
│   ├── build_manager.py     # Logika inti untuk proses build
│   ├── history_manager.py   # Fungsi untuk menyimpan history bot
│   ├── openwrt_api.py       # Fungsi untuk scraping data OpenWrt
│   └── uploader.py          # Modul uploader file besar via Telethon
├── handlers/
│   ├── command_handlers.py  # Handler untuk perintah utama (/start, /build)
│   ├── constant.py          # Handler untuk tombol menu
│   ├── settings_handler.py  # Handler untuk percakapan menu /settings
│   └── utils.py             # Fungsi utilitas (e.g., decorator @restricted)
├── config.py                # Semua konfigurasi terpusat
├── main.py                  # Titik masuk utama aplikasi bot
├── requirements.txt         # Daftar dependensi Python
└── state.json               # (Dibuat otomatis) Menyimpan state konfigurasi
```

---

## 🚀 Persiapan & Instalasi

#### Update & Install dependencies
```bash
sudo apt update && sudo apt upgrade -y && sudo apt-get install -y $(curl -fsSL https://raw.githubusercontent.com/ophub/amlogic-s9xxx-armbian/main/compile-kernel/tools/script/ubuntu2004-openwrt-depends)
```
Lalu

```bash
sudo apt install build-essential libncurses5-dev libncursesw5-dev \
zlib1g-dev gawk git gettext libssl-dev xsltproc rsync wget unzip python3
```

#### 1. Clone Repositori
```bash
git clone https://github.com/st4ngkudut/Telegram-Openwrt-Builder.git
cd Telegram-Openwrt-Builder
```

#### 2. Instal Dependensi
Pastikan Anda memiliki Python 3.10 atau lebih baru.
```bash
pip install -r requirements.txt
```

#### 3. Konfigurasi Bot
Edit file `config.py`. Isi semua nilai yang diperlukan:

- `TELEGRAM_TOKEN`: Token bot dari `@BotFather`.
- `AUTHORIZED_USER_IDS`: Daftar User ID Telegram Anda yang diizinkan menggunakan bot. Dapatkan ID Anda dari `@userinfobot`.
- `API_ID` & `API_HASH`: Dapatkan dari [my.telegram.org](https://my.telegram.org)

---

## ▶️ Menjalankan Bot

Proses menjalankan bot terdiri dari dua tahap utama: otorisasi satu kali dan menjalankan secara permanen.

#### Tahap 1: Otorisasi Telethon (Hanya Perlu Dilakukan Sekali)

Sebelum menjalankan bot sebagai layanan, Anda harus melakukan login Telethon secara manual untuk membuat file sesi.

1.  Jalankan skrip langsung dari terminal:
    ```bash
    python3 main.py
    ```
2.  Terminal akan meminta Anda untuk memasukkan kredensial:
    - Masukkan **nomor telepon** Anda (format `+62...`).
    - Masukkan **kode verifikasi** yang dikirim ke aplikasi Telegram Anda.
    - Masukkan **password 2FA** jika Anda mengaktifkannya.
3.  Setelah berhasil, file `telegram_user_session.session` akan dibuat. Anda bisa menghentikan skrip dengan `Ctrl + C`.

#### Tahap 2: Menjalankan dengan PM2 (atau sebagai layanan lain)

Setelah file `.session` ada, Anda bisa menjalankan bot secara permanen di latar belakang.

```bash
pm2 start main.py --name bot-builder --interpreter python3
```

Untuk melihat log:
```bash
pm2 logs bot-builder
```

---

## 📖 Cara Penggunaan

- `/start` - Memulai bot dan menampilkan keyboard utama.
- `/status` - Menampilkan semua konfigurasi yang sedang aktif dan status proses build saat ini.
- `/settings` - Membuka menu pengaturan interaktif berbasis tombol.
- `/build` - Memulai proses build dengan konfigurasi yang sedang aktif.
- `/cancel` - Menghentikan paksa proses build yang sedang berjalan.
- `/getlog` - Mengunduh file `build.log` dari build terakhir.

---

## 📜 Lisensi

![Python Version](https://img.shields.io/badge/Python-3.10%2B-blue)
![License](https://img.shields.io/badge/License-MIT-green)
