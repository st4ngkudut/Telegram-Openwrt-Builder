# core/uploader.py

import asyncio
import logging
import os
from telethon import TelegramClient

import config

logger = logging.getLogger(__name__)

client = TelegramClient('telegram_user_session', config.API_ID, config.API_HASH)

async def upload_file_for_forwarding(file_path: str, destination_id, status_message) -> 'Message' or None:
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
        async with client:
            logger.info(f"Telethon: Koneksi berhasil. Mengirim file {file_path} ke {dest_name}")
            
            async def progress_callback(current, total):
                progress_percent = round((current / total) * 100, 1)
                try:
                    await status_message.edit_text(f"📤 Mengunggah ke '{dest_name}': {progress_percent}%")
                except Exception:
                    pass

            uploaded_message = await client.send_file(
                entity=target_entity,
                file=file_path,
                caption=f"Build artifact: {os.path.basename(file_path)}",
                progress_callback=progress_callback
            )
        
        logger.info(f"Telethon: File berhasil diunggah ke {dest_name}.")
        await status_message.edit_text(f"✅ Berhasil diunggah ke '{dest_name}'. Meneruskan...")
        return uploaded_message

    except Exception as e:
        logger.error(f"Telethon: Gagal mengunggah file. Error: {e}")
        await status_message.edit_text(f"❌ Gagal mengunggah file via Telethon.\nError: {e}")
        return None
