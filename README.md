# Smart Web-Printchi 🖨️
### Netlify & Raspberry Pi Asosidagi Simsiz Chop Etish Tizimi

Ushbu tizim foydalanuvchilarga **Netlify** da joylashgan zamonaviy global veb-sayt orqali dunyoning istalgan nuqtasidan hujjatlarni yuklash va Raspberry Pi ga ulangan USB printer orqali avtomatik chop etish imkonini beradi.

---

## 🌐 Arxitektura Qanday Ishlaydi?

```
[Foydalanuvchi Telefoni / Noutbuki]
            │
            ▼ (HTTPS orqali kirish)
[Netlify Web Sayt: https://smart-printchi.netlify.app]
            │
            ▼ (Fayl va sozlamalarni yuborish)
[Cloudflare Tunnel (Xavfsiz bepul HTTPS shlyuzi)]
            │
            ▼
[Raspberry Pi 3 Model B (Flask Backend: app.py)]
            │
            ▼ (Linux CUPS "lp" buyrug'i)
[USB Printer (A4 Qog'ozda Chop Etish)]
```

---

## 🚀 1-BOSQICH: Loyihani GitHub ga Yuklash

Kompyuteringizda yoki Raspberry Pi da loyiha papkasida (`d:/antigravity/set print`) turib quyidagi buyruqlarni bajaring:

```bash
# 1. Git repozitoriysini initsializatsiya qilish
git init
git branch -M main

# 2. Fayllarni qo'shish va birinchi commitni yaratish
git add .
git commit -m "feat: Initial commit of Smart Web-Printchi for Netlify & Raspberry Pi"

# 3. GitHub da yangi repozitoriy oching (masalan: smart-printchi) va unga ulang:
git remote add origin https://github.com/<GITHUB_FOYDALANUVCHI_NOMI>/smart-printchi.git

# 4. GitHub ga yuklash (push):
git push -u origin main
```

---

## ⚡ 2-BOSQICH: Netlify da Saytni Ishga Tushirish (Deploy)

1. [Netlify.com](https://www.netlify.com) saytiga kiring va kiring (Sign up / Log in via GitHub).
2. **"Add new site"** -> **"Import an existing project"** ni bosing.
3. **GitHub** ni tanlang va boya ochgan `smart-printchi` repozitoriyangizni tanlang.
4. Netlify sozlamalari avtomatik `netlify.toml` dan olinadi:
   - **Publish directory:** `public`
5. **"Deploy smart-printchi"** tugmasini bosing!
6. Bir necha soniyada sizga bepul HTTPS domen beriladi:
   `https://sizning-saytingiz.netlify.app`

---

## 🔌 3-BOSQICH: Raspberry Pi ni Sozlash va Internetga Bog‘lash

### 1. Raspberry Pi da zarur dasturlarni o‘rnatish:
```bash
sudo apt update
sudo apt install -y python3-pip python3-venv cups libcups2-dev libreoffice
```

### 2. Loyihani Raspberry Pi ga ko‘chirish va virtual muhitni yoqish:
```bash
cd /home/pi
git clone https://github.com/<GITHUB_FOYDALANUVCHI_NOMI>/smart-printchi.git
cd smart-printchi

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Bepul Cloudflare Tunnel o‘rnatish (Routerda port ochmasdan oqimga chiqish):
```bash
# Cloudflare rasmiy vositasini yuklab olish:
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-arm.deb
sudo dpkg -i cloudflared.deb

# 5000-portni bepul HTTPS ga chiqarish:
cloudflared tunnel --url http://localhost:5000
```
*Terminalda sizga bepul havola beriladi: `https://xxxx-xxxx.trycloudflare.com`.*

### 4. Netlify Saytida Ulanish:
Netlify da ochilgan saytingizga kiring, yuqori o‘ng burchakdagi **Sozlamalar (⚙️)** tugmasini bosing va o‘sha `https://xxxx.trycloudflare.com` manzilini kiriting. Status yashil bo‘lib, printeringiz nomi ko‘rinadi!

---

## ⚙️ Avtomatik Ishga Tushirish (Systemd Service)

Raspberry Pi yoqilganda server avtomatik ishlashi uchun:
```bash
sudo cp printchi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable printchi.service
sudo systemctl start printchi.service
```
