# core/uploader.py

import asyncio
import logging
import os
import time
from telethon import TelegramClient, errors
from telegram.error import RetryAfter, BadRequest

import config

logger = logging.getLogger(__name__)

async def upload_file_for_forwarding(file_path: str, destination_id, status_message) -> 'Message' or None:
    # Buat instance client di dalam fungsi async untuk stabilitas
    client = TelegramClient('telegram_user_session', config.API_ID, config.API_HASH)
    
    try:
        try:
            if str(destination_id).lower() == 'me':
                target_entity = 'me'
                dest_name = "Saved Messages"
            else:
                target_entity = int(destination_id)
                dest_name = f"grup/channel ({destination_id})"
        except ValueError:
            logger.error(f"Destination ID '{destination_id}' tidak valid. Harus 'me' atau integer.")
            await status_message.edit_text(f"❌ ID Tujuan Leech tidak valid: {destination_id}")
            return None

        logger.info(f"Telethon: Menghubungkan untuk mengunggah ke {dest_name}...")
        
        last_update_time = 0
        file_name = os.path.basename(file_path)

        async def progress_callback(current, total):
            nonlocal last_update_time
            current_time = time.time()
            if current_time - last_update_time < 2.0: # Batasi update setiap 2 detik
                return
            
            progress_percent = round((current / total) * 100, 1)
            try:
                # Edit pesan status yang sudah ada dengan progres
                await status_message.edit_text(f"📤 Mengunggah `{file_name}`: {progress_percent}%", parse_mode='Markdown')
                last_update_time = current_time
            except (RetryAfter, BadRequest):
                # Jika kena rate limit, tunggu sebentar
                await asyncio.sleep(5)
            except Exception:
                # Abaikan error lain pada progress, yang penting upload jalan terus
                pass

        logger.info("Mencoba koneksi Telethon dengan timeout 30 detik...")
        try:
            # Menggunakan client.start() dengan timeout, lebih andal daripada async with
            await asyncio.wait_for(client.start(), timeout=30.0)
            logger.info("Koneksi Telethon berhasil dibuat.")
            
            uploaded_message = await client.send_file(
                entity=target_entity,
                file=file_path,
                caption=f"Build artifact: {file_name}",
                progress_callback=progress_callback
            )
            
            logger.info(f"Telethon: File berhasil diunggah ke {dest_name}.")
            await status_message.edit_text(f"✅ Berhasil diunggah. Meneruskan...", parse_mode='Markdown')
            return uploaded_message

        except asyncio.TimeoutError:
            logger.error("Koneksi Telethon timeout setelah 30 detik.")
            await status_message.edit_text("❌ Gagal terhubung ke Telegram (timeout). Periksa jaringan server Anda.")
            return None
        except errors.rpcerrorlist.PhoneNumberInvalidError:
            logger.error("Nomor telepon untuk sesi Telethon tidak valid.")
            await status_message.edit_text("❌ Sesi Telethon gagal: Nomor telepon tidak valid.")
            return None
        except Exception as e:
            logger.error(f"Terjadi error tak terduga saat koneksi atau upload Telethon: {e}", exc_info=True)
            await status_message.edit_text(f"❌ Error Telethon: {e}")
            return None
        finally:
            if client.is_connected():
                await client.disconnect()
                logger.info("Koneksi Telethon ditutup.")

    except Exception as e:
        logger.error(f"Error tak terduga di dalam upload_file_for_forwarding: {e}", exc_info=True)
        await status_message.edit_text(f"❌ Terjadi kesalahan kritis pada fungsi uploader.")
        return None
