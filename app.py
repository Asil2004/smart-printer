import os
import io
import json
import time
import uuid
import shutil
import logging

# .env fayldan muhit o'zgaruvchilarini yuklash
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # python-dotenv o'rnatilmagan — muhit o'zgaruvchilari OS dan olinadi

import threading
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from PIL import Image
from pypdf import PdfReader

# Smart printer routing moduli
from printer_detector import get_printer_for_job, get_all_printer_status, detect_connected_printers

# AI Writer moduli
try:
    from ai_writer import (
        generate_document_text, create_docx, calculate_price,
        extract_text_from_image, DOC_TYPES
    )
    AI_WRITER_AVAILABLE = True
except Exception as _ai_err:
    AI_WRITER_AVAILABLE = False
    logging.getLogger("smart_printchi").warning(f"AI Writer yuklanmadi: {_ai_err}")


# CORS moduli (Netlify saytidan so'rovlarni qabul qilish uchun)
try:
    from flask_cors import CORS
except ImportError:
    CORS = None

# ----------------- LOGGING SOZLAMALARI -----------------
logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("smart_web_printchi")

# ----------------- ILOVA KONFIGURATSIYASI -----------------
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", 5000))
MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB
ALLOWED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg"}

# Narxlar (so'mda) - Jonli kalkulyator uchun
PRICE_PER_PAGE_BW = 500      # Oq-qora bir sahifa
PRICE_PER_PAGE_COLOR = 1500  # Rangli bir sahifa
FILE_RETENTION_SECONDS = 1800  # 30 daqiqadan so'ng fayllarni o'chirish

app = Flask(__name__, template_folder="templates", static_folder="public")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "smart-web-printchi-secret-2026")

# CORS ni barcha API larda faollashtirish
if CORS:
    CORS(app, resources={r"/*": {"origins": "*"}})
    logger.info("Flask-CORS muvaffaqiyatli faollashtirildi!")


