# core/build_manager.py

import os
import asyncio
import logging
import time
import glob
import re
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.error import RetryAfter, BadRequest

from config import BUILD_LOG_PATH
from core.openwrt_api import find_imagebuilder_url_and_name, get_device_profiles
from core.uploader import upload_file_for_forwarding
from core.history_manager import add_build_entry
from handlers.utils import send_temporary_message

logger = logging.getLogger(__name__)

LOG_UPDATE_INTERVAL = 4.0
NO_OUTPUT_TIMEOUT = 300 

async def _update_rootfs_in_config(ib_dir: str, rootfs_size: str):
    config_path = os.path.join(ib_dir, '.config')
    if not (rootfs_size and rootfs_size.isdigit() and int(rootfs_size) > 0):
        return False
    logger.info(f"Akan mengatur ROOTFS_PARTSIZE ke {rootfs_size}MB di {config_path}")
    try:
        proc = await asyncio.create_subprocess_shell(
            f"make -C {ib_dir} defconfig",
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        await proc.wait()
    except Exception as e:
        logger.error(f"Gagal menjalankan 'make defconfig': {e}")
    if not os.path.exists(config_path):
        return False
    try:
        with open(config_path, 'r') as f:
            lines = f.readlines()
        new_lines = []
        found = False
        config_string = f"CONFIG_TARGET_ROOTFS_PARTSIZE={rootfs_size}\n"
        for line in lines:
            if line.strip().startswith("CONFIG_TARGET_ROOTFS_PARTSIZE") or line.strip().startswith("# CONFIG_TARGET_ROOTFS_PARTSIZE is not set"):
                new_lines.append(config_string)
                found = True
            else:
                new_lines.append(line)
        if not found:
            new_lines.append(config_string)
        with open(config_path, 'w') as f:
            f.writelines(new_lines)
        return True
    except Exception as e:
        logger.error(f"Gagal membaca/menulis file .config: {e}")
        return False

class BuildManager:
    def __init__(self):
        self.status = "Idle"
        self.ib_dir = None
        self.process = None

    async def cancel_current_build(self):
        if self.process and self.status == "Building...":
            try:
                self.process.terminate()
                await self.process.wait()
                self.status = "Cancelled"
                self.process = None
                return True
            except ProcessLookupError:
                self.process = None
                self.status = "Idle"
                return False
        return False

    async def run_build_task(self, context, chat_id, current_config):
        status_message = None
        try:
            self.status = "Preparing"
            status_message = await context.bot.send_message(chat_id, "⏳ Mempersiapkan build...")
            
            full_url, ib_filename = await find_imagebuilder_url_and_name(
                current_config["VERSION"], current_config["TARGET"], current_config["SUBTARGET"]
            )
            if not full_url:
                await status_message.delete()
                await send_temporary_message(context, chat_id, "❌ GAGAL: Tidak dapat menemukan file Image Builder.")
                self.status = "Failed"
                return
                
            self.ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")
            context.bot_data['ib_dir'] = self.ib_dir
            
            if not os.path.isdir(self.ib_dir):
                if not os.path.exists(ib_filename):
                    await status_message.edit_text(f"📥 Mengunduh `{ib_filename}`...", parse_mode='Markdown')
                    download_proc = await asyncio.create_subprocess_shell(f"wget -q --show-progress {full_url} -O {ib_filename}")
                    await download_proc.wait()
                await status_message.edit_text(f"📦 Mengekstrak `{ib_filename}`...", parse_mode='Markdown')
                extract_command = f"tar --use-compress-program=zstd -xf {ib_filename}" if ib_filename.endswith(".tar.zst") else f"tar -xf {ib_filename}"
                extract_proc = await asyncio.create_subprocess_shell(extract_command)
                await extract_proc.wait()
                try:
                    os.remove(ib_filename)
                    await status_message.edit_text(f"📦 Ekstraksi selesai, file arsip dihapus.")
                except OSError as e:
                    logger.error(f"Gagal menghapus file arsip {ib_filename}: {e}")

            current_profile = current_config["DEVICE_PROFILE"]
            valid_profiles = await get_device_profiles(self.ib_dir)
            if valid_profiles is None:
                await status_message.delete()
                await send_temporary_message(context, chat_id, "❌ GAGAL: Tidak bisa membaca daftar profil.")
                self.status = "Failed"
                return

            if current_profile not in valid_profiles:
                self.status = "Awaiting Profile"
                from handlers.settings_handler import create_paginated_keyboard
                keyboard = await create_paginated_keyboard(valid_profiles, 0, "p_select_")
                await status_message.edit_text(f"⚠️ **Profil `{current_profile}` tidak valid!**\n\nPilih profil yang benar untuk melanjutkan:", reply_markup=keyboard, parse_mode='Markdown')
                return

            if await _update_rootfs_in_config(self.ib_dir, str(current_config.get("ROOTFS_SIZE", "")).strip()):
                 await send_temporary_message(context, chat_id, f"💡 Info: Ukuran RootFS kustom diterapkan ke .config.")

            self.status = "Building..."
            command = (
                f"make -C {self.ib_dir} image "
                f"PROFILE='{current_config['DEVICE_PROFILE']}' "
                f"PACKAGES='{current_config['CUSTOM_PACKAGES']}' V=s"
            )
            await status_message.edit_text(
                f"✅ Konfigurasi valid. Memulai build...\nPerintah `/cancel` tersedia.\n\n```\nLog akan muncul di sini...\n```",
                parse_mode='Markdown'
            )
            
            self.process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            log_content, last_update_time, last_output_time, last_displayed_log = "", time.time(), time.time(), ""
            
            while self.process.returncode is None:
                try:
                    line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)
                    if line:
                        last_output_time = time.time()
                        log_content += line.decode('utf-8', errors='ignore')
                    else: break
                except asyncio.TimeoutError:
                    if (time.time() - last_output_time) > NO_OUTPUT_TIMEOUT:
                        await self.cancel_current_build()
                        await send_temporary_message(context, chat_id, f"❌ Build dibatalkan otomatis karena macet.")
                        break
                    continue
                if (time.time() - last_update_time) > LOG_UPDATE_INTERVAL:
                    display_log = '\n'.join(log_content.strip().split('\n')[-15:])
                    if display_log.strip() and display_log != last_displayed_log:
                        try:
                            await status_message.edit_text(f"```\n{display_log}\n```", parse_mode='Markdown')
                            last_displayed_log = display_log
                        except (RetryAfter, BadRequest): await asyncio.sleep(5)
                        last_update_time = time.time()
            
            await self.process.wait()
            
            if self.status == "Cancelled":
                await status_message.edit_text("🛑 **Build Dibatalkan oleh Pengguna.**")
            elif self.process.returncode == 0:
                self.status = "Success"
                await self.handle_successful_build(context, chat_id, current_config, self.ib_dir, status_message)
            else:
                self.status = "Failed"
                final_log = "..." + log_content[-3800:] if len(log_content) > 3800 else log_content
                await status_message.edit_text(f"```\n{final_log}\n```\n❌ **Build GAGAL!** Kode error: {self.process.returncode}", parse_mode='Markdown')
            
            with open(BUILD_LOG_PATH, "w") as f: f.write(log_content)
        except Exception as e:
            logger.error(f"Terjadi error tak terduga dalam run_build_task: {e}", exc_info=True)
            if status_message: await status_message.delete()
            await send_temporary_message(context, chat_id, f"❌ Terjadi error kritis pada proses build: {e}")
            self.status = "Failed"
        finally:
            logger.info(f"Build task selesai dengan status akhir: {self.status}")
            self.process = None
            if self.status not in ["Success", "Failed", "Cancelled", "Awaiting Profile"]: self.status = "Idle"

    async def handle_successful_build(self, context, chat_id, config, ib_dir, status_message):
        try:
            VALID_EXTENSIONS = (".img.gz", ".bin", ".trx", ".vdi", ".vmdk", ".qcow2")
            all_files = glob.glob(os.path.join(ib_dir, 'bin', 'targets', '**/*'), recursive=True)
            firmware_files = sorted([f for f in all_files if os.path.isfile(f) and f.endswith(VALID_EXTENSIONS)])
            
            if not firmware_files:
                await status_message.edit_text("🤔 Gagal menemukan file firmware yang dihasilkan meskipun build sukses.")
                return
            
            new_entry_id = add_build_entry(
                version=config['VERSION'], target=config['TARGET'], subtarget=config['SUBTARGET'],
                profile=config['DEVICE_PROFILE'], packages=config['CUSTOM_PACKAGES'],
                firmware_files=firmware_files, ib_dir=ib_dir
            )
            if not new_entry_id:
                await status_message.edit_text("❌ Gagal menyimpan catatan build ke histori.")
                return

            keyboard = [[InlineKeyboardButton(os.path.basename(f), callback_data=f"upload_choice_{new_entry_id}_{i}")] for i, f in enumerate(firmware_files)]
            await status_message.edit_text(
                "✅ **Build Selesai!**\n\nDisimpan ke `/arsip`.\n👇 Pilih file untuk diunggah:",
                reply_markup=InlineKeyboardMarkup(keyboard)
            )
        except Exception as e:
            logger.error(f"Gagal dalam proses pasca-build: {e}")
            await status_message.edit_text(f"Terjadi kesalahan saat memproses hasil build: {e}")

    async def perform_upload(self, context, chat_id, file_path, status_message):
        try:
            config = context.bot_data.get('config', {})
            await status_message.edit_text(f"📤 Mengunggah `{os.path.basename(file_path)}`...", parse_mode='Markdown', reply_markup=None)
            
            uploaded_message = await upload_file_for_forwarding(
                file_path=file_path, destination_id=config.get("LEECH_DESTINATION_ID", "me"),
                status_message=status_message
            )
            if uploaded_message:
                try:
                    await context.bot.forward_message(chat_id=chat_id, from_chat_id=uploaded_message.chat_id, message_id=uploaded_message.id)
                    await status_message.delete()
                except Exception as e:
                    await status_message.edit_text(f"❌ Gagal me-forward file.\nError: {e}")
            else:
                logger.error("Gagal mendapatkan pesan yang diunggah dari Telethon (pesan error seharusnya sudah diedit).")
        except Exception as e:
            await send_temporary_message(context, chat_id, f"Terjadi kesalahan saat mengirim file: {e}")
            if status_message: await status_message.delete()

build_manager = BuildManager()
