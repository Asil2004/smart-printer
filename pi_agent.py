#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - Raspberry Pi Kiosk Print Agent
================================================
Loyiha rahbari: Ravshanov Muhammad Ali

Ushbu agent Raspberry Pi 3 da fonda ishlaydi (15-20 MB RAM):
1. Canon LBP3010 (A4 Lazer) - Asosiy hujjatlar uchun
2. XP-58 (58mm Termal Chek) - Dasturchi rejimi va cheklar uchun
3. Bulutli Render.com serveridan navbatdagi buyurtmalarni avtomat oladi
4. Uskuna holatini jonli ravishda Render ga yuboradi (Heartbeat)
"""

import os
import sys
import glob
import time
import uuid
import shutil
import logging
import tempfile
import subprocess
from pathlib import Path

# Bitta buyurtmada eng ko'p nusxa (server bilan bir xil: .env MAX_COPIES)
MAX_COPIES = max(1, int(os.environ.get("MAX_COPIES", 50)))

# Kerakli kutubxonalar
try:
    import requests
except ImportError:
    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    import requests

try:
    from PIL import Image, ImageDraw, ImageOps, ImageFont
except ImportError:
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
        from PIL import Image, ImageDraw, ImageOps, ImageFont
    except Exception:
        Image = None
        ImageDraw = None
        ImageOps = None
        ImageFont = None

try:
    from printer_detector import get_all_printer_status, detect_connected_printers
except Exception:
    def get_all_printer_status():
        return [{"type": "laser_bw", "label": "Canon LBP3010 Lazer", "connected": True, "ready": True}]
    def detect_connected_printers():
        return {}

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Pi-Agent]: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pi_agent")

CLOUD_URL = os.environ.get("CLOUD_URL", "https://smart-printer-mo1g.onrender.com").rstrip("/")
CANON_PRINTER = os.environ.get("PRINTER_NAME", "Canon-LBP3010")
POLL_INTERVAL = 2

# ──────────────────────────────────────────────────────────
# ESC/POS Buyruqlari (XP-58 Termal Printer uchun)
# ──────────────────────────────────────────────────────────
ESC = b'\x1b'
GS  = b'\x1d'
INIT_PRINTER = ESC + b'@'
ALIGN_CENTER = ESC + b'a\x01'
ALIGN_LEFT   = ESC + b'a\x00'
ALIGN_RIGHT  = ESC + b'a\x02'
BOLD_ON      = ESC + b'E\x01'
BOLD_OFF     = ESC + b'E\x00'
DOUBLE_SIZE  = GS + b'!\x11'
NORMAL_SIZE  = GS + b'!\x00'
FEED_CUT     = b'\n\n\n\n' + GS + b'V\x00'


def find_xp58_port() -> str | None:
    """XP-58 printerining /dev/usb/lp* portini topadi."""
    ports = glob.glob('/dev/usb/lp*')
    if ports:
        return ports[0]
    return None


def print_to_xp58(order: dict, note: str = "") -> bool:
    """
    XP-58 termal printeriga to'g'ridan-to'g'ri ESC/POS chek chiqaradi.
    CUPS drayveriga bog'liq emas — 100% ishonchli va tezkor (0.1 soniya).
    """
    port = find_xp58_port()
    if not port:
        logger.warning("XP-58 porti topilmadi (/dev/usb/lp* yo'q)")
        return False

    oid = order.get("id", "TEST")
    fname = order.get("filename", "Hujjat")
    copies = order.get("copies", 1)
    pages = order.get("pages", 1)
    amount = order.get("amount", 0)
    now_str = time.strftime("%Y-%m-%d %H:%M:%S")

    data = bytearray()
    data.extend(INIT_PRINTER)

    # Sarlavha
    data.extend(ALIGN_CENTER)
    data.extend(DOUBLE_SIZE + BOLD_ON)
    data.extend("SMART PRINTCHI\n".encode("utf-8", errors="ignore"))
    data.extend(NORMAL_SIZE + BOLD_OFF)
    data.extend("Avtomatlashtirilgan Kiosk\n".encode("utf-8", errors="ignore"))
    data.extend("--------------------------------\n".encode("utf-8"))

    # Ma'lumotlar
    data.extend(ALIGN_LEFT)
    data.extend(BOLD_ON + "Loyiha rahbari:\n".encode("utf-8") + BOLD_OFF)
    data.extend("  Ravshanov Muhammad Ali\n".encode("utf-8", errors="ignore"))
    data.extend(f"Buyurtma  : #{oid}\n".encode("utf-8", errors="ignore"))
    data.extend(f"Fayl      : {fname[:24]}\n".encode("utf-8", errors="ignore"))
    data.extend(f"Hajmi     : {pages} bet x {copies} nusxa\n".encode("utf-8", errors="ignore"))
    data.extend(f"Summa     : {amount} so'm\n".encode("utf-8", errors="ignore"))
    data.extend(f"Sana/Vaqt : {now_str}\n".encode("utf-8", errors="ignore"))

    if note:
        data.extend("--------------------------------\n".encode("utf-8"))
        data.extend(BOLD_ON + f"Izoh: {note}\n".encode("utf-8", errors="ignore") + BOLD_OFF)

    data.extend("--------------------------------\n".encode("utf-8"))
    data.extend(ALIGN_CENTER)
    data.extend(BOLD_ON + "CHOP ETILDI [OK]\n".encode("utf-8") + BOLD_OFF)
    data.extend("https://smart-printer-mo1g.onrender.com\n".encode("utf-8"))
    data.extend("--------------------------------\n".encode("utf-8"))
    data.extend(FEED_CUT)

    try:
        with open(port, "wb") as f:
            f.write(data)
            f.flush()
        logger.info(f"✅ XP-58 orqali chek chiqarildi (Buyurtma #{oid})")
        return True
    except PermissionError:
        logger.error(f"XP-58 portiga ruxsat yetarli emas! 'sudo usermod -aG lp cail' kerak.")
        return False
    except Exception as e:
        logger.error(f"XP-58 ga yozishda xatolik: {e}")
        return False


def image_to_escpos(image) -> bytes:
    """
    PIL Image obyektini XP-58 (384px) uchun ESC/POS raster komandalariga ('GS v 0') aylantiradi.
    Har qanday rasm yoki PDF betini 384px ga zichlab, Floyd-Steinberg dithering bilan monoxrom qiladi.
    """
    if Image is None:
        return b""
    w, h = image.size
    if w != 384:
        new_w = 384
        new_h = max(1, int(h * (384.0 / w)))
        image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    if image.mode != "RGB":
        image = image.convert("RGB")
    bw = image.convert("1")

    w, h = bw.size
    row_bytes = (w + 7) // 8  # 384 // 8 = 48 bayt
    raw = bw.tobytes()
    inverted = bytes([~b & 0xFF for b in raw])

    CHUNK_LINES = 256
    buf = bytearray()
    for start_y in range(0, h, CHUNK_LINES):
        chunk_h = min(CHUNK_LINES, h - start_y)
        chunk_start = start_y * row_bytes
        chunk_end = (start_y + chunk_h) * row_bytes
        chunk_data = inverted[chunk_start:chunk_end]

        # GS v 0 0 xL xH yL yH
        buf.extend(b"\x1d\x76\x30\x00")
        buf.extend(bytes([row_bytes & 0xFF, (row_bytes >> 8) & 0xFF]))
        buf.extend(bytes([chunk_h & 0xFF, (chunk_h >> 8) & 0xFF]))
        buf.extend(chunk_data)

    return bytes(buf)


def pdf_to_images(pdf_path: Path, max_pages: int = 1) -> list:
    """PDF sahifalarini (ko'pi bilan max_pages) PIL Image ro'yxatiga tezkor aylantirish."""
    if Image is None:
        return []
    images = []
    tmp_prefix = f"/tmp/thermal_pdf_{int(time.time())}_{uuid.uuid4().hex[:4]}"

    # 1. pdftoppm orqali tezkor (scale-to-x 384, max 1 sahifa, timeout=10s)
    try:
        cmd = [
            "pdftoppm", "-png", "-f", "1", "-l", str(max_pages),
            "-scale-to-x", "384", "-scale-to-y", "-1",
            str(pdf_path), tmp_prefix
        ]
        res = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if res.returncode == 0:
            for f in sorted(glob.glob(f"{tmp_prefix}-*.png")):
                try:
                    with Image.open(f) as img:
                        images.append(img.copy())
                    os.remove(f)
                except Exception:
                    pass
            if images:
                return images
    except Exception as e:
        logger.debug(f"pdftoppm ishlamadi: {e}")

    # 2. Ghostscript (gs) orqali (timeout=10s, faqat 1-sahifa)
    try:
        gs_cmd = [
            "gs", "-sDEVICE=png16m", "-r72", "-dNOPAUSE", "-dBATCH", "-dSAFER",
            "-dFirstPage=1", f"-dLastPage={max_pages}",
            f"-sOutputFile={tmp_prefix}-%03d.png", str(pdf_path)
        ]
        res = subprocess.run(gs_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if res.returncode == 0:
            for f in sorted(glob.glob(f"{tmp_prefix}-*.png")):
                try:
                    with Image.open(f) as img:
                        images.append(img.copy())
                    os.remove(f)
                except Exception:
                    pass
            if images:
                return images
    except Exception as e:
        logger.debug(f"gs xatosi: {e}")

    return images


def text_to_image(text: str):
    """Oddiy matnni 384px kenglikdagi chiroyli rasmga aylantirish."""
    if Image is None or ImageDraw is None:
        return None
    lines = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        while len(line) > 30:
            lines.append(line[:30])
            line = line[30:]
        lines.append(line)

    line_h = 24
    img_h = max(60, len(lines) * line_h + 20)
    img = Image.new("RGB", (384, img_h), (255, 255, 255))
    d = ImageDraw.Draw(img)
    y = 10
    for l in lines:
        d.text((10, y), l, fill=(0, 0, 0))
        y += line_h
    return img


def write_to_thermal_port(port: str, data: bytes | bytearray, chunk_size: int = 1024, delay: float = 0.01) -> bool:
    """XP-58 apparati USB buferi to'lib qotib qolmasligi uchun baytlarni bo'lib-bo'lib (chunk) yozadi."""
    try:
        with open(port, "wb") as f:
            for offset in range(0, len(data), chunk_size):
                chunk = data[offset:offset + chunk_size]
                f.write(chunk)
                f.flush()
                if delay > 0:
                    time.sleep(delay)
        return True
    except PermissionError:
        logger.error("XP-58 portiga ruxsat yetarli emas! 'sudo usermod -aG lp cail' kerak.")
        return False
    except Exception as e:
        logger.error(f"XP-58 ga yozishda xato: {e}")
        return False


def print_file_to_xp58(file_path: Path, order: dict) -> bool:
    """
    XP-58 termal chek printerida chop etish:
    - Ko'p sahifali PDF/DOCX hujjatlar uchun rasmiy to'lov cheki (kvitansiya) chiqaradi.
    - 1-sahifali rasm yoki kvitansiya bo'lsa, rasmni 384px ga moslab chiqaradi.
    """
    port = find_xp58_port()
    if not port:
        logger.warning("XP-58 porti topilmadi (/dev/usb/lp* yo'q)")
        return False

    oid = order.get("id", "TEST")
    fname = order.get("filename", file_path.name)
    copies = order.get("copies", 1)
    pages = order.get("pages", 1)

    # 1. Haqiqiy formatni aniqlash
    is_pdf = False
    try:
        with open(file_path, "rb") as f:
            header = f.read(16)
            if b"%PDF" in header:
                is_pdf = True
    except Exception:
        pass

    # 2. Agar ko'p sahifali hujjat bo'lsa (masalan 9 betlik taqdimot yoki Word fayl):
    # XP-58 58mm chek apparati bo'lgani uchun rasmiy chek/kvitansiya chiqarish to'g'ri va xavfsiz
    if pages > 1 or (is_pdf and pages > 1):
        logger.info(f"Ko'p sahifali hujjat (#{oid}, {pages} bet) → XP-58 da rasmiy buyurtma cheki chiqarilmoqda...")
        return print_to_xp58(order, note="Ko'p sahifali hujjat qabul qilindi.\n(A4 chop etish uchun Canon LBP3010 tanlang)")

    # 3. Yagona sahifali rasm yoki 1-sahifali fayl bo'lsa:
    images = []
    if is_pdf or file_path.suffix.lower() == ".pdf":
        images = pdf_to_images(file_path, max_pages=1)

    if not images and Image:
        try:
            with Image.open(file_path) as img:
                images.append(img.copy())
        except Exception:
            pass

    if not images and file_path.suffix.lower() in [".txt", ".receipt"]:
        try:
            txt = file_path.read_text(encoding="utf-8", errors="ignore")
            t_img = text_to_image(txt)
            if t_img:
                images.append(t_img)
        except Exception:
            pass

    if not images:
        logger.info(f"Fayl matnli chek sifatida chiqarilmoqda: #{oid}")
        return print_to_xp58(order, note="Buyurtma cheki")

    # Rasmli chek tayyorlash
    data = bytearray()
    data.extend(INIT_PRINTER)
    data.extend(ALIGN_CENTER)
    data.extend(DOUBLE_SIZE + BOLD_ON)
    data.extend("SMART PRINTCHI (58mm)\n".encode("utf-8", errors="ignore"))
    data.extend(NORMAL_SIZE + BOLD_OFF)
    data.extend(f"Buyurtma: #{oid} | {fname[:20]}\n".encode("utf-8", errors="ignore"))
    data.extend("--------------------------------\n".encode("utf-8"))

    for idx, img in enumerate(images):
        raster_bytes = image_to_escpos(img)
        data.extend(raster_bytes)
        data.extend(b"\n")

    now_str = time.strftime("%Y-%m-%d %H:%M:%S")
    data.extend(ALIGN_CENTER)
    data.extend("--------------------------------\n".encode("utf-8"))
    data.extend(BOLD_ON + "CHOP ETILDI [OK]\n".encode("utf-8") + BOLD_OFF)
    data.extend("Loyiha: Ravshanov Muhammad Ali\n".encode("utf-8"))
    data.extend(f"Sana: {now_str}\n".encode("utf-8"))
    data.extend("--------------------------------\n".encode("utf-8"))
    data.extend(FEED_CUT)

    for _ in range(max(1, min(copies, MAX_COPIES))):
        ok = write_to_thermal_port(port, data)
        if not ok:
            return False

    logger.info(f"✅ XP-58 da muvaffaqiyatli chop etildi (#{oid})")
    return True


def print_to_canon(pdf_path: Path, copies: int = 1, orientation: str = "portrait", page_ranges: str = "") -> tuple[bool, str]:
    """
    Canon LBP3010 ga CUPS orqali fayl yuboradi va uning haqiqatda chop
    bo'lganini yoki qotib qolganini kuzatadi.
    """
    cmd = ["lp", "-d", CANON_PRINTER, "-n", str(copies), "-o", "media=A4"]
    if orientation == "landscape":
        cmd.extend(["-o", "orientation-requested=4"])
    else:
        cmd.extend(["-o", "orientation-requested=3"])
    if page_ranges:
        cmd.extend(["-o", f"page-ranges={page_ranges}"])
    cmd.append(str(pdf_path))

    logger.info(f"Canon buyrug'i: {' '.join(cmd)}")
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        err = proc.stderr.strip()
        logger.error(f"CUPS xatoligi: {err}")
        return False, f"CUPS xatosi: {err}"

    stdout = proc.stdout.strip()
    logger.info(f"CUPS qabul qildi: {stdout}")

    # Ish raqamini ajratib olish (masalan: Canon-LBP3010-25)
    job_id = ""
    for part in stdout.split():
        if CANON_PRINTER in part:
            job_id = part.strip()
            break

    if not job_id:
        return True, "Chop etishga yuborildi"

    # Ish holatini 20 soniya davomida kuzatish (qog'oz chiqqanini tekshirish)
    logger.info(f"Canon ish holati kuzatilmoqda: {job_id}...")
    for _ in range(10):
        time.sleep(2)
        q_check = subprocess.run(["lpstat", "-o", CANON_PRINTER], stdout=subprocess.PIPE, text=True)
        if job_id not in q_check.stdout:
            logger.info(f"✅ Canon LBP3010 ishni muvaffaqiyatli yakunladi: {job_id}")
            return True, "Muvaffaqiyatli chop etildi"

    # Agar 20 soniyadan so'ng ham navbatda bo'lsa:
    p_check = subprocess.run(["lpstat", "-p", CANON_PRINTER], stdout=subprocess.PIPE, text=True)
    if "disabled" in p_check.stdout:
        logger.warning("Canon printeri o'chirilgan (disabled) holatda!")
        return False, "Canon navbatda to'xtab qoldi (disabled)"

    # Aks holda, agar Rendering completed bo'lsa, CUPS printerga ma'lumot uzatmoqda
    logger.info(f"Canon printeriga ma'lumot uzatildi, chop etish davom etmoqda: {job_id}")
    return True, "Chop etishga yuborildi (printer ishlamoqda)"


def get_spool_dir() -> Path:
    """Xavfsiz va ruxsatlar bilan muammosiz foydalanuvchi spool papkasi."""
    d = Path.home() / ".smart_printchi_spool"
    try:
        d.mkdir(parents=True, exist_ok=True)
        return d
    except Exception:
        fallback = Path(__file__).resolve().parent / ".spool"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def cleanup_stale_files():
    """Eski vaqtincha fayllar va /tmp dagi qotib qolgan fayllarni tozalash."""
    try:
        import glob
        for f in glob.glob("/tmp/printchi_*"):
            try:
                os.remove(f)
            except Exception:
                pass
    except Exception:
        pass
    try:
        spool = get_spool_dir()
        for f in spool.glob("job_*.pdf"):
            if time.time() - f.stat().st_mtime > 1800:
                f.unlink(missing_ok=True)
    except Exception:
        pass


# Qayta ishlangan buyurtmalar kesh (bitta buyurtmani 2 marta chop etmaslik uchun)
PROCESSED_JOBS = set()


def ensure_single_instance():
    """pi_agent.py bir vaqtda faqat 1 ta nusxada ishlashini ta'minlaydi."""
    lock_file_path = Path.home() / ".smart_printchi_agent.lock"
    try:
        import fcntl
        global lock_fd
        lock_fd = open(lock_file_path, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except Exception:
        logger.warning("⚠️ Boshqa pi_agent.py jarayoni topildi! Eski nusxalar to'xtatilmoqda...")
        my_pid = os.getpid()
        subprocess.run(f"pkill -9 -f 'python.*pi_agent.py' --inverse --pid {my_pid}", shell=True, stderr=subprocess.DEVNULL)
        time.sleep(1)
        try:
            lock_fd = open(lock_file_path, "w")
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except Exception:
            pass


def process_job(job: dict):
    order_id = job["id"]
    if order_id in PROCESSED_JOBS:
        logger.info(f"Buyurtma #{order_id} allaqachon bajarilgan, o'tkazib yuborildi.")
        return

    PROCESSED_JOBS.add(order_id)
    # Kesh hajmini cheklash (oxirgi 100 ta ID)
    if len(PROCESSED_JOBS) > 100:
        PROCESSED_JOBS.pop()

    logger.info(f"Yangi buyurtma qabul qilindi: #{order_id} ({job.get('filename')})")

    # 1. Holatni "PRINTING" ga o'tkazish
    try:
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json={"status": "PRINTING"}, timeout=5)
    except Exception:
        pass

    target = job.get("printer_type", "laser_bw")
    filename = job.get("filename", "")

    # Faylni xavfsiz spool papkasiga yuklab olish
    spool_dir = get_spool_dir()
    clean_ext = Path(filename).suffix.lower() if Path(filename).suffix else ".pdf"
    tmp_file = spool_dir / f"job_{order_id}_{int(time.time())}{clean_ext}"
    try:
        download_url = f"{CLOUD_URL}/api/agent/download/{order_id}"
        logger.info(f"Fayl yuklab olinmoqda: {download_url}")
        res = requests.get(download_url, timeout=(15, 300), stream=True)
        if not res.ok:
            raise RuntimeError(f"Faylni yuklab bo'lmadi: status {res.status_code}")
        total_dl = 0
        with open(tmp_file, "wb") as f:
            for chunk in res.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total_dl += len(chunk)
        logger.info(f"Fayl to'liq yuklandi ({total_dl / (1024*1024):.2f} MB): {tmp_file.name}")
    except Exception as e:
        logger.error(f"Fayl yuklab olishda xato: {e}")
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}",
                      json={"status": "FAILED", "error": f"Agent yuklay olmadi: {e}"}, timeout=5)
        return

    # 1. Agar XP-58 (termal chek) tanlangan bo'lsa: faylni 384px ga zichlab chop etamiz!
    if target == "thermal" or filename.endswith(".receipt"):
        logger.info(f"Buyurtma #{order_id} → XP-58 termal printeriga zichlab (raster) chiqarilmoqda...")
        ok = print_file_to_xp58(tmp_file, order=job)
        if ok:
            requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json={"status": "PRINTED"}, timeout=5)
        else:
            requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}",
                          json={"status": "FAILED", "error": "XP-58 termal printer xatosi"}, timeout=5)
        try:
            tmp_file.unlink(missing_ok=True)
        except Exception:
            pass
        return

    # 2. Asosiy: Canon LBP3010 (A4 lazer)
    copies = job.get("copies", 1)
    orientation = job.get("orientation", "portrait")
    ranges = job.get("page_ranges", "")
    ok, note = print_to_canon(tmp_file, copies=copies, orientation=orientation, page_ranges=ranges)

    if ok:
        logger.info(f"Buyurtma #{order_id} muvaffaqiyatli chop etildi!")
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json={"status": "PRINTED"}, timeout=5)
    else:
        logger.error(f"Canon muvaffaqiyatsiz bo'ldi: {note}")
        requests.post(f"{CLOUD_URL}/api/agent/status/{order_id}",
                      json={"status": "FAILED", "error": note}, timeout=5)

    try:
        tmp_file.unlink(missing_ok=True)
    except Exception:
        pass


