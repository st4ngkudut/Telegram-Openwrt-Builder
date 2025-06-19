# core/history_manager.py

import json
import logging
import os
import time
import uuid
import shutil

from config import HISTORY_DB_PATH

logger = logging.getLogger(__name__)

def load_history():
    if not os.path.exists(HISTORY_DB_PATH):
        return []
    try:
        with open(HISTORY_DB_PATH, 'r') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Gagal membaca history.json: {e}. Mengembalikan list kosong.")
        return []

def save_history(history_data):
    try:
        with open(HISTORY_DB_PATH, 'w') as f:
            json.dump(history_data, f, indent=4)
        return True
    except IOError as e:
        logger.error(f"Gagal menyimpan history.json: {e}")
        return False

def add_build_entry(config_data, firmware_files, ib_dir):
    """Menambahkan entri baru ke dalam database histori menggunakan dictionary config."""
    history = load_history()
    
    files_to_store = {os.path.basename(path): path for path in firmware_files}
    new_entry_id = str(uuid.uuid4())
    
    # Membuat entri baru dengan mengambil data dari dictionary config_data
    new_entry = {
        "id": new_entry_id,
        "timestamp": int(time.time()),
        "build_mode": config_data.get('build_mode', 'official'),
        
        # Data dari build resmi
        "version": config_data.get('VERSION'),
        "target": config_data.get('TARGET'),
        "subtarget": config_data.get('SUBTARGET'),
        "profile": config_data.get('DEVICE_PROFILE'),
        "packages": config_data.get('CUSTOM_PACKAGES'),
        
        # Data dari build amlogic
        "ROOTFS_URL": config_data.get('ROOTFS_URL'),
        "BOARD": config_data.get('BOARD'),
        "ROOTFS_SIZE": config_data.get('ROOTFS_SIZE'),
        "KERNEL_VERSION": config_data.get('KERNEL_VERSION'),
        "KERNEL_TAG": config_data.get('KERNEL_TAG'),
        "KERNEL_AUTO_UPDATE": config_data.get('KERNEL_AUTO_UPDATE'),
        "BUILDER_NAME": config_data.get('BUILDER_NAME'),

        # Data umum
        "firmware_files": files_to_store,
        "ib_dir": ib_dir
    }
    
    # Membersihkan entri dari kunci yang nilainya None atau kosong
    final_entry = {k: v for k, v in new_entry.items() if v is not None and v != ""}

    history.insert(0, final_entry)
    
    if save_history(history):
        return new_entry_id
    return None

def remove_build_entry(build_id):
    history = load_history()
    entry_to_delete = next((entry for entry in history if entry.get('id') == build_id), None)
    if not entry_to_delete:
        return False
    files_to_delete = entry_to_delete.get('firmware_files', {}).values()
    for f_path in files_to_delete:
        if os.path.exists(f_path):
            try:
                os.remove(f_path)
                logger.info(f"Menghapus file hasil compile: {f_path}")
            except OSError as e:
                logger.error(f"Gagal menghapus file {f_path}: {e}")
    history_after_deletion = [entry for entry in history if entry.get('id') != build_id]
    save_history(history_after_deletion)
    logger.info(f"Entri build dengan ID {build_id} berhasil dihapus dari histori.")
    return True

def remove_ib_directory_and_entries(ib_dir_to_delete):
    if os.path.isdir(ib_dir_to_delete):
        try:
            shutil.rmtree(ib_dir_to_delete)
            logger.info(f"Menghapus direktori Image Builder: {ib_dir_to_delete}")
        except OSError as e:
            logger.error(f"Gagal menghapus direktori {ib_dir_to_delete}: {e}")
            return False
    history = load_history()
    history_after_deletion = [
        entry for entry in history 
        if entry.get('ib_dir') != ib_dir_to_delete
    ]
    save_history(history_after_deletion)
    logger.info(f"Semua entri histori yang terkait dengan {ib_dir_to_delete} telah dihapus.")
    return True
