"""
printer_detector.py — Smart Printer Routing moduli
====================================================
USB orqali ulangan printerlarni avtomatik aniqlaydi va
print job uchun to'g'ri printerni tanlaydi.

Printer turlari:
  - thermal  : XP-58 IIL (chek, receipt)
  - laser_bw : Canon 2900/3010/3018 (oq-qora hujjat)
  - color    : Har qanday rangli printer (rangli hujjat)
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
        "color": False,
    },
    {
        "type": "thermal",
        "label": "Termal Chek (XP-58)",
        "usb_ids": [
            ("0483", "070b"),  # STMicroelectronics (XP-58)
            ("0483", "5743"),  # XP-58IIH / POS-58
            ("0483", "5720"),  # Xprinter Thermal
            ("0416", "5011"),  # Winbond POS58
            ("1fc9", "2016"),  # NXP POS58
            ("0471", "0055"),  # Philips POS
            ("0fe6", "811e"),  # ICS POS58
            ("6868", "0200"),  # Zhuhai POS58
            ("1a86", "7584"),  # QinHeng CH34x USB printer
            ("067b", "2305"),  # Prolific USB printer
        ],
        "cups_name_hints": ["XP-58", "XP58", "POS", "Thermal", "ZJ-58", "Xprinter", "58mm"],
        "media": "Roll58",
        "color": False,
    },
    {
        "type": "color",
        "label": "Rangli Printer",
        "usb_ids": [
            ("04f9", "0027"),  # Brother MFC
            ("03f0", "c511"),  # HP DeskJet
            ("04b8", "08d1"),  # Epson L3110
            ("04b8", "08a1"),  # Epson L805
            ("04a9", "10dc"),  # Canon PIXMA G3410
            ("04a9", "1746"),  # Canon PIXMA MP280
        ],
        "cups_name_hints": ["PIXMA", "DeskJet", "Epson_L", "Brother", "Color", "MFC", "Inkjet"],
        "media": "A4",
        "color": True,
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
    Natija: [{"name": "XP-58", "state": "idle", "raw": "...", "paper_out": False, "jam": False}, ...]
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


def inspect_thermal_escpos_status() -> dict:
    """
    /dev/usb/lp0 dagi XP-58 termal printeriga to'g'ridan-to'g'ri DLE EOT status so'rovini yuboradi.
    Termal printer qog'oz holati, qopqog'i va xatoliklarni aniqlaydi.
    """
    dev_path = "/dev/usb/lp0"
    import os
    if not os.path.exists(dev_path):
        return {"available": False, "paper_out": False, "cover_open": False}

    try:
        # DLE EOT 4 (Real-time paper status transmission)
        # ESC/POS standard: 0x10 0x04 0x04
        # Response byte:
        #   bit 5-6: 11 (Paper end sensor: paper not present)
        #   bit 2-3: 11 (Paper near-end sensor: paper near end)
        import select
        fd = os.open(dev_path, os.O_RDWR | os.O_NONBLOCK)
        try:
            os.write(fd, b"\x10\x04\x04")
            # 100ms kutamiz
            r, _, _ = select.select([fd], [], [], 0.1)
            if r:
                res = os.read(fd, 4)
                if res:
                    status_byte = res[0]
                    paper_out = bool(status_byte & 0x60)  # bit 5 yoki bit 6
                    near_end = bool(status_byte & 0x0C)   # bit 2 yoki bit 3
                    return {
                        "available": True,
                        "paper_out": paper_out,
                        "near_end": near_end,
                        "status_reason": "Qog'oz tugagan" if paper_out else ("Qog'oz tugamoqda" if near_end else "Normal")
                    }
        finally:
            os.close(fd)
    except Exception as e:
        logger.debug(f"ESC/POS status so'rovida ogohlantirish: {e}")

    return {"available": True, "paper_out": False, "near_end": False, "status_reason": "Normal"}


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

        # Termal printer uchun /dev/usb/lp* mavjudligi
        thermal_dev = False
        if ptype == "thermal":
            import os
            thermal_dev = os.path.exists("/dev/usb/lp0") or os.path.exists("/dev/usb/lp1")

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

        # FAQAT Pi3 ga jismonan ulangan bo'lsagina is_connected True bo'ladi!
        if ptype == "thermal":
            is_connected = usb_match or thermal_dev
        else:
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
            "color": db["color"],
        }
        status_str = f"✅ Tayyor" if ready else (f"⚠️ {status_reason}" if is_connected else "❌ yo'q")
        logger.info(
            f"[{ptype}] USB:{usb_match} CUPS:'{cups_name}' → {status_str}"
        )

    return result


def get_printer_for_job(color_mode: str = "gray", job_type: str = "document") -> dict:
    """
    Print job uchun eng mos printerni tanlaydi.

    Args:
        color_mode : "gray" | "color"
        job_type   : "document" | "receipt"

    Returns:
        {
            "cups_name": "Canon",
            "type": "laser_bw",
            "media": "A4",
            "found": True,
            "reason": "Oq-qora hujjat → Canon lazer"
        }
    """
    printers = detect_connected_printers()

    # 1. Rangli hujjat → rangli printer
    if color_mode == "color":
        p = printers.get("color", {})
        if p.get("connected"):
            if not p.get("ready"):
                return {"found": False, "reason": f"Rangli printerda xatolik: {p.get('status_reason')}"}
            return {
                "cups_name": p["cups_name"],
                "type": "color",
                "media": p["media"],
                "found": True,
                "reason": "Rangli hujjat → rangli printer"
            }
        return {"found": False, "reason": "Rangli printer ulanmagan"}

    # 2. Oq-qora hujjat / har qanday fayl → Canon LBP 3010 Lazer printer
    p_laser = printers.get("laser_bw", {})
    if p_laser.get("connected"):
        if not p_laser.get("ready"):
            return {"found": False, "reason": f"Canon LBP printerida muammo: {p_laser.get('status_reason')}"}
        return {
            "cups_name": p_laser["cups_name"] or "Canon-LBP3010",
            "type": "laser_bw",
            "media": p_laser["media"],
            "found": True,
            "reason": "Hujjat → Canon LBP lazer printer"
        }

    # 3. Agar faqat Termal Chek (XP-58) ulangan bo'lsa
    p_thermal = printers.get("thermal", {})
    if p_thermal.get("connected"):
        if not p_thermal.get("ready"):
            return {"found": False, "reason": f"Termal printerda muammo: {p_thermal.get('status_reason')}"}
        return {
            "cups_name": p_thermal["cups_name"] or "XP58",
            "type": "thermal",
            "media": p_thermal["media"],
            "found": True,
            "reason": "Termal printer (XP-58) → Chek/Lenta"
        }

    return {"found": False, "reason": "Printer ulanmagan yoki o'chirilgan"}

    return {"found": False, "reason": "Noma'lum holat"}


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
