# AGENT_NOTES — Claude ↔ Antigravity hamkorlik jurnali

Bu fayl ikki agent (Claude va Antigravity) bir loyihada to'qnashmasdan ishlashi uchun.
**Qoida:** ishni boshlashdan oldin shu faylni o'qing, tugatgach o'z bo'limingizga qisqa yozing.
Bir faylni ikki agent bir vaqtda tahrirlamasin — "Hozir kim nima ustida" jadvalini yangilang.

## Hozir kim nima ustida

| Agent        | Fayl(lar)                                  | Holat        |
|--------------|--------------------------------------------|--------------|
| Antigravity  | `prezentatsiya.html`, `Smart_Printchi_Prezentatsiya.pptx` | Davom etmoqda (Claude tegmaydi) |
| Claude       | `public/index.html`, `public/styles.css` (yangi), `public/app.js`, `public/config.js`, `templates/index.html`, `app.py`, `payments.py`, `start_demo.bat` (yangi), `DESIGN.md` (yangi) | Tugadi — 2026-11-15 |

> **2026-11-26, Claude:** `pi_agent.py`, `app.py` (agent API, zaxira, test_print), `public/panel.html` (yangi),
> `printchi-agent.service` (yangi) o'zgardi — tafsilot `HISOBOT.md` da. Promokod `feat/control-panel` branchida
> (`app.py`, `public/app.js`, `public/index.html`, `public/styles.css`). Antigravity: shu fayllarni o'zgartirishdan oldin o'qing.

> Antigravity: `public/app.js` dagi to'lov oynasi mantig'i o'zgardi (pastga qarang).
> AI Writer olib tashlandi (pastda). HTML'dagi "To'lov Qildim — Chop Etilsin!" tugma matnini "To'lov qildim" ga o'zgartirish tavsiya etiladi.

---

## Claude — 2026-11-26: Admin panel (logo bosilganda) — shablonlar va promokodlar
Branch: `feat/admin-panel` (`origin/main` asosida).
- **Logo (`#brandBtn`) bir marta bosilsa admin panel ochiladi** (oldin 5 marta bosish edi). Parol (`ADMIN_TOKEN`)
  so'raladi, `localStorage` da saqlanadi, "Chiqish" bilan o'chadi. Ikki bo'lim: Shablonlar | Promokodlar.
- **Shablonlar har qanday formatda yuklanadi**: PDF/DOCX/PNG/JPG o'zicha; boshqa rasmlar → PNG; DOC/ODT/RTF/TXT/
  XLSX/PPTX… → PDF (LibreOffice). Sahifalar soni endi DOCX uchun ham to'g'ri.
- **Har shablon rasm sifatida ko'rinadi**: `catalog.py` 1-sahifani JPG ga chizadi (`pypdfium2`; DOCX — LibreOffice,
  u yo'q joyda matn varaqqa chiziladi). `GET /api/templates/<id>/preview.jpg`, `/api/templates` da `preview` maydoni.
  Rasm admin panelda ham, mijozning "Tayyor shablonlar" ro'yxatida ham. Server yonganda fonda oldindan tayyorlanadi.
- **Promokodlar admin paneldan**: `GET/POST /api/admin/promos`, `DELETE /api/admin/promos/<code>` (X-Admin-Token).
  Kod (bo'sh bo'lsa avtomatik), chegirma %, necha marta, necha kun, izoh. `data/promo_codes.json` da.
  `PROMO_CODES` env ham ishlayveradi (panelda "server" belgisi bilan, o'chirib bo'lmaydi). Muddat tekshiruvi qo'shildi.
- **Render diski vaqtinchalik** — shuning uchun admin yuklagan shablonlar va promokodlar ham Pi'ga zaxiralanadi:
  `GET /api/agent/catalog`, `/api/agent/catalog/file/<id>`, `POST /api/agent/catalog/restore`;
  `pi_agent.py` → `sync_catalog()` (`~/.smart_printchi_backup/catalog.json` + `templates/`).
- `requirements.txt`: `pypdfium2`. Pi'da agentni yangilash kerak (`git pull` + `systemctl restart printchi-agent`).
- Sinov (lokal, scratch nusxada): 401 parolsiz · PDF 2 bet/WEBP yuklandi va rasmi chiqdi · TXT/ODT LibreOffice'siz aniq xato ·
  promokod yaratish/takror/50% qo'llash/o'chirish · katalog zaxira → tiklash (idempotent) · brauzerda kompyuter va telefon.

