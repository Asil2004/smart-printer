"""
printer_detector.py — Smart Printer Routing moduli
====================================================
USB orqali ulangan printerlarni avtomatik aniqlaydi va
print job uchun to'g'ri printerni tanlaydi.

Printer turi: laser_bw — Canon LBP3010 (A4, oq-qora). Loyihada boshqa printer yo'q
(rangli va XP-58 chek printerlari 2026-11-26 da olib tashlandi).
"""

import subprocess
import logging

logger = logging.getLogger("smart_printchi.detector")


# ──────────────────────────────────────────────────────────
# Ma'lum printerlar ro'yxati (USB Vendor:Product ID lari)
# ──────────────────────────────────────────────────────────
KNOWN_PRINTER_DB = [
    {
        "type": "laser_bw",
        "label": "Canon LBP3010 Lazer",
        "usb_ids": [
            ("04a9", "26da"),  # Canon LBP3010/LBP3018/LBP3050 (Asl apparat ID)
            ("04a9", "176b"),  # Canon LBP3010
            ("04a9", "176d"),  # Canon LBP2900
            ("04a9", "1601"),  # Canon LBP3018/3050
            ("04a9", "2771"),  # Canon LBP6020
            ("04a9", "2760"),  # Canon LBP6030
            ("04e8", "326c"),  # Samsung ML-2160
            ("04e8", "3413"),  # Samsung M2020
            ("03f0", "b711"),  # HP LaserJet Pro M15
            ("03f0", "002a"),  # HP LaserJet 1020
        ],
        "cups_name_hints": ["Canon", "LBP", "Samsung", "LaserJet", "HP_Laser", "ML-"],
        "media": "A4",
    },
]


def _run(cmd: list) -> str:
    """Tizim buyrug'ini xavfsiz ishga tushiradi va natijani qaytaradi."""
    try:
        res = subprocess.run(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5
        )
        return res.stdout.strip()
    except Exception as e:
        logger.warning(f"Buyruq bajarishda xatolik ({' '.join(cmd)}): {e}")
        return ""


def get_connected_usb_ids() -> list[tuple[str, str]]:
    """
    Linux /sys/bus/usb/devices dan to'g'ridan-to'g'ri tezkor o'qiydi (0.001 soniya, CPU yuklama 0%).
    Agar /sys mavjud bo'lmasa, lsusb dan foydalanadi.
    Natija: [("04a9", "26da"), ("0483", "070b"), ...]
    """
    import glob
    ids = []
    sys_paths = glob.glob("/sys/bus/usb/devices/*/idVendor")
    if sys_paths:
        for v_path in sys_paths:
            try:
                p_path = v_path.replace("idVendor", "idProduct")
                with open(v_path, "r") as fv, open(p_path, "r") as fp:
                    vid = fv.read().strip().lower()
                    pid = fp.read().strip().lower()
                    ids.append((vid, pid))
            except Exception:
                continue
        if ids:
            return ids

    # Fallback: lsusb
    output = _run(["lsusb"])
    for line in output.splitlines():
        if "ID " in line:
            try:
                id_part = line.split("ID ")[1].split()[0]
                vendor, product = id_part.lower().split(":")
                ids.append((vendor, product))
            except Exception:
                continue
    return ids


def get_live_cups_usb_printers() -> list[str]:
    """
    lpinfo -v orqali Raspberry Pi ga ayni paytda USB port orqali
    jismonan ulangan apparatlarning URI manzillarini qaytaradi.
    Masalan: ['usb://Canon/LBP3010/LBP3018/LBP3050?serial=...', 'usb://Printer%20/...']
    """
    output = _run(["lpinfo", "-v"])
    live = []
    for line in output.splitlines():
        if "direct usb://" in line:
            parts = line.split()
            if len(parts) >= 2:
                live.append(parts[1])
    return live


def get_cups_printers() -> list[dict]:
    """
    CUPS tizimida ro'yxatdan o'tgan printerlar ro'yxatini va ularning statusini oladi.
    Natija: [{"name": "Canon-LBP3010", "state": "idle", "raw": "...", "paper_out": False, "jam": False}, ...]
    """
    output = _run(["lpstat", "-p", "-l"])
    if not output:
        output = _run(["lpstat", "-p"])
        
    printers = []
    current_printer = None
    for line in output.splitlines():
        if line.startswith("printer "):
            parts = line.split()
            name = parts[1] if len(parts) > 1 else ""
            state = "idle" if "idle" in line else ("printing" if "printing" in line else "unknown")
            current_printer = {
                "name": name,
                "state": state,
                "raw": line,
                "paper_out": False,
                "jam": False,
                "error": False,
                "status_reason": ""
            }
            # Tezkor holat tekshiruvi
            lower_line = line.lower()
            if "out of paper" in lower_line or "media-empty" in lower_line or "paper-empty" in lower_line:
                current_printer["paper_out"] = True
                current_printer["status_reason"] = "Qog'oz tugagan"
            elif "jam" in lower_line or "media-jam" in lower_line:
                current_printer["jam"] = True
                current_printer["status_reason"] = "Qog'oz qisilib qolgan"
            elif "disabled" in lower_line or "paused" in lower_line:
                current_printer["error"] = True
                current_printer["status_reason"] = "Printer to'xtatilgan (Pauza)"
                
            printers.append(current_printer)
        elif current_printer and line.strip().startswith("Alerts:"):
            alert_str = line.lower()
            if "media-empty" in alert_str or "paper" in alert_str:
                current_printer["paper_out"] = True
                current_printer["status_reason"] = "Qog'oz tugagan"
            if "jam" in alert_str:
                current_printer["jam"] = True
                current_printer["status_reason"] = "Qog'oz tiqilib qolgan"
            if "toner" in alert_str or "low" in alert_str:
                current_printer["status_reason"] = "Toner/Siyoh kam qolgan"

    return printers


