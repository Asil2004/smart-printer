#!/bin/bash
# =============================================================================
# Canon LBP3010 (CAPT) — Raspberry Pi uchun o'rnatish skripti
# =============================================================================
# Ochiq manbali captdriver (rastertocapt) ni yig'adi, CUPS ga to'g'ri o'rnatadi
# va printerni USB orqali qo'shadi.
#
#   sudo bash setup_canon_lbp3010.sh            # o'rnatish
#   sudo bash setup_canon_lbp3010.sh --test     # o'rnatish + sinov sahifasi
#
# Muhit o'zgaruvchilari:
#   PRINTER_URI=...   USB manzilni qo'lda berish (odatda avtomatik topiladi)
#   SKIP_APT=1        paketlarni o'rnatishni o'tkazib yuborish
#
# Eski skriptdagi xatolar (2026-11-09 da sinovda topilgan va tuzatilgan):
#   1. PPD fayl yig'ilmasdi ("make ppd" yo'q) va noto'g'ri nom bilan qidirilardi
#      (*LBP3010* — haqiqiy nomi CanonLBP-3010-3018-3050.ppd) → printer "raw"
#      rejimda qo'shilib, LBP3010 hech narsa chop etmasdi.
#   2. "make install" filtrni /usr/local/bin ga qo'yadi, CUPS esa uni
#      /usr/lib/cups/filter dan qidiradi → har ishda "filter failed".
#   3. PPD da cupsManualCopies: False, lekin drayver nusxalarni qilmaydi →
#      2 nusxa to'langanda 1 nusxa chiqardi. True ga o'zgartiriladi.
#   4. USB manzil qo'lda yozilgan edi (usb://Canon/LBP3010) — haqiqiysi
#      lpinfo -v dan olinadi.
#   5. Xato siyosati "stop-printer" edi: bitta xato butun navbatni to'xtatardi.
# =============================================================================

set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
ok()   { echo -e "${GREEN}$*${NC}"; }
warn() { echo -e "${YELLOW}$*${NC}"; }
die()  { echo -e "${RED}[XATO] $*${NC}"; exit 1; }

PRINTER_NAME="Canon-LBP3010"
CAPT_REPO="https://github.com/agalakhov/captdriver.git"
CAPT_COMMIT="175f8ff4464591feb67728c7752ac752c7b48d43"   # 0.1.4.1 — sinovdan o'tgan versiya
PPD_NAME="CanonLBP-3010-3018-3050.ppd"
PPD_DIR="/usr/share/cups/model/captdriver"
WORK_DIR="/tmp/captdriver_build"
RUN_TEST=0
[ "${1:-}" = "--test" ] && RUN_TEST=1

echo -e "${BLUE}=======================================================${NC}"
echo -e "${YELLOW}  🖨️  CANON LBP3010 — RASPBERRY PI O'RNATISH             ${NC}"
echo -e "${BLUE}=======================================================${NC}"

[ "$EUID" -eq 0 ] || die "Skriptni sudo bilan ishga tushiring: sudo bash $0"

# ── 1. Paketlar ──────────────────────────────────────────────────────────────
ok "[1/6] Kerakli paketlar..."
if [ "${SKIP_APT:-0}" != "1" ]; then
    apt-get update -y
    apt-get install -y cups cups-client cups-filters ghostscript cups-ppdc \
        libcups2-dev libcupsimage2-dev build-essential git autoconf automake libtool
    # DOCX → PDF uchun (Word fayllar va shablonlar)
    apt-get install -y --no-install-recommends libreoffice-writer-nogui \
        || apt-get install -y --no-install-recommends libreoffice-writer \
        || warn "LibreOffice o'rnatilmadi — DOCX fayllar chop etilmaydi!"
fi

if [ -d /run/systemd/system ]; then   # systemd haqiqatan ishlayaptimi (Raspberry Pi OS — ha)
    systemctl enable cups
    systemctl restart cups
else
    pgrep -x cupsd >/dev/null || cupsd
fi
sleep 2

# ── 2. captdriver ni yig'ish ─────────────────────────────────────────────────
ok "[2/6] captdriver (rastertocapt) ni yig'ish..."
rm -rf "$WORK_DIR"
git clone --quiet "$CAPT_REPO" "$WORK_DIR" || die "GitHub dan yuklab bo'lmadi — internetni tekshiring"
cd "$WORK_DIR"
git checkout --quiet "$CAPT_COMMIT"
autoreconf -i >/dev/null 2>&1
./configure >/dev/null
make -s
make -s ppd

