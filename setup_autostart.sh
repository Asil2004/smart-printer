#!/bin/bash
# ==============================================================================
# Smart Web-Printchi - Avtomatik Ishga Tushish (Autostart on Boot) Skripti
# Ushbu skript Raspberry Pi har safar tokka ulanganda server va ngrok ni
# avtomatik yoqiladigan (systemd service) qilib sozlaydi.
# ==============================================================================

set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
CURRENT_USER="$(id -un)"

if [ "$CURRENT_USER" = "root" ]; then
    REAL_USER="${SUDO_USER:-cail}"
else
    REAL_USER="$CURRENT_USER"
fi

USER_HOME=$(getent passwd "$REAL_USER" | cut -d: -f6)
PYTHON_BIN=$(which python3)
NGROK_BIN=$(which ngrok || echo "/usr/bin/ngrok")

echo "--------------------------------------------------------"
echo "  [+] AVTOSTART SERVISLARI O'RNATILMOQDA..."
echo "  Foydalanuvchi: $REAL_USER"
echo "  Loyiha papkasi: $DIR"
echo "  Python: $PYTHON_BIN"
echo "  Ngrok: $NGROK_BIN"
echo "--------------------------------------------------------"

# 1. smart-printer.service yaratish
cat <<EOF | sudo tee /etc/systemd/system/smart-printer.service > /dev/null
[Unit]
Description=Smart Web-Printchi Backend
After=network-online.target cups.service
Wants=network-online.target cups.service

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$DIR
Environment="HOME=$USER_HOME"
Environment="PYTHONUNBUFFERED=1"
ExecStart=$PYTHON_BIN $DIR/app.py
Restart=always
RestartSec=5
StandardOutput=append:$DIR/server.log
StandardError=append:$DIR/server.log

[Install]
WantedBy=multi-user.target
EOF

# 2. smart-ngrok.service yaratish
cat <<EOF | sudo tee /etc/systemd/system/smart-ngrok.service > /dev/null
[Unit]
Description=Smart Web-Printchi Ngrok Tunnel
After=network-online.target smart-printer.service
Wants=network-online.target smart-printer.service

[Service]
Type=simple
User=$REAL_USER
WorkingDirectory=$DIR
Environment="HOME=$USER_HOME"
ExecStart=$NGROK_BIN http --url=snazzy-chosen-lyricism.ngrok-free.dev 5000
Restart=always
RestartSec=5
StandardOutput=append:$DIR/ngrok.log
StandardError=append:$DIR/ngrok.log

[Install]
WantedBy=multi-user.target
EOF

# 3. Servislarni yangilash va faollashtirish
echo "[+] Systemd servislar ro'yxati yangilanmoqda..."
sudo systemctl daemon-reload

echo "[+] smart-printer servisi yoqilmoqda..."
sudo systemctl enable smart-printer.service
sudo systemctl restart smart-printer.service

echo "[+] smart-ngrok servisi yoqilmoqda..."
sudo systemctl enable smart-ngrok.service
sudo systemctl restart smart-ngrok.service

echo ""
echo "========================================================"
echo "   BARCHASI MUVAFFAQIYATLI SOZLANDI VA ISHGA TUSHDI!    "
echo "   Endi Raspberry Pi har safar tokka ulanganda:         "
echo "   - Server va Ngrok avtomatik o'zi yoqiladi!          "
echo "   - Hech qanday terminal ochish shart emas!           "
echo "   Saytingiz: https://smart-printx.netlify.app         "
echo "========================================================"
