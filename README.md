# Telegram OpenWrt Builder V2

Bot Telegram canggih yang berfungsi sebagai 'bengkel kerja' atau *toolchain* pribadi untuk membuat firmware OpenWrt khusus langsung dari Telegram, dengan dukungan untuk build resmi, ImmortalWrt, dan Amlogic Remake.


---

## ✨ Daftar Fitur

### 🤖 Sistem Build Ganda & Interaktif
- **Build Resmi & ImmortalWrt:** Membuat firmware langsung dari Image Builder resmi OpenWrt atau ImmortalWrt.
- **Amlogic Remake:** Mengemas ulang `rootfs` untuk perangkat Amlogic menggunakan skrip `ophub/remake`.
- **Alur Build Interaktif (`/build`):** Percakapan terpandu untuk memulai build, lengkap dengan layar konfirmasi dan validasi profil proaktif untuk mencegah build gagal di tengah jalan.

### ⚙️ Menu Pengaturan Lengkap & Dinamis (`/settings`)
- **Mode Ganda:** Beralih dengan mudah antara konfigurasi "Build Resmi" dan "Amlogic Remake".
- **Pemilihan Sumber:** Pilih antara `OpenWrt` dan `ImmortalWrt` sebagai sumber build. Bot akan secara otomatis mengambil data dari server yang benar.
- **Konfigurasi Mendalam:** Atur Versi, Target, Subtarget, Profil Perangkat, Ukuran RootFS, Paket Kustom, dan lainnya melalui menu tombol yang interaktif.

### 🛠️ Kustomisasi Tingkat Lanjut
- **Custom Repository per Arsitektur:** Tambahkan repositori paket pihak ketiga yang berbeda untuk setiap arsitektur build (`x86_64`, `ramips`, dll).
  - Mendukung placeholder `{arch}` untuk URL dinamis.
  - Opsi `check_signature` dinonaktifkan secara otomatis.
- **Upload Skrip `uci-defaults`:** Unggah skrip `.sh` untuk melakukan konfigurasi otomatis saat firmware pertama kali di-boot.
- **Upload Paket `.ipk` Kustom:** Unggah satu atau beberapa file `.ipk` kustom dalam sekali kirim untuk disertakan dalam build.
- **Upload `rootfs`:** Unggah file `rootfs` untuk Amlogic Remake langsung dari Telegram.

### 🗂️ Manajemen & Utilitas
- **Arsip Build (`/arsip`):** Semua hasil build tercatat dalam histori, lengkap dengan detail konfigurasinya.
- **Paginasi:** Daftar file hasil build dan daftar histori di `/arsip` & `/cleanup` memiliki halaman untuk menangani hasil yang banyak tanpa error.
- **Manajemen File (`/cleanup`):** Hapus entri build satu per satu atau lakukan "sapu bersih" total semua data build dengan konfirmasi berlapis yang aman.
- **Panel Status Cerdas (`/status`):** Menampilkan panel konfigurasi dan status build saat ini yang selalu ter-update dan bersih.
- **Log Real-time:** Dapatkan log proses `make` atau `remake` secara langsung di Telegram.

---

## 🚀 Instalasi & Konfigurasi

**1. Prasyarat di Server (Ubuntu/Debian)**
```bash
sudo apt-get update
sudo apt-get install -y git python3 python3-pip wget curl build-essential libncurses5-dev libncursesw5-dev zlib1g-dev gawk flex gettext npm
```
Pastikan `pm2` juga terinstal untuk manajemen proses:
```bash
sudo npm install -g pm2
```

**2. Clone Repositori**
```bash
git clone [https://github.com/st4ngkudut/Telegram-Openwrt-Builder.git](https://github.com/st4ngkudut/Telegram-Openwrt-Builder.git)
cd Telegram-Openwrt-Builder
```

**3. Instalasi Dependensi Python**
```bash
pip3 install -r requirements.txt
```

**4. Konfigurasi `config.py`**
Buka file `config.py` dan isi semua variabel yang diperlukan, terutama:
- `TELEGRAM_TOKEN`: Token bot Anda dari @BotFather.
- `AUTHORIZED_USER_IDS`: User ID Telegram Anda (harus dalam format list, misal `[12345678]`).
- `API_ID` & `API_HASH`: Diambil dari my.telegram.org untuk sesi Telethon.

**5. Login Sesi Telethon (Hanya untuk pertama kali)**
Telethon memerlukan sesi login untuk fitur upload. Lakukan ini secara manual di terminal:
```bash
# Hentikan bot jika sedang berjalan
pm2 stop ST4Bot-builder

# Hapus file sesi lama (jika ada) untuk memaksa login baru
rm telegram_user_session.session

# Jalankan bot secara langsung
python3 main.py

# Ikuti instruksi di terminal: masukkan nomor telepon, kode login, dan password 2FA
# Setelah bot berhasil berjalan, hentikan dengan Ctrl + C
```

**6. Menjalankan Bot dengan PM2**
Setelah sesi Telethon berhasil dibuat, jalankan bot di latar belakang.
```bash
# Mulai bot
pm2 start main.py --name "ST4Bot-builder"

# Melihat log
pm2 logs ST4Bot-builder

# Menghentikan bot
pm2 stop ST4Bot-builder
```

---

## 📖 Panduan Penggunaan

- `/start`: Menampilkan pesan selamat datang dan keyboard perintah.
- `/settings`: Masuk ke menu utama untuk mengatur semua parameter build.
- `/build`: Memulai proses build interaktif.
- `/upload_rootfs`: Memulai sesi untuk mengunggah file `rootfs` Amlogic.
- `/upload_ipk`: Memulai sesi untuk mengunggah file `.ipk` kustom.
- `/status`: Menampilkan panel konfigurasi dan status build saat ini.
- `/arsip`: Melihat riwayat build yang telah selesai.
- `/cleanup`: Mengelola atau membersihkan file build.
- `/getlog`: Mengambil `build.log` dari proses build terakhir.
- `/cancel`: Membatalkan proses build yang sedang berjalan.

---

## 🏗️ Dikembangkan Oleh

Bot ini dikembangkan oleh **[ST4NGKUDUT](https://t.me/ST4NGKUDUT)** dengan bantuan dan sesi diskusi intensif bersama **Gemini Advanced**.

## ⚖️ Lisensi
![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg) ![License](https://img.shields.io/badge/License-MIT-green.svg)
