# core/build_manager.py

import os
import asyncio
import logging
import time
import glob
from telegram.error import RetryAfter, BadRequest

from config import BUILD_LOG_PATH
from core.openwrt_api import find_imagebuilder_url_and_name, get_device_profiles
from core.uploader import upload_file_for_forwarding

logger = logging.getLogger(__name__)

LOG_UPDATE_INTERVAL = 3.0
NO_OUTPUT_TIMEOUT = 300 

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
                logger.info("Proses build berhasil dibatalkan oleh pengguna.")
                return True
            except ProcessLookupError:
                logger.warning("Mencoba membatalkan proses yang sudah tidak ada.")
                self.process = None
                self.status = "Idle"
                return False
        return False

    async def run_build_task(self, context, chat_id, current_config):
        try:
            self.status = "Preparing"
            await context.bot.send_message(chat_id, "Mempersiapkan build...")
            
            full_url, ib_filename = await find_imagebuilder_url_and_name(
                current_config["VERSION"], current_config["TARGET"], current_config["SUBTARGET"]
            )
            if not full_url:
                self.status = "Failed"
                await context.bot.send_message(chat_id, "❌ GAGAL: Tidak dapat menemukan file Image Builder.")
                return
                
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
            
            current_profile = current_config["DEVICE_PROFILE"]
            valid_profiles = await get_device_profiles(self.ib_dir)
            if valid_profiles is None:
                self.status = "Failed"
                await context.bot.send_message(chat_id, "❌ GAGAL: Tidak bisa membaca daftar profil.")
                return

            if current_profile not in valid_profiles:
                self.status = "Awaiting Profile"
                from handlers.settings_handler import create_paginated_keyboard
                keyboard = await create_paginated_keyboard(valid_profiles, 0, "p_select_")
                await context.bot.send_message(chat_id, f"⚠️ **Profil `{current_profile}` tidak valid!**\n\nPilih profil yang benar untuk melanjutkan:", reply_markup=keyboard, parse_mode='Markdown')
                return

            self.status = "Building..."
            
            rootfs_size = str(current_config.get("ROOTFS_SIZE", "")).strip()
            env_prefix = ""
            if rootfs_size and rootfs_size.isdigit() and int(rootfs_size) > 0:
                env_prefix = f"ROOTFS_PART_SIZE={rootfs_size}m "
                await context.bot.send_message(chat_id, f"💡 Menggunakan ukuran RootFS kustom: {rootfs_size}MB")

            command = (
                f"{env_prefix}make -C {self.ib_dir} image "
                f"PROFILE={current_config['DEVICE_PROFILE']} "
                f"PACKAGES='{current_config['CUSTOM_PACKAGES']}' V=s"
            )

            progress_message = await context.bot.send_message(
                chat_id,
                f"✅ Konfigurasi valid. Memulai build...\n\nPerintah `/cancel` tersedia untuk membatalkan.\n\n```\nLog akan muncul di sini...\n```",
                parse_mode='Markdown'
            )
            logger.info(f"Executing command: {command}")
            
            message_id = progress_message.message_id
            self.process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
            
            log_content = ""
            last_update_time = time.time()
            last_output_time = time.time()

            while self.process.returncode is None:
                try:
                    line = await asyncio.wait_for(self.process.stdout.readline(), timeout=1.0)
                    if line:
                        last_output_time = time.time()
                        decoded_line = line.decode('utf-8', errors='ignore').strip()
                        if decoded_line: log_content += decoded_line + "\n"
                    else:
                        break
                except asyncio.TimeoutError:
                    if (time.time() - last_output_time) > NO_OUTPUT_TIMEOUT:
                        logger.warning(f"Tidak ada output selama {NO_OUTPUT_TIMEOUT} detik. Proses dianggap macet.")
                        await self.cancel_current_build()
                        await context.bot.send_message(chat_id, f"❌ Build dibatalkan secara otomatis karena macet (tidak ada output selama {NO_OUTPUT_TIMEOUT / 60:.0f} menit).")
                        break
                    continue

                if (time.time() - last_update_time) > LOG_UPDATE_INTERVAL:
                    log_lines = log_content.strip().split('\n')
                    last_15_lines = log_lines[-15:]
                    display_log = '\n'.join(last_15_lines)

                    if display_log.strip():
                        try:
                            await context.bot.edit_message_text(
                                chat_id=chat_id, 
                                message_id=message_id, 
                                text=f"```\n{display_log}\n```", 
                                parse_mode='Markdown'
                            )
                            last_update_time = time.time()
                        except (RetryAfter, BadRequest):
                            pass
            
            await self.process.wait()
            return_code = self.process.returncode
            
            final_log = "..." + log_content[-3800:] if len(log_content) > 3800 else log_content

            if self.status == "Cancelled":
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text="🛑 **Build Dibatalkan oleh Pengguna.**")
            elif return_code == 0:
                self.status = "Success"
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"```\n{final_log}\n```\n✅ **Build Selesai!**", parse_mode='Markdown')
                await self.send_firmware(context, chat_id, current_config, self.ib_dir)
            else:
                self.status = "Failed"
                await context.bot.edit_message_text(chat_id=chat_id, message_id=message_id, text=f"```\n{final_log}\n```\n❌ **Build GAGAL!** Kode error: {return_code}", parse_mode='Markdown')
            
            with open(BUILD_LOG_PATH, "w") as f: f.write(log_content)

        except Exception as e:
            logger.error(f"Terjadi error tak terduga dalam run_build_task: {e}")
            await context.bot.send_message(chat_id, f"❌ Terjadi error kritis pada proses build: {e}")
            self.status = "Failed"
        
        finally:
            logger.info(f"Build task selesai dengan status akhir: {self.status}")
            self.process = None
            if self.status not in ["Success", "Failed", "Cancelled", "Awaiting Profile"]:
                self.status = "Idle"

    async def send_firmware(self, context, chat_id, config, ib_dir):
        try:
            keyword = config.get("UPLOAD_FILENAME_CONTAINS", "combined-efi")
            search_pattern = f"**/*{keyword}*.img.gz"
            search_path = os.path.join(ib_dir, 'bin/targets', search_pattern)
            firmware_files = glob.glob(search_path, recursive=True)

            if not firmware_files:
                await context.bot.send_message(chat_id, f"🤔 Gagal menemukan file `.img.gz` yang mengandung kata kunci `{keyword}`.")
                return

            latest_file = max(firmware_files, key=os.path.getmtime)
            file_name = os.path.basename(latest_file)
            file_size_mb = os.path.getsize(latest_file) / (1024 * 1024)

            status_message = await context.bot.send_message(
                chat_id,
                f"✔️ Menemukan file: `{file_name}` ({file_size_mb:.2f} MB).\nMempersiapkan pengiriman..."
            )

            leech_destination = config.get("LEECH_DESTINATION_ID", "me")

            uploaded_message = await upload_file_for_forwarding(
                file_path=latest_file,
                destination_id=leech_destination,
                status_message=status_message
            )

            if uploaded_message:
                try:
                    await context.bot.forward_message(
                        chat_id=chat_id,
                        from_chat_id=uploaded_message.chat_id,
                        message_id=uploaded_message.id
                    )
                    logger.info(f"Berhasil me-forward file dari {leech_destination} ke pengguna.")
                    await status_message.delete()
                except Exception as e:
                    logger.error(f"Gagal me-forward pesan: {e}")
                    await status_message.edit_text(f"❌ Gagal me-forward file.\nError: {e}")
            else:
                logger.error("Gagal mendapatkan pesan yang diunggah dari Telethon.")

        except Exception as e:
            logger.error(f"Gagal dalam proses pengiriman firmware: {e}")
            await context.bot.send_message(chat_id, f"Terjadi kesalahan saat mengirim file: {e}")

build_manager = BuildManager()
