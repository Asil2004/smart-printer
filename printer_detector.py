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
    CUPS tizimida ro'yxatdan o'tgan printerlar ro'yxatini oladi.
    Natija: [{"name": "XP-58", "state": "idle"}, ...]
    """
    output = _run(["lpstat", "-p"])
    printers = []
    for line in output.splitlines():
        if line.startswith("printer "):
            parts = line.split()
            name = parts[1] if len(parts) > 1 else ""
            state = "idle" if "idle" in line else ("printing" if "printing" in line else "unknown")
            printers.append({"name": name, "state": state})
    return printers


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
    for db in KNOWN_PRINTER_DB:
        ptype = db["type"]
        usb_match = _match_by_usb(usb_ids, db)
        cups_name = _match_by_cups_name(cups_printers, db)

        result[ptype] = {
            "connected": usb_match or bool(cups_name),
            "cups_name": cups_name,
            "label": db["label"],
            "media": db["media"],
            "color": db["color"],
        }
        status_str = "✅ ulangan" if result[ptype]["connected"] else "❌ yo'q"
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
            return {
                "cups_name": p["cups_name"],
                "type": "laser_bw",
                "media": p["media"],
                "found": True,
                "reason": "Oq-qora hujjat → Canon lazer"
            }
        # Lazer yo'q — termal printer bilan urinib ko'r
        t = printers.get("thermal", {})
        if t.get("connected"):
            return {
                "cups_name": t["cups_name"],
                "type": "thermal",
                "media": t["media"],
                "found": True,
                "reason": "Lazer yo'q, oq-qora → XP-58 (zaxira)"
            }
        return {"found": False, "reason": "Hech qanday printer ulanmagan"}

    return {"found": False, "reason": "Noma'lum holat"}


def get_all_printer_status() -> list[dict]:
    """
    UI uchun barcha printerlar holatini qaytaradi.
    Natija: [{"type": "thermal", "label": "...", "connected": True, "cups_name": "XP-58"}, ...]
    """
    printers = detect_connected_printers()
    return [
        {
            "type": ptype,
            "label": info["label"],
            "connected": info["connected"],
            "cups_name": info["cups_name"],
            "media": info["media"],
        }
        for ptype, info in printers.items()
    ]
