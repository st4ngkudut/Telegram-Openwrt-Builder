# core/openwrt_api.py

import os
import logging
import re
from collections import defaultdict
import asyncio

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

version_cache = None
target_cache = {}

async def scrape_openwrt_versions():
    global version_cache
    if version_cache:
        return version_cache

    versions = defaultdict(list)
    url = "https://downloads.openwrt.org/releases/"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        version_pattern = re.compile(r'^\d{2}\.\d{2}\.\d+.*\/$')
        
        for link in soup.find_all('a'):
            href = link.get('href')
            if href and version_pattern.match(href):
                version_str = href.strip('/')
                major_series = ".".join(version_str.split('.')[:2])
                versions[major_series].append(version_str)
        
        for key in versions:
            versions[key].sort(key=lambda v: list(map(int, re.findall(r'\d+', v))), reverse=True)
        
        version_cache = dict(sorted(versions.items(), reverse=True))
        logger.info(f"Berhasil mengambil dan mem-cache {len(version_cache)} seri rilis OpenWrt.")
        return version_cache
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengambil daftar versi: {e}")
        return None

async def scrape_targets_for_version(version):
    if version in target_cache:
        return target_cache[version]

    targets = []
    url = f"https://downloads.openwrt.org/releases/{version}/targets/"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        for link in soup.find_all('a'):
            href = link.get('href')
            if href.endswith('/') and not href.startswith('?') and '..' not in href:
                target_name = href.strip('/')
                if target_name and 'sha256sums' not in target_name:
                    targets.append(target_name)
        
        target_cache[version] = sorted(targets)
        logger.info(f"Berhasil mengambil {len(targets)} target untuk versi {version}.")
        return sorted(targets)
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengambil daftar target untuk versi {version}: {e}")
        return None

async def scrape_subtargets_for_target(version, target):
    subtargets = []
    url = f"https://downloads.openwrt.org/releases/{version}/targets/{target}/"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        for link in soup.find_all('a'):
            href = link.get('href')
            if href.endswith('/') and not href.startswith('?'):
                subtarget_name = href.strip('/')
                if subtarget_name and subtarget_name != '..':
                    subtargets.append(subtarget_name)
        
        logger.info(f"Berhasil mengambil {len(subtargets)} subtarget untuk {target}.")
        return sorted(subtargets)
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengambil daftar subtarget untuk {target}: {e}")
        return None
        
async def find_imagebuilder_url_and_name(version, target, subtarget):
    base_url = f"https://downloads.openwrt.org/releases/{version}/targets/{target}/{subtarget}/"
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(base_url)
            response.raise_for_status()

        soup = BeautifulSoup(response.text, 'lxml')
        for link in soup.find_all('a'):
            href = link.get('href')
            if href and href.startswith('openwrt-imagebuilder-') and (href.endswith('.tar.xz') or href.endswith('.tar.zst')):
                filename = href
                full_url = base_url + filename
                logger.info(f"Ditemukan file Image Builder: {filename}")
                return full_url, filename
        
        logger.warning(f"Tidak ada file Image Builder yang ditemukan di {base_url}")
        return None, None
    except (httpx.RequestError, httpx.TimeoutException) as e:
        logger.error(f"Gagal mengakses halaman target {base_url}: {e}")
        return None, None

async def get_device_profiles(ib_dir):
    if not os.path.isdir(ib_dir):
        logger.error(f"Direktori Image Builder tidak ditemukan: {ib_dir}")
        return None

    profiles = []
    command = f"make -C {ib_dir} info"
    try:
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()

        if process.returncode != 0:
            logger.error(f"Gagal menjalankan 'make info': {stderr.decode()}")
            return None

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