def check_hardware_paper_sensor(pin: int = None) -> bool | None:
    """
    Raspberry Pi GPIO orqali optik/IR qog'oz datchigini tekshiradi (TCRT5000 / Optical Switch).
    Qaytadi:
      True  -> Qog'oz bor
      False -> Qog'oz TUGAGAN
      None  -> Datchik mavjud emas (Linux/RPi muhiti emas yoki GPIO o'rnatilmagan)
    """
    try:
        import RPi.GPIO as GPIO
        pin = pin or 24
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        val = GPIO.input(pin)
        # Odatda to'siq bo'lsa (qog'oz bo'lsa) LOW (0), qog'oz tugasa HIGH (1) bo'ladi
        return val == 0
    except Exception:
        return None


def _match_by_usb(usb_ids: list, db_entry: dict) -> bool:
    """USB ID lar orqali printer turini aniqlaydi."""
    for vid, pid in usb_ids:
        for db_vid, db_pid in db_entry["usb_ids"]:
            if vid == db_vid.lower() and pid == db_pid.lower():
                return True
    return False


def _match_by_cups_name(cups_printers: list, db_entry: dict) -> str:
    """CUPS printer nomi orqali mosligini topadi. Mos nom qaytaradi."""
    for hint in db_entry["cups_name_hints"]:
        for p in cups_printers:
            if hint.lower() in p["name"].lower():
                return p["name"]
    return ""


def detect_connected_printers() -> dict:
    """
    Ulangan printerlarni aniqlaydi.
    Linux /sys va USB shina orqali Pi 3 ga ayni damda jismonan ulangan
    printerlarni 0.001 soniyada aniqlaydi.
    """
    usb_ids = get_connected_usb_ids()
    cups_printers = get_cups_printers()

    result = {}
    for db in KNOWN_PRINTER_DB:
        ptype = db["type"]
        usb_match = _match_by_usb(usb_ids, db)

        # Maxsus Canon tekshiruvi: agar USB da istalgan Canon (04a9) qurilmasi bo'lsa
        if ptype == "laser_bw" and not usb_match:
            for vid, _ in usb_ids:
                if vid == "04a9":
                    usb_match = True
                    break

        cups_name = _match_by_cups_name(cups_printers, db)

        # Status va xatoliklarni aniqlash
        paper_out = False
        paper_jam = False
        status_reason = "Tayyor"

        matching_cups = next((p for p in cups_printers if p["name"].lower() == cups_name.lower()), None)
        if matching_cups:
            if matching_cups.get("paper_out"):
                paper_out = True
                status_reason = "Qog'oz tugagan"
            elif matching_cups.get("jam"):
                paper_jam = True
                status_reason = "Qog'oz tiqilgan"
            elif matching_cups.get("error"):
                status_reason = matching_cups.get("status_reason", "Xatolik")

        # FAQAT USB orqali apparat jismonan ulangan bo'lsagina is_connected True bo'ladi
        is_connected = usb_match
        ready = is_connected and not paper_out and not paper_jam

        result[ptype] = {
            "connected": is_connected,
            "ready": ready,
            "paper_out": paper_out,
            "paper_jam": paper_jam,
            "status_reason": status_reason if is_connected else "Ulanmagan (USB uzilgan)",
            "cups_name": cups_name,
            "label": db["label"],
            "media": db["media"],
        }
        status_str = f"✅ Tayyor" if ready else (f"⚠️ {status_reason}" if is_connected else "❌ yo'q")
        logger.info(
            f"[{ptype}] USB:{usb_match} CUPS:'{cups_name}' → {status_str}"
        )

    return result


def get_printer_for_job(color_mode: str = "gray", job_type: str = "document", printer_type: str = "") -> dict:
    """Har qanday hujjat → Canon LBP (oq-qora). Argumentlar eski chaqiruvlar bilan moslik uchun qoldirilgan."""
    p = detect_connected_printers().get("laser_bw", {})
    if not p.get("connected"):
        return {"found": False, "reason": "Canon LBP printeri ulanmagan yoki o'chirilgan"}
    if not p.get("ready"):
        return {"found": False, "reason": f"Canon LBP printerida muammo: {p.get('status_reason')}"}
    return {
        "cups_name": p["cups_name"] or "Canon-LBP3010",
        "type": "laser_bw",
        "media": p["media"],
        "found": True,
        "reason": "Hujjat → Canon LBP lazer printer",
    }


def get_all_printer_status(only_connected: bool = True) -> list[dict]:
    """
    UI uchun barcha printerlar holatini qaytaradi.
    only_connected=True bo'lsa (sukut bo'yicha), FAQAT Pi3 ga ayni damda
    jismonan ulangan printerlar ro'yxatini qaytaradi.
    """
    printers = detect_connected_printers()
    res = []
    for ptype, info in printers.items():
        if only_connected and not info["connected"]:
            continue
        res.append({
            "type": ptype,
            "label": info["label"],
            "connected": info["connected"],
            "ready": info.get("ready", info["connected"]),
            "paper_out": info.get("paper_out", False),
            "paper_jam": info.get("paper_jam", False),
            "status_reason": info.get("status_reason", "Tayyor" if info["connected"] else "Ulanmagan (USB uzilgan)"),
            "cups_name": info["cups_name"],
            "media": info["media"],
        })
    return res
