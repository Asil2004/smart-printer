# Smart Printchi — UI qoidalari ("Bento + Chat")

**2026-11-15 dan boshlab loyihaning yagona UI uslubi shu.** Yangi ekran yoki o'zgarish shu qoidalarga mos bo'lsin.
Asos: dizayn kanvasidagi 11-variant (03 "Bento" + 09 "Chat" birlashmasi).

## Fayllar
| Fayl | Vazifasi |
|---|---|
| `public/index.html` | Yagona sahifa (Netlify/GitHub Pages ham, Pi'dagi Flask `/` ham shuni beradi) |
| `public/styles.css` | Dizayn tokenlari va barcha komponentlar (Tailwind/SweetAlert/FontAwesome **yo'q**) |
| `public/app.js` | Holat, chat tahlili, to'lov oqimi, shablonlar, admin |
| `public/config.js` | Backend manzili (statik xostingda tunnel URL), karta/Click/Payme sozlamalari |
| `templates/index.html` | `public/index.html` nusxasi (Flask endi uni ishlatmaydi — eski havolalar uchun) |

## Tokenlar (`:root` da)
- Fon `--bg #ECEEE8`, kartochka `--tile #FFFFFF`, to'q panel/matn `--ink #1B1F23`, izoh `--muted #5B6168`
- Urg'u `--accent #C6F36B` — **faqat to'q matn bilan** (oq matn kontrasti yetmaydi)
- Holat ranglari: `--ok`, `--warn`, `--err` (+ `-bg`)
- Radiuslar: kartochka 20px, tugma 12px, chip/pill 999px. Shrift: DM Sans (bo'lmasa system-ui)

## Tuzilish (yuqoridan pastga)
1. **Sarlavha**: logo + printer holati (yashil/sariq/qizil nuqta + matn) + "Shablonlar →"
2. **Chat**: fayl — o'ng tomonda to'q pufak; yordamchi — chapda oq pufak, oxirgi qatori **qalin xulosa**
   (`barcha 12 bet · kitob · oq-qora · 1 nusxa = 6 000 so'm`). Yordamchi bitta pufakda yangilanadi, spam qilmaydi.
3. **Tez javoblar** (chip): kontekstga qarab 3–4 ta ("2 nusxa", "Faqat 1–3 bet", "Albom qilib", "Boshqa fayl")
4. **Bento kartochkalar** 2×2: Nusxa (−/+), Yo'nalish, Sahifalar (Hammasi/Tanlash), Rang. Tanlangan tugma — to'q fon.
5. **To'q "Jami" paneli** + urg'u rangidagi "To'lash" tugmasi — doim pastda ko'rinadi
6. **Yozish qatori**: qisqich (fayl) + matn + yuborish. Buyruqlar: `3 nusxa`, `5-8 bet`, `1,3,5`, `albom`, `kitob`,
   `rangli`, `oq-qora`, `hammasi`, `to'lash`. Tushunilmasa — misollar bilan izoh.

Tugmalar va yozma buyruq **bir xil holatni** o'zgartiradi — biri o'zgarsa ikkinchisi ham yangilanadi.

## To'lov oynasi (pastdan chiquvchi sheet)
Buyurtma kodi → to'q summa kartochkasi → usullar (QR / Click / Payme / Karta) → panel → holat qatori →
"Bekor qilish" + "To'lov qildim". Holatlar: kutilmoqda (sariq) → tekshirilmoqda (ko'k) → chop etilmoqda (yashil) →
natija oynasi (✓ "Hujjat tayyor!" yoki ! xato + buyurtma kodi). Summa **doim serverdan** olinadi.

## Qoidalar
- Teginish maydoni ≥ 44px; matn kontrasti ≥ 4.5:1; emoji ishlatilmaydi — ikonlar inline SVG (stroke)
- Haqiqiy `<button>`, `<input>` + `<label>`; dinamik hududlarda `aria-live`
- Narx/betlar brauzerda faqat **taxminiy**; yakuniy summa `/api/order/create` javobidan
- Admin: logoni 5 marta bosish yoki `/#admin` → shablon yuklash/o'chirish (`X-Admin-Token`)
- Telefon birinchi: ustun kengligi ≤ 460px; kompyuterda markazda "telefon kartasi" bo'lib turadi

## Lokal demo
`start_demo.bat` (Windows) → `http://localhost:5000`. `DEMO_AUTO_CONFIRM=1`: "To'lov qildim" 3 s da o'zi tasdiqlanadi,
Telegram o'chiq, printer yo'q bo'lsa chop etish simulyatsiya. **Kioskda bu rejimni yoqmang.**
