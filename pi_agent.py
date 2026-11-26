#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - Raspberry Pi Kiosk Print Agent
================================================
Loyiha rahbari: Ravshanov Muhammad Ali

Ushbu agent Raspberry Pi 3 da fonda ishlaydi (15-20 MB RAM):
1. Canon LBP3010 (A4, oq-qora lazer) — yagona printer
2. Bulutli Render.com serveridan navbatdagi buyurtmalarni avtomat oladi
3. Uskuna holatini jonli ravishda Render ga yuboradi (Heartbeat), buyurtmalarni zaxiralaydi
"""

import os
import sys
import glob
import time
import uuid
import shutil
import logging
import tempfile
import json
import threading
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
    from printer_detector import get_all_printer_status, detect_connected_printers
except Exception:
    def get_all_printer_status():
        return [{"type": "laser_bw", "label": "Canon LBP3010 Lazer", "connected": True, "ready": True}]
    def detect_connected_printers():
        return {}

import cups_jobs  # CUPS ish holati (IPP)

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [Pi-Agent]: %(message)s",
    datefmt="%H:%M:%S"
)
logger = logging.getLogger("pi_agent")

CLOUD_URL = os.environ.get("CLOUD_URL", "https://smart-printer-mo1g.onrender.com").rstrip("/")
CANON_PRINTER = os.environ.get("PRINTER_NAME", "Canon-LBP3010")
POLL_INTERVAL = 2
# Render bilan umumiy maxfiy kalit (Render'dagi AGENT_TOKEN bilan bir xil bo'lishi kerak)
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
HEARTBEAT_INTERVAL = 5     # s — chop etish paytida ham to'xtamaydi (alohida oqim)
BACKUP_INTERVAL = 10       # s — Render buyurtmalarini Pi'ga nusxalash
BACKUP_DIR = Path(os.environ.get("AGENT_BACKUP_DIR", str(Path.home() / ".smart_printchi_backup")))
PRINT_GIVE_UP_S = 20 * 60  # shuncha vaqtda tugamasa CUPS ishi bekor qilinadi

cloud = requests.Session()
if AGENT_TOKEN:
    cloud.headers["X-Agent-Token"] = AGENT_TOKEN

def print_to_canon(pdf_path: Path, copies: int = 1, orientation: str = "portrait",
                   page_ranges: str = "", order_id: str = "", pages: int = 1) -> tuple[bool, str]:
    """
    Canon LBP3010 ga CUPS orqali fayl yuboradi va ish HAQIQATAN tugaguncha kutadi.
    captdriver qog'oz tugaganini CUPS'ga aytmaydi: ish shunchaki navbatda turadi.
    Shuning uchun "PRINTED" faqat CUPS ishni "completed" qilganda qaytariladi.
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
    logger.info(f"CUPS qabul qildi: {proc.stdout.strip()}")

    job_id = cups_jobs.parse_lp_job_id(proc.stdout)
    if not job_id:
        return False, "CUPS ish raqamini qaytarmadi"

    started = time.time()
    alert_after = 60 + 10 * max(1, pages) * max(1, copies)
    alerted = False
    unknown = 0
    while True:
        time.sleep(2)
        info = cups_jobs.get_job(CANON_PRINTER, job_id)
        state = info.get("state")
        reasons = str(info.get("reasons", ""))
        if state in cups_jobs.FINAL_OK:
            if "with-errors" in reasons:
                return False, f"CUPS ishi xato bilan tugadi: {info.get('message', '')}"
            logger.info(f"✅ Canon LBP3010 ishni yakunladi: #{job_id} ({int(time.time() - started)} s)")
            return True, "Muvaffaqiyatli chop etildi"
        if state in cups_jobs.FINAL_BAD:
            return False, f"CUPS ishi {state}: {info.get('message', '')}"
        # printer-error-policy=retry-job: buzilgan fayl qayta-qayta urinib yotmasin
        if "with-errors" in reasons:
            cups_jobs.cancel_job(CANON_PRINTER, job_id)
            return False, f"Faylni chop etib bo'lmadi: {info.get('message', '')}"
        if state == "unknown":
            unknown += 1
            if unknown >= 15:   # IPP javob bermayapti — lpstat bilan tekshiramiz
                q = subprocess.run(["lpstat", "-o", CANON_PRINTER], stdout=subprocess.PIPE, text=True)
                if f"{CANON_PRINTER}-{job_id} " not in q.stdout + " ":
                    return True, "Chop etildi (lpstat)"
                unknown = 0
        else:
            unknown = 0
        elapsed = time.time() - started
        if not alerted and elapsed > alert_after:
            alerted = True
            logger.warning(f"Canon #{job_id} {int(elapsed)} s dan beri tugamadi — qog'oz/USB?")
            if order_id:
                report(order_id, {"status": "PRINTING", "stuck": True,
                                  "note": "Printer javob bermayapti — qog'oz yoki USB ulanishini tekshiring"})
        if elapsed > PRINT_GIVE_UP_S:
            cups_jobs.cancel_job(CANON_PRINTER, job_id)
            return False, (f"Printer {PRINT_GIVE_UP_S // 60} daqiqa javob bermadi (qog'oz yoki USB). "
                           f"Ish bekor qilindi.")


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


