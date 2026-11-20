#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Smart Printchi - XP-58 Thermal Printer Test Script (Raspberry Pi / Linux)
Loyiha rahbari: Ravshanov Muhammad Ali
"""

import os
import sys
import glob

# ESC/POS Buyruqlari
ESC = b'\x1b'
GS  = b'\x1d'

INIT_PRINTER = ESC + b'@'             # Printerni qayta boshlash
ALIGN_CENTER = ESC + b'a\x01'         # Markazga tekislash
ALIGN_LEFT   = ESC + b'a\x00'         # Chapga tekislash
ALIGN_RIGHT  = ESC + b'a\x02'         # O'ngga tekislash
BOLD_ON      = ESC + b'E\x01'         # Qalin shrift
BOLD_OFF     = ESC + b'E\x00'         # Oddiy shrift
DOUBLE_SIZE  = GS + b'!\x11'          # 2x Kattalashtirish (eni va bo'yi)
NORMAL_SIZE  = GS + b'!\x00'          # Normal hajm
FEED_CUT     = b'\n\n\n\n' + GS + b'V\x00' # Qog'oz chiqarish va kesish (agar avto-kesgich bo'lsa)

def find_printer_port():
    ports = glob.glob('/dev/usb/lp*')
    if ports:
        return ports[0]
    return None

def generate_receipt():
    data = bytearray()
    data.extend(INIT_PRINTER)
    
    # Sarlavha
    data.extend(ALIGN_CENTER)
    data.extend(DOUBLE_SIZE + BOLD_ON)
    data.extend("SMART PRINTCHI\n".encode('utf-8'))
    data.extend(NORMAL_SIZE + BOLD_OFF)
    data.extend("Avtomatlashtirilgan Kiosk\n".encode('utf-8'))
    data.extend("--------------------------------\n".encode('utf-8'))
    
    # Ma'lumotlar
    data.extend(ALIGN_LEFT)
    data.extend(BOLD_ON + "Loyiha rahbari:\n".encode('utf-8') + BOLD_OFF)
    data.extend("  Ravshanov Muhammad Ali\n".encode('utf-8'))
    data.extend("Printer turi : XP-58 (58mm POS)\n".encode('utf-8'))
    data.extend("Aloqa porti  : USB / Raw ESC-POS\n".encode('utf-8'))
    data.extend("Holati       : TEST MUVAFFAQITYATLI!\n".encode('utf-8'))
    data.extend("--------------------------------\n".encode('utf-8'))
    
    # Test matni
    data.extend(ALIGN_CENTER)
    data.extend("QR Tekshiruv:\n".encode('utf-8'))
    data.extend("https://asil2004.github.io/smart-printer/\n".encode('utf-8'))
    data.extend("--------------------------------\n".encode('utf-8'))
    data.extend("Tizim sinovdan o'tdi.\n".encode('utf-8'))
    data.extend("Chop etishga to'liq tayyor!\n".encode('utf-8'))
    
    # Chiqarish
    data.extend(FEED_CUT)
    return data

def main():
    port = find_printer_port()
    if not port:
        print("XATO: /dev/usb/lp0 topilmadi! XP-58 USB orqali ulanganligini tekshiring:")
        print("1. 'lsusb' buyrug'ini tering")
        print("2. 'dmesg | grep usblp' ni tekshiring")
        sys.exit(1)
        
    print(f"[+] XP-58 printeri topildi: {port}")
    try:
        with open(port, 'wb') as f:
            receipt = generate_receipt()
            f.write(receipt)
            f.flush()
        print("[OK] Test cheki muvaffaqiyatli chiqarildi!")
    except PermissionError:
        print(f"Ruxsat yetarli emas! Quyidagicha ishga tushiring:\n  sudo python3 {sys.argv[0]}")
    except Exception as e:
        print(f"Xatolik: {e}")

if __name__ == '__main__':
    main()
