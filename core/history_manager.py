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

def add_build_entry(version, target, subtarget, profile, packages, firmware_files, ib_dir):
    history = load_history()
    files_to_store = {os.path.basename(path): path for path in firmware_files}
    new_entry_id = str(uuid.uuid4())
    
    new_entry = {
        "id": new_entry_id, 
        "timestamp": int(time.time()),
        "version": version,
        "target": target,
        "subtarget": subtarget,
        "profile": profile,
        "packages": packages,
        "firmware_files": files_to_store,
        "ib_dir": ib_dir
    }
    
    history.insert(0, new_entry)
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
