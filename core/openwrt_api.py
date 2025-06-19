# core/openwrt_api.py

import os
import logging
import re
from collections import defaultdict
import asyncio

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# Cache sekarang perlu membedakan sumber
version_cache = {}
target_cache = {}


async def scrape_openwrt_versions(base_url: str):
    """Mengambil dan meng-cache versi dari base_url yang diberikan."""
    global version_cache
    # Gunakan base_url sebagai kunci cache
    if base_url in version_cache:
        return version_cache[base_url]
    
    versions = defaultdict(list)
    url = f"{base_url}/releases/"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
        
        soup = BeautifulSoup(response.text, 'lxml')
        # Pattern yang lebih umum untuk mencakup OpenWrt & ImmortalWrt
        version_pattern = re.compile(r'^\d{2}\.\d{2}(\.\d+)?(-rc\d)?.*\/$')
        
        for link in soup.find_all('a'):
            href = link.get('href')
            if href and version_pattern.match(href):
                version_str = href.strip('/')
                major_series = ".".join(version_str.split('.')[:2])
                versions[major_series].append(version_str)
                
        for key in versions:
            versions[key].sort(key=lambda v: list(map(int, re.findall(r'\d+', v))), reverse=True)
            
        # Simpan ke cache menggunakan base_url sebagai kunci
        version_cache[base_url] = dict(sorted(versions.items(), reverse=True))
        logger.info(f"Berhasil mengambil dan mem-cache {len(version_cache[base_url])} seri rilis dari {base_url}.")
        return version_cache[base_url]
        
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengambil daftar versi dari {url}: {e}")
        return None

async def scrape_targets_for_version(version: str, base_url: str):
    """Mengambil target untuk versi spesifik dari base_url."""
    cache_key = f"{base_url}_{version}"
    if cache_key in target_cache:
        return target_cache[cache_key]
        
    targets = []
    url = f"{base_url}/releases/{version}/targets/"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'lxml')
        for link in soup.find_all('a'):
            href = link.get('href')
            if href.endswith('/') and not href.startswith('?') and '..' not in href:
                target_name = href.strip('/')
                if target_name and 'sha256sums' not in target_name:
                    targets.append(target_name)
                    
        target_cache[cache_key] = sorted(targets)
        logger.info(f"Berhasil mengambil {len(targets)} target untuk v{version} dari {base_url}.")
        return sorted(targets)
        
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengambil daftar target untuk v{version} dari {url}: {e}")
        return None

async def scrape_subtargets_for_target(version: str, target: str, base_url: str):
    """Mengambil subtarget dari target/versi/base_url yang diberikan."""
    subtargets = []
    url = f"{base_url}/releases/{version}/targets/{target}/"
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(url)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'lxml')
        for link in soup.find_all('a'):
            href = link.get('href')
            if href.endswith('/') and not href.startswith('?'):
                subtarget_name = href.strip('/')
                if subtarget_name and subtarget_name != '..':
                    subtargets.append(subtarget_name)
                    
        logger.info(f"Berhasil mengambil {len(subtargets)} subtarget untuk {target} dari {base_url}.")
        return sorted(subtargets)
        
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengambil daftar subtarget untuk {target} dari {url}: {e}")
        return None
        
async def find_imagebuilder_url_and_name(version: str, target: str, subtarget: str, base_url: str):
    """Mencari URL Image Builder dari parameter dan base_url yang diberikan."""
    # Subtarget bisa kosong, jadi kita filter
    path_parts = [base_url, "releases", version, "targets", target, subtarget]
    full_base_url = "/".join(filter(None, path_parts)) + "/"
    
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            response = await client.get(full_base_url)
            response.raise_for_status()
            
        soup = BeautifulSoup(response.text, 'lxml')
        # Pattern untuk openwrt-imagebuilder atau immortalwrt-imagebuilder
        ib_pattern = re.compile(r'^(openwrt|immortalwrt)-imagebuilder-.*(\.tar\.xz|\.tar\.zst)$')
        
        for link in soup.find_all('a'):
            href = link.get('href')
            if href and ib_pattern.match(href):
                logger.info(f"Ditemukan file Image Builder: {href} di {full_base_url}")
                return full_base_url + href, href
                
        logger.warning(f"Tidak ada file Image Builder yang ditemukan di {full_base_url}")
        return None, None
        
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengakses halaman target {full_base_url}: {e}")
        return None, None

async def get_device_profiles(ib_dir: str):
    """Mengambil profil perangkat dari direktori Image Builder yang diekstrak."""
    if not os.path.isdir(ib_dir):
        logger.error(f"Direktori Image Builder tidak ditemukan: {ib_dir}")
        return None
        
    profiles = []
    command = f"make -C {ib_dir} info"
    try:
        process = await asyncio.create_subprocess_shell(command, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Gagal menjalankan 'make info': {stderr.decode()}")
            return None
            
        # Logika parsing output 'make info'
        for line in stdout.decode().splitlines():
            if ':' in line and not line.startswith(' '):
                profile_name = line.split(':')[0].strip()
                if profile_name and 'Default' not in profile_name:
                    profiles.append(profile_name)
                    
        logger.info(f"Ditemukan {len(profiles)} profil perangkat.")
        return sorted(profiles)
        
    except Exception as e:
        logger.error(f"Error saat mengambil profil perangkat: {e}")
        return None