@app.after_request
def add_cors_headers(response):
    """Barcha so'rovlar (Netlify, Ngrok, Local) uchun to'liq CORS ruxsatlarini ta'minlaydi."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, ngrok-skip-browser-warning, X-Requested-With"
    return response


# ----------------- YORDAMCHI FUNKSIYALAR -----------------
def allowed_file(filename: str) -> bool:
    """Fayl kengaytmasi ruxsat etilganligini tekshiradi."""
    if "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def get_default_printer() -> str:
    """CUPS tizimidagi standart printerni aniqlaydi."""
    try:
        res = subprocess.run(["lpstat", "-d"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in res.stdout.splitlines():
            if "system default destination:" in line:
                return line.split(":", 1)[1].strip()
        
        # Agar standart belgilanmagan bo'lsa, mavjud birinchi printerni oladi
        res_p = subprocess.run(["lpstat", "-p"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        for line in res_p.stdout.splitlines():
            if line.startswith("printer "):
                return line.split()[1].strip()
    except Exception as e:
        logger.warning(f"Standart printerni aniqlashda xatolik: {e}")
    return ""


def convert_docx_to_pdf(docx_path: Path) -> Path:
    """
    DOCX faylni LibreOffice headless orqali PDF ga aylantiradi.
    """
    out_dir = docx_path.parent
    expected_pdf = out_dir / (docx_path.stem + ".pdf")

    libreoffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice_cmd:
        raise RuntimeError(
            "LibreOffice tizimda topilmadi! Iltimos, o'rnating: sudo apt install -y libreoffice"
        )

    cmd = [
        libreoffice_cmd,
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]
    logger.info(f"DOCX ni PDF ga konvertatsiya qilish: {' '.join(cmd)}")
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if res.returncode != 0 or not expected_pdf.exists():
        raise RuntimeError(f"DOCX konvertatsiyasida xatolik: {res.stderr}")

    return expected_pdf


def convert_image_to_pdf(image_path: Path) -> Path:
    """
    Rasmni (PNG/JPG) A4 formatidagi markazlashtirilgan PDF ga aylantiradi.
    """
    output_pdf = image_path.with_suffix(".pdf")
    # A4 300 DPI: 2480 x 3508 piksel
    a4_width, a4_height = 2480, 3508

    with Image.open(image_path) as img:
        if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[3] if len(img.split()) >= 4 else None)
        else:
            rgb_img = img.convert("RGB")

        img_w, img_h = rgb_img.size
        ratio = min(a4_width / img_w, a4_height / img_h)
        new_w = int(img_w * ratio)
        new_h = int(img_h * ratio)

        resized_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        canvas = Image.new("RGB", (a4_width, a4_height), (255, 255, 255))
        pos_x = (a4_width - new_w) // 2
        pos_y = (a4_height - new_h) // 2
        canvas.paste(resized_img, (pos_x, pos_y))
        canvas.save(output_pdf, "PDF", resolution=300.0)

    return output_pdf


def prepare_printable_file(file_path: Path) -> Path:
    """
    Yuklangan faylni tekshiradi va CUPS uchun tayyor fayl (PDF) yo'lini qaytaradi.
    """
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return file_path
    elif suffix == ".docx":
        return convert_docx_to_pdf(file_path)
    elif suffix in [".png", ".jpg", ".jpeg"]:
        return convert_image_to_pdf(file_path)
    else:
        raise ValueError(f"Qo'llab-quvvatlanmaydigan fayl formati: {suffix}")


def get_pdf_page_count(pdf_path: Path) -> int:
    """PDF faylning sahifalar sonini qaytaradi."""
    try:
        reader = PdfReader(str(pdf_path))
        return len(reader.pages)
    except Exception as e:
        logger.warning(f"PDF sahifalar sonini aniqlashda xatolik: {e}")
        return 1


# ----------------- FONDA TOZALASH OQIMI -----------------
def background_cleanup_worker():
    """Vaqti o'tgan yuklangan fayllarni avtomatik o'chirib turadi."""
    while True:
        try:
            now = time.time()
            for item in UPLOAD_FOLDER.iterdir():
                if item.is_file() and item.name != ".gitkeep":
                    file_age = now - item.stat().st_mtime
                    if file_age > FILE_RETENTION_SECONDS:
                        item.unlink(missing_ok=True)
                        logger.info(f"Eskirgan fayl tozalandi: {item.name}")
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xatolik: {e}")
        time.sleep(600)


cleanup_thread = threading.Thread(target=background_cleanup_worker, daemon=True)
cleanup_thread.start()


# ----------------- VEB VA API MARSHRUTLARI -----------------
@app.route("/")
def index():
    """Lokal tarmoqda ochilganda xizmat qiladi."""
    return render_template(
        "index.html",
        price_bw=PRICE_PER_PAGE_BW,
        price_color=PRICE_PER_PAGE_COLOR
    )


@app.route("/api/health", methods=["GET"])
def health_check():
    """Netlify saytidan terminal holatini tekshirish uchun. Barcha printerlar holatini qaytaradi."""
    printers = get_all_printer_status()
    connected = [p for p in printers if p["connected"]]

    # Asosiy printer — birinchi ulangan
    main_printer = connected[0]["cups_name"] if connected else ""

    return jsonify({
        "status": "online",
        "printer": main_printer or "Printer ulanmagan",
        "printers": printers,           # Barcha printerlar holati (UI uchun)
        "price_bw": PRICE_PER_PAGE_BW,
        "price_color": PRICE_PER_PAGE_COLOR,
        "timestamp": time.time()
    })


@app.route("/api/inspect-file", methods=["POST"])
def inspect_file():
    """Fayl yuklanganda uning sahifalar sonini tezkor aniqlab beradi."""
    if "file" not in request.files:
        return jsonify({"success": False, "error": "Fayl yuborilmadi"}), 400

    file = request.files["file"]
    if not file or not allowed_file(file.filename):
        return jsonify({"success": False, "error": "Noto'g'ri fayl formati"}), 400

    temp_id = str(uuid.uuid4())[:8]
    ext = file.filename.rsplit(".", 1)[1].lower()
    temp_path = UPLOAD_FOLDER / f"inspect_{temp_id}.{ext}"
    file.save(str(temp_path))

    page_count = 1
    try:
        if ext == ".pdf":
            page_count = get_pdf_page_count(temp_path)
        elif ext in [".png", ".jpg", ".jpeg"]:
            page_count = 1
        elif ext == ".docx":
            import zipfile
            import xml.etree.ElementTree as ET
            try:
                with zipfile.ZipFile(temp_path, "r") as docx_zip:
                    if "docProps/app.xml" in docx_zip.namelist():
                        app_xml = docx_zip.read("docProps/app.xml")
                        root = ET.fromstring(app_xml)
                        for elem in root.iter():
                            if elem.tag.endswith("Pages"):
                                page_count = int(elem.text)
                                break
            except Exception as e:
                logger.warning(f"DOCX sahifalarini o'qishda xatolik: {e}")
                page_count = 1
    except Exception as err:
        logger.error(f"Faylni tahlil qilishda xatolik: {err}")
    finally:
        temp_path.unlink(missing_ok=True)

    return jsonify({
        "success": True,
        "page_count": max(1, page_count)
    })


@app.route("/api/print", methods=["POST"])
def print_document():
    """
    Faylni qabul qiladi va Smart Router orqali to'g'ri printerga yuboradi:
      - job_type=receipt  → XP-58 termal printer
      - color_mode=gray   → Canon lazer (oq-qora)
      - color_mode=color  → Rangli printer
    """
    if "file" not in request.files:
        return jsonify({"success": False, "message": "Hech qanday fayl tanlanmadi!"}), 400

    file = request.files["file"]
    if file.filename == "":
        return jsonify({"success": False, "message": "Fayl nomi bo'sh!"}), 400

    if not allowed_file(file.filename):
        return jsonify({
            "success": False,
            "message": f"Fayl formati noto'g'ri! Faqat {', '.join(ALLOWED_EXTENSIONS).upper()} qabul qilinadi."
        }), 400

    # ── Parametrlar ──────────────────────────────────────
    color_mode  = request.form.get("color_mode", "gray")      # "gray" | "color"
    orientation = request.form.get("orientation", "portrait")
    duplex      = request.form.get("duplex", "one-sided")
    page_ranges = request.form.get("page_ranges", "").strip()
    job_type    = request.form.get("job_type", "document")    # "document" | "receipt"

    try:
        copies = int(request.form.get("copies", 1))
        copies = max(1, min(copies, 10))
    except ValueError:
        copies = 1

    # ── Faylni saqlash ───────────────────────────────────
    file_id    = str(uuid.uuid4())
    clean_name = secure_filename(file.filename)
    saved_path = UPLOAD_FOLDER / f"{file_id}_{clean_name}"
    file.save(str(saved_path))
    logger.info(f"Fayl saqlandi: {saved_path}")

    # ── Smart Router: qaysi printer? ─────────────────────
    routing = get_printer_for_job(color_mode=color_mode, job_type=job_type)
    logger.info(f"Smart Routing: {routing}")

    if not routing.get("found"):
        return jsonify({
            "success": False,
            "message": f"Printer topilmadi: {routing.get('reason', 'Noma\'lum')}"
        }), 503

    selected_printer = routing["cups_name"]
    selected_media   = routing["media"]
    routing_reason   = routing["reason"]

    # ── Faylni chop etishga tayyorlash ───────────────────
    # Termal printer uchun: faqat rasm PDF ga 58mm formatda o'tkaziladi
    try:
        if routing["type"] == "thermal":
            # Termal: DOCX/PDF ham qabul qilinadi, lekin rasm 58mm formatga o'tkaziladi
            ready_file = prepare_printable_file(saved_path)
        else:
            # A4 lazer/rangli printerlar uchun
            ready_file = prepare_printable_file(saved_path)
    except Exception as e:
        logger.error(f"Faylni tayyorlashda xatolik: {e}")
        return jsonify({
            "success": False,
            "message": f"Faylni chop etishga tayyorlashda xatolik: {str(e)}"
        }), 500

    # ── CUPS buyrug'ini shakllantirish ───────────────────
    cmd = ["lp", "-d", selected_printer, "-n", str(copies)]
    cmd.extend(["-o", f"media={selected_media}"])

    if routing["type"] != "thermal":
        # Orientatsiya (termal printerda orientatsiya yo'q)
        if orientation == "landscape":
            cmd.extend(["-o", "orientation-requested=4"])
        else:
            cmd.extend(["-o", "orientation-requested=3"])

        # Rang
        if color_mode == "color":
            cmd.extend(["-o", "ColorModel=Color"])
        else:
            cmd.extend(["-o", "ColorModel=Gray"])

        # Duplex
        if duplex == "two-sided":
            cmd.extend(["-o", "sides=two-sided-long-edge"])
        else:
            cmd.extend(["-o", "sides=one-sided"])
    else:
        # Termal: har doim oq-qora, bir tomonlama, portrait
        cmd.extend(["-o", "ColorModel=Gray", "-o", "sides=one-sided"])

    # Sahifalar oralig'i
    if page_ranges and page_ranges.lower() not in ["all", "barchasi"]:
        cmd.extend(["-o", f"page-ranges={page_ranges}"])

    # Rasm fit-to-page
    if saved_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        cmd.extend(["-o", "fit-to-page"])

    cmd.append(str(ready_file))
    logger.info(f"CUPS ijro buyrug'i: {' '.join(cmd)}")

    # ── To'lov ma'lumotlari ───────────────────────────────
    payment_method = request.form.get("payment_method", "card")
    amount         = request.form.get("amount", "0")
    payment_status = request.form.get("payment_status", "PAID")
    logger.info(f"To'lov: {amount} so'm | {payment_method} | {clean_name} → [{selected_printer}]")

    order_info = {
        "id":             file_id[:8],
        "filename":       clean_name,
        "amount":         amount,
        "payment_method": payment_method,
        "payment_status": payment_status,
        "copies":         copies,
        "printer":        selected_printer,
        "printer_type":   routing["type"],
        "routing_reason": routing_reason,
        "timestamp":      time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    recent_orders.append(order_info)
    if len(recent_orders) > 50:
        recent_orders.pop(0)

    # ── Simulyatsiya rejimi (Windows / test) ─────────────
    if not shutil.which("lp"):
        logger.warning("CUPS 'lp' topilmadi. Simulyatsiya qilindi.")
        return jsonify({
            "success":        True,
            "simulated":      True,
            "message":        f"Hujjat [{selected_printer}] ga muvaffaqiyatli yuborildi! (Simulyatsiya)",
            "printer":        selected_printer,
            "printer_type":   routing["type"],
            "routing_reason": routing_reason,
            "copies":         copies,
            "order":          order_info,
        })

    # ── Haqiqiy CUPS ijrosi ───────────────────────────────
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        cups_output = proc.stdout.strip() or "Chop etish vazifasi qabul qilindi"
        logger.info(f"CUPS natijasi: {cups_output}")
        return jsonify({
            "success":        True,
            "simulated":      False,
            "message":        f"Hujjat [{selected_printer}] printerga yuborildi! Qog'ozni printerdan oling.",
            "cups_response":  cups_output,
            "printer":        selected_printer,
            "printer_type":   routing["type"],
            "routing_reason": routing_reason,
            "copies":         copies,
            "order":          order_info,
        })
    except subprocess.CalledProcessError as err:
        err_msg = err.stderr.strip() or err.stdout.strip() or "Noma'lum printer xatosi"
        logger.error(f"CUPS xatosi: {err_msg}")
        return jsonify({
            "success": False,
            "message": f"Printer xatosi [{selected_printer}]: {err_msg}"
        }), 500


# ----------------- TO'LOV VA BUYURTMALAR TARIXI API -----------------
recent_orders = []


@app.route("/api/printers", methods=["GET"])
def get_printers():
    """
    Ulangan va kutilayotgan barcha printerlar holatini qaytaradi.
    UI da har bir printer uchun 🟢/🔴 ko'rsatgich uchun ishlatiladi.
    """
    printers = get_all_printer_status()
    return jsonify({
        "success": True,
        "printers": printers
    })

@app.route("/api/orders", methods=["GET"])
def get_recent_orders():
    """Admin uchun oxirgi to'lovlar va chop etilgan fayllar ro'yxati."""
    return jsonify({
        "success": True,
        "orders": list(reversed(recent_orders))
    })


# Click / Payme Webhook integratsiyalari (Kelgusida Click Merchant ulanishi uchun)
@app.route("/api/payments/click/prepare", methods=["POST"])
def click_prepare():
    click_trans_id = request.form.get("click_trans_id")
    service_id = request.form.get("service_id")
    merchant_trans_id = request.form.get("merchant_trans_id")
    amount = request.form.get("amount")
    action = request.form.get("action")
    error = request.form.get("error", 0)

    logger.info(f"Click Prepare so'rovi: trans={click_trans_id}, sum={amount}")
    return jsonify({
        "click_trans_id": click_trans_id,
        "merchant_trans_id": merchant_trans_id,
        "merchant_prepare_id": click_trans_id,
        "error": 0,
        "error_note": "Success"
    })


@app.route("/api/payments/click/complete", methods=["POST"])
def click_complete():
    click_trans_id       = request.form.get("click_trans_id")
    merchant_prepare_id  = request.form.get("merchant_prepare_id")
    merchant_trans_id    = request.form.get("merchant_trans_id")
    error                = request.form.get("error", 0)

    logger.info(f"Click Complete so'rovi: trans={click_trans_id}")
    return jsonify({
        "click_trans_id":       click_trans_id,
        "merchant_trans_id":    merchant_trans_id,
        "merchant_confirm_id":  click_trans_id,
        "error":       0,
        "error_note":  "Success"
    })


# ═══════════════════════════════════════════════════════════
# TAYYOR SHABLONLAR API
# ═══════════════════════════════════════════════════════════
TEMPLATES_JSON = BASE_DIR / "template_data" / "templates.json"
TEMPLATES_DIR  = BASE_DIR / "templates_files"


def _load_templates() -> list:
    """templates.json dan shablonlar ro'yxatini yuklaydi."""
    try:
        with open(TEMPLATES_JSON, "r", encoding="utf-8") as f:
            templates = json.load(f)
        # Fayl mavjudligini tekshirish
        for t in templates:
            fpath = TEMPLATES_DIR / t.get("file", "")
            t["file_exists"] = fpath.exists()
        return templates
    except Exception as e:
        logger.error(f"Shablonlarni yuklashda xatolik: {e}")
        return []