- **Login + parol** (yangilanish): `POST /api/admin/login` {login, password} → 30 kunlik imzolangan sessiya kaliti
  (`s1.<muddat>.<hmac>`), `X-Admin-Token` sifatida yuboriladi. Env: `ADMIN_LOGIN` (standart `admin`), `ADMIN_PASSWORD`
  (bo'lmasa `ADMIN_TOKEN`). Parol almashsa barcha sessiyalar bekor bo'ladi. 15 daqiqada 8 xato urinishdan keyin 429.
  Eski `ADMIN_TOKEN` ham ishlayveradi (`panel.html`, API).
- **PWA**: `public/manifest.webmanifest`, `public/sw.js` (sahifa: avval tarmoq, oflaynda kesh; `/api/` keshlanmaydi),
  `public/icons/`, sarlavhada "o'rnatish" tugmasi (`beforeinstallprompt`). Headless Chrome'da: SW faol,
  installability xatosi yo'q, oflaynda ochiladi. `app.py` da `.js`/`.webmanifest` MIME turlari aniq berildi.

---

## Claude — 2026-11-15: Yangi UI "Bento + Chat" (Asilbek qarori: bundan buyon shu UI)
⚠️ **Antigravity: frontendni o'zgartirishdan oldin `DESIGN.md` ni o'qing.** Eski Tailwind/SweetAlert UI butunlay almashtirildi.
- `public/index.html`, `public/styles.css`, `public/app.js` qaytadan yozildi (tashqi kutubxonalarsiz, faqat DM Sans shrifti).
  Chat yordamchi + bento kartochkalar + to'q "Jami" paneli + yozma buyruqlar ("2 nusxa, 5-8 bet, albom").
- `public/config.js`: `localhost`/Pi IP da ochilganda API endi o'sha serverning o'zi (oldin Cloudflare tunnelga ketardi).
- `app.py`: `/` endi `public/index.html` ni beradi (bitta manba); `/api/inspect-file` DOCX ni buyurtma bilan bir xil
  aniq sanaydi; `DEMO_AUTO_CONFIRM` (faqat lokal demo).
- `payments.py`: `DEMO_AUTO_CONFIRM` — demo rejimida Telegram o'chiq.
- `start_demo.bat`: Windows'da lokal demo, `http://localhost:5000`.
- Sinov (Playwright + CUPS emulator): fayl → chip → yozma buyruq → to'lov → "Hujjat tayyor!", shablon oqimi, admin,
  DOCX sanash, kompyuter ko‘rinishi — 16/16 ✅, JS xatosiz.
- Eslatma: Antigravity qo'shgan `test_xp58_*.py` va `.bat` o'zgarishlariga tegilmadi.

---

## Claude — 2026-11-09: Canon LBP3010 drayveri to'liq sinovi
captdriver (agalakhov, commit 175f8ff, v0.1.4.1) yuklab yig'ildi, CUPS + LBP3010 CAPT protokoli emulatori
(`tools/captsim.py` — CUPS backend) bilan butun zanjir sinaldi: sayt → server → LibreOffice → CUPS →
Ghostscript → rastertocapt → CAPT → "printer". Drayver LBP3010 ni taniydi, A4 600 dpi sahifalar uzatiladi.

### Topilgan va tuzatilgan xatolar
| # | Joy | Xato | Natija | Tuzatish |
|---|---|---|---|---|
| 1 | `setup_canon_lbp3010.sh` | PPD yig'ilmasdi (`make ppd` yo'q) va `*LBP3010*` deb qidirilardi (asl nomi `CanonLBP-3010-3018-3050.ppd`) | printer **raw** qo'shilib, hech narsa chop etmasdi | skript qayta yozildi |
| 2 | skript | `make install` filtrni `/usr/local/bin` ga qo'yadi | har ishda "filter failed" | `$(cups-config --serverbin)/filter` ga o'rnatiladi |
| 3 | drayver PPD | `cupsManualCopies: False`, drayver nusxa qilmaydi | **2 nusxa to'langanda 1 chiqardi** | PPD `True` ga o'zgartiriladi |
| 4 | skript | USB manzil qo'lda yozilgan | navbat "printer kutilmoqda" da qolishi mumkin | `lpinfo -v` dan olinadi, topilmasa aniq xato |
| 5 | skript | xato siyosati `stop-printer` | bitta xato butun navbatni to'xtatardi | `printer-error-policy=retry-job` |
| 6 | `app.py` | `lp` navbatga qo'yishi bilanoq **PRINTED** | qog'oz/USB yo'q bo'lsa ham "Hujjat chiqdi!" | `cups_jobs.py`: IPP orqali ish holati kuzatiladi |
| 7 | `app.py` | DOCX sahifalari `docProps/app.xml` dan | LibreOffice/Google Docs fayllarida **narx kam** | DOCX → PDF aylantirib sanaladi |
| 8 | `app.py` | LibreOffice umumiy profil | bir vaqtda 2 DOCX → biri xato | har konvertatsiyaga alohida profil, 3 daq timeout, kesh |
| 9 | `payments.py` | qayta yonishda PRINTING → PAID, lekin hech kim chop etmasdi | to'langan buyurtma osilib qolardi | CUPS ishi kuzatuvi davom etadi / qayta navbatga |

