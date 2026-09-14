import os
import time
import uuid
import shutil
import logging
import threading
import subprocess
from pathlib import Path
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from PIL import Image
from pypdf import PdfReader

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
    CORS(app, resources={r"/api/*": {"origins": "*"}})
    logger.info("Flask-CORS muvaffaqiyatli faollashtirildi!")


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
    """Netlify saytidan terminal holatini tekshirish uchun."""
    default_printer = get_default_printer()
    return jsonify({
        "status": "online",
        "printer": default_printer or "Standart USB Printer",
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
            page_count = 1
    finally:
        temp_path.unlink(missing_ok=True)

    return jsonify({
        "success": True,
        "page_count": max(1, page_count)
    })


@app.route("/api/print", methods=["POST"])
def print_document():
    """
    Faylni qabul qiladi va to'g'ridan-to'g'ri CUPS orqali printerga yuboradi.
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

    # Parametrlar
    color_mode = request.form.get("color_mode", "gray")
    orientation = request.form.get("orientation", "portrait")
    duplex = request.form.get("duplex", "one-sided")
    page_ranges = request.form.get("page_ranges", "").strip()

    try:
        copies = int(request.form.get("copies", 1))
        copies = max(1, min(copies, 10))
    except ValueError:
        copies = 1

    file_id = str(uuid.uuid4())
    clean_name = secure_filename(file.filename)
    saved_path = UPLOAD_FOLDER / f"{file_id}_{clean_name}"
    file.save(str(saved_path))
    logger.info(f"Fayl saqlandi: {saved_path}")

    try:
        ready_file = prepare_printable_file(saved_path)
    except Exception as e:
        logger.error(f"Faylni tayyorlashda xatolik: {e}")
        return jsonify({
            "success": False,
            "message": f"Faylni chop etishga tayyorlashda xatolik: {str(e)}"
        }), 500

    # CUPS buyrug'i
    default_printer = get_default_printer()
    cmd = ["lp"]

    if default_printer:
        cmd.extend(["-d", default_printer])

    cmd.extend(["-n", str(copies)])
    cmd.extend(["-o", "media=A4"])

    # Orientatsiya
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

    # Sahifalar oralig'i
    if page_ranges and page_ranges.lower() not in ["all", "barchasi"]:
        cmd.extend(["-o", f"page-ranges={page_ranges}"])

    # Rasmlar uchun
    if saved_path.suffix.lower() in [".png", ".jpg", ".jpeg"]:
        cmd.extend(["-o", "fit-to-page"])

    cmd.append(str(ready_file))
    logger.info(f"CUPS ijro buyrug'i: {' '.join(cmd)}")

    # Agar Linux / CUPS bo'lmasa (Simulyatsiya)
    if not shutil.which("lp"):
        logger.warning("CUPS 'lp' buyrug'i topilmadi. Simulyatsiya qilindi.")
        return jsonify({
            "success": True,
            "simulated": True,
            "message": "Hujjat printerga muvaffaqiyatli yuborildi! (Simulyatsiya rejimi)",
            "printer": default_printer or "Standart USB Printer",
            "copies": copies,
        })

    # Haqiqiy CUPS ijrosi
    try:
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        cups_output = proc.stdout.strip() or "Chop etish vazifasi qabul qilindi"
        logger.info(f"CUPS natijasi: {cups_output}")
        return jsonify({
            "success": True,
            "simulated": False,
            "message": "Hujjat printerga yuborildi! Qog'ozni printerdan oling.",
            "cups_response": cups_output,
            "printer": default_printer or "USB Printer",
            "copies": copies,
        })
    except subprocess.CalledProcessError as err:
        err_msg = err.stderr.strip() or err.stdout.strip() or "Noma'lum printer xatosi"
        logger.error(f"CUPS xatosi: {err_msg}")
        return jsonify({
            "success": False,
            "message": f"Printer xatosi: {err_msg}"
        }), 500


if __name__ == "__main__":
    logger.info(f"Smart Web-Printchi serveri ishga tushmoqda...")
    logger.info(f"Manzil: http://{SERVER_HOST}:{SERVER_PORT}")
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
