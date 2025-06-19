# core/build_manager.py

import os
import asyncio
import logging
import time
import glob
import re
import shutil
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import RetryAfter, BadRequest

import config
from config import OPENWRT_DOWNLOAD_URL, IMMORTALWRT_DOWNLOAD_URL, AML_BUILD_SCRIPT_DIR, AML_BUILD_SCRIPT_REPO, BUILD_LOG_PATH
from .openwrt_api import find_imagebuilder_url_and_name, get_device_profiles
from .uploader import upload_file_for_forwarding
from .history_manager import add_build_entry
from handlers.utils import send_temporary_message

logger = logging.getLogger(__name__)

LOG_UPDATE_INTERVAL = 3.0
NO_OUTPUT_TIMEOUT = 900
FILES_PER_PAGE = 5

class BuildManager:
    def __init__(self):
        self.status = "Idle"
        self.process = None
        self.is_starting_build = False
    
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

    async def run_build_task(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, build_config: dict, mode: str):
        self.status = f"Preparing {mode} build..."
        status_message = await context.bot.send_message(chat_id, f"⏳ Mempersiapkan build mode: {mode.title()}...")
        try:
            if mode == 'official':
                await self._run_official_build(context, chat_id, build_config, status_message)
            elif mode == 'amlogic':
                await self._run_amlogic_remake(context, chat_id, build_config, status_message)
            else:
                raise ValueError(f"Mode build tidak dikenal: {mode}")
        except Exception as e:
            logger.error(f"Terjadi error tak terduga dalam run_build_task (mode: {mode}): {e}", exc_info=True)
            if status_message:
                try: await status_message.delete()
                except: pass
            await send_temporary_message(context, chat_id, f"❌ Terjadi error kritis pada proses build: {e}")
            self.status = "Failed"
        finally:
            logger.info(f"Build task selesai dengan status akhir: {self.status}")
            if self.status not in ["Success", "Failed", "Cancelled", "Awaiting Profile"]:
                self.status = "Idle"

    async def _apply_customizations(self, ib_dir: str, config: dict, context: ContextTypes.DEFAULT_TYPE, chat_id: int):
        source = config.get('BUILD_SOURCE', 'openwrt')
        target = config.get('TARGET')
        subtarget = config.get('SUBTARGET')
        if not target:
            logger.info("Target belum diatur, melewati kustomisasi repo.")
            return
        arch_key = f"{source}_{target}_{subtarget or 'default'}"
        custom_repos_for_arch = config.get("CUSTOM_REPOS", {}).get(arch_key, "").strip()
        template_repo_conf_path = os.path.join(ib_dir, "repositories.conf")
        if not os.path.exists(template_repo_conf_path):
            logger.warning("File template repositories.conf tidak ditemukan, tidak bisa menerapkan kustomisasi.")
            return
        with open(template_repo_conf_path, 'r') as f_template:
            content = f_template.read()
        original_content = content; modified_content = content
        if custom_repos_for_arch:
            modified_content += "\n# --- Custom Repositories by Bot ---\n"
            package_arch = "all"
            match = re.search(r'packages/([\w.-]+)/base', original_content)
            if match: package_arch = match.group(1); logger.info(f"Arsitektur paket terdeteksi: {package_arch}")
            else:
                package_arch = f"{target}/{subtarget}" if subtarget else target
                logger.warning(f"Tidak dapat mendeteksi arsitektur paket dari URL, menggunakan fallback: {package_arch}")
            for i, repo_url in enumerate(custom_repos_for_arch.splitlines()):
                if repo_url.strip():
                    repo_url_final = repo_url.strip().replace("{arch}", package_arch)
                    repo_name = f"custom_repo_{i+1}"
                    modified_content += f"src/gz {repo_name} {repo_url_final}\n"
            modified_content = re.sub(r"^\s*option\s+check_signature.*$", "# option check_signature", modified_content, flags=re.MULTILINE)
        if modified_content != original_content:
            try:
                # Membuat backup sebelum menimpa
                shutil.copyfile(template_repo_conf_path, template_repo_conf_path + ".bak")
                with open(template_repo_conf_path, "w") as f_final:
                    f_final.write(modified_content)
                logger.info(f"File {template_repo_conf_path} berhasil dimodifikasi secara langsung.")
                await send_temporary_message(context, chat_id, "ℹ️ Info: Custom repo diterapkan pada repositories.conf.")
            except Exception as e:
                logger.error(f"Gagal memodifikasi repositories.conf: {e}")
                await send_temporary_message(context, chat_id, "❌ Gagal menerapkan custom repo.")
        else:
            logger.info("Tidak ada perubahan yang dilakukan pada repositories.conf.")

    async def _update_rootfs_config(self, ib_dir: str, rootfs_size: str):
        if not (rootfs_size and rootfs_size.isdigit() and int(rootfs_size) > 0): return False
        config_path = os.path.join(ib_dir, '.config')
        try:
            lines = [];
            if os.path.exists(config_path):
                with open(config_path, 'r') as f: lines = f.readlines()
            new_lines, found = [], False
            config_string = f"CONFIG_TARGET_ROOTFS_PARTSIZE={rootfs_size}\n"
            for line in lines:
                if line.strip().startswith("CONFIG_TARGET_ROOTFS_PARTSIZE"): new_lines.append(config_string); found = True
                else: new_lines.append(line)
            if not found: new_lines.append(config_string)
            with open(config_path, 'w') as f: f.writelines(new_lines)
            return True
        except Exception as e:
            logger.error(f"Gagal update .config rootfs: {e}")
            return False

    async def _run_official_build(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, config: dict, status_message):
        source = config.get("BUILD_SOURCE", "openwrt"); base_url = IMMORTALWRT_DOWNLOAD_URL if source == 'immortalwrt' else OPENWRT_DOWNLOAD_URL
        full_url, ib_filename = await find_imagebuilder_url_and_name(config["VERSION"], config["TARGET"], config["SUBTARGET"], base_url)
        if not full_url: raise ValueError("Tidak dapat menemukan file Image Builder dari sumber yang dipilih.")
        ib_dir = ib_filename.replace(".tar.xz", "").replace(".tar.zst", "")
        if not os.path.isdir(ib_dir):
            if not os.path.exists(ib_filename):
                await status_message.edit_text(f"📥 Mengunduh `{ib_filename}`...", parse_mode='Markdown')
                download_proc = await asyncio.create_subprocess_shell(f"wget -q --show-progress {full_url} -O {ib_filename}")
                await download_proc.wait()
            await status_message.edit_text(f"📦 Mengekstrak `{ib_filename}`...", parse_mode='Markdown')
            extract_command = f"tar --use-compress-program=zstd -xf {ib_filename}" if ib_filename.endswith(".tar.zst") else f"tar -xf {ib_filename}"
            extract_proc = await asyncio.create_subprocess_shell(extract_command)
            await extract_proc.wait()
            if os.path.exists(ib_filename): os.remove(ib_filename)
        valid_profiles = await get_device_profiles(ib_dir)
        if config["DEVICE_PROFILE"] not in valid_profiles:
            self.status = "Awaiting Profile"
            keyboard = [[InlineKeyboardButton(p, callback_data=f"build_fix_profile_{p}")] for p in valid_profiles[:20]]
            await status_message.edit_text(f"⚠️ **Profil `{config['DEVICE_PROFILE']}` tidak valid!**\n\nPilih profil yang benar:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode='Markdown'); return
        await self._apply_customizations(ib_dir, config, context, chat_id)
        if await self._update_rootfs_config(ib_dir, str(config.get("ROOTFS_SIZE", "")).strip()):
            await send_temporary_message(context, chat_id, f"💡 Info: Ukuran RootFS kustom diterapkan.")
        self.status = "Building..."
        command = (f"make -C {ib_dir} image PROFILE='{config['DEVICE_PROFILE']}' PACKAGES='{config['CUSTOM_PACKAGES']}' V=s")
        await self._execute_and_stream_log(context, chat_id, command, config, ib_dir, status_message, 'official')

    async def _run_amlogic_remake(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, config: dict, status_message):
        await status_message.edit_text("⚙️ Mempersiapkan Amlogic Remake...")
        if not os.path.isdir(AML_BUILD_SCRIPT_DIR):
            await status_message.edit_text(f"📥 Melakukan clone repo skrip build Amlogic...")
            clone_proc = await asyncio.create_subprocess_shell(f"git clone --depth=1 {AML_BUILD_SCRIPT_REPO}")
            await clone_proc.wait()
            if clone_proc.returncode != 0: raise Exception("Gagal clone repositori skrip Amlogic.")
            remake_script_path = os.path.join(AML_BUILD_SCRIPT_DIR, 'remake')
            chmod_proc = await asyncio.create_subprocess_shell(f"chmod +x {remake_script_path}")
            await chmod_proc.wait()
            logger.info("Izin eksekusi untuk 'remake' telah berhasil diatur.")
        
        rootfs_source_path = config.get("local_rootfs_path")
        rootfs_url = config.get("ROOTFS_URL")
        
        if not rootfs_source_path and not rootfs_url:
            raise ValueError("Sumber RootFS (URL atau Lokal) untuk Amlogic belum diatur.")
        
        # Tentukan nama file yang akan digunakan
        if rootfs_source_path:
            temp_rootfs_filename = os.path.basename(rootfs_source_path)
            await status_message.edit_text(f"ℹ️ Menggunakan RootFS lokal dari `{temp_rootfs_filename}`...")
            # Salin file lokal, jangan pindahkan, agar file asli tetap ada
            shutil.copy(rootfs_source_path, temp_rootfs_filename)
        else:
            temp_rootfs_filename = os.path.basename(rootfs_url)
            await status_message.edit_text(f"📥 Mengunduh RootFS dari `{rootfs_url}`...")
            download_proc = await asyncio.create_subprocess_shell(f"wget -q --show-progress {rootfs_url} -O {temp_rootfs_filename}")
            await download_proc.wait()
            if download_proc.returncode != 0: raise Exception("Gagal mengunduh RootFS.")
        
        rootfs_dest_dir = os.path.join(AML_BUILD_SCRIPT_DIR, "openwrt-armsr")
        os.makedirs(rootfs_dest_dir, exist_ok=True)
        final_rootfs_path = os.path.join(rootfs_dest_dir, "openwrt-armsr-armv8-generic-rootfs.tar.gz") # Nama file target
        if os.path.exists(final_rootfs_path): os.remove(final_rootfs_path)
        shutil.move(temp_rootfs_filename, final_rootfs_path)
        logger.info(f"RootFS ditempatkan di: {final_rootfs_path}")

        self.status = "Building..."
        size_arg = ""; rootfs_size = str(config.get("ROOTFS_SIZE", "")).strip()
        if rootfs_size.isdigit() and int(rootfs_size) > 0: size_arg = f"-s {rootfs_size}"
        kernel_version = config.get("KERNEL_VERSION", ""); kernel_tag = config.get("KERNEL_TAG", "stable")
        kernel_full_version = f"{kernel_version}-{kernel_tag}" if kernel_tag and kernel_tag.lower() != "stable" else kernel_version
        kernel_arg = f"-k {kernel_full_version}" if kernel_full_version else ""
        board_arg = f"-b {config.get('BOARD')}" if config.get("BOARD") else ""
        builder_arg = f"-n {config.get('BUILDER_NAME')}" if config.get("BUILDER_NAME") else ""
        autoupdate_arg = f"-a {'true' if config.get('KERNEL_AUTO_UPDATE') else 'false'}"
        command_parts = ["cd", AML_BUILD_SCRIPT_DIR, "&&", "sudo", "./remake", board_arg, kernel_arg, size_arg, builder_arg, autoupdate_arg]
        command = " ".join(filter(None, command_parts))
        output_dir = os.path.join(AML_BUILD_SCRIPT_DIR, 'out')
        await self._execute_and_stream_log(context, chat_id, command, config, output_dir, status_message, 'amlogic')

    async def _execute_and_stream_log(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, command: str, config: dict, build_dir: str, status_message, mode: str):
        await status_message.edit_text(f"🚀 Memulai eksekusi...\n`{command}`", parse_mode='Markdown')
        self.process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)
        log_content_bytes = b''; last_update_time, last_output_time = time.time(), time.time(); last_displayed_log = ""
        while self.process.returncode is None:
            try:
                chunk = await asyncio.wait_for(self.process.stdout.read(2048), timeout=1.0)
                if chunk: last_output_time = time.time(); log_content_bytes += chunk
                else:
                    await asyncio.sleep(0.5)
                    if self.process.stdout.at_eof(): break
            except asyncio.TimeoutError: pass
            if (time.time() - last_output_time) > NO_OUTPUT_TIMEOUT:
                await self.cancel_current_build(); await send_temporary_message(context, chat_id, "❌ Build dibatalkan otomatis karena tidak ada output (macet)."); return
            if (time.time() - last_update_time) > LOG_UPDATE_INTERVAL:
                decoded_log = log_content_bytes.decode('utf-8', errors='ignore')
                display_log = decoded_log[-2000:]
                if display_log.strip() and display_log != last_displayed_log:
                    try:
                        await status_message.edit_text(f"```\n{display_log}\n```", parse_mode='Markdown')
                        last_displayed_log = display_log
                    except (RetryAfter, BadRequest) as e: logger.warning(f"Gagal update log: {e}"); await asyncio.sleep(5)
                    last_update_time = time.time()
        await self.process.wait()
        if self.process.returncode == 0:
            self.status = "Success"
            await self.handle_successful_build(context, chat_id, config, build_dir, status_message, mode)
        else:
            final_log = log_content_bytes.decode('utf-8', errors='ignore')
            display_log = "..." + final_log[-3800:] if len(final_log) > 3800 else final_log
            raise Exception(f"Proses build gagal dengan kode error {self.process.returncode}.\n\nLog Akhir:\n{display_log}")

    async def handle_successful_build(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, config: dict, build_dir: str, status_message, mode: str):
        search_path = os.path.join(build_dir, '**/*')
        VALID_EXTENSIONS = (".img.gz", ".img", ".bin", ".trx", ".vdi", ".vmdk", ".qcow2")
        all_files = glob.glob(search_path, recursive=True)
        firmware_files = sorted([f for f in all_files if os.path.isfile(f) and f.endswith(VALID_EXTENSIONS)])
        if not firmware_files:
            await status_message.edit_text("🤔 Gagal menemukan file firmware yang dihasilkan meskipun build sukses."); return
        entry_data = config.copy(); entry_data['build_mode'] = mode
        entry_data['version'] = config.get('VERSION', 'Amlogic')
        new_entry_id = add_build_entry(config_data=entry_data, firmware_files=firmware_files, ib_dir=(build_dir if mode == 'official' else AML_BUILD_SCRIPT_DIR))
        if not new_entry_id:
            await status_message.edit_text("❌ Gagal menyimpan catatan build ke histori."); return
        total_pages = -(-len(firmware_files) // FILES_PER_PAGE)
        paginated_files = firmware_files[:FILES_PER_PAGE]
        keyboard = [[InlineKeyboardButton(os.path.basename(f), callback_data=f"upload_choice_{new_entry_id}_{i}")] for i, f in enumerate(paginated_files)]
        nav_row = []
        if total_pages > 1: nav_row.append(InlineKeyboardButton("Berikutnya »", callback_data=f"build_page_{new_entry_id}_1"))
        if nav_row: keyboard.append(nav_row)
        if mode == 'official' and any("rootfs" in f for f in firmware_files):
             keyboard.append([InlineKeyboardButton("➡️ Lanjutkan ke Amlogic Remake", callback_data=f"chain_relic_{new_entry_id}")])
        await status_message.edit_text(
            f"✅ **Build Selesai!** (Halaman 1/{total_pages})\n\nDisimpan ke `/arsip`.\n👇 Pilih file untuk diunggah:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    
    async def perform_upload(self, context: ContextTypes.DEFAULT_TYPE, chat_id: int, file_path: str, status_message):
        try:
            from handlers.settings_handler import get_config
            config_full = get_config(context)
            active_mode = config_full.get('active_build_mode', 'official')
            config = config_full.get(active_mode, {})
            leech_dest = config.get("LEECH_DESTINATION_ID", "me")
            await status_message.edit_text(f"📤 Mengunggah `{os.path.basename(file_path)}`...", parse_mode='Markdown', reply_markup=None)
            uploaded_message = await upload_file_for_forwarding(file_path=file_path, destination_id=leech_dest, status_message=status_message)
            if uploaded_message:
                try:
                    await context.bot.forward_message(chat_id=chat_id, from_chat_id=uploaded_message.chat_id, message_id=uploaded_message.id)
                    await status_message.delete()
                except Exception as e:
                    await status_message.edit_text(f"❌ Gagal me-forward file.\nError: {e}")
        except Exception as e:
            await send_temporary_message(context, chat_id, f"Terjadi kesalahan saat mengirim file: {e}")
            if status_message: 
                try: await status_message.delete()
                except: pass

build_manager = BuildManager()
