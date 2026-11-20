#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - XP-58 Thermal Printer Test Script (Windows)
Loyiha rahbari: Ravshanov Muhammad Ali
"""

import sys
import subprocess

ESC = b'\x1b'
GS  = b'\x1d'

INIT_PRINTER = ESC + b'@'
ALIGN_CENTER = ESC + b'a\x01'
ALIGN_LEFT   = ESC + b'a\x00'
BOLD_ON      = ESC + b'E\x01'
BOLD_OFF     = ESC + b'E\x00'
DOUBLE_SIZE  = GS + b'!\x11'
NORMAL_SIZE  = GS + b'!\x00'
FEED_CUT     = b'\n\n\n\n' + GS + b'V\x00'

def generate_receipt():
    data = bytearray()
    data.extend(INIT_PRINTER)
    data.extend(ALIGN_CENTER)
    data.extend(DOUBLE_SIZE + BOLD_ON)
    data.extend("SMART PRINTCHI\n".encode('ascii', errors='ignore'))
    data.extend(NORMAL_SIZE + BOLD_OFF)
    data.extend("Avtomatlashtirilgan Kiosk\n".encode('ascii', errors='ignore'))
    data.extend("--------------------------------\n".encode('ascii'))
    data.extend(ALIGN_LEFT)
    data.extend(BOLD_ON + "Loyiha rahbari:\n".encode('ascii') + BOLD_OFF)
    data.extend("  Ravshanov Muhammad Ali\n".encode('ascii'))
    data.extend("Printer turi : XP-58 (58mm POS)\n".encode('ascii'))
    data.extend("Holati       : TEST OK!\n".encode('ascii'))
    data.extend("--------------------------------\n".encode('ascii'))
    data.extend(ALIGN_CENTER)
    data.extend("Web Portal:\n".encode('ascii'))
    data.extend("asil2004.github.io/smart-printer\n".encode('ascii'))
    data.extend("--------------------------------\n".encode('ascii'))
    data.extend("Chop etishga to'liq tayyor!\n".encode('ascii'))
    data.extend(FEED_CUT)
    return data

def main():
    try:
        import win32print
    except ImportError:
        print("[!] pywin32 kutubxonasi o'rnatilmoqda...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pywin32"])
        import win32print

    # Printerlarni tekshirish
    printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
    print("[*] Mavjud printerlar:", printers)
    
    pos_printer = None
    for p in printers:
        if any(keyword in p.lower() for keyword in ['pos', 'xp', '58', 'thermal', 'receipt']):
            pos_printer = p
            break
            
    if not pos_printer:
        print("\n[!] XP-58 nomli printer topilmadi.")
        print("Agar printer 'Generic / Text Only' yoki boshqa nomda bo'lsa, quyidagi ro'yxatdan nomini tanlang:")
        for idx, p in enumerate(printers):
            print(f"  {idx + 1}. {p}")
        choice = input("\nPrinter raqamini kiriting (yoki chiqish uchun Enter): ").strip()
        if choice and choice.isdigit() and 1 <= int(choice) <= len(printers):
            pos_printer = printers[int(choice) - 1]
        else:
            return

    print(f"\n[+] '{pos_printer}' printeriga test cheki yuborilmoqda...")
    hPrinter = win32print.OpenPrinter(pos_printer)
    try:
        hJob = win32print.StartDocPrinter(hPrinter, 1, ("Smart Printchi Test", None, "RAW"))
        try:
            win32print.StartPagePrinter(hPrinter)
            receipt = generate_receipt()
            win32print.WritePrinter(hPrinter, bytes(receipt))
            win32print.EndPagePrinter(hPrinter)
        finally:
            win32print.EndDocPrinter(hPrinter)
        print("[OK] Test cheki muvaffaqiyatli chiqarildi!")
    finally:
        win32print.ClosePrinter(hPrinter)

if __name__ == '__main__':
    main()