def fix_canon_cups():
    """Canon LBP3010 dagi qotib qolgan ishlarni tozalaydi va CUPS ni qayta tiklaydi."""
    logger.info("Canon LBP3010 qayta tiklanmoqda...")
    subprocess.run(["sudo", "cancel", "-a"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # usblp konflikti bo'lsa, modulni qayta yuklash
    subprocess.run(["sudo", "rmmod", "usblp"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "systemctl", "restart", "cups"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "cupsenable", CANON_PRINTER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["sudo", "cupsaccept", CANON_PRINTER], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    logger.info("✅ CUPS navbati tozalandi va Canon LBP3010 faollashtirildi!")
    logger.info("Eslatma: Agar motor aylanmasa, Canon printerini o'chirib, 10 soniyadan so'ng yoqing.")


def main():
    if "--test-xp58" in sys.argv:
        print("[*] XP-58 Termal Printer sinovi...")
        test_job = {
            "id": "DEV-TEST",
            "filename": "dasturchi_sinovi.receipt",
            "copies": 1,
            "pages": 1,
            "amount": 0,
        }
        res = print_to_xp58(test_job, note="Dasturchi sinovi muvaffaqiyatli!")
        if res:
            print("[OK] XP-58 qog'oz chiqardi!")
        else:
            print("[XATO] XP-58 dan qog'oz chiqmadi.")
        return

    if "--test-canon" in sys.argv:
        print("[*] Canon LBP3010 Lazer printer sinovi...")
        test_file = Path("/usr/share/cups/data/default-testpage.pdf")
        if not test_file.exists():
            test_file = Path("/usr/share/cups/data/testprint")
        ok, msg = print_to_canon(test_file)
        print(f"Natija: {ok} -> {msg}")
        return

    if "--fix-canon" in sys.argv:
        fix_canon_cups()
        return

    logger.info("==================================================")
    logger.info("  Smart Printchi - Raspberry Pi Agenti Ishga Tushdi")
    logger.info(f"  Bulut manzili   : {CLOUD_URL}")
    logger.info(f"  Asosiy (Lazer)  : {CANON_PRINTER}")
    xp_port = find_xp58_port()
    logger.info(f"  Dasturchi (POS) : {'XP-58 (' + xp_port + ')' if xp_port else 'Ulanmagan'}")
    logger.info("==================================================")
    ensure_single_instance()
    cleanup_stale_files()

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
