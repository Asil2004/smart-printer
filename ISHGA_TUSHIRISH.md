# Smart Printchi — mustaqil ishlatish qo'llanmasi

Bu qo'llanma tizimni Claude yordamisiz ishlatish, tekshirish va tuzatish uchun.

## Tizim qanday ishlaydi

```
Mijoz (telefon) → sayt: https://smart-printer-mo1g.onrender.com
                     │  buyurtma, noyob summa (masalan 2 537 so'm)
                     ▼
Render server  ◄──── Pi agenti har 2 soniyada so'raydi (printchi-agent)
                     │
Mijoz kartaga o'tkazadi → CardXabar Telegram'da "+2 537" deb yozadi
                     │
Pi to'lov kuzatuvchisi xabarni o'qiydi (printchi-payments) → Render tasdiqlaydi
                     │
Pi agenti faylni oladi → CUPS → Canon LBP3010 → qog'oz
```

## Har kuni: hech narsa qilish shart emas

Pi'ni elektrga ulang, Canon'ni yoqing va qog'oz soling. 1–2 daqiqada hammasi o'zi ishga tushadi:

| Xizmat | Vazifasi | O'zi yonadimi |
|---|---|---|
| `cups` | printer navbati | ✅ |
| `printchi-agent` | Render'dan buyurtma olib chop etadi, buyurtmalar zaxirasi | ✅ |
| `printchi-payments` | CardXabar'dan kartaga tushgan pulni o'qiydi | ✅ |

Render (sayt va server) bulutda doim ishlaydi. Pi agenti so'rov yuborib turgani uchun u uxlab qolmaydi.

Telegram'dagi **@SmartPrintchiAdminBot** sizga quyidagilar haqida xabar beradi:

- ✅ to'lov avtomatik tasdiqlandi;
- 💳 pul tushdi, lekin unga mos buyurtma yo'q, siz o'zingiz tekshirasiz;
- ⚠️ to'lov kuzatuvchisi javob bermayapti;
- 🟠 printer kutib qoldi (qog'oz yoki USB).

## Tekshirish

**Boshqaruv paneli:** https://smart-printer-mo1g.onrender.com/panel.html

Panelda server, Pi agenti, Canon holati va navbat ko'rinadi. Sinov sahifasini chop etish uchun avval admin parolni kiriting. Parol Pi'dagi `.env` faylida `ADMIN_TOKEN` qatorida.

**Pi terminalida:**

```bash
systemctl status printchi-agent printchi-payments   # ikkalasi "active (running)" bo'lishi kerak
journalctl -u printchi-agent -f                    # agent jurnali (Ctrl+C — chiqish)
journalctl -u printchi-payments -f                 # to'lov kuzatuvchisi jurnali
lpstat -l -o Canon-LBP3010                          # printer navbati
```

## Muammo bo'lsa

| Belgisi | Sababi | Nima qilish kerak |
|---|---|---|
| Saytda "printer ulanmagan" | Canon o'chiq yoki USB chiqib ketgan | Canon'ni yoqing, kabelni tekshiring. Agent 5 soniyada o'zi topadi |
| Botda 🟠 "printer kutib qoldi" | qog'oz tugagan yoki tiqilgan | Qog'oz soling, ish o'zi davom etadi |
| Printer "disabled" yoki "Paused" | CUPS xato tufayli to'xtagan | `cupsenable Canon-LBP3010` |
| Botda ⚠️ "kuzatuvchi javob bermayapti" | internet yoki Telegram uzildi | `sudo systemctl restart printchi-payments` |
| Kuzatuvchi jurnalida "Telegram seansi yo'q" | Telegram → Devices bo'limida "Printchi" seansi o'chirilgan | Qayta kiring (pastda) |
| Pul tushdi, lekin chop etilmadi | mijoz boshqa summa o'tkazgan | Botdagi ✅ tugmasini bosing yoki paneldan tasdiqlang |
| Hech narsa ishlamayapti | — | `sudo reboot` (Pi qayta yonadi, hammasi o'zi ishga tushadi) |

### Telegram'ga qayta kirish (seans o'chirilgan bo'lsa)

```bash
cd ~/projects/smart-printer-main
venv/bin/python tools/tg_login.py send +998944737627   # Telegram ilovasiga kod keladi
venv/bin/python tools/tg_login.py code 12345            # kelgan kodni yozing
venv/bin/python tools/tg_login.py password 'PAROL'      # agar 2FA paroli so'ralsa
sudo systemctl restart printchi-payments
```

## Sozlamalarni o'zgartirish (Render)

Render → **smart-printer** → **Environment**. Saqlagandan keyin Render serverni o'zi qayta ishga tushiradi.

| Sozlama | Nimani boshqaradi |
|---|---|
| `CARD_AUTO_CONFIRM=1` | kartaga to'lov avtomatik tasdiqlanadi (noyob summa bilan) |
| `CARD_LAST4=2570` | qaysi karta kuzatiladi |
| `DEMO_AUTO_CONFIRM=0` | `1` bo'lsa, to'lov TEKSHIRILMASDAN tasdiqlanadi. Ishda doim `0` turishi kerak |
| `PROMO_CODES=KOD:100:20` | promokodlar: `KOD:chegirma_foizi:limit`, bir nechtasi vergul bilan |
| `ADMIN_TOKEN` | admin paroli (panel va admin tugmalari uchun) |
| `AGENT_TOKEN` | Pi bilan maxfiy kalit. Pi'dagi `~/.config/printchi-agent.env` bilan bir xil bo'lishi kerak |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | admin boti |
| `COLOR_ENABLED`, `THERMAL_ENABLED` | rangli yoki XP-58 printer ulanganda `1` qiling (saytda: `public/config.js` → `FEATURES`) |

**Karta raqamini almashtirish:** `public/config.js` faylida `cardNumber`, `cardHolder` va `cardBank` ni o'zgartiring. Render'da `CARD_LAST4` ni ham almashtiring. Yangi karta @CardXabarBot'ga ulangan bo'lishi kerak.

**Narxlar:** `app.py` faylining boshida (`PRICE_PER_PAGE_BW = 250`). Saytdagi narxlar jadvali `public/index.html` da.

## Kodni yangilash

Render GitHub'dagi `main` branchini avtomatik deploy qiladi:

```bash
cd ~/projects/smart-printer-main
git add -A && git commit -m "o'zgarish tavsifi"
git push origin HEAD:main          # GitHub foydalanuvchi nomi va token so'raladi
```

`pi_agent.py` yoki `tools/payment_watcher.py` o'zgarsa, Pi'da xizmatlarni qayta ishga tushiring:

```bash
sudo systemctl restart printchi-agent printchi-payments
```

## Maxfiy fayllar (Pi'da, git'ga tushmaydi)

| Fayl | Ichida |
|---|---|
| `~/projects/smart-printer-main/.env` | `ADMIN_TOKEN` va boshqalar |
| `~/.config/printchi-agent.env` | `AGENT_TOKEN` |
| `~/.config/printchi-tg/` | Telegram API kalitlari, seans, admin bot tokeni |
| `~/.smart_printchi_backup/` | buyurtmalar zaxirasi |

`~/.config/printchi-tg/printchi.session` fayli Telegram akkauntingizga to'liq kirish beradi. Pi parolini hech kimga bermang.