# ──────────────────────────────────────────────────────────
# Render bilan aloqa: holat xabari, heartbeat, zaxira
# ──────────────────────────────────────────────────────────
_backup_lock = threading.Lock()


def _backup_load() -> dict:
    try:
        return json.loads((BACKUP_DIR / "orders.json").read_text(encoding="utf-8"))
    except Exception:
        return {"boot_id": "", "orders": {}}


def _backup_save(data: dict):
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    tmp = BACKUP_DIR / "orders.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(BACKUP_DIR / "orders.json")


def report(order_id: str, payload: dict, tries: int = 3) -> bool:
    """Buyurtma holatini Render'ga yuboradi (3 urinish) va Pi zaxirasida ham yangilaydi."""
    with _backup_lock:
        data = _backup_load()
        o = data["orders"].get(order_id)
        if o is not None:
            o["status"] = payload.get("status", o.get("status"))
            o["updated_at"] = time.time()
            _backup_save(data)
    for i in range(tries):
        try:
            r = cloud.post(f"{CLOUD_URL}/api/agent/status/{order_id}", json=payload, timeout=10)
            if r.ok or r.status_code == 404:
                return r.ok
        except requests.exceptions.RequestException:
            pass
        time.sleep(2 * (i + 1))
    logger.warning(f"#{order_id} holatini ({payload.get('status')}) Render'ga yuborib bo'lmadi")
    return False


def sync_backup(server_boot_id: str):
    """Render buyurtmalarini Pi'ga nusxalaydi; server qayta yongan bo'lsa — tiklaydi."""
    with _backup_lock:
        data = _backup_load()
    files_dir = BACKUP_DIR / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    if data.get("boot_id") and data["boot_id"] != server_boot_id and data.get("orders"):
        logger.warning("Render qayta ishga tushgan — buyurtmalar Pi zaxirasidan tiklanmoqda...")
        handles = []
        try:
            files = {}
            for oid, o in data["orders"].items():
                f = files_dir / oid
                if o.get("_has_file") and f.exists():
                    h = open(f, "rb")
                    handles.append(h)
                    files[f"file_{oid}"] = (oid, h)
            r = cloud.post(f"{CLOUD_URL}/api/agent/restore",
                           data={"orders": json.dumps(list(data["orders"].values()), ensure_ascii=False)},
                           files=files or None, timeout=(15, 300))
            if not r.ok:
                logger.error(f"Tiklash muvaffaqiyatsiz: HTTP {r.status_code} {r.text[:200]}")
                return
            logger.info(f"♻️ Tiklandi: {r.json().get('restored', 0)} ta buyurtma")
        finally:
            for h in handles:
                h.close()

    r = cloud.get(f"{CLOUD_URL}/api/agent/backup", timeout=15)
    if not r.ok:
        return
    body = r.json()
    new_orders = {o["id"]: o for o in body.get("orders", [])}
    for oid, o in new_orders.items():
        f = files_dir / oid
        if o.get("_has_file") and not f.exists():
            fr = cloud.get(f"{CLOUD_URL}/api/agent/backup/file/{oid}", timeout=(15, 300), stream=True)
            if fr.ok:
                tmp = f.with_suffix(".part")
                with open(tmp, "wb") as out:
                    for chunk in fr.iter_content(65536):
                        out.write(chunk)
                tmp.replace(f)
    for f in files_dir.iterdir():   # faol bo'lmagan buyurtmalar fayllarini o'chirish
        if f.name not in new_orders or not new_orders[f.name].get("_has_file"):
            f.unlink(missing_ok=True)
    with _backup_lock:
        _backup_save({"boot_id": body.get("boot_id", server_boot_id), "orders": new_orders,
                      "saved_at": time.time()})


