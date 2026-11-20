#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - Raspberry Pi Kiosk Print Agent
================================================
Bulutli Render.com serveridan tayyor buyurtmalarni qabul qiladi
va ularni to'g'ridan-to'g'ri Canon LBP3010 yoki XP-58 printeriga uzatadi.

Bu skript atigi 15 MB RAM sarflaydi va Pi 3 ni hech qachon qotirmaydi!
"""

import os
import sys
import time
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path

try:
    import requests
except ImportError:
    print("[!] requests o'rnatilmoqda...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Pi-Agent]: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pi_agent")

# Render.com dagi bulutli server manzili (Render yaratilgach o'zgartiriladi)
CLOUD_URL = os.environ.get("CLOUD_URL", "https://smart-printer-asil2004.onrender.com").rstrip("/")
DEFAULT_PRINTER = os.environ.get("PRINTER_NAME", "Canon-LBP3010")
POLL_INTERVAL = 2  # har 2 soniyada navbat tekshiriladi


def print_pdf(pdf_path: Path, copies: int = 1, orientation: str = "portrait", page_ranges: str = "") -> bool:
    """Faylni CUPS orqali chop etishga yuboradi."""
    cmd = ["lp", "-d", DEFAULT_PRINTER, "-n", str(copies), "-o", "media=A4"]
    if orientation == "landscape":
        cmd.extend(["-o", "orientation-requested=4"])
    else:
        cmd.extend(["-o", "orientation-requested=3"])
    if page_ranges:
        cmd.extend(["-o", f"page-ranges={page_ranges}"])
    cmd.append(str(pdf_path))

    logger.info(f"Chop etish buyrug'i: {' '.join(cmd)}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        logger.error(f"CUPS xatoligi: {proc.stderr.strip()}")
        return False
    logger.info(f"Printerga muvaffaqiyatli uzatildi: {proc.stdout.strip()}")
    return True


def process_job(job: dict):
    order_id = job["id"]
    logger.info(f"Yangi buyurtma qabul qilindi: #{order_id} ({job.get('filename')})")

    # 1. Holatni "PRINTING" ga o'tkazish
    try:
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json={"status": "PRINTING"}, timeout=5)
    except Exception:
        pass

    # 2. Tayyor PDF faylni bulutdan yuklab olish
    tmp_pdf = Path(tempfile.gettempdir()) / f"printchi_{order_id}.pdf"
    try:
        download_url = f"{CLOUD_URL}/api/agent/download/{order_id}"
        logger.info(f"Fayl yuklab olinmoqda: {download_url}")
        res = requests.get(download_url, timeout=30, stream=True)
        if not res.ok:
            raise RuntimeError(f"Faylni yuklab bo'lmadi: status {res.status_code}")
        with open(tmp_pdf, "wb") as f:
            for chunk in res.iter_content(chunk_size=8192):
                f.write(chunk)
    except Exception as e:
        logger.error(f"Fayl yuklab olishda xato: {e}")
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}",
                      json={"status": "FAILED", "error": f"Agent yuklay olmadi: {e}"}, timeout=5)
        return

    # 3. Printerdan chiqarish
    copies = job.get("copies", 1)
    orientation = job.get("orientation", "portrait")
    ranges = job.get("page_ranges", "")
    ok = print_pdf(tmp_pdf, copies=copies, orientation=orientation, page_ranges=ranges)

    # 4. Natijani bulutga xabar qilish
    if ok:
        logger.info(f"Buyurtma #{order_id} muvaffaqiyatli chop etildi!")
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json={"status": "PRINTED"}, timeout=5)
    else:
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}",
                      json={"status": "FAILED", "error": "CUPS printer xatosi"}, timeout=5)

    # Tozalash
    try:
        tmp_pdf.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    logger.info("==================================================")
    logger.info("  Smart Printchi - Raspberry Pi Agenti Ishga Tushdi")
    logger.info(f"  Bulut manzili: {CLOUD_URL}")
    logger.info(f"  Asosiy printer: {DEFAULT_PRINTER}")
    logger.info("==================================================")

    while True:
        try:
            r = requests.get(f"{CLOUD_URL}/api/agent/queue", timeout=5)
            if r.ok:
                data = r.json()
                jobs = data.get("jobs", [])
                for job in jobs:
                    process_job(job)
        except requests.exceptions.ConnectionError:
            # Bulut bilan aloqa vaqtincha yo'q bo'lsa
            pass
        except Exception as e:
            logger.warning(f"Navbatni tekshirishda xatolik: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
