#!/bin/bash
# =============================================================================
# Canon LBP3010 ni Raspberry Pi-da "Rendering completed" qotishini tuzatish
# =============================================================================
# Sababi:
# 1. CUPS usb backend Canon CAPT-dan javob kutib turib qoladi (unidir kerak)
# 2. Kernel 'usblp' moduli Canon interfeysini band qilib oladi (XP-58 bilan konflikt)
# 3. Printer kontrollerida eski sessiya xotirasi qolib ketgan
# =============================================================================

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}=======================================================${NC}"
echo -e "${YELLOW}  🔧 CANON LBP3010 QOTISHINI TUZATISH (Raspberry Pi)     ${NC}"
echo -e "${BLUE}=======================================================${NC}"

if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}[XATO] Ushbu skriptni sudo bilan ishga tushiring: sudo bash $0${NC}"
    exit 1
fi

PRINTER_NAME="Canon-LBP3010"
CANON_VID="04a9"
CANON_PID="26da"

# 1. Eski qotib qolgan ishlarni tozalash
echo -e "${YELLOW}[1/7] Navbatdagi qotgan ishlarni tozalash...${NC}"
cancel -a 2>/dev/null || true
rm -f /tmp/printchi_* 2>/dev/null || true
which pdftoppm >/dev/null 2>&1 || apt-get install -y poppler-utils 2>/dev/null || true

# 2. CUPS USB Quirks faylini sozlash (no-reattach, unidir siz - chunki rastertocapt 6 bayt javob kutadi!)
echo -e "${YELLOW}[2/7] CUPS USB quirks sozlanmoqda (no-reattach)...${NC}"
for QFILE in "/usr/share/cups/usb/org.cups.usb-quirks" "/usr/share/cups/quirks/org.cups.usb-quirks"; do
    mkdir -p "$(dirname "$QFILE")"
    touch "$QFILE"
    # Eski Canon qatorlarini tozalash
    sed -i '/0x04a9 0x26da/d' "$QFILE" 2>/dev/null || true
    # Faqat no-reattach (unidir EMAS, chunki rastertocapt backchannel kutadi)
    echo "0x04a9 0x26da no-reattach" >> "$QFILE"
    echo -e "${GREEN}   Quirk qo'shildi: $QFILE${NC}"
done

# ipp-usb servisini to'xtatish (agar bo'lsa, USB portni qulflab oladi)
systemctl stop ipp-usb 2>/dev/null || true

