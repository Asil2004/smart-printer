#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - Raspberry Pi Kiosk Print Agent
================================================
Bulutli Render.com serveridan tayyor buyurtmalarni qabul qiladi
va ularni to'g'ridan-to'g'ri Canon LBP3010 yoki XP-58 printeriga uzatadi.

XP-58 uchun har qanday rasm yoki PDF hujjatni 384px (58mm) ga zichlab,
to'g'ridan-to'g'ri ESC/POS raster grafik formatida chop etadi!
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

# Majburiy kutubxonalarni tekshirish
try:
    import requests
except ImportError:
    print("[!] requests o'rnatilmoqda...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("[!] Pillow o'rnatilmoqda...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "Pillow"])
    from PIL import Image, ImageDraw, ImageFont

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
    ports = sorted(glob.glob("/dev/usb/lp*"))
    if ports:
        port = ports[0]
        try:
            os.chmod(port, 0o666)
        except Exception:
            pass
        return port
    return ""


def choose_active_printer() -> tuple[str, str]:
    """
    Ulangan printerlar orasidan ayni paytda faol bo'lganini tanlaydi.
    Qaytaradi: (printer_type, target_name)
    """
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


def image_to_escpos_raster(img: Image.Image, max_width: int = 384, chunk_lines: int = 128) -> bytes:
    """
    Har qanday PIL rasmini XP-58 uchun 384px ga proporsional siqib (zichlab),
    ESC/POS 'GS v 0' raster bit-image formatiga aylantiradi.
    """
    # 1. RGBA bo'lsa oq fonga qo'yish
    if img.mode != "RGB":
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            bg = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[3] if len(img.split()) >= 4 else None)
            img = bg
        else:
            img = img.convert("RGB")

    # 2. Enini 384px ga proporsional siqish (zichlash)
    w, h = img.size
    if w != max_width:
        new_h = max(1, int(h * (max_width / w)))
        img = img.resize((max_width, new_h), Image.Resampling.LANCZOS)
        w, h = img.size

    # 3. Floyd-Steinberg dithering orqali yuqori sifatli 1-bit oq-qoraga aylantirish
    bw = img.convert("1")
    bytes_per_row = max_width // 8  # 384 / 8 = 48 bayt

    raw_bytes = bw.tobytes()
    # Invert: PIL da 0=qora, 255=oq. ESC/POS da 1=qora nuqta (kuydirish), 0=oq qog'oz
    inv_bytes = bytes([(~b) & 0xFF for b in raw_bytes])

    # 4. Printer buferi to'lib ketmasligi uchun bo'laklab (chunk_lines) yuborish
    out = bytearray()
    # Chiziqlar orasidagi bo'shliqni 0 qilish
    out.extend(b"\x1b3\x00")

    for y_start in range(0, h, chunk_lines):
        y_end = min(y_start + chunk_lines, h)
        lines = y_end - y_start
        start_byte = y_start * bytes_per_row
        end_byte = y_end * bytes_per_row
        chunk_data = inv_bytes[start_byte:end_byte]

        # GS v 0 0 xL xH yL yH
        # xL = 48, xH = 0
        # yL = lines % 256, yH = lines // 256
        header = bytes([0x1d, 0x76, 0x30, 0x00, bytes_per_row, 0, lines % 256, lines // 256])
        out.extend(header)
        out.extend(chunk_data)

    # Standart qator oralig'iga qaytarish
    out.extend(b"\x1b2")
    return bytes(out)


def pdf_to_images(pdf_path: Path) -> list:
    """PDF faylni sahifalar bo'yicha PIL Image ro'yxatiga aylantiradi."""
    images = []

    # pdftoppm mavjudligini tekshirish
    if not shutil.which("pdftoppm"):
        logger.info("pdftoppm (poppler-utils) o'rnatilmoqda...")
        try:
            subprocess.run(["sudo", "apt-get", "install", "-y", "poppler-utils"], timeout=60)
        except Exception as e:
            logger.warning(f"poppler-utils o'rnatishda xatolik: {e}")

    if shutil.which("pdftoppm"):
        tmp_dir = Path(tempfile.mkdtemp(prefix="pdf_ppm_"))
        tmp_prefix = tmp_dir / "page"
        try:
            # 150 DPI termal uchun ideal zichlik
            cmd = ["pdftoppm", "-png", "-r", "150", str(pdf_path), str(tmp_prefix)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            if proc.returncode == 0:
                page_files = sorted(glob.glob(f"{tmp_prefix}-*.png"))
                for pf in page_files:
                    try:
                        with Image.open(pf) as im:
                            images.append(im.copy())
                    except Exception:
                        pass
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    # Agar pdftoppm orqali olinmagan bo'lsa va pypdf matn o'qiy olsa
    if not images:
        try:
            from pypdf import PdfReader
            reader = PdfReader(str(pdf_path))
            full_text = []
            for p in reader.pages:
                t = p.extract_text()
                if t:
                    full_text.append(t)
            if full_text:
                # Matnni rasm qilib chizamiz
                text_content = "\n".join(full_text)
                img = render_text_to_image(text_content)
                if img:
                    images.append(img)
        except Exception as e:
            logger.warning(f"PDF matnini olishda xatolik: {e}")

    return images


def render_text_to_image(text: str, max_width: int = 384) -> Image.Image:
    """Matnni 384px kenglikdagi chiroyli rasmga aylantiradi."""
    import textwrap
    lines = []
    for paragraph in text.splitlines():
        if paragraph.strip():
            wrapped = textwrap.wrap(paragraph, width=32)
            lines.extend(wrapped)
        else:
            lines.append("")

    line_height = 24
    img_height = max(100, len(lines) * line_height + 40)
    img = Image.new("RGB", (max_width, img_height), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    y = 20
    for line in lines:
        draw.text((10, y), line, fill=(0, 0, 0))
        y += line_height

    return img


def print_thermal_job(file_path: Path, copies: int = 1, job_info: dict = None) -> bool:
    """
    XP-58 termal chek printeriga to'liq rasm yoki faylni 384px ga zichlab chop etadi.
    """
    job_info = job_info or {}
    order_id = job_info.get("id", "BUYURTMA")
    fname = job_info.get("filename", file_path.name)
    port = get_thermal_device_port()

    if not port or not os.path.exists(port):
        logger.error("Termal printer porti (/dev/usb/lp0) topilmadi! Kabelni tekshiring.")
        return False

    # 1. Faylni rasm(lar)ga aylantirish
    images = []
    ext = file_path.suffix.lower()

    if ext in (".png", ".jpg", ".jpeg", ".bmp", ".webp"):
        try:
            with Image.open(file_path) as im:
                images.append(im.copy())
        except Exception as e:
            logger.error(f"Rasmni ochishda xato: {e}")
            return False

    elif ext == ".pdf":
        images = pdf_to_images(file_path)

    # 2. Agar sahifalar topilsa — raster formatda zichlab chiqarish
    if images:
        try:
            logger.info(f"[{port}] {len(images)} ta sahifa XP-58 ga zichlab (384px raster) yuborilmoqda...")
            with open(port, "wb") as f:
                for c in range(copies):
                    # Sarlavha
                    f.write(b"\x1b@")                      # Init
                    f.write(b"\x1ba\x01\x1d!\x01")          # Center
                    f.write(f"SMART PRINTCHI #{order_id}\n".encode("utf-8"))
                    f.write(b"\x1d!\x00")
                    f.write("================================\n".encode("utf-8"))
                    f.flush()

                    # Har bir sahifani ESC/POS raster grafik sifatida zichlab chiqarish
                    for idx, img in enumerate(images):
                        if len(images) > 1:
                            f.write(f"--- Sahifa {idx+1}/{len(images)} ---\n".encode("utf-8"))
                            f.flush()
                        raster_data = image_to_escpos_raster(img, max_width=384, chunk_lines=128)
                        f.write(raster_data)
                        f.write(b"\n")
                        f.flush()

                    # Yakuniy chek qismi
                    f.write(b"\x1ba\x01")
                    f.write("--------------------------------\n".encode("utf-8"))
                    f.write(f"{fname}\n{time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode("utf-8"))
                    f.write(b"Muvaffaqiyatli chop etildi!\n".encode("utf-8"))
                    f.write(b"\n\n\n\n\x1dV\x00")          # Feed & Cut
                    f.flush()

            logger.info(f"Buyurtma #{order_id} to'liq zichlangan holda chop etildi!")
            return True
        except Exception as ex:
            logger.error(f"Grafik chop etishda xato: {ex}")
            return False

    # 3. Zaxira matnli chek (agar tasvirga aylantirib bo'lmasa)
    try:
        with open(port, "wb") as f:
            for _ in range(copies):
                f.write(b"\x1b@\x1ba\x01\x1d!\x11SMART PRINTCHI\n\x1d!\x00")
                f.write("Avtomatlashtirilgan Kiosk\n--------------------------------\n\x1ba\x00")
                f.write(f"Buyurtma : #{order_id}\nFayl     : {fname}\n".encode("utf-8"))
                f.write(f"Vaqt     : {time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode("utf-8"))
                f.write(b"--------------------------------\n\x1ba\x01Chop etildi!\n\n\n\n\x1dV\x00")
                f.flush()
        return True
    except Exception as e:
        logger.error(f"Zaxira matn yozishda xato: {e}")
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
            pass
        except Exception as e:
            logger.warning(f"Navbatni tekshirishda xatolik: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
