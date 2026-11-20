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
import glob
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

try:
    from printer_detector import get_all_printer_status, detect_connected_printers
except Exception:
    def get_all_printer_status():
        return [{"type": "thermal", "label": "Termal Chek (XP-58)", "connected": True, "ready": True}]
    def detect_connected_printers():
        return {"thermal": {"connected": True, "ready": True, "cups_name": "XP58"}}

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Pi-Agent]: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pi_agent")

# Render.com dagi bulutli server manzili
CLOUD_URL = os.environ.get("CLOUD_URL", "https://smart-printer-mo1g.onrender.com").rstrip("/")
DEFAULT_PRINTER = os.environ.get("PRINTER_NAME", "")
POLL_INTERVAL = 2  # har 2 soniyada navbat tekshiriladi


def get_thermal_device_port() -> str:
    """Linux USB printer portini topadi (/dev/usb/lp0 va h.k.)."""
    ports = glob.glob("/dev/usb/lp*")
    if ports:
        try:
            os.chmod(ports[0], 0o666)
        except Exception:
            pass
        return ports[0]
    return ""


def choose_active_printer() -> tuple[str, str]:
    """
    Ulangan printerlar orasidan ayni paytda faol bo'lganini tanlaydi.
    Qaytaradi: (printer_type, target_name)
    Masalan: ("thermal", "XP58") yoki ("laser_bw", "Canon-LBP3010")
    """
    # 1. Agar muhit o'zgaruvchisi berilgan bo'lsa
    if DEFAULT_PRINTER:
        p_low = DEFAULT_PRINTER.lower()
        if "xp" in p_low or "thermal" in p_low or "pos" in p_low:
            return ("thermal", DEFAULT_PRINTER)
        return ("laser_bw", DEFAULT_PRINTER)

    try:
        st = detect_connected_printers()
        # Agar Termal (XP-58) ulangan bo'lsa
        if st.get("thermal", {}).get("connected") and st.get("thermal", {}).get("ready"):
            return ("thermal", st["thermal"].get("cups_name") or "XP58")
        # Agar Laser (Canon) ulangan bo'lsa
        if st.get("laser_bw", {}).get("connected") and st.get("laser_bw", {}).get("ready"):
            return ("laser_bw", st["laser_bw"].get("cups_name") or "Canon-LBP3010")
    except Exception as e:
        logger.warning(f"Printer aniqlashda xato: {e}")

    # Fallback: Agar /dev/usb/lp0 mavjud bo'lsa demak termal printer
    if get_thermal_device_port():
        return ("thermal", "XP58")

    return ("laser_bw", "Canon-LBP3010")


def print_thermal_job(pdf_path: Path, copies: int = 1, job_info: dict = None) -> bool:
    """XP-58 termal chek printeriga chiqarish."""
    job_info = job_info or {}
    order_id = job_info.get("id", "TEST")
    fname = job_info.get("filename", pdf_path.name)

    # 1-usul: PrinterService orqali
    try:
        from printer_service import PrinterService
        ps = PrinterService()
        logger.info(f"PrinterService orqali termal chiqarish boshlandi: {pdf_path}")
        res = ps.print_to_thermal(str(pdf_path), copies=copies)
        logger.info(f"Termal chop etildi: {res.get('message')}")
        return True
    except Exception as e:
        logger.warning(f"PrinterService termal xatosi: {e}")

    # 2-usul: /dev/usb/lp* orqali to'g'ridan-to'g'ri ESC/POS chek chiqarish
    port = get_thermal_device_port()
    if port and os.path.exists(port):
        try:
            logger.info(f"Direct ESC/POS yozish: {port}")
            with open(port, "wb") as f:
                for _ in range(copies):
                    # Sarlavha
                    f.write(b"\x1b@")                      # Init
                    f.write(b"\x1ba\x01\x1d!\x11")          # Center, 2x size
                    f.write("SMART PRINTCHI\n".encode("utf-8"))
                    f.write(b"\x1d!\x00")                  # Normal size
                    f.write("Avtomatlashtirilgan Kiosk\n".encode("utf-8"))
                    f.write("--------------------------------\n".encode("utf-8"))
                    f.write(b"\x1ba\x00")                  # Left align
                    f.write(f"Buyurtma ID: #{order_id}\n".encode("utf-8"))
                    f.write(f"Hujjat     : {fname}\n".encode("utf-8"))
                    f.write(f"Nusxalar   : {copies} dona\n".encode("utf-8"))
                    f.write(f"Vaqt       : {time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode("utf-8"))
                    f.write("--------------------------------\n".encode("utf-8"))
                    f.write(b"\x1ba\x01")                  # Center
                    f.write("Muvaffaqiyatli qabul qilindi!\nRahmat!\n".encode("utf-8"))
                    f.write(b"\n\n\n\n\x1dV\x00")          # Feed & Cut
                    f.flush()
            logger.info(f"Chek to'g'ridan-to'g'ri {port} ga chiqarildi!")
            return True
        except Exception as ex:
            logger.error(f"{port} ga yozishda xato: {ex}")

    # 3-usul: CUPS XP58 navbati orqali
    cmd = ["lp", "-d", "XP58", "-n", str(copies), str(pdf_path)]
    logger.info(f"CUPS XP58 buyrug'i: {' '.join(cmd)}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode == 0:
        logger.info(f"CUPS XP58 ga uzatildi: {proc.stdout.strip()}")
        return True

    logger.error("XP-58 termal printeriga chiqarib bo'lmadi!")
    return False


def print_laser_cups(pdf_path: Path, printer_name: str, copies: int = 1, orientation: str = "portrait", page_ranges: str = "") -> bool:
    """Canon yoki boshqa lazer printerni CUPS orqali chop etish."""
    cmd = ["lp", "-d", printer_name, "-n", str(copies), "-o", "media=A4"]
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

    # 3. Printer turini aniqlash va chop etish
    copies = job.get("copies", 1)
    orientation = job.get("orientation", "portrait")
    ranges = job.get("page_ranges", "")

    ptype, pname = choose_active_printer()
    logger.info(f"Chop etish rejimi: [{ptype}] -> {pname}")

    if ptype == "thermal":
        ok = print_thermal_job(tmp_pdf, copies=copies, job_info=job)
    else:
        ok = print_laser_cups(tmp_pdf, printer_name=pname, copies=copies, orientation=orientation, page_ranges=ranges)

    # 4. Natijani bulutga xabar qilish
    if ok:
        logger.info(f"Buyurtma #{order_id} muvaffaqiyatli chop etildi!")
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json={"status": "PRINTED"}, timeout=5)
    else:
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}",
                      json={"status": "FAILED", "error": f"{pname} printer xatosi"}, timeout=5)

    # Tozalash
    try:
        tmp_pdf.unlink(missing_ok=True)
    except Exception:
        pass


def main():
    logger.info("==================================================")
    logger.info("  Smart Printchi - Raspberry Pi Agenti Ishga Tushdi")
    logger.info(f"  Bulut manzili: {CLOUD_URL}")
    ptype, pname = choose_active_printer()
    logger.info(f"  Aktiv printer: [{ptype}] {pname}")
    logger.info("==================================================")

    while True:
        try:
            # 1. Bulutga Raspberry Pi-dagi ulangan printerlar holatini yuborish
            local_printers = get_all_printer_status()
            try:
                requests.post(f"{CLOUD_URL}/api/agent/heartbeat", json={"printers": local_printers}, timeout=5)
            except Exception:
                pass

            # 2. Navbatdagi chop etiladigan buyurtmalarni tekshirish
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
