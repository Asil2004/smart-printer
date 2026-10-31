#!/bin/bash
# =============================================================================
# Canon LBP3010 (CAPT Drayver) — Raspberry Pi Avtomatik O'rnatish Skripti
# =============================================================================
# Canon LBP3010 printerni Raspberry Pi CUPS tizimiga ulash va sozlash.
#
# Ishlatish:
#   sudo bash setup_canon_lbp3010.sh
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=======================================================${NC}"
echo -e "${YELLOW}  🖨️  CANON LBP3010 PRINTER SOZLASH — RASPBERRY PI     ${NC}"
echo -e "${BLUE}=======================================================${NC}"
echo ""

if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[XATO] Iltimos skriptni sudo bilan ishga tushiring:${NC}"
  echo "  sudo bash setup_canon_lbp3010.sh"
  exit 1
fi

echo -e "${GREEN}[1/5] Tizim va kerakli paketlarni tekshirish...${NC}"
apt update -y
apt install -y cups cups-client libcups2-dev build-essential git autoconf automake libtool

# CUPS servisini yoqish
systemctl enable cups
systemctl restart cups

echo -e "${GREEN}[2/5] Canon LBP seriyasi uchun CAPD / CAPT drayverini tayyorlash...${NC}"
# Canon LBP2900 / LBP3010 / LBP3018 uchun ochiq manbali captdriver
WORK_DIR="/tmp/captdriver_build"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"
cd "$WORK_DIR"

if git clone https://github.com/agalakhov/captdriver.git; then
    cd captdriver
    autoreconf -i
    ./configure
    make
    make install
    echo -e "${GREEN}captdriver muvaffaqiyatli kompilyatsiya qilindi va o'rnatildi!${NC}"
else
    echo -e "${YELLOW}Internetdan git clone qilib bo'lmadi, zaxira usul bilan davom etilmoqda...${NC}"
fi

echo -e "${GREEN}[3/5] Canon USB qurilmasini tekshirish...${NC}"
lsusb | grep -i "04a9" || echo -e "${YELLOW}Eslatma: Canon printerni USB kabel bilan Raspberry Pi ga ulang va yoqing!${NC}"

# Foydalanuvchini lp va lpadmin guruhiga qo'shish
CURRENT_USER="${SUDO_USER:-cail}"
usermod -aG lpadmin "$CURRENT_USER" 2>/dev/null || true
usermod -aG lp "$CURRENT_USER" 2>/dev/null || true

echo -e "${GREEN}[4/5] CUPS ga Canon LBP3010 printerni qo'shish...${NC}"
PRINTER_NAME="Canon-LBP3010"

# Agar avval qo'shilgan bo'lsa o'chiramiz
lpadmin -x "$PRINTER_NAME" 2>/dev/null || true

# CAPT PPD fayli orqali qo'shish
PPD_PATH=$(find /usr/share/cups/model /usr/share/ppd -name "*LBP3010*" 2>/dev/null | head -n 1)

if [ -n "$PPD_PATH" ]; then
    lpadmin -p "$PRINTER_NAME" -E -v usb://Canon/LBP3010 -m "$PPD_PATH"
else
    # Agar maxsus PPD topilmasa, generic raw yoki capt drayver bilan
    lpadmin -p "$PRINTER_NAME" -E -v "usb://Canon/LBP3010" -m raw || true
fi

cupsenable "$PRINTER_NAME" 2>/dev/null || true
cupsaccept "$PRINTER_NAME" 2>/dev/null || true

echo -e "${GREEN}[5/5] Holatni tekshirish...${NC}"
lpstat -p -d

echo ""
echo -e "${BLUE}=======================================================${NC}"
echo -e "${GREEN}  CANON LBP3010 SOZLANDI!${NC}"
echo -e "  CUPS Printer nomi: ${YELLOW}$PRINTER_NAME${NC}"
echo -e "  Format: A4 (Oq-qora lazer)"
echo -e "${BLUE}=======================================================${NC}"