# ── 3. Filtr va PPD ni CUPS ga o'rnatish ─────────────────────────────────────
ok "[3/6] Filtr va PPD ni o'rnatish..."
SERVERBIN="$(cups-config --serverbin 2>/dev/null || echo /usr/lib/cups)"
install -m 0755 src/rastertocapt "$SERVERBIN/filter/rastertocapt"
mkdir -p "$PPD_DIR"
install -m 0644 "ppd/$PPD_NAME" "$PPD_DIR/$PPD_NAME"
# Drayver nusxalarni o'zi qilmaydi — CUPS qilsin
sed -i 's/^\*cupsManualCopies: False/*cupsManualCopies: True/' "$PPD_DIR/$PPD_NAME"
grep -q '^\*cupsManualCopies: True' "$PPD_DIR/$PPD_NAME" || die "PPD ni moslab bo'lmadi"
ok "   filtr: $SERVERBIN/filter/rastertocapt"
ok "   PPD:   $PPD_DIR/$PPD_NAME"

# ── 4. USB manzilni topish ───────────────────────────────────────────────────
ok "[4/6] Canon LBP3010 USB orqali qidirilmoqda..."
CURRENT_USER="${SUDO_USER:-cail}"
usermod -aG lpadmin "$CURRENT_USER" 2>/dev/null || true
usermod -aG lp "$CURRENT_USER" 2>/dev/null || true

URI="${PRINTER_URI:-}"
if [ -z "$URI" ]; then
    for i in 1 2 3 4 5; do
        URI="$(lpinfo -v 2>/dev/null | awk '/usb:\/\/Canon/ {print $2; exit}')"
        [ -n "$URI" ] && break
        sleep 2
    done
fi
if [ -z "$URI" ]; then
    lsusb 2>/dev/null | grep -i "04a9" || true
    die "Canon LBP3010 topilmadi. Printerni USB ga ulang, YOQING va skriptni qayta ishga tushiring.
       (Qo'lda: PRINTER_URI='usb://Canon/LBP3010/LBP3018/LBP3050?serial=...' sudo -E bash $0)"
fi
ok "   manzil: $URI"

# ── 5. Printerni CUPS ga qo'shish ────────────────────────────────────────────
ok "[5/6] CUPS ga '$PRINTER_NAME' qo'shilmoqda..."
lpadmin -x "$PRINTER_NAME" 2>/dev/null || true
lpadmin -p "$PRINTER_NAME" -E -v "$URI" -P "$PPD_DIR/$PPD_NAME" \
    -D "Canon LBP3010 (Smart Printchi)" -L "Kiosk" \
    -o PageSize=A4 -o printer-error-policy=retry-job
cupsenable "$PRINTER_NAME"
cupsaccept "$PRINTER_NAME"
lpoptions -d "$PRINTER_NAME" >/dev/null

# ── 6. Tekshiruv ─────────────────────────────────────────────────────────────
ok "[6/6] Tekshiruv..."
lpstat -p "$PRINTER_NAME"
grep -q "rastertocapt" "/etc/cups/ppd/$PRINTER_NAME.ppd" || die "Printer drayversiz (raw) qo'shilgan!"

if [ "$RUN_TEST" = "1" ]; then
    TESTFILE="/usr/share/cups/data/testprint"
    [ -f "$TESTFILE" ] || TESTFILE="/usr/share/cups/data/default-testpage.pdf"
    JOB="$(lp -d "$PRINTER_NAME" "$TESTFILE" | awk '{print $4}')"
    ok "   Sinov sahifasi yuborildi: $JOB — printerdan chiqishini kuting (≈20 s)."
    for i in $(seq 1 60); do
        sleep 2
        lpstat -o "$PRINTER_NAME" | grep -q "$JOB" || break
    done
    if lpstat -o "$PRINTER_NAME" | grep -q "$JOB"; then
        warn "   Sinov sahifasi hali navbatda: qog'oz va USB ni tekshiring (lpstat -l -o)."
    else
        ok "   Sinov sahifasi tugadi ✅"
    fi
fi

echo -e "${BLUE}=======================================================${NC}"
echo -e "${GREEN}  CANON LBP3010 SOZLANDI!${NC}"
echo -e "  CUPS nomi: ${YELLOW}$PRINTER_NAME${NC}   Manzil: $URI"
echo -e "  Format: A4, oq-qora lazer, 600 dpi"
echo -e "${BLUE}=======================================================${NC}"