def sync_catalog(server_boot_id: str):
    """Admin yuklagan shablonlar va promokodlarni Pi'ga nusxalaydi; Render qayta yongan bo'lsa — qaytaradi."""
    cat_file = BACKUP_DIR / "catalog.json"
    tdir = BACKUP_DIR / "templates"
    tdir.mkdir(parents=True, exist_ok=True)
    try:
        saved = json.loads(cat_file.read_text(encoding="utf-8"))
    except Exception:
        saved = {}

    if saved.get("boot_id") and saved["boot_id"] != server_boot_id and (saved.get("promos") or saved.get("templates")):
        handles, files = [], {}
        try:
            for t in saved.get("templates", []):
                f = tdir / t.get("file", "")
                if t.get("file") and f.exists():
                    h = open(f, "rb")
                    handles.append(h)
                    files[f"file_{t['id']}"] = (t["file"], h)
            r = cloud.post(f"{CLOUD_URL}/api/agent/catalog/restore",
                           data={"catalog": json.dumps(saved, ensure_ascii=False)},
                           files=files or None, timeout=(15, 300))
            if r.ok:
                b = r.json()
                logger.info(f"♻️ Katalog tiklandi: {b.get('templates', 0)} shablon, {b.get('promos', 0)} promokod")
            elif r.status_code != 404:          # 404 — server eski versiya
                logger.error(f"Katalogni tiklash muvaffaqiyatsiz: HTTP {r.status_code}")
                return
        finally:
            for h in handles:
                h.close()

    r = cloud.get(f"{CLOUD_URL}/api/agent/catalog", timeout=15)
    if not r.ok:
        return
    body = r.json()
    keep = set()
    for t in body.get("templates", []):
        f = tdir / t.get("file", "")
        if not t.get("file"):
            continue
        keep.add(f.name)
        if not f.exists():
            fr = cloud.get(f"{CLOUD_URL}/api/agent/catalog/file/{t['id']}", timeout=(15, 300), stream=True)
            if fr.ok:
                tmp = f.with_suffix(f.suffix + ".part")
                with open(tmp, "wb") as out:
                    for chunk in fr.iter_content(65536):
                        out.write(chunk)
                tmp.replace(f)
    for f in tdir.iterdir():
        if f.name not in keep:
            f.unlink(missing_ok=True)
    tmp = cat_file.with_suffix(".tmp")
    tmp.write_text(json.dumps({"boot_id": body.get("boot_id", server_boot_id), "promos": body.get("promos", {}),
                               "templates": body.get("templates", []), "saved_at": time.time()},
                              ensure_ascii=False), encoding="utf-8")
    tmp.replace(cat_file)


