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
        "type": "thermal",
        "label": "Termal (Chek)",
        "usb_ids": [
            ("0483", "070b"),  # STMicroelectronics — XP-58 IIL
            ("0416", "5011"),  # Winbond — XP-58
            ("04b8", "0e03"),  # Epson TM-T20
        ],
        "cups_name_hints": ["XP-58", "XP58", "Thermal", "Receipt", "TM-T"],
        "media": "58x297mm",
        "color": False,
    },
    {
        "type": "laser_bw",
        "label": "Lazer Oq-Qora",
        "usb_ids": [
            ("04a9", "176d"),  # Canon LBP2900
            ("04a9", "176b"),  # Canon LBP3010
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
    lsusb natijasidan barcha USB Vendor:Product ID larni oladi.
    Natija: [("0483", "070b"), ("04a9", "176d"), ...]
    """
    output = _run(["lsusb"])
    ids = []
    for line in output.splitlines():
        # Natija: "Bus 001 Device 005: ID 0483:070b STMicroelectronics USB Printer Port"
        if "ID " in line:
            try:
                id_part = line.split("ID ")[1].split()[0]  # "0483:070b"
                vendor, product = id_part.lower().split(":")
                ids.append((vendor, product))
            except Exception:
                continue
    return ids


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

    Natija:
    {
        "thermal":  {"connected": True,  "cups_name": "XP-58",  "label": "Termal (Chek)"},
        "laser_bw": {"connected": True,  "cups_name": "Canon",  "label": "Lazer Oq-Qora"},
        "color":    {"connected": False, "cups_name": "",        "label": "Rangli Printer"},
    }
    """
    usb_ids = get_connected_usb_ids()
    cups_printers = get_cups_printers()

    result = {}
    thermal_stat = inspect_thermal_escpos_status()
    hw_paper = check_hardware_paper_sensor()

    for db in KNOWN_PRINTER_DB:
        ptype = db["type"]
        usb_match = _match_by_usb(usb_ids, db)
        cups_name = _match_by_cups_name(cups_printers, db)

        # Status va xatoliklarni aniqlash
        paper_out = False
        paper_jam = False
        status_reason = "Tayyor"

        # Agar CUPS dan xatolik kelsa
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

        # Termal printer uchun ESC/POS yoki Hardware datchik tekshiruvi
        if ptype == "thermal":
            if thermal_stat.get("paper_out"):
                paper_out = True
                status_reason = "Qog'oz tugagan (Termal)"
            elif thermal_stat.get("near_end"):
                status_reason = "Qog'oz kam qolgan"

            if hw_paper is False:
                paper_out = True
                status_reason = "Qog'oz tugagan (Datchik)"

        is_connected = usb_match or bool(cups_name)
        ready = is_connected and not paper_out and not paper_jam

        result[ptype] = {
            "connected": is_connected,
            "ready": ready,
            "paper_out": paper_out,
            "paper_jam": paper_jam,
            "status_reason": status_reason if is_connected else "Ulanmagan",
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

    # 1. Chek/receipt → har doim termal
    if job_type == "receipt":
        p = printers.get("thermal", {})
        if p.get("connected"):
            if not p.get("ready"):
                return {"found": False, "reason": f"Termal printerda xatolik: {p.get('status_reason')}"}
            return {
                "cups_name": p["cups_name"],
                "type": "thermal",
                "media": p["media"],
                "found": True,
                "reason": "Chek → XP-58 termal printer"
            }
        return {"found": False, "reason": "Termal printer ulanmagan (XP-58 kerak)"}

    # 2. Rangli hujjat → rangli printer
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
        # Rangli printer yo'q — xato
        return {"found": False, "reason": "Rangli printer ulanmagan"}

    # 3. Oq-qora hujjat → lazer printer
    if color_mode == "gray":
        p = printers.get("laser_bw", {})
        if p.get("connected"):
            if not p.get("ready"):
                logger.warning(f"Lazer printerda xatolik ({p.get('status_reason')}), zaxiraga o'tiladi")
            else:
                return {
                    "cups_name": p["cups_name"],
                    "type": "laser_bw",
                    "media": p["media"],
                    "found": True,
                    "reason": "Oq-qora hujjat → Canon lazer"
                }
        # Lazer yo'q yoki tayyor emas — termal printer bilan urinib ko'r
        t = printers.get("thermal", {})
        if t.get("connected"):
            if not t.get("ready"):
                return {"found": False, "reason": f"Barcha printerlarda muammo: {t.get('status_reason')}"}
            return {
                "cups_name": t["cups_name"],
                "type": "thermal",
                "media": t["media"],
                "found": True,
                "reason": "Lazer yo'q/ishlamaydi, oq-qora → XP-58 (zaxira)"
            }
        return {"found": False, "reason": "Hech qanday printer ulanmagan"}

    return {"found": False, "reason": "Noma'lum holat"}


def get_all_printer_status() -> list[dict]:
    """
    UI uchun barcha printerlar holatini qaytaradi.
    Natija: [{"type": "thermal", "label": "...", "connected": True, "ready": True, "paper_out": False, "status_reason": "Tayyor"}, ...]
    """
    printers = detect_connected_printers()
    return [
        {
            "type": ptype,
            "label": info["label"],
            "connected": info["connected"],
            "ready": info.get("ready", info["connected"]),
            "paper_out": info.get("paper_out", False),
            "paper_jam": info.get("paper_jam", False),
            "status_reason": info.get("status_reason", "Tayyor" if info["connected"] else "Ulanmagan"),
            "cups_name": info["cups_name"],
            "media": info["media"],
        }
        for ptype, info in printers.items()
    ]
