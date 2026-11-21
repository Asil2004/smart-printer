# Smart Printchi — Ikki Rejimli Printer Arxitekturasi va To'liq Qo'llanma

**Muallif / Loyiha rahbari:** Ravshanov Muhammad Ali  
**Holat:** Ishchi va sinovdan o'tgan (Canon LBP3010 A4 Lazer + XP-58 Termal Chek)  
**Sana:** 2026-11-21  

---

## 1. Tizim Arxitekturasi

Smart Printchi tizimi ikkita apparat printeri bilan parallel ishlaydi:

```
                  ┌────────────────────────────────────────┐
                  │          Render.com Bulut Server       │
                  │   (Flask + Web UI + To'lov tizimlari)  │
                  └───────────────────┬────────────────────┘
                                      │  Heartbeat & Job Queue
                                      ▼
                  ┌────────────────────────────────────────┐
                  │       Raspberry Pi Kiosk Agent         │
                  │             (pi_agent.py)              │
                  └──────┬──────────────────────────┬──────┘
                         │                          │
        (A4 Lazer Hujjatlar)              (Tezkor Chek / Dev)
                         ▼                          ▼
        ┌────────────────────────────────┐   ┌───────────────────────────────┐
        │       Canon LBP3010            │   │      XP-58 Termal Chek        │
        │   CUPS + mounaiban/captdriver  │   │  To'g'ridan-to'g'ri ESC/POS   │
        │      (A4 oq-qora, 600 dpi)     │   │      (/dev/usb/lp0 porti)     │
        └────────────────────────────────┘   └───────────────────────────────┘
```

---

## 2. Hal Qilingan Muammolar va Maxsus Sozlamalar

### A. Canon LBP3010 "Rendering completed" va "Pages 0/0/0/0" qotishi
* **Muammo:** Canon CAPT printerlari yopiq protokolda ishlaydi. 2017-yilgi eski `agalakhov/captdriver` drayverida sahifa holatini so'rash sikli qotib qolardi (`pages 0/0/0/0 loop`).
* **Yechim:** Zamonaviy va tuzatilgan **`mounaiban/captdriver`** forki o'rnatildi.
* **CUPS USB Quirk:** `/usr/share/cups/usb/org.cups.usb-quirks` fayliga quyidagi qoida yozildi:
  ```text
  0x04a9 0x26da no-reattach
  ```
  *(Eslatma: `unidir` qo'yilmasligi shart, chunki `rastertocapt` printerdan 6 baytli tasdiq javobini kutadi).*

### B. XP-58 va Canon USB Konflikti (Kernel `usblp`)
* **Muammo:** XP-58 ulanganda kernel `usblp` modulini yuklaydi. Bu modul esa Canon portini ham band qilib, CUPS libusb-ga ruxsat bermasdi.
* **Yechim:** Maxsus udev qoidasi (`/etc/udev/rules.d/99-canon-lbp-quirk.rules`) orqali `usblp` moduli faqat Canon (`04a9:26da`) dan ajratiladi (unbind). XP-58 esa `/dev/usb/lp0` da to'siqsiz ishlayveradi.

### C. Fayllar ruxsati (`[Errno 13] Permission denied`)
* **Muammo:** `/tmp` papkasida oldin `sudo` bilan yaratilgan fayllar oddiy `cail` foydalanuvchisiga ruxsat bermay xato bergan.
* **Yechim:** `pi_agent.py` barcha vaqtincha fayllarni foydalanuvchining shaxsiy `~/.smart_printchi_spool/` papkasiga xavfsiz yuklaydi va eski keshni avtomatik tozalaydi.

---

## 3. Web UI da Printer Tanlash Imkoniyati
* Sozlamalar oynasida `🖨️ Canon LBP3010 (A4 Lazer)` va `🧾 XP-58 (58mm Chek)` tugmalari mavjud.
* Chatda `xp58`, `chek`, `canon`, `lazer` buyruqlari printerlarni avtomatik almashtiradi.
* Test buyruqlari: Chatga `test` yoki `sinov` deb yozilsa, darhol to'lovsiz sinov cheki chiqariladi.

---

## 4. Raspberry Pi da Tizimni Qayta Tiklash (Tezkor Buyruqlar)

Agar tizim qayta o'rnatilsa yoki yangi Raspberry Pi ga ko'chirilsa:

```bash
# 1. Loyihani yuklab olish
cd ~
git clone https://github.com/Asil2004/smart-printer.git smart-printchi
cd smart-printchi

# 2. Canon drayveri va sozlamalarini 1 ta buyruq bilan o'rnatish
sudo bash fix_canon_lbp3010.sh

# 3. Raspberry Pi agentini ishga tushirish
python3 pi_agent.py
```

---

## 5. Agentni Avtomatik Ishga Tushirish (Systemd Service)

Raspberry Pi har gal yoqilganda agent o'zi fonda ishlashi uchun:

```bash
sudo bash -c 'cat << EOF > /etc/systemd/system/smart-printchi.service
[Unit]
Description=Smart Printchi Kiosk Agent
After=network.target cups.service

[Service]
Type=simple
User=cail
WorkingDirectory=/home/cail/smart-printchi
ExecStart=/usr/bin/python3 /home/cail/smart-printchi/pi_agent.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF'

sudo systemctl daemon-reload
sudo systemctl enable smart-printchi.service
sudo systemctl start smart-printchi.service
```

Holatini tekshirish:
```bash
sudo systemctl status smart-printchi.service
```