def heartbeat_and_backup_loop():
    last_backup = 0.0
    warned = False
    while True:
        try:
            local_printers = get_all_printer_status()
            r = cloud.post(f"{CLOUD_URL}/api/agent/heartbeat", json={"printers": local_printers}, timeout=10)
            info = r.json() if r.ok else {}
            if info.get("backup_enabled") and info.get("boot_id") and time.time() - last_backup > BACKUP_INTERVAL:
                last_backup = time.time()
                sync_backup(info["boot_id"])
                try:
                    sync_catalog(info["boot_id"])
                except Exception as e:
                    logger.debug(f"Katalog zaxirasi xatosi: {e}")
            elif r.ok and not info.get("backup_enabled") and not warned:
                warned = True
                logger.warning("Zaxira o'chiq: Render'da AGENT_TOKEN o'rnatilmagan")
        except Exception as e:
            logger.debug(f"Heartbeat/zaxira xatosi: {e}")
        time.sleep(HEARTBEAT_INTERVAL)


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
    report(order_id, {"status": "PRINTING"})

    filename = job.get("filename", "")

    # Faylni xavfsiz spool papkasiga yuklab olish
    spool_dir = get_spool_dir()
    clean_ext = Path(filename).suffix.lower() if Path(filename).suffix else ".pdf"
    tmp_file = spool_dir / f"job_{order_id}_{int(time.time())}{clean_ext}"
    try:
        download_url = f"{CLOUD_URL}/api/agent/download/{order_id}"
        logger.info(f"Fayl yuklab olinmoqda: {download_url}")
        res = cloud.get(download_url, timeout=(15, 300), stream=True)
        if not res.ok:
            raise RuntimeError(f"Faylni yuklab bo'lmadi: status {res.status_code}")
        total_dl = 0
        with open(tmp_file, "wb") as f:
            for chunk in res.iter_content(chunk_size=65536):
                if chunk:
                    f.write(chunk)
                    total_dl += len(chunk)
        logger.info(f"Fayl to'liq yuklandi ({total_dl / (1024*1024):.2f} MB): {tmp_file.name}")
        # Server ba'zan oddiy matnni (masalan /api/dev/test_print) job_X.pdf nomi bilan beradi.
        # CUPS turini kengaytmadan aniqlaydi: .pdf matn bo'lsa pdftopdf yiqiladi va qog'oz chiqmaydi.
        if tmp_file.suffix == ".pdf":
            with open(tmp_file, "rb") as f:
                head = f.read(1024)
            if b"%PDF" not in head:
                txt_file = tmp_file.with_suffix(".txt")
                tmp_file.rename(txt_file)
                tmp_file = txt_file
                logger.info(f"Fayl PDF emas, matn sifatida chop etiladi: {tmp_file.name}")
    except Exception as e:
        logger.error(f"Fayl yuklab olishda xato: {e}")
        report(order_id, {"status": "FAILED", "error": f"Agent yuklay olmadi: {e}"})
        return

    # Canon LBP3010 (A4 lazer)
    copies = job.get("copies", 1)
    orientation = job.get("orientation", "portrait")
    ranges = job.get("page_ranges", "")
    ok, note = print_to_canon(tmp_file, copies=copies, orientation=orientation, page_ranges=ranges,
                              order_id=order_id, pages=job.get("pages", 1))
    try:
        tmp_file.unlink(missing_ok=True)
    except Exception:
        pass

    if ok:
        logger.info(f"Buyurtma #{order_id} muvaffaqiyatli chop etildi!")
        report(order_id, {"status": "PRINTED"})
    else:
        logger.error(f"Canon muvaffaqiyatsiz bo'ldi: {note}")
        report(order_id, {"status": "FAILED", "error": note})

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
    logger.info("==================================================")
    ensure_single_instance()
    cleanup_stale_files()

    threading.Thread(target=heartbeat_and_backup_loop, daemon=True).start()

    while True:
        try:
            r = cloud.get(f"{CLOUD_URL}/api/agent/queue", timeout=10)
            if r.status_code == 401:
                logger.error("Render agent kalitini rad etdi: AGENT_TOKEN ikkala tomonda bir xilmi?")
            elif r.ok:
                for job in r.json().get("jobs", []):
                    process_job(job)
        except requests.exceptions.RequestException:
            pass
        except Exception as e:
            logger.warning(f"Navbatni tekshirishda xatolik: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    main()