@app.route("/api/templates", methods=["GET"])
def get_templates():
    """Mavjud shablonlar ro'yxatini qaytaradi."""
    templates = _load_templates()
    category  = request.args.get("category", "")
    if category:
        templates = [t for t in templates if t.get("category") == category]
    return jsonify({"success": True, "templates": templates})


def _save_templates(templates: list):
    """templates.json ga saqlaydi."""
    TEMPLATES_JSON.parent.mkdir(exist_ok=True)
    with open(TEMPLATES_JSON, "w", encoding="utf-8") as f:
        json.dump(templates, f, ensure_ascii=False, indent=2)


@app.route("/api/admin/templates/upload", methods=["POST"])
def admin_upload_template():
    """
    Admin: yangi shablon fayl yuklash.
    Multipart/form-data:
      - file: PDF yoki DOCX fayl
      - name, description, category, price_per_page (ixtiyoriy)
    """
    if "file" not in request.files:
        return jsonify({"success": False, "message": "Fayl yuborilmadi"}), 400

    f        = request.files["file"]
    ext      = f.filename.rsplit(".", 1)[-1].lower() if "." in f.filename else ""
    if ext not in ("pdf", "docx"):
        return jsonify({"success": False, "message": "Faqat PDF yoki DOCX qabul qilinadi"}), 400

    name        = request.form.get("name", f.filename.rsplit(".", 1)[0]).strip()
    description = request.form.get("description", "").strip()
    category    = request.form.get("category", "other").strip()
    color       = request.form.get("color", "false").lower() == "true"
    try:
        price   = int(request.form.get("price_per_page", 1500 if color else 500))
    except ValueError:
        price   = 500

    # Fayl nomini xavfsiz qilish
    safe_name  = secure_filename(f.filename)
    file_id    = str(uuid.uuid4())[:6]
    filename   = f"{file_id}_{safe_name}"
    TEMPLATES_DIR.mkdir(exist_ok=True)
    save_path  = TEMPLATES_DIR / filename
    f.save(str(save_path))

    # Sahifalar soni
    pages = 1
    if ext == "pdf":
        try:
            pages = get_pdf_page_count(save_path)
        except Exception:
            pass

    # templates.json ga qo'shish
    templates  = _load_templates()
    # file_exists kalitini olib tashlaymiz (faqat runtime uchun)
    for t in templates:
        t.pop("file_exists", None)

    new_entry = {
        "id":             file_id + "_" + secure_filename(name).lower().replace(" ", "_"),
        "name":           name,
        "description":    description or f"{name} shabloni",
        "category":       category,
        "pages":          pages,
        "preview":        "",
        "file":           filename,
        "price_per_page": price,
        "color":          color,
        "tags":           [category, name.lower()],
    }
    templates.append(new_entry)
    _save_templates(templates)

    logger.info(f"Yangi shablon qo'shildi: {name} ({filename})")
    return jsonify({"success": True, "message": f"'{name}' shabloni qo'shildi!", "template": new_entry})