# 3. usblp ni Canon dan ajratish (XP-58 uchun usblp saqlanadi!)
echo -e "${YELLOW}[3/7] Kernel 'usblp' modulini Canon LBP3010 dan ajratish...${NC}"
UNBOUND=0
for DEV in /sys/bus/usb/drivers/usblp/*:*; do
    if [ -e "$DEV" ]; then
        PARENT_UEVENT="$DEV/../uevent"
        if [ -f "$PARENT_UEVENT" ] && grep -qi "PRODUCT=4a9/26da" "$PARENT_UEVENT"; then
            DEV_ID=$(basename "$DEV")
            echo -n "$DEV_ID" > /sys/bus/usb/drivers/usblp/unbind 2>/dev/null || true
            echo -e "${GREEN}   Canon USB ($DEV_ID) 'usblp' dan muvaffaqiyatli ajratildi!${NC}"
            UNBOUND=1
        fi
    fi
done

if [ "$UNBOUND" -eq 0 ]; then
    echo -e "   Canon LBP3010 hozir usblp da emas yoki USB qayta ulanishi kerak."
fi

# Doimiy udev qoidasini yaratish (har safar ulanganda avtomatik unbind qiladi)
cat << 'EOF' > /etc/udev/rules.d/99-canon-lbp-quirk.rules
# Canon LBP3010 (04a9:26da) uchun usblp ni unbind qilish — CUPS (libusb) to'liq boshqarishi uchun
ACTION=="add", SUBSYSTEM=="usb", ATTR{idVendor}=="04a9", ATTR{idProduct}=="26da", RUN+="/bin/sh -c 'for d in /sys/bus/usb/drivers/usblp/*:*; do [ -e \"$$d\" ] && grep -qi \"PRODUCT=4a9/26da\" \"$$d/../uevent\" 2>/dev/null && echo -n $$(basename \"$$d\") > /sys/bus/usb/drivers/usblp/unbind; done || true'"
EOF
udevadm control --reload-rules 2>/dev/null || true

# 4. PPD va rastertocapt filtrini tekshirish
echo -e "${YELLOW}[4/7] Filtr va PPD fayllarini tekshirish...${NC}"
FILTER="/usr/lib/cups/filter/rastertocapt"
if [ ! -f "$FILTER" ]; then
    if [ -f "/home/cail/captdriver/src/rastertocapt" ]; then
        cp /home/cail/captdriver/src/rastertocapt "$FILTER"
    elif [ -f "$(pwd)/captdriver/src/rastertocapt" ]; then
        cp "$(pwd)/captdriver/src/rastertocapt" "$FILTER"
    fi
fi
chmod 755 "$FILTER" 2>/dev/null || true

# PPD faylini to'g'irlash
PPD_SRC=""
if [ -f "/home/cail/captdriver/ppd/CanonLBP-3010-3018-3050.ppd" ]; then
    PPD_SRC="/home/cail/captdriver/ppd/CanonLBP-3010-3018-3050.ppd"
elif [ -f "/usr/share/cups/model/captdriver/CanonLBP-3010-3018-3050.ppd" ]; then
    PPD_SRC="/usr/share/cups/model/captdriver/CanonLBP-3010-3018-3050.ppd"
fi

if [ -n "$PPD_SRC" ]; then
    cp "$PPD_SRC" "/etc/cups/ppd/${PRINTER_NAME}.ppd"
    sed -i 's/^\*cupsManualCopies: False/*cupsManualCopies: True/' "/etc/cups/ppd/${PRINTER_NAME}.ppd"
    chmod 644 "/etc/cups/ppd/${PRINTER_NAME}.ppd"
    echo -e "${GREEN}   PPD to'g'rilandi: $PPD_SRC -> /etc/cups/ppd/${PRINTER_NAME}.ppd${NC}"
fi

# 5. CUPS printer navbatini yangilash
echo -e "${YELLOW}[5/7] CUPS printerni qayta ro'yxatdan o'tkazish...${NC}"
URI=$(lpinfo -v 2>/dev/null | awk '/usb:\/\/Canon/ {print $2; exit}')
if [ -z "$URI" ]; then
    URI="usb://Canon/LBP3010/LBP3018/LBP3050?serial=0000A3A73B3K"
fi

lpadmin -p "$PRINTER_NAME" -v "$URI" -P "/etc/cups/ppd/${PRINTER_NAME}.ppd" \
    -o PageSize=A4 -o cupsManualCopies=True \
    -R usb-unidir-default \
    -o usb-no-reattach-default=true \
    -o printer-error-policy=retry-job

# 6. CUPS xizmatini qayta ishga tushirish
echo -e "${YELLOW}[6/7] CUPS servisi qayta ishga tushirilmoqda...${NC}"
systemctl restart cups
sleep 2
cupsenable "$PRINTER_NAME"
cupsaccept "$PRINTER_NAME"

echo -e "${BLUE}=======================================================${NC}"
echo -e "${GREEN}  ✅ BARCHA SOZLAMALAR MUVAFFAQIYATLI QO'LLANDI!        ${NC}"
echo -e "${BLUE}=======================================================${NC}"
echo -e ""
echo -e "${YELLOW}MUHIM: Printer ichki xotirasi (buffer) tozalanadi:${NC}"
echo -e "1. Canon LBP3010 printerining quvvat (Power) tugmasini bosing va O'CHIRING."
echo -e "2. 5 soniya kuting."
echo -e "3. Qayta YOQING (printer motori aylanib tayyor bo'ladi)."
echo -e ""
echo -e "Shundan so'ng sinab ko'rish buyrug'i:"
echo -e "   ${GREEN}lp -d Canon-LBP3010 /usr/share/cups/data/default-testpage.pdf${NC}"
