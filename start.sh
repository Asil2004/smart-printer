#!/bin/bash
# Smart Web-Printchi - Avtomatik Ishga Tushiruvchi Skript

echo "==================================================="
echo "       🖨️ SMART WEB-PRINTCHI ISHGA TUSHMOQDA 🖨️      "
echo "==================================================="

# Loyiha papkasiga o'tish
cd "$(dirname "$0")"

# Eski jarayonlarni tozalash (agar qolib ketgan bo'lsa)
pkill -f "python3 app.py" 2>/dev/null
pkill -f "ngrok http" 2>/dev/null
sleep 1

# 1. Flask serverini fonda ishga tushirish
nohup python3 app.py > server.log 2>&1 &
echo "[+] 1. Python print-serveri orqa fonda yoqildi."
sleep 2

# 2. Ngrok doimiy tunnelini fonda ishga tushirish
nohup ngrok http --url=snazzy-chosen-lyricism.ngrok-free.dev 5000 > ngrok.log 2>&1 &
echo "[+] 2. Ngrok global tuneli orqa fonda yoqildi."
sleep 2

echo ""
echo "==================================================="
echo "   ✅ BARCHASI MUVAFFAQIYATLI ISHGA TUSHDI!        "
echo "   Saytingiz: https://smart-printx.netlify.app     "
echo "   Domen: https://snazzy-chosen-lyricism.ngrok-free.dev"
echo "==================================================="
