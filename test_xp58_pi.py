#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - XP-58 Thermal Printer Test Script (Raspberry Pi / Linux)
Loyiha rahbari: Ravshanov Muhammad Ali

Matn va grafik (rasm / shtrix kod) ni 384px zichlab sinash uchun.
"""

import os
import sys
import glob
import time

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# ESC/POS Buyruqlari
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


def find_printer_port():
    ports = glob.glob('/dev/usb/lp*')
    if ports:
        return ports[0]
    return None


def generate_graphic_test():
    """384px kenglikdagi chiroyli grafik banner yaratish."""
    if not HAS_PIL:
        return b""
    img = Image.new("RGB", (384, 120), (255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Qora ramka
    draw.rectangle([(4, 4), (379, 115)], outline=(0, 0, 0), width=3)
    # Ichki qora sarlavha paneli
    draw.rectangle([(8, 8), (375, 45)], fill=(0, 0, 0))
    draw.text((30, 16), "SMART PRINTCHI KIOSK", fill=(255, 255, 255))

    draw.text((20, 55), "Loyiha: Ravshanov Muhammad Ali", fill=(0, 0, 0))
    draw.text((20, 80), "Grafik rejim: 384px Zichlangan", fill=(0, 0, 0))

    # ESC/POS raster ga aylantirish
    bw = img.convert("1")
    bytes_per_row = 384 // 8  # 48 bayt
    raw = bw.tobytes()
    inv = bytes([(~b) & 0xFF for b in raw])

    h = 120
    header = bytes([0x1d, 0x76, 0x30, 0x00, bytes_per_row, 0, h % 256, h // 256])
    return b"\x1b3\x00" + header + inv + b"\x1b2\n"


def generate_receipt():
    data = bytearray()
    data.extend(INIT_PRINTER)

    # 1. Grafik qism (agar PIL bo'lsa)
    graphic = generate_graphic_test()
    if graphic:
        data.extend(graphic)

    # 2. Matn qismi
    data.extend(ALIGN_CENTER)
    data.extend(DOUBLE_SIZE + BOLD_ON)
    data.extend("XP-58 TEST\n".encode('utf-8'))
    data.extend(NORMAL_SIZE + BOLD_OFF)
    data.extend("--------------------------------\n".encode('utf-8'))

    data.extend(ALIGN_LEFT)
    data.extend(BOLD_ON + "Holat: ".encode('utf-8') + BOLD_OFF + "Muvaffaqiyatli!\n".encode('utf-8'))
    data.extend(f"Sana : {time.strftime('%Y-%m-%d %H:%M:%S')}\n".encode('utf-8'))
    data.extend("Rejim: ESC/POS Raster + Text\n".encode('utf-8'))
    data.extend("Eni  : 58mm (384 nuqta)\n".encode('utf-8'))
    data.extend("--------------------------------\n".encode('utf-8'))

    data.extend(ALIGN_CENTER)
    data.extend("Saytdan rasm yoki PDF yuboring,\n".encode('utf-8'))
    data.extend("to'liq zichlab chiqaradi!\n".encode('utf-8'))

    data.extend(FEED_CUT)
    return data


def main():
    port = find_printer_port()
    if not port:
        print("XATO: /dev/usb/lp0 topilmadi! Kabelni tekshiring.")
        sys.exit(1)

    print(f"[+] XP-58 printeri topildi: {port}")
    try:
        os.chmod(port, 0o666)
    except Exception:
        pass

    try:
        with open(port, 'wb') as f:
            receipt = generate_receipt()
            f.write(receipt)
            f.flush()
        print("[OK] Test cheki va grafika muvaffaqiyatli chiqarildi!")
    except Exception as e:
        print(f"Xatolik: {e}")


if __name__ == '__main__':
    main()