@app.route("/api/admin/templates/delete/<template_id>", methods=["DELETE"])
def admin_delete_template(template_id: str):
    """Admin: shablonni o'chirish."""
    templates = _load_templates()
    for t in templates:
        t.pop("file_exists", None)

    target = next((t for t in templates if t["id"] == template_id), None)
    if not target:
        return jsonify({"success": False, "message": "Shablon topilmadi"}), 404

    # Faylni o'chirish
    fpath = TEMPLATES_DIR / target["file"]
    fpath.unlink(missing_ok=True)

    templates = [t for t in templates if t["id"] != template_id]
    _save_templates(templates)
    logger.info(f"Shablon o'chirildi: {target['name']}")
    return jsonify({"success": True, "message": f"'{target['name']}' o'chirildi"})


@app.route("/api/templates/print", methods=["POST"])
def print_template():
    """Tanlangan shablonni chop etadi."""
    data        = request.get_json() or {}
    template_id = data.get("template_id", "")
    copies      = max(1, min(int(data.get("copies", 1)), 10))
    color_mode  = data.get("color_mode", "gray")

    # Shablon topish
    templates = _load_templates()
    template  = next((t for t in templates if t["id"] == template_id), None)
    if not template:
        return jsonify({"success": False, "message": "Shablon topilmadi"}), 404

    file_path = TEMPLATES_DIR / template["file"]
    if not file_path.exists():
        return jsonify({
            "success": False,
            "message": f"Shablon fayli mavjud emas: {template['file']}\n"
                       f"Iltimos, {TEMPLATES_DIR} papkasiga faylni joylashtiring."
        }), 404

    # Smart Router orqali printer tanlash
    routing = get_printer_for_job(color_mode=color_mode, job_type="document")
    if not routing.get("found"):
        return jsonify({"success": False, "message": routing.get("reason")}), 503

    printer      = routing["cups_name"]
    total_price  = template.get("price_per_page", 500) * copies * template.get("pages", 1)

    # To'lov ma'lumotlari
    payment_method = data.get("payment_method", "card")
    amount         = data.get("amount", str(total_price))
    logger.info(f"Shablon chop etish: {template['name']} x{copies} → [{printer}] | {amount} so'm")

    # CUPS orqali chop etish
    if shutil.which("lp"):
        cmd = ["lp", "-d", printer, "-n", str(copies),
               "-o", f"media={routing['media']}", str(file_path)]
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, check=True)
            msg = f"Shablon [{template['name']}] printerga yuborildi!"
        except subprocess.CalledProcessError as err:
            return jsonify({"success": False, "message": f"Printer xatosi: {err.stderr}"}), 500
    else:
        msg = f"[SIMULYATSIYA] Shablon [{template['name']}] chop etildi"

    order = {
        "id":          str(uuid.uuid4())[:8],
        "type":        "template",
        "template":    template["name"],
        "amount":      amount,
        "copies":      copies,
        "printer":     printer,
        "timestamp":   time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    recent_orders.append(order)
    return jsonify({"success": True, "message": msg, "order": order})


# ═══════════════════════════════════════════════════════════
# AI WRITER API
# ═══════════════════════════════════════════════════════════

@app.route("/api/ai/doc-types", methods=["GET"])
def get_doc_types():
    """AI Writer uchun hujjat turlari ro'yxatini qaytaradi."""
    if not AI_WRITER_AVAILABLE:
        return jsonify({"success": False, "message": "AI Writer mavjud emas"}), 503
    return jsonify({"success": True, "doc_types": DOC_TYPES})


@app.route("/api/ai/price", methods=["POST"])
def get_ai_price():
    """Hujjat narxini oldindan hisoblaydi."""
    if not AI_WRITER_AVAILABLE:
        return jsonify({"success": False, "message": "AI Writer mavjud emas"}), 503

    data        = request.get_json() or {}
    doc_type    = data.get("doc_type", "ariza")
    word_count  = int(data.get("word_count", 200))
    print_pages = int(data.get("print_pages", 1))
    color       = data.get("color", False)

    price = calculate_price(doc_type, word_count, print_pages=print_pages, color=color)
    return jsonify({"success": True, "price": price})


@app.route("/api/ai/write", methods=["POST"])
def ai_write():
    """
    AI yordamida hujjat yaratadi va DOCX faylini qaytaradi.
    Multipart/form-data qabul qiladi (matn va/yoki rasm).
    """
    if not AI_WRITER_AVAILABLE:
        return jsonify({"success": False, "message": "AI Writer mavjud emas (GEMINI_API_KEY kerak)"}), 503

    doc_type     = request.form.get("doc_type", "ariza")
    recipient    = request.form.get("recipient", "")
    content      = request.form.get("content", "")
    author_name  = request.form.get("author_name", "")
    date_str     = request.form.get("date", "")
    organization = request.form.get("organization", "")

    if not doc_type or not content:
        return jsonify({
            "success": False,
            "message": "Hujjat turi va mazmun kiritish shart!"
        }), 400

    # Rasm (ixtiyoriy)
    image_bytes = None
    image_mime  = "image/jpeg"
    if "image" in request.files:
        img_file    = request.files["image"]
        image_bytes = img_file.read()
        image_mime  = img_file.mimetype or "image/jpeg"
        logger.info(f"Rasm qabul qilindi: {img_file.filename} ({len(image_bytes)} bayt)")

    try:
        # AI hujjat yaratish
        result = generate_document_text(
            doc_type=doc_type,
            recipient=recipient,
            content=content,
            author_name=author_name,
            date=date_str,
            organization=organization,
            image_bytes=image_bytes,
            image_mime=image_mime,
        )

        # DOCX fayl yaratish
        doc_id    = str(uuid.uuid4())[:8]
        docx_path = UPLOAD_FOLDER / f"ai_{doc_type}_{doc_id}.docx"
        create_docx(
            text=result["text"],
            doc_type=doc_type,
            author_name=author_name,
            output_path=docx_path,
        )

        logger.info(f"AI hujjat yaratildi: {docx_path} ({result['word_count']} so'z)")
        return jsonify({
            "success":    True,
            "doc_id":     doc_id,
            "text":       result["text"],
            "word_count": result["word_count"],
            "price":      result["price"],
            "download_url": f"/api/ai/download/{doc_id}",
            "print_url":    f"/api/ai/print/{doc_id}",
        })

    except ValueError as e:
        return jsonify({"success": False, "message": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"success": False, "message": str(e)}), 503
    except Exception as e:
        logger.error(f"AI Writer xatolik: {e}")
        return jsonify({"success": False, "message": f"Hujjat yaratishda xatolik: {str(e)}"}), 500


@app.route("/api/ai/download/<doc_id>", methods=["GET"])
def ai_download(doc_id: str):
    """Yaratilgan DOCX faylni yuklab olish."""
    # Xavfsizlik: faqat ruxsat etilgan belgilar
    safe_id = "".join(c for c in doc_id if c.isalnum() or c == "-")
    matches = list(UPLOAD_FOLDER.glob(f"ai_*_{safe_id}.docx"))
    if not matches:
        return jsonify({"success": False, "message": "Fayl topilmadi"}), 404

    return send_file(
        matches[0],
        as_attachment=True,
        download_name=f"hujjat_{safe_id}.docx",
        mimetype="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )


@app.route("/api/ai/print/<doc_id>", methods=["POST"])
def ai_print(doc_id: str):
    """Yaratilgan AI hujjatni to'lovdan so'ng chop etadi."""
    safe_id = "".join(c for c in doc_id if c.isalnum() or c == "-")
    matches = list(UPLOAD_FOLDER.glob(f"ai_*_{safe_id}.docx"))
    if not matches:
        return jsonify({"success": False, "message": "Fayl topilmadi"}), 404

    docx_path  = matches[0]
    data       = request.get_json() or {}
    color_mode = data.get("color_mode", "gray")
    copies     = max(1, min(int(data.get("copies", 1)), 10))

    # Smart Router
    routing = get_printer_for_job(color_mode=color_mode, job_type="document")
    if not routing.get("found"):
        return jsonify({"success": False, "message": routing.get("reason")}), 503

    printer = routing["cups_name"]
    media   = routing["media"]

    # DOCX → PDF konvertatsiya (LibreOffice)
    try:
        ready_file = prepare_printable_file(docx_path)
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500

    amount = data.get("amount", "0")
    logger.info(f"AI hujjat chop etish: {docx_path.name} → [{printer}] | {amount} so'm")

    if shutil.which("lp"):
        cmd = ["lp", "-d", printer, "-n", str(copies),
               "-o", f"media={media}", "-o", "ColorModel=Gray", str(ready_file)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except subprocess.CalledProcessError as err:
            return jsonify({"success": False, "message": f"Printer xatosi: {err.stderr}"}), 500

    order = {
        "id":        safe_id,
        "type":      "ai_document",
        "amount":    amount,
        "copies":    copies,
        "printer":   printer,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    recent_orders.append(order)
    return jsonify({
        "success": True,
        "message": f"AI hujjat [{printer}] printerga yuborildi!",
        "order":   order,
    })


if __name__ == "__main__":
    logger.info("Smart Web-Printchi serveri ishga tushmoqda...")
    logger.info(f"Manzil: http://{SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
