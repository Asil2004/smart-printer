# Smart Printchi: UI qoidalari ("Ufq + Chek")

**2026-11-23 dan boshlab loyihaning yagona UI uslubi shu.** Yangi ekran yoki o'zgarish shu qoidalarga mos bo'lsin.
Asos: `design-lab/` dagi V3 (V1 taste-skill + V2 charles-unslop dagi chek tizimi). Oldingi uslub "Bento + Chat" edi.

**Konsepsiya:** har bir buyurtma XP-58 chiqaradigan chekdek o'qiladi: har bir tanlov bitta qator, jami pastda.

## Fayllar
| Fayl | Vazifasi |
|---|---|
| `public/index.html` | Yagona sahifa: landing + ilova (Netlify/GitHub Pages ham, Pi'dagi Flask `/` ham shuni beradi) |
| `public/styles.css` | Tokenlar va barcha komponentlar (Tailwind yo'q). Oxiridagi "V3" bloklari chek, rejim, scrollbar |
| `public/app.js` | Holat, chat tahlili, to'lov oqimi, shablonlar, admin |
| `public/receipt.js` | Buyurtma cheki va to'lov cheki qatorlari, light/dark tugmasi, landing tugmalari |
| `public/config.js` | Backend manzili, karta/Click/Payme sozlamalari |
| `design-lab/` | Dizayn variantlari (V1, V2, V3) va solishtirish sahifasi. `demo-mock.js` faqat shu yerda |
| `templates/index.html` | Eski nusxa (Flask uni ishlatmaydi) |

## Tokenlar (`:root` da)
- **Asosiy rejim light.** Dark faqat oy/quyosh tugmasi bilan (`data-theme="dark"`), tizimga ergashmaydi, tanlov `localStorage` da
- Fon `--bg #F3F4F1`, kartochka `--tile #FFFFFF`, matn `--ink #161719`, izoh `--muted #5C6168`
- Urg'u `--accent #C6F36B` (brend lime): asosiy harakat, tanlov, ufq nuri. **Faqat to'q matn bilan**
- Qog'oz `--paper #FFFFFF`: chek dark rejimda ham oq qoladi. Muhr `--stamp #3F6E12`
- Shrift: **Geist** (interfeys) + **Geist Mono** (chek, raqamlar, buyurtma kodi). Raqamlarda `tabular-nums`
- Shrift shkalasi: 12 / 14 / 16 / 20 / 28 / 40-60. Manfiy harf oralig'i faqat 28px dan katta sarlavhalarda
- Shakl: bosiladigan narsa pill (999px), konteyner 24px, ilova ichidagi kartochka 16px, input 14px. Qog'oz yirtilgan chetli
- Ikonlar: Phosphor (regular), 18px; katta joylarda 24px. Emoji ishlatilmaydi

## Tuzilish
**Kompyuter (1024px dan keng):** chapda landing, o'ngda ilova paneli ekranga yopishib turadi.
**Telefon:** hero, ilova, Qanday ishlaydi, Narxlar, Shablonlar, footer.

Landing:
1. **Hero**: sarlavha + bir jumla. Pastda ufq (21st "Horizon Glow" asosida): lime chet chapdan ochiladi, nur sekin suzadi,
   scroll'da sayyora ko'tarilib sarlavha so'nadi. Kompyuterda hero tugmalari yo'q (ish ilovada)
2. **Qanday ishlaydi**: Yuklang / To'lang / Oling, hero matnini takrorlamaydi
3. **Narxlar**: chek ko'rinishida (A4 oq-qora, A4 rangli, chek 58 mm, shablonlar)
4. **Shablonlar**: pill ro'yxat, bosilsa ilovadagi shablonlar sahifasi ochiladi

Ilova (yuqoridan pastga):
1. **Sarlavha**: logo + printer holati + rejim tugmasi + "Shablonlar →". Shablonlar sahifasida "← Chop etish" chapda
2. **Chat**: fayl (o'ngda to'q pufak) va yordamchi (chapda). Xulosa chatda emas, **chekda**
3. **Tez javoblar** (chip)
4. **Sozlamalar**: Printer, Nusxa, Yo'nalish, Sahifalar, Rang. **Shablon tanlanganda faqat Printer va Nusxa**
5. **Buyurtma cheki**: har tanlov qator bo'lib bosiladi (faqat o'zgargan qator qayta bosiladi), jami + "To'lash".
   Kompyuterda yozish qatori ustida yopishib turadi; telefonda sozlamalardan keyin
6. **Yozish qatori** pastga yopishgan. Buyruqlar: `3 nusxa`, `5-8 bet`, `1,3,5`, `albom`, `kitob`, `rangli`, `oq-qora`,
   `hammasi`, `to'lash`

Tugmalar va yozma buyruq **bir xil holatni** o'zgartiradi.

## Shablon oqimi
Shablon bosilsa darhol to'lov ochilmaydi: u chop etish ekraniga hujjat kabi yuklanadi, nusxa (1-10) va printer tanlanadi,
chek yangilanadi, keyin "To'lash". Serverga `copies` yuboriladi, summa `narx × bet × nusxa`.

## To'lov oynasi
Buyurtma kodi, **to'lov cheki** (ilova chekidagi qatorlar + jami), usullar (QR / Click / Payme / Karta), panel, holat qatori,
"Bekor qilish" + "To'lov qildim". To'lov tasdiqlansa chekka **"To'landi" muhri** bosiladi. Natija oynasi ham chek ko'rinishida.
Summa **doim serverdan** olinadi.

## Motion
- Faqat ma'no beradigan harakat: ufq (hero), chek qatorining bosilishi, muhr, kartochkalarning ketma-ket kirishi, summa o'zgarishi
- `prefers-reduced-motion` da hammasi o'chadi, sahifa tayyor holatda ko'rinadi
- Scroll'ga bog'langan hero animatsiyasi CSS `animation-timeline` (Chrome/Edge); boshqa brauzerlarda oddiy scroll

## Qoidalar
- Teginish maydoni 44px dan kam emas; matn kontrasti 4.5:1 dan kam emas
- Haqiqiy `<button>`, `<input>` + `<label>`; dinamik hududlarda `aria-live`
- Em-dash (—) ishlatilmaydi; italic serif va sloganlar yo'q
- Scrollbar ingichka va yumshoq, lekin yashirilmaydi; panel scroll'i sahifani sudramaydi
- Narx/betlar brauzerda **taxminiy**; yakuniy summa `/api/order/create` javobidan
- Admin: logoni 5 marta bosish yoki `/#admin`

## Lokal ko'rish
- Haqiqiy server bilan: `start_demo.bat` → `http://localhost:5000`. `DEMO_AUTO_CONFIRM=1` kioskda yoqilmasin
- Faqat dizayn: `python -m http.server 8770 --directory .` → `http://localhost:8770/design-lab/` (soxta backend bilan)