### Yangi xatti-harakat
- Ish 60 s + 10 s/bet ichida tugamasa: buyurtma PRINTING + izoh, adminga 🟠 Telegram, saytda printer
  "band", yangi to'lov qabul qilinmaydi (503). Qog'oz solinsa ish o'zi davom etadi → PRINTED.
- 20 daqiqada tugamasa: CUPS ishi bekor qilinadi, FAILED, adminga 🔁 tugma.
- Drayver qog'oz tugaganini CUPS'ga xabar qilmaydi (faqat chiroqni miltillatadi) — shuning uchun kuzatuv vaqt bo'yicha.

### Sinov natijalari (hammasi ✅)
PDF 5 bet · 2-3 betlar × 2 nusxa (4 bet) · DOCX 2 bet · JPG · albom · shablon · qog'oz tugadi→server qayta yondi→
qog'oz solindi · qog'oz solinmadi→FAILED→qayta chop etish · USB uzildi→ulandi.

### Pi'da haqiqiy printer bilan qilish kerak
`sudo bash setup_canon_lbp3010.sh --test` → sinov sahifasi chiqishi. Emulator x86 da sinaldi; Pi (ARM) da
drayver xuddi shu manbadan yig'iladi. Qog'oz tugashi va tiqilishini haqiqiy printerda bir marta sinab ko'ring.

---

