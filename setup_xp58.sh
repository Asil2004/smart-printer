#!/bin/bash
# ============================================================
# XP-58 IIL Termal Printer — Raspberry Pi O'rnatish Skripti
# ============================================================
# Ishlatish: sudo bash setup_xp58.sh
# ============================================================

set -e

YELLOW='\033[1;33m'
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m' # No Color

echo -e "${YELLOW}╔══════════════════════════════════════════╗${NC}"
echo -e "${YELLOW}║   XP-58 IIL Printer Setup — Raspberry Pi ║${NC}"
echo -e "${YELLOW}╚══════════════════════════════════════════╝${NC}"
echo ""

# Root tekshirish
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[XATO] Iltimos sudo bilan ishga tushiring: sudo bash setup_xp58.sh${NC}"
  exit 1
fi

CURRENT_USER=${SUDO_USER:-pi}
echo -e "${GREEN}[1/7] Tizim paketlarini yangilash...${NC}"
apt update -y

echo -e "${GREEN}[2/7] CUPS va zarur kutubxonalarni o'rnatish...${NC}"
apt install -y \
    cups \
    libcups2-dev \
    libcupsimage2-dev \
    git \
    build-essential \
    python3-pip \
    python3-venv

echo -e "${GREEN}[3/7] zj-58 drayverini yuklab kompilyatsiya qilish...${NC}"
TMP_DIR=$(mktemp -d)
cd "$TMP_DIR"

git clone https://github.com/klirichek/zj-58.git
cd zj-58
make

# Filterlarni o'rnatish
cp rastertozj58 /usr/lib/cups/filter/
chmod 755 /usr/lib/cups/filter/rastertozj58

# PPD faylini o'rnatish
mkdir -p /usr/share/cups/model/xprinter
cp ZJ-58.ppd /usr/share/cups/model/xprinter/

echo -e "${GREEN}[4/7] CUPS xizmatini yoqish va sozlash...${NC}"
systemctl enable cups
systemctl start cups

# Foydalanuvchini lp va lpadmin guruhlariga qo'shish
usermod -aG lp "$CURRENT_USER"
usermod -aG lpadmin "$CURRENT_USER"

echo -e "${GREEN}[5/7] CUPS masofadan boshqaruvga ruxsat berish...${NC}"
cupsctl --remote-admin --remote-any
systemctl restart cups

echo -e "${GREEN}[6/7] USB printer qurilmasini topish...${NC}"
echo "USB qurilmalari:"
lsusb | grep -i "Xprinter\|Winbond\|0416\|printer" || echo "  (Printer topilmadi — USB kabelni ulang va qayta tekshiring)"

echo ""
echo "USB print qurilmalari:"
ls /dev/usb/lp* 2>/dev/null || echo "  /dev/usb/lp0 — hali mavjud emas (printer ulanmagan bo'lishi mumkin)"

echo ""
echo -e "${GREEN}[7/7] python-escpos kutubxonasini o'rnatish (ESC/POS rejimi uchun)...${NC}"
pip3 install python-escpos

# Tozalash
cd /
rm -rf "$TMP_DIR"

echo ""
echo -e "${YELLOW}════════════════════════════════════════════${NC}"
echo -e "${GREEN}✅ O'rnatish tugadi!${NC}"
echo ""
echo "Keyingi qadamlar:"
echo ""
echo "  1. XP-58 IIL printeringizni USB orqali Raspberry Pi ga ulang"
echo ""
echo "  2. CUPS Web UI orqali printer qo'shing:"
echo "     http://$(hostname -I | awk '{print $1}'):631"
echo "     → Administration → Add Printer → USB Printers"
echo "     → Driver: ZJ-58 (yoki Xprinter 58mm)"
echo "     → Printer nomi: XP-58 (muhim!)"
echo ""
echo "  3. Test chop etish:"
echo "     echo 'Test chop etish' | lp -d XP-58"
echo ""
echo "  4. Printer nomini .env fayliga yozing:"
echo "     echo 'PRINTER_NAME=XP-58' >> /home/$CURRENT_USER/smart-printchi/.env"
echo -e "${YELLOW}════════════════════════════════════════════${NC}"
