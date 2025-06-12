# core/build_manager.py (Versi Final dengan Verifikasi Paket)

import os
import shutil
import asyncio
import logging
import time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, BadRequest

from config import BUILD_LOG_PATH
from core.openwrt_api import find_imagebuilder_url_and_name, get_device_profiles

logger = logging.getLogger(__name__)

LOG_UPDATE_INTERVAL = 3.0 

class BuildManager:
    def __init__(self):
        self.status = "Idle"
        self.ib_dir = None

    async def get_available_packages(self, ib_dir):
        """
        Membaca dan mem-parsing file Packages.gz untuk mendapatkan daftar semua paket yang tersedia.
        """
        package_list = set()
        packages_path = os.path.join(ib_dir, "packages")
        if not os.path.isdir(packages_path):
            return None
        
        # Perintah shell untuk dekompresi dan filtering
        command = f'find {packages_path} -name "Packages.gz" | xargs gunzip -c | grep "Package:"'
        
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Gagal membaca daftar paket: {stderr.decode()}")
            return None
            
        for line in stdout.decode().splitlines():
            # Mengambil nama paket dari baris "Package: nama-paket"
            package_name = line.split(':')[1].strip()
            package_list.add(package_name)
            
        logger.info(f"Ditemukan {len(package_list)} paket yang tersedia di Image Builder.")
        return package_list

    async def run_build_task(self, context, chat_id, current_config):
        """
        Tugas build dengan verifikasi paket dan profil terlebih dahulu.
        """
        self.status = "Preparing"
        await context.bot.send_message(chat_id, "Mempersiapkan build...")
        
        # 1. Temukan, Download, dan Ekstrak
        full_url, ib_filename = await find_imagebuilder_url_and_name(
            current_config["VERSION"], current_config["TARGET"], current_config["SUBTARGET"]
        )
        if not full_url:
            await context.bot.send_message(chat_id, "❌ GAGAL: Tidak dapat menemukan file Image Builder."); self.status = "Failed"; return
            
        self.ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")
        
        if not os.path.isdir(self.ib_dir):
            if not os.path.exists(ib_filename):
                progress_message = await context.bot.send_message(chat_id, f"Mengunduh `{ib_filename}`...", parse_mode='Markdown')
                download_proc = await asyncio.create_subprocess_shell(f"wget -q --show-progress {full_url} -O {ib_filename}")
                await download_proc.wait()
                await context.bot.delete_message(chat_id=chat_id, message_id=progress_message.message_id)

            extract_message = await context.bot.send_message(chat_id, f"Mengekstrak `{ib_filename}`...", parse_mode='Markdown')
            extract_command = f"tar --use-compress-program=zstd -xf {ib_filename}" if ib_filename.endswith(".tar.zst") else f"tar -xf {ib_filename}"
            extract_proc = await asyncio.create_subprocess_shell(extract_command)
            await extract_proc.wait()
            await context.bot.delete_message(chat_id=chat_id, message_id=extract_message.message_id)

        # --- TAHAP VERIFIKASI BARU ---
        # 2. Verifikasi Paket Kustom
        self.status = "Verifying Packages"
        await context.bot.send_message(chat_id, "Memverifikasi daftar paket kustom...")
        
        available_packages = await self.get_available_packages(self.ib_dir)
        if available_packages is None:
            await context.bot.send_message(chat_id, "❌ GAGAL: Tidak bisa membaca repositori paket dari Image Builder."); self.status = "Failed"; return

        custom_packages = set(current_config["CUSTOM_PACKAGES"].split())
        invalid_packages = custom_packages - available_packages

        if invalid_packages:
            await context.bot.send_message(
                chat_id,
                f"❌ **Paket Tidak Valid Ditemukan!**\n\n"
                f"Paket berikut tidak tersedia untuk rilis ini:\n`{', '.join(invalid_packages)}`\n\n"
                "Proses build dibatalkan. Silakan perbaiki daftar paket Anda melalui /settings.",
                parse_mode='Markdown'
            )
            self.status = "Failed"
            return
        
        await context.bot.send_message(chat_id, "✅ Semua paket kustom valid.")

        # 3. Verifikasi Profil Perangkat (Logika dari sebelumnya)
        current_profile = current_config["DEVICE_PROFILE"]
        valid_profiles = await get_device_profiles(self.ib_dir)
        if valid_profiles is None:
            await context.bot.send_message(chat_id, "❌ GAGAL: Tidak bisa membaca daftar profil."); self.status = "Failed"; return

        if current_profile not in valid_profiles:
            self.status = "Awaiting Profile"
            from handlers.callback_handlers import create_paginated_keyboard
            keyboard = await create_paginated_keyboard(valid_profiles, 0, "build_with_profile_", back_callback="cancel_build")
            await context.bot.send_message(chat_id, f"⚠️ **Profil `{current_profile}` tidak valid!**\n\nPilih profil yang benar untuk melanjutkan:", reply_markup=keyboard, parse_mode='Markdown')
            return

        # 4. Jika semua valid, lanjutkan build
        self.status = "Building..."
        progress_message = await context.bot.send_message(chat_id, f"✅ Konfigurasi valid. Memulai build...\n\n```\nLog akan muncul di sini...\n```", parse_mode='Markdown')
        # ... (sisa logika real-time logging tidak berubah) ...
        message_id = progress_message.message_id; command = (f"make -C {self.ib_dir} image PROFILE={current_profile} PACKAGES='{current_config['CUSTOM_PACKAGES']}' V=s"); process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT); log_content = ""; last_update_time = time.time()
        while True:
            line = await process.stdout.readline();
            if not line: break;
            decoded_line = line.decode('utf-8', errors='ignore').strip()
            if decoded_line: log_content += decoded_line + "\n";
            if (time.time() - last_update_time) > LOG_UPDATE_INTERVAL:
                try:
                    display_log = "..." + log_content[-3800:] if len(log_content) > 3800 else log_content
                    if display_log.strip() != (await context.bot.get_chat(chat_id=chat_id).description or "").strip():
                        await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"```\n{display_log}```", parse_mode='Markdown')
                    last_update_time = time.time()
                except (RetryAfter, BadRequest): pass
        await process.wait()
        final_log = "..." + log_content[-3800:] if len(log_content) > 3800 else log_content
        if process.returncode == 0:
            self.status = "Success"; await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"```\n{final_log}\n```\n✅ **Build Selesai!**", parse_mode='Markdown'); await self.send_firmware(context, chat_id, current_config, self.ib_dir)
        else:
            self.status = "Failed"; await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"```\n{final_log}\n```\n❌ **Build GAGAL!** Kode error: {process.returncode}", parse_mode='Markdown')
        with open(BUILD_LOG_PATH, "w") as f: f.write(log_content)

    async def send_firmware(self, context, chat_id, config, ib_dir):
        # ... (Fungsi ini tidak diubah) ...
        pass

build_manager = BuildManager()