## Claude — 2026-11-09: AI Writer olib tashlandi (Asilbek qarori)
Saytda faqat **Chop etish** va **Tayyor shablonlar** qoldi.
- `public/index.html`, `templates/index.html`: "AI Writer" tabi va bo'limi o'chirildi, sarlavha matni yangilandi.
- `public/app.js`: AI kodi (Gemini chaqiruvi, Word yaratish, AI to'lov) o'chirildi.
- `public/config.js`: **ochiq Gemini API kaliti olib tashlandi.** Kalit avval GitHub/Netlify'da ochiq turgani uchun
  uni AI Studio'da baribir o'chirib tashlash (revoke) kerak — git tarixida qoladi.
- `app.py`: `/api/ai/*` endpointlari va `ai_writer` importi o'chirildi; `/api/order/create` faqat `file` va `template`.
- `requirements.txt`: `google-genai` olib tashlandi. `.env.example`: `GEMINI_API_KEY` olib tashlandi.
- `ai_writer.py` fayli endi hech qayerda ishlatilmaydi — Asilbek xohlasa o'chirishi mumkin.
- ⚠️ Antigravity: `prezentatsiya.html` / `.pptx` da AI Writer haqida slayd yoki gap bo'lsa, olib tashlang.

---

## Claude — 2026-11-09: Server tomonida to'lov tekshiruvi

### Asosiy qoida
Printer **faqat to'lovi tasdiqlangan buyurtmani** chop etadi. Narx **serverda** hisoblanadi
(mijoz yuborgan `amount` e'tiborga olinmaydi).

### Oqim
```
Mijoz fayl/shablon/AI hujjat tanlaydi
  → POST /api/order/create            (server sahifalarni sanaydi, narxni hisoblaydi) → PENDING
  → mijoz kartaga o'tkazadi, "To'ladim" bosadi
  → POST /api/order/<id>/claim         → CLAIMED, adminga Telegram: [✅ Tasdiqlash] [❌ Rad etish]
  → admin ✅ bosadi (yoki Click/Payme webhook, yoki Admin API)
  → PAID → PRINTING → PRINTED  (yoki FAILED → adminga [🔁 Qayta chop etish])
Sayt har 2 soniyada GET /api/order/status/<id> ni so'raydi.
```

### Yangi / o'zgargan endpointlar
| Endpoint | Izoh |
|---|---|
| `POST /api/order/create` | `source=file` (multipart file) · `source=template` (`template_id`) |
| `POST /api/order/<id>/claim` | Mijoz "To'ladim" dedi. Chop ETMAYDI |
| `GET /api/order/status/<id>` | `PENDING/CLAIMED/PAID/PRINTING/PRINTED/FAILED/REJECTED/EXPIRED/CANCELLED` |
| `POST /api/admin/orders/<id>/confirm\|reject\|reprint` | `X-Admin-Token` sarlavhasi kerak |
| `GET /api/orders` | Endi admin-only |
| `POST /api/payments/click/prepare\|complete` | MD5 `sign_string` + summa tekshiriladi (`CLICK_SECRET_KEY`) |
| `POST /api/payments/payme` | Basic auth + to'liq Merchant API: Check/Create/Perform/Cancel/CheckTransaction/GetStatement |
| `/api/print`, `/api/templates/print` | Endi `402` — faqat admin token bilan ishlaydi |
| `/api/admin/templates/upload\|delete` | `X-Admin-Token` kerak (frontend parol so'raydi) |
| `GET /api/health` | `payment_verification`, `confirm_via` maydonlari qo'shildi |

### Fayllar
- `payments.py` — buyurtma holati, `data/orders.json` ga saqlash (restartda yo'qolmaydi), Telegram long-polling
  (port ochish shart emas), Click/Payme tekshiruvlari.
- `app.py` — buyurtma endpointlari, umumiy `_execute_print()`, faol buyurtma fayllarini tozalash oqimi o'chirmaydi.
- `public/app.js` — `openPaymentModal(source)` endi fayl/shablon/AI uchun yagona; summa serverdan olinadi;
  "To'ladim" → `claim` + kutish; holatlar bo'yicha xabarlar; admin parol `localStorage`da.
- Eski xato tuzatildi: Pi'dan ochilgan sahifada `app.js`/`config.js` 404 berardi (`static_url_path=""`).

### Testlar (o'tdi)
Bypass 402 · soxta Click imzosi -1 · noto'g'ri summa -2/-31001 · Payme auth -32504 · begona Telegram chatdan
tasdiq rad etiladi · ikki marta tasdiq idempotent · brauzerda to'liq oqim (Playwright): 3 sahifali PDF → 1500 so'm →
CLAIMED → admin tasdig'i → "Hujjat Chiqdi!" · shablon rad etilishi → mijozga xabar.

### Raspberry Pi'da qilish kerak (Asilbek)
1. `.env` ga qo'shing: `ADMIN_TOKEN`, `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (namuna `.env.example` da).
   Telegram uchun **alohida bot** oching — boshqa dastur shu tokenni ishlatsa 409 xato bo'ladi.
2. Netlify/GitHub Pages ga yangi `public/app.js` ni deploy qiling va Pi'da serverni qayta ishga tushiring.
   Ikkalasi birga yangilanishi kerak: eski sayt `/api/print` ga to'g'ridan-to'g'ri murojaat qiladi va endi 402 oladi.
3. Haqiqiy Canon LBP3010 bilan sinov: shablon (DOCX → PDF, LibreOffice) chop etilishi.

### Hali ochiq
- Kichik: `printer_detector.py` da `"low" in alert_str` juda keng.

---

## Claude — 2026-11-08
`app.py`: `config` import (Telegram NameError), `/api/inspect-file` sahifa soni doim 1 edi (narx noto'g'ri),
shablon DOCX → PDF konvertatsiyasi, takroriy `recent_orders` olib tashlandi.
