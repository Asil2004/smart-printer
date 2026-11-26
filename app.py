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
import tempfile
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
from PIL import Image
from pypdf import PdfReader

# Smart printer routing & service moduli
from printer_detector import get_printer_for_job, get_all_printer_status, detect_connected_printers
from printer_service import PrinterService
import config  # TELEGRAM_* va boshqa sozlamalar
import payments  # buyurtma, to'lov tasdig'i, admin token
import cups_jobs  # CUPS ish holatini kuzatish (IPP)
printer_service = PrinterService()

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
PRICE_PER_PAGE_BW = 250      # Oq-qora bir sahifa
PRICE_PER_PAGE_COLOR = 400   # Rangli bir sahifa
MAX_COPIES = config.MAX_COPIES  # bitta buyurtmada eng ko'p nusxa
FILE_RETENTION_SECONDS = 1800  # 30 daqiqadan so'ng fayllarni o'chirish

app = Flask(__name__, template_folder="templates", static_folder="public", static_url_path="")
app.config["UPLOAD_FOLDER"] = str(UPLOAD_FOLDER)
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "smart-web-printchi-secret-2026")

# CORS ni barcha API larda faollashtirish
if CORS:
    CORS(app, resources={r"/*": {"origins": "*"}})
    logger.info("Flask-CORS muvaffaqiyatli faollashtirildi!")


@app.after_request
def add_cors_headers(response):
    """Barcha so'rovlar (Netlify, Ngrok, Local) uchun to'liq CORS ruxsatlarini ta'minlaydi va brauzer keshini tozalaydi."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization, ngrok-skip-browser-warning, X-Requested-With, X-Admin-Token"
    # Brauzer qotib qolishi va keshlanishini oldini olish
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
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
    docx_path = Path(docx_path).resolve()
    out_dir = docx_path.parent.resolve()
    expected_pdf = out_dir / (docx_path.stem + ".pdf")

    libreoffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
    if not libreoffice_cmd:
        raise RuntimeError(
            "LibreOffice tizimda topilmadi! Iltimos, o'rnating: sudo apt install -y libreoffice-writer"
        )

    # Avval aylantirilgan va fayldan yangi bo'lsa — qayta aylantirmaymiz
    if expected_pdf.exists() and expected_pdf.stat().st_mtime >= docx_path.stat().st_mtime:
        return expected_pdf

    # Har konvertatsiyaga alohida LibreOffice profili: bir vaqtda ikki buyurtma kelsa
    # umumiy profil qulflanib, ikkinchisi xato bilan tugaydi.
    profile_dir = Path(tempfile.mkdtemp(prefix="lo_profile_")).resolve()
    cmd = [
        libreoffice_cmd,
        f"-env:UserInstallation=file://{profile_dir}",
        "--headless",
        "--convert-to",
        "pdf",
        "--outdir",
        str(out_dir),
        str(docx_path),
    ]
    logger.info(f"DOCX ni PDF ga konvertatsiya qilish: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
        # Agar oddiy pdf bo'lmasa, writer_pdf_Export filtri bilan qayta urinish
        if not expected_pdf.exists():
            cmd_filter = [
                libreoffice_cmd,
                f"-env:UserInstallation=file://{profile_dir}",
                "--headless",
                "--convert-to",
                "pdf:writer_pdf_Export",
                "--outdir",
                str(out_dir),
                str(docx_path),
            ]
            res = subprocess.run(cmd_filter, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180)
    except subprocess.TimeoutExpired:
        raise RuntimeError("DOCX konvertatsiyasi 3 daqiqada tugamadi")
    finally:
        shutil.rmtree(profile_dir, ignore_errors=True)

    if not expected_pdf.exists():
        err_msg = (res.stderr.strip() or res.stdout.strip() or "Noma'lum xatolik")
        if "source file could not be loaded" in err_msg:
            err_msg = "LibreOffice-Writer o'rnatilmagan! Terminalda: sudo apt install -y libreoffice-writer"
        raise RuntimeError(f"DOCX konvertatsiyasida xatolik: {err_msg}")

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
            payments.expire_old_orders()
            keep = payments.protected_paths()
            for item in UPLOAD_FOLDER.iterdir():
                if item.is_file() and item.name != ".gitkeep" and str(item) not in keep:
                    file_age = now - item.stat().st_mtime
                    if file_age > FILE_RETENTION_SECONDS:
                        item.unlink(missing_ok=True)
                        logger.info(f"Eskirgan fayl tozalandi: {item.name}")
        except Exception as e:
            logger.error(f"Fayllarni tozalashda xatolik: {e}")
        time.sleep(600)


cleanup_thread = threading.Thread(target=background_cleanup_worker, daemon=True)
cleanup_thread.start()


# Telegram bot orqali ogohlantirish yuborish
def send_telegram_alert(message: str):
    """Adminning Telegram botiga muhim tizim ogohlantirishlarini jo'natadi."""
    bot_token = getattr(config, "TELEGRAM_BOT_TOKEN", "") or os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id   = getattr(config, "TELEGRAM_CHAT_ID", "") or os.environ.get("TELEGRAM_CHAT_ID", "")
    if not bot_token or not chat_id:
        return
    try:
        import urllib.request
        import urllib.parse
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = urllib.parse.urlencode({"chat_id": chat_id, "text": message, "parse_mode": "HTML"}).encode()
        req = urllib.request.Request(url, data=payload, method="POST")
        urllib.request.urlopen(req, timeout=4)
        logger.info("Telegram xabarnomasi yuborildi.")
    except Exception as e:
        logger.warning(f"Telegram xabarnoma xatosi: {e}")


# ----------------- VEB VA API MARSHRUTLARI -----------------
@app.route("/")
def index():
    """Lokal tarmoqda / tunnel orqali ochilganda — Netlify bilan bir xil public/index.html."""
    resp = app.send_static_file("index.html")
    resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.route("/api/health", methods=["GET"])
def health_check():
    """Netlify saytidan terminal holatini tekshirish uchun. Barcha printerlar holatini qaytaradi."""
    printers = get_all_printer_status()
    connected = [p for p in printers if p["connected"]]

    # Asosiy printer — ulangan Canon yoki birinchi printer
    main_printer = ""
    for p in connected:
        if p.get("type") == "laser_bw" or "canon" in p.get("label", "").lower():
            main_printer = p.get("cups_name") or "Canon-LBP3010"
            break
    if not main_printer and connected:
        main_printer = connected[0].get("cups_name") or connected[0].get("label")

    return jsonify({
        "status": "online",
        "printer": main_printer or "Printer ulanmagan",
        "printers": printers,           # Barcha printerlar holati (UI uchun)
        "price_bw": PRICE_PER_PAGE_BW,
        "max_copies": MAX_COPIES,
        "price_color": PRICE_PER_PAGE_COLOR,
        "payment_verification": payments.REQUIRE_PAYMENT,
        "confirm_via": "telegram" if payments.telegram_enabled() else "admin",
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
        # Buyurtma narxi bilan bir xil usulda sanaymiz (DOCX → PDF aylantirib)
        page_count = _count_file_pages(temp_path)
    except Exception as err:
        logger.error(f"Faylni tahlil qilishda xatolik: {err}")
    finally:
        temp_path.unlink(missing_ok=True)
        if ext == "docx":
            temp_path.with_suffix(".pdf").unlink(missing_ok=True)  # konvertatsiya nusxasi

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
    blocked = _require_paid_or_admin()
    if blocked:
        return blocked
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
        copies = max(1, min(copies, MAX_COPIES))
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
        err_msg = routing.get("reason", "Mos printer topilmadi yoki printer tayyor emas.")
        send_telegram_alert(f"⚠️ <b>Smart Web-Printchi Ogohlantirish!</b>\nFoydalanuvchi chop etmoqchi bo'ldi, biroq xatolik:\n❌ <code>{err_msg}</code>")
        return jsonify({
            "success": False,
            "message": err_msg
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

    # ── Termal printer (XP-58) to'g'ridan-to'g'ri chop etish ──
    if routing["type"] == "thermal":
        try:
            printer_service.print_to_thermal(saved_path, copies=copies)
            return jsonify({
                "success":        True,
                "simulated":      False,
                "message":        f"Hujjat [{selected_printer}] termal printerda muvaffaqiyatli chop etildi!",
                "printer":        selected_printer,
                "printer_type":   routing["type"],
                "routing_reason": routing_reason,
                "copies":         copies,
                "order":          order_info,
            })
        except Exception as e:
            logger.error(f"Termal printer xatosi: {e}")
            return jsonify({
                "success": False,
                "message": f"Termal printer xatosi [{selected_printer}]: {str(e)}"
            }), 500

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

    # ── Haqiqiy CUPS ijrosi (Lazer / Rangli printerlar) ────
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
_agent_last_seen = 0
_agent_printers = []

# Pi agenti bilan umumiy maxfiy kalit (Render env + Pi xizmati). O'rnatilmagan bo'lsa agent
# endpointlari eski agentlar uchun ochiq qoladi, lekin zaxira/tiklash endpointlari O'CHIQ bo'ladi.
AGENT_TOKEN = os.environ.get("AGENT_TOKEN", "").strip()
# Har ishga tushishda yangi: agent shu orqali server qayta yonganini (diski tozalanganini) sezadi.
BOOT_ID = uuid.uuid4().hex


def _agent_token_valid(req) -> bool:
    import hmac
    token = req.headers.get("X-Agent-Token", "")
    return bool(AGENT_TOKEN) and hmac.compare_digest(token.encode(), AGENT_TOKEN.encode())


def _agent_allowed(req) -> bool:
    return not AGENT_TOKEN or _agent_token_valid(req)


def _agent_denied():
    return jsonify({"success": False, "message": "Agent kaliti (X-Agent-Token) noto'g'ri"}), 401


@app.route("/api/printers", methods=["GET"])
def get_printers():
    """
    Ulangan va kutilayotgan barcha printerlar holatini qaytaradi.
    UI da har bir printer uchun 🟢/🔴 ko'rsatgich uchun ishlatiladi.
    """
    global _agent_last_seen, _agent_printers
    if IS_CLOUD_SERVER:
        # Bulutda ishlayotgan bo'lsa: Raspberry Pi agentidan kelgan holatni ko'rsatadi
        if time.time() - _agent_last_seen < 60 and _agent_printers:
            printers = _agent_printers
        else:
            printers = []
    else:
        printers = get_all_printer_status()

    stuck = _stuck_order()
    if stuck:
        for p in printers:
            if p.get("type") == "laser_bw" and p.get("connected"):
                p["ready"] = False
                p["status_reason"] = "Printer band: qog'oz yoki ulanishni tekshiring"
    queued = sum(1 for o in list(payments.orders.values()) if o.get("status") == "PAID")
    return jsonify({
        "success": True,
        "printers": printers,
        "queue": queued,
        "agent_seen_ago": int(time.time() - _agent_last_seen) if _agent_last_seen else None,
    })


@app.route("/api/agent/heartbeat", methods=["POST"])
def agent_heartbeat():
    """Raspberry Pi agenti o'zining va ulangan printerlarning holatini xabar qiladi."""
    global _agent_last_seen, _agent_printers
    if not _agent_allowed(request):
        return _agent_denied()
    data = request.get_json(silent=True) or {}
    _agent_last_seen = time.time()
    _agent_printers = data.get("printers", [])
    return jsonify({"success": True, "boot_id": BOOT_ID,
                    "backup_enabled": bool(AGENT_TOKEN)})

@app.route("/api/orders", methods=["GET"])
def get_recent_orders():
    """Admin uchun oxirgi to'lovlar va chop etilgan fayllar ro'yxati (X-Admin-Token kerak)."""
    if not payments.is_admin(request):
        return jsonify({"success": False, "message": "Admin token kerak"}), 401
    all_orders = sorted(payments.orders.values(), key=lambda o: o.get("created_at", 0), reverse=True)
    public = [{k: v for k, v in o.items() if k != "saved_path"} for o in all_orders[:100]]
    return jsonify({"success": True, "orders": public, "legacy": list(reversed(recent_orders))})


# ═══════════════════════════════════════════════════════════
# BUYURTMA VA TO'LOV TASDIG'I (payments.py bilan)
# ═══════════════════════════════════════════════════════════
def _count_file_pages(path: Path) -> int:
    """PDF / DOCX / rasm sahifalar sonini aniqlaydi (narx uchun)."""
    ext = path.suffix.lower()
    if ext == ".pdf":
        return get_pdf_page_count(path)
    if ext == ".docx":
        try:
            return get_pdf_page_count(convert_docx_to_pdf(path))
        except Exception as e:
            logger.warning(f"DOCX ni PDF ga aylantirib sanab bo'lmadi, app.xml ishlatiladi: {e}")
        import zipfile
        import xml.etree.ElementTree as ET
        try:
            with zipfile.ZipFile(path, "r") as z:
                if "docProps/app.xml" in z.namelist():
                    for elem in ET.fromstring(z.read("docProps/app.xml")).iter():
                        if elem.tag.endswith("Pages") and elem.text:
                            return max(1, int(elem.text))
        except Exception as e:
            logger.warning(f"DOCX sahifalarini o'qishda xatolik: {e}")
    return 1


def _int_form(src, key, default, lo=None, hi=None):
    try:
        v = int(src.get(key, default))
    except (TypeError, ValueError):
        v = default
    if lo is not None:
        v = max(lo, v)
    if hi is not None:
        v = min(hi, v)
    return v


def _execute_print(saved_path: Path, color_mode="gray", copies=1, orientation="portrait",
                   duplex="one-sided", page_ranges="") -> dict:
    """Faylni Smart Router tanlagan printerga yuboradi. Xato bo'lsa RuntimeError."""
    routing = get_printer_for_job(color_mode=color_mode, job_type="document")
    if not routing.get("found"):
        raise RuntimeError(routing.get("reason", "Mos printer topilmadi"))
    printer = routing["cups_name"]

    if routing["type"] == "thermal":
        printer_service.print_to_thermal(saved_path, copies=copies)
        return {"printer": printer, "simulated": False}

    ready_file = prepare_printable_file(saved_path)
    cmd = ["lp", "-d", printer, "-n", str(copies), "-o", f"media={routing['media']}",
           "-o", "orientation-requested=4" if orientation == "landscape" else "orientation-requested=3",
           "-o", "ColorModel=Color" if color_mode == "color" else "ColorModel=Gray",
           "-o", "sides=two-sided-long-edge" if duplex == "two-sided" else "sides=one-sided"]
    if page_ranges and page_ranges.lower() not in ("all", "barchasi"):
        cmd += ["-o", f"page-ranges={page_ranges}"]
    if saved_path.suffix.lower() in (".png", ".jpg", ".jpeg"):
        cmd += ["-o", "fit-to-page"]
    cmd.append(str(ready_file))

    if not shutil.which("lp"):
        logger.warning(f"[SIMULYATSIYA] CUPS yo'q: {' '.join(cmd)}")
        return {"printer": printer, "simulated": True}

    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or "Noma'lum CUPS xatosi")
    return {"printer": printer, "simulated": False, "cups": proc.stdout.strip(),
            "job_id": cups_jobs.parse_lp_job_id(proc.stdout)}


# CUPS ishini kuzatish chegaralari (Canon LBP3010 ≈ 14 bet/daqiqa)
PRINT_ALERT_BASE_S = 60      # shundan keyin ham tugamasa — adminga ogohlantirish
PRINT_ALERT_PER_PAGE_S = 10
PRINT_GIVE_UP_S = 20 * 60    # 20 daqiqa: ish bekor qilinadi, buyurtma FAILED


def _stuck_order():
    """Uzoq vaqt tugamay turgan (qog'oz/USB muammosi) chop etish buyurtmasi."""
    for o in payments.orders.values():
        if o.get("status") == "PRINTING" and o.get("stuck"):
            return o
    return None


def _fail_order(order: dict, reason: str):
    payments.set_status(order, "FAILED", error=reason, stuck=False)
    payments.tg_send(
        f"⚠️ <b>#{order['id']} TO'LANGAN, lekin chop etilmadi!</b>\n"
        f"{payments.order_summary(order)}\n❌ <code>{reason[:300]}</code>",
        buttons=[[{"text": "🔁 Qayta chop etish", "callback_data": f"rep:{order['id']}"}]])


def _wait_cups_job(order: dict, printer: str, job_id: int):
    """CUPS ishi tugaguncha kutadi. True = haqiqatan chop etildi."""
    pages = int(order.get("pages", 1)) * int(order.get("copies", 1))
    alert_after = PRINT_ALERT_BASE_S + PRINT_ALERT_PER_PAGE_S * pages
    started, alerted, unknown = time.time(), False, 0
    while True:
        info = cups_jobs.get_job(printer, job_id)
        state = info.get("state")
        if state in cups_jobs.FINAL_OK:
            return True, ""
        if state in cups_jobs.FINAL_BAD:
            return False, f"CUPS ishi {state}: {info.get('message', '')}"
        if state == "unknown":
            unknown += 1
            if unknown >= 15:          # CUPS IPP javob bermayapti — eski xatti-harakat
                logger.warning(f"#{order['id']}: CUPS ish holatini o'qib bo'lmadi ({info.get('error')})")
                return True, ""
        else:
            unknown = 0
        elapsed = time.time() - started
        if not alerted and elapsed > alert_after:
            alerted = True
            payments.set_status(order, "PRINTING", stuck=True,
                                note="Printer javob bermayapti — qog'oz yoki ulanish tekshirilmoqda")
            payments.tg_send(
                f"🟠 <b>#{order['id']} printerda kutib qoldi</b> ({int(elapsed)} s)\n"
                f"Canon LBP3010 ga qog'oz soling yoki USB kabelni tekshiring — "
                f"ish o'zi davom etadi.\nCUPS: <code>{info.get('message', '')[:200]}</code>")
        if elapsed > PRINT_GIVE_UP_S:
            cups_jobs.cancel_job(printer, job_id)
            return False, (f"Printer {max(1, PRINT_GIVE_UP_S // 60)} daqiqa javob bermadi "
                           f"(qog'oz yoki USB). Ish bekor qilindi.")
        time.sleep(2)


def _print_worker(order: dict):
    try:
        res = _execute_print(Path(order["saved_path"]), order.get("color_mode", "gray"),
                             order.get("copies", 1), order.get("orientation", "portrait"),
                             order.get("duplex", "one-sided"), order.get("page_ranges", ""))
    except Exception as e:
        logger.error(f"Order #{order['id']} chop etishda xatolik: {e}")
        _fail_order(order, str(e))
        return

    if not res["simulated"] and res.get("job_id"):
        payments.set_status(order, "PRINTING", printer=res["printer"], cups_job=res["job_id"])
        ok, reason = _wait_cups_job(order, res["printer"], res["job_id"])
        if not ok:
            logger.error(f"Order #{order['id']}: {reason}")
            _fail_order(order, reason)
            return

    was_stuck = order.get("stuck")
    payments.set_status(order, "PRINTED", printer=res["printer"], simulated=res["simulated"],
                        printed_at=time.time(), stuck=False, note="")
    logger.info(f"Order #{order['id']} chop etildi → {res['printer']}")
    payments.tg_send(f"✅ <b>#{order['id']} chop etildi</b> → {res['printer']}"
                     f"{' (kutishdan keyin)' if was_stuck else ''}\n"
                     f"💰 {order['amount']} so'm • {order.get('paid_by', '')}")


IS_CLOUD_SERVER = os.environ.get("IS_CLOUD_SERVER", "0").strip().lower() in ("1", "true", "yes")


def _start_print(order: dict):
    if IS_CLOUD_SERVER:
        # Bulutda (Render.com) ishlayotgan bo'lsa: faylni yuqori tezlikda PDF ga tayyorlaymiz
        try:
            ready_file = prepare_printable_file(Path(order["saved_path"]))
            order["ready_file"] = str(ready_file)
            payments.set_status(order, "PAID", ready=True, note="Raspberry Pi printeriga uzatilmoqda…")
            logger.info(f"Bulut: Buyurtma #{order['id']} agent uchun tayyorlandi: {ready_file}")
        except Exception as e:
            logger.error(f"Bulutda fayl tayyorlashda xatolik #{order['id']}: {e}")
            _fail_order(order, str(e))
    else:
        # Mahalliy Pi da bevosita ishlayotgan bo'lsa
        payments.set_status(order, "PRINTING")
        threading.Thread(target=_print_worker, args=(order,), daemon=True).start()


def confirm_order(order_id: str, source: str) -> str:
    """To'lovni tasdiqlaydi va chop etishni boshlaydi. Idempotent."""
    with payments._lock:
        order = payments.get_order(order_id)
        if not order:
            return "Buyurtma topilmadi"
        if order["status"] in ("PAID", "PRINTING", "PRINTED", "FAILED"):
            return f"#{order['id']} allaqachon tasdiqlangan ({order['status']})"
        if order["status"] not in ("PENDING", "CLAIMED", "EXPIRED"):
            return f"#{order['id']} tasdiqlab bo'lmaydi ({order['status']})"
        payments.set_status(order, "PAID", paid_by=source, paid_at=time.time())
    recent_orders.append({"id": order["id"], "filename": order["filename"],
                          "amount": order["amount"], "payment_method": source,
                          "payment_status": "PAID", "copies": order["copies"],
                          "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")})
    del recent_orders[:-50]
    _start_print(order)
    return f"#{order['id']} tasdiqlandi — chop etilmoqda"


def reject_order(order_id: str, source: str) -> str:
    order = payments.get_order(order_id)
    if not order:
        return "Buyurtma topilmadi"
    if order["status"] not in ("PENDING", "CLAIMED"):
        return f"#{order['id']} rad etib bo'lmaydi ({order['status']})"
    payments.set_status(order, "REJECTED", rejected_by=source)
    return f"#{order['id']} rad etildi"


def reprint_order(order_id: str, source: str) -> str:
    order = payments.get_order(order_id)
    if not order:
        return "Buyurtma topilmadi"
    if order["status"] not in ("FAILED", "PRINTED"):
        return f"#{order['id']} qayta chop etib bo'lmaydi ({order['status']})"
    if not Path(order["saved_path"]).exists():
        return f"#{order['id']} fayli o'chib ketgan"
    _start_print(order)
    return f"#{order['id']} qayta chop etilmoqda"


@app.route("/api/order/create", methods=["POST"])
def create_pending_order():
    """
    To'lovdan oldin buyurtma yaratadi. Narx SERVERDA hisoblanadi.
    source:
      - file     : multipart "file" (+ color_mode, copies, orientation, duplex, page_ranges)
      - template : "template_id" (+ copies, color_mode)
    """
    if _stuck_order():
        return jsonify({"success": False, "printer_busy": True,
                        "message": "Printer hozir band (qog'oz yoki ulanish). Iltimos, birozdan so'ng urinib ko'ring."}), 503
    form   = request.form if request.form else (request.get_json(silent=True) or {})
    source = form.get("source", "file")
    copies = _int_form(form, "copies", 1, 1, MAX_COPIES)
    color_mode = "color" if form.get("color_mode") == "color" else "gray"
    printer_type = form.get("printer_type", "laser_bw")
    order_id = uuid.uuid4().hex[:6].upper()
    order = {"id": order_id, "kind": source, "copies": copies, "color_mode": color_mode,
             "printer_type": printer_type,
             "orientation": "landscape" if form.get("orientation") == "landscape" else "portrait",
             "duplex": "two-sided" if form.get("duplex") == "two-sided" else "one-sided",
             "page_ranges": (form.get("page_ranges") or "").strip()[:50],
             "status": "PENDING", "created_at": time.time()}

    if source == "template":
        tmpl = next((t for t in _load_templates() if t["id"] == form.get("template_id")), None)
        if not tmpl or not tmpl.get("file_exists"):
            return jsonify({"success": False, "message": "Shablon topilmadi"}), 404
        pages = int(tmpl.get("pages", 1))
        order.update(filename=tmpl["name"], saved_path=str(TEMPLATES_DIR / tmpl["file"]),
                     pages=pages, page_ranges="",
                     amount=int(tmpl.get("price_per_page", PRICE_PER_PAGE_BW)) * pages * copies)

    else:
        file = request.files.get("file")
        if not file or not allowed_file(file.filename):
            return jsonify({"success": False, "message": "Fayl tanlanmadi yoki formati noto'g'ri!"}), 400
        clean_name = secure_filename(file.filename) or f"fayl.{file.filename.rsplit('.', 1)[-1]}"
        saved_path = UPLOAD_FOLDER / f"pending_{order_id}_{clean_name}"
        file.save(str(saved_path))
        total = _count_file_pages(saved_path)
        pages = payments.count_selected_pages(order["page_ranges"], total)
        per_page = PRICE_PER_PAGE_COLOR if color_mode == "color" else PRICE_PER_PAGE_BW
        order.update(filename=clean_name, saved_path=str(saved_path), pages=pages,
                     total_pages=total, amount=pages * copies * per_page)

    if CARD_AUTO_CONFIRM and order["amount"] > 0:
        order["base_amount"] = order["amount"]
        order["amount"] = _unique_amount(order["amount"])
    payments.add_order(order)
    logger.info(f"Yangi buyurtma #{order_id} [{source}] | {order['amount']} so'm")
    return jsonify({"success": True, "order_id": order_id, "amount": order["amount"],
                    "pages": order["pages"], "status": "PENDING",
                    "verification": "telegram" if payments.telegram_enabled() else "admin"})


# ── Kartaga o'tkazmani avtomatik tasdiqlash (CardXabar → Pi agenti) ──────
# Har buyurtmaga 1..99 so'm qo'shiladi: kutayotgan buyurtmalar summasi takrorlanmaydi,
# shuning uchun kartaga tushgan summa bo'yicha buyurtma aniq topiladi.
CARD_AUTO_CONFIRM = os.environ.get("CARD_AUTO_CONFIRM", "0").strip().lower() in ("1", "true", "yes")
CARD_LAST4 = os.environ.get("CARD_LAST4", "").strip()       # masalan 0424
PAYMENT_MATCH_WINDOW_S = 45 * 60                              # buyurtmadan keyin shuncha vaqt ichida
_seen_payments: dict = {}                                     # xabar id -> vaqt (takrorni oldini olish)
_amount_lock = threading.Lock()


def _awaiting(o: dict) -> bool:
    return o.get("status") in ("PENDING", "CLAIMED", "EXPIRED") and \
        time.time() - o.get("created_at", 0) < PAYMENT_MATCH_WINDOW_S


def _unique_amount(base: int) -> int:
    import random
    with _amount_lock:
        taken = {o.get("amount") for o in list(payments.orders.values()) if _awaiting(o)}
        offsets = list(range(1, 100))
        random.shuffle(offsets)
        for k in offsets:
            if base + k not in taken:
                return base + k
    return base + 100 + random.randint(0, 899)   # 99 tadan ko'p bir vaqtda kutsa (amalda bo'lmaydi)


@app.route("/api/agent/payment-seen", methods=["POST"])
def agent_payment_seen():
    """Pi agenti kartaga kirimni ko'rdi (CardXabar). Summa bo'yicha buyurtmani topib tasdiqlaydi."""
    if not _agent_token_valid(request):
        return _agent_denied()
    data = request.get_json(silent=True) or {}
    msg_id = str(data.get("msg_id", ""))
    try:
        amount = int(round(float(data.get("amount", 0))))
    except (TypeError, ValueError):
        return jsonify({"success": False, "message": "amount noto'g'ri"}), 400
    card = str(data.get("card_last4", ""))
    if msg_id and msg_id in _seen_payments:
        return jsonify({"success": True, "result": "duplicate"})
    if msg_id:
        _seen_payments[msg_id] = time.time()
        for k in [k for k, t in _seen_payments.items() if time.time() - t > 86400]:
            _seen_payments.pop(k, None)
    if CARD_LAST4 and card and card != CARD_LAST4:
        return jsonify({"success": True, "result": "other_card"})

    with payments._lock:
        matches = [o for o in payments.orders.values() if _awaiting(o) and o.get("amount") == amount]
    if len(matches) == 1:
        o = matches[0]
        payments.set_status(o, o["status"], paid_amount=amount, paid_msg_id=msg_id)
        msg = confirm_order(o["id"], f"CARD_AUTO:{card or '?'}")
        logger.info(f"Kartaga {amount} so'm tushdi → #{o['id']} avtomatik tasdiqlandi ({msg})")
        return jsonify({"success": True, "result": "confirmed", "order_id": o["id"]})

    reason = "mos buyurtma yo'q" if not matches else f"{len(matches)} ta buyurtma mos keldi"
    logger.warning(f"Kartaga {amount} so'm tushdi, lekin {reason}")
    payments.tg_send(f"💳 Kartaga <b>{amount} so'm</b> tushdi (…{card}), lekin {reason}.\n"
                     f"Kerak bo'lsa buyurtmani qo'lda tasdiqlang.")
    return jsonify({"success": True, "result": "unmatched", "reason": reason})


# ── Promokodlar ───────────────────────────────────────────
# Render env: PROMO_CODES="TEST0:100:20,YARIM:50"  →  KOD:chegirma_foizi[:eng_ko'p_ishlatish]
# Kodlar faqat serverda turadi; saytda ham, git'da ham ko'rinmaydi.
_promo_fails: dict = {}          # ip -> [vaqtlar] (taxmin qilib topishga qarshi)
PROMO_FAIL_LIMIT = 10            # 10 daqiqada shuncha noto'g'ri urinish


def _promo_codes() -> dict:
    codes = {}
    for part in os.environ.get("PROMO_CODES", "").split(","):
        bits = [b.strip() for b in part.split(":")]
        if not bits[0]:
            continue
        try:
            pct = max(0, min(100, int(bits[1]))) if len(bits) > 1 and bits[1] else 100
            limit = int(bits[2]) if len(bits) > 2 and bits[2] else 0
        except ValueError:
            logger.warning(f"PROMO_CODES dagi noto'g'ri qism o'tkazib yuborildi: {part!r}")
            continue
        codes[bits[0].upper()] = {"percent": pct, "max_uses": limit}
    return codes


@app.route("/api/order/<order_id>/promo", methods=["POST"])
def apply_promo(order_id):
    """Mijoz promokod kiritdi. Narx 0 bo'lsa — to'lovsiz darhol chop etiladi."""
    ip = request.headers.get("X-Forwarded-For", request.remote_addr or "").split(",")[0].strip()
    now = time.time()
    fails = [t for t in _promo_fails.get(ip, []) if now - t < 600]
    _promo_fails[ip] = fails
    if len(fails) >= PROMO_FAIL_LIMIT:
        return jsonify({"success": False, "message": "Juda ko'p urinish. 10 daqiqadan so'ng qayta urinib ko'ring."}), 429

    order = payments.get_order(order_id)
    if not order:
        return jsonify({"success": False, "message": "Buyurtma topilmadi"}), 404
    if order["status"] != "PENDING":
        return jsonify({"success": False, "message": "Promokodni faqat to'lovdan oldin qo'llash mumkin"}), 409
    if order.get("promo_code"):
        return jsonify({"success": False, "message": "Bu buyurtmaga promokod allaqachon qo'llangan"}), 409

    code = str((request.get_json(silent=True) or {}).get("code", "")).strip().upper()[:40]
    promo = _promo_codes().get(code) if code else None
    if not promo:
        fails.append(now)
        return jsonify({"success": False, "message": "Promokod noto'g'ri"}), 400
    if promo["max_uses"]:
        used = sum(1 for o in list(payments.orders.values())
                   if o.get("promo_code") == code and o.get("status") not in ("EXPIRED", "CANCELLED", "REJECTED"))
        if used >= promo["max_uses"]:
            return jsonify({"success": False, "message": "Bu promokodning muddati tugagan"}), 410

    original = int(order.get("amount", 0))
    base = int(order.get("base_amount", original))
    amount = base * (100 - promo["percent"]) // 100
    if CARD_AUTO_CONFIRM and amount > 0:
        amount = _unique_amount(amount)     # kartaga tushgan summa bo'yicha topilishi uchun
    payments.set_status(order, "PENDING", amount=amount, amount_before_promo=original,
                        promo_code=code, promo_percent=promo["percent"])
    logger.info(f"#{order['id']}: promokod {code} (-{promo['percent']}%) {original} → {amount} so'm")
    free = amount == 0
    if free:
        confirm_order(order["id"], f"PROMO:{code}")
    return jsonify({"success": True, "amount": amount, "amount_before": original,
                    "percent": promo["percent"], "free": free, "status": order["status"]})


@app.route("/api/order/<order_id>/claim", methods=["POST"])
def claim_order_payment(order_id):
    """Mijoz 'To'ladim' bosdi → adminga Telegramda tasdiq so'rovi ketadi. Chop etmaydi!"""
    order = payments.get_order(order_id)
    if not order:
        return jsonify({"success": False, "status": "NOT_FOUND"}), 404
    if order["status"] == "PENDING":
        payments.set_status(order, "CLAIMED", claimed_at=time.time(),
                            claimed_method=(request.get_json(silent=True) or {}).get("method", ""))
        payments.notify_claim(order)
        if payments.DEMO_AUTO_CONFIRM:
            # Faqat demo rejimida avtomatik tasdiq. Telegram sozlanmagan bo'lsa ham to'lov TEKSHIRILMASDAN
            # tasdiqlanmaydi: kartaga tushgan summa (CARD_AUTO_CONFIRM) yoki admin tasdig'i kutiladi.
            threading.Timer(1.0, confirm_order, args=(order["id"], "AUTO_CONFIRM")).start()
    return jsonify({"success": True, "status": order["status"]})


@app.route("/api/order/status/<order_id>", methods=["GET"])
def check_order_payment_status(order_id):
    """Veb-sayt har 2 soniyada holatni so'raydi."""
    order = payments.get_order(order_id)
    if not order:
        return jsonify({"success": False, "status": "NOT_FOUND"}), 404
    return jsonify({"success": True, "order_id": order["id"], "status": order["status"],
                    "amount": order["amount"], "printer": order.get("printer", ""),
                    "note": order.get("note", "") if order["status"] == "PRINTING" else "",
                    "error": order.get("error", "") if order["status"] == "FAILED" else ""})


@app.route("/api/admin/orders/<order_id>/<action>", methods=["POST"])
def admin_order_action(order_id, action):
    """Admin: confirm | reject | reprint (X-Admin-Token kerak)."""
    if not payments.is_admin(request):
        return jsonify({"success": False, "message": "Admin token noto'g'ri"}), 401
    fn = {"confirm": confirm_order, "reject": reject_order, "reprint": reprint_order}.get(action)
    if not fn:
        return jsonify({"success": False, "message": "Noma'lum amal"}), 400
    msg = fn(order_id, "ADMIN_API")
    order = payments.get_order(order_id)
    return jsonify({"success": bool(order), "message": msg,
                    "status": order["status"] if order else "NOT_FOUND"})


# ── Click Merchant SHOP API ───────────────────────────────
def _click_resp(form, error: int, note: str, **extra):
    body = {"click_trans_id": form.get("click_trans_id"),
            "merchant_trans_id": form.get("merchant_trans_id"),
            "error": error, "error_note": note}
    body.update(extra)
    return jsonify(body)  # Click har doim HTTP 200 kutadi


def _click_common_checks(form, action: int):
    if not payments.CLICK_SECRET_KEY:
        return _click_resp(form, -8, "Click sozlanmagan")
    if str(form.get("action")) != str(action):
        return _click_resp(form, -3, "Action not found")
    if not payments.click_sign_ok(form, action):
        logger.warning(f"Click: imzo noto'g'ri! {dict(form)}")
        return _click_resp(form, -1, "SIGN CHECK FAILED!")
    if payments.CLICK_SERVICE_ID and form.get("service_id") != payments.CLICK_SERVICE_ID:
        return _click_resp(form, -1, "Wrong service_id")
    order = payments.get_order(form.get("merchant_trans_id"))
    if not order:
        return _click_resp(form, -5, "Order not found")
    try:
        if abs(float(form.get("amount", 0)) - float(order["amount"])) > 0.01:
            return _click_resp(form, -2, "Incorrect parameter amount")
    except ValueError:
        return _click_resp(form, -2, "Incorrect parameter amount")
    if order["status"] in ("PAID", "PRINTING", "PRINTED", "FAILED"):
        return _click_resp(form, -4, "Already paid")
    if order["status"] in ("REJECTED", "CANCELLED"):
        return _click_resp(form, -9, "Transaction cancelled")
    return order


@app.route("/api/payments/click/prepare", methods=["POST"])
def click_prepare():
    form = request.form
    res = _click_common_checks(form, 0)
    if not isinstance(res, dict):
        return res
    payments.set_status(res, res["status"], click_trans_id=form.get("click_trans_id"),
                        click_prepare_id=int(time.time() * 1000) % 2_000_000_000)
    return _click_resp(form, 0, "Success", merchant_prepare_id=res["click_prepare_id"])


@app.route("/api/payments/click/complete", methods=["POST"])
def click_complete():
    form = request.form
    res = _click_common_checks(form, 1)
    if not isinstance(res, dict):
        return res
    order = res
    if str(form.get("merchant_prepare_id")) != str(order.get("click_prepare_id")):
        return _click_resp(form, -6, "Transaction does not exist")
    if str(form.get("error", "0")) != "0":   # Click tomonida bekor qilingan
        payments.set_status(order, "CANCELLED")
        return _click_resp(form, -9, "Transaction cancelled")
    confirm_order(order["id"], "CLICK")
    return _click_resp(form, 0, "Success", merchant_confirm_id=order["click_prepare_id"])


# ── Payme Merchant API (JSON-RPC) ─────────────────────────
@app.route("/api/payments/payme", methods=["POST"])
def payme_webhook():
    req = request.get_json(silent=True) or {}
    rid, method, params = req.get("id"), req.get("method"), req.get("params", {}) or {}
    err = payments.payme_error
    if not payments.payme_auth_ok(request):
        return jsonify(err(rid, -32504, "Avtorizatsiya xatosi"))

    def ok(result):
        return jsonify({"jsonrpc": "2.0", "id": rid, "result": result})

    def check_order(p):
        order = payments.get_order((p.get("account") or {}).get("order_id"))
        if not order:
            return None, err(rid, -31050, "Buyurtma topilmadi", "order_id")
        if int(p.get("amount", -1)) != int(order["amount"]) * 100:
            return None, err(rid, -31001, "Summa noto'g'ri")
        if order["status"] not in ("PENDING", "CLAIMED"):
            return None, err(rid, -31008, "Buyurtmani to'lab bo'lmaydi")
        return order, None

    now_ms = int(time.time() * 1000)
    txns = payments.payme_txns

    if method == "CheckPerformTransaction":
        order, e = check_order(params)
        return jsonify(e) if e else ok({"allow": True})

    if method == "CreateTransaction":
        tid = params.get("id")
        if tid in txns:
            t = txns[tid]
            if t["state"] != 1:
                return jsonify(err(rid, -31008, "Tranzaksiya faol emas"))
            return ok({"create_time": t["create_time"], "transaction": t["transaction"], "state": 1})
        order, e = check_order(params)
        if e:
            return jsonify(e)
        busy = [t for t in txns.values() if t["order_id"] == order["id"] and t["state"] == 1]
        if busy:
            return jsonify(err(rid, -31050, "Buyurtma boshqa tranzaksiyada", "order_id"))
        txns[tid] = {"id": tid, "order_id": order["id"], "transaction": order["id"],
                     "amount": params.get("amount"), "time": params.get("time"),
                     "create_time": now_ms, "perform_time": 0, "cancel_time": 0,
                     "state": 1, "reason": None}
        payments.save_state()
        return ok({"create_time": now_ms, "transaction": order["id"], "state": 1})

    t = txns.get(params.get("id"))
    if method in ("PerformTransaction", "CancelTransaction", "CheckTransaction") and not t:
        return jsonify(err(rid, -31003, "Tranzaksiya topilmadi"))

    if method == "PerformTransaction":
        if t["state"] == 1:
            t["state"], t["perform_time"] = 2, now_ms
            payments.save_state()
            confirm_order(t["order_id"], "PAYME")
        elif t["state"] != 2:
            return jsonify(err(rid, -31008, "Tranzaksiya bekor qilingan"))
        return ok({"transaction": t["transaction"], "perform_time": t["perform_time"], "state": 2})

    if method == "CancelTransaction":
        if t["state"] in (1, 2):
            t["state"] = -1 if t["state"] == 1 else -2
            t["cancel_time"], t["reason"] = now_ms, params.get("reason")
            order = payments.get_order(t["order_id"])
            if order and order["status"] in ("PENDING", "CLAIMED"):
                payments.set_status(order, "CANCELLED")
            payments.save_state()
        return ok({"transaction": t["transaction"], "cancel_time": t["cancel_time"], "state": t["state"]})

    if method == "CheckTransaction":
        return ok({k: t[k] for k in ("create_time", "perform_time", "cancel_time",
                                     "transaction", "state", "reason")})

    if method == "GetStatement":
        frm, to = int(params.get("from", 0)), int(params.get("to", now_ms))
        return ok({"transactions": [
            {"id": x["id"], "time": x["time"], "amount": x["amount"],
             "account": {"order_id": x["order_id"]}, "create_time": x["create_time"],
             "perform_time": x["perform_time"], "cancel_time": x["cancel_time"],
             "transaction": x["transaction"], "state": x["state"], "reason": x["reason"]}
            for x in txns.values() if frm <= x["create_time"] <= to]})

    return jsonify(err(rid, -32601, "Metod topilmadi"))


def _require_paid_or_admin():
    """Eski to'g'ridan-to'g'ri chop etish endpointlari uchun himoya."""
    if payments.REQUIRE_PAYMENT and not payments.is_admin(request):
        return jsonify({
            "success": False, "payment_required": True,
            "message": "To'lov tasdiqlanmagan. Avval /api/order/create orqali buyurtma yarating."
        }), 402
    return None


def _resume_worker(order: dict):
    """Server qayta yonganda CUPS'ga allaqachon yuborilgan ishni kuzatishni davom ettiradi."""
    ok, reason = _wait_cups_job(order, order.get("printer", ""), int(order["cups_job"]))
    if ok:
        payments.set_status(order, "PRINTED", printed_at=time.time(), stuck=False, note="")
        payments.tg_send(f"✅ <b>#{order['id']} chop etildi</b> → {order.get('printer', '')} "
                         f"(server qayta ishga tushgandan keyin)\n💰 {order['amount']} so'm")
    else:
        _fail_order(order, reason)


def _resume_interrupted_orders():
    now = time.time()
    for o in list(payments.orders.values()):
        if now - o.get("paid_at", o.get("created_at", 0)) > 3 * 3600:
            continue
        if o.get("status") == "PRINTING" and o.get("cups_job") and o.get("printer"):
            logger.info(f"#{o['id']}: CUPS ishi #{o['cups_job']} kuzatuvi davom ettirilmoqda")
            threading.Thread(target=_resume_worker, args=(o,), daemon=True).start()
        elif o.get("status") in ("PAID", "PRINTING"):
            logger.info(f"#{o['id']}: to'langan, lekin chop etilmagan — navbatga qo'yildi")
            _start_print(o)


_workers_started = False

def start_background_workers():
    global _workers_started
    if _workers_started:
        return
    _workers_started = True
    payments.load_state()
    if payments.DEMO_AUTO_CONFIRM:
        logger.warning("DEMO_AUTO_CONFIRM=1: to'lovlar AVTOMATIK tasdiqlanadi — faqat lokal demo uchun!")
    _resume_interrupted_orders()
    if payments.telegram_enabled():
        payments.TelegramPoller(confirm_order, reject_order, reprint_order).start()
    else:
        logger.warning("Telegram sozlanmagan: to'lovlarni faqat Admin API orqali tasdiqlash mumkin.")
    if payments.REQUIRE_PAYMENT and not (payments.ADMIN_TOKEN or payments.telegram_enabled()):
        logger.error("DIQQAT: REQUIRE_PAYMENT_VERIFICATION=true, lekin ADMIN_TOKEN ham, Telegram ham yo'q — "
                     "hech bir buyurtmani tasdiqlab bo'lmaydi!")


# Modul yuklanganda (Gunicorn da ham) fon ishchilari ishga tushadi
start_background_workers()


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
    if not payments.is_admin(request):
        return jsonify({"success": False, "message": "Admin token noto'g'ri yoki sozlanmagan"}), 401
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
    if not payments.is_admin(request):
        return jsonify({"success": False, "message": "Admin token noto'g'ri yoki sozlanmagan"}), 401
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
    """Tanlangan shablonni chop etadi (faqat admin; mijozlar /api/order/create orqali)."""
    blocked = _require_paid_or_admin()
    if blocked:
        return blocked
    data        = request.get_json() or {}
    template_id = data.get("template_id", "")
    copies      = max(1, min(int(data.get("copies", 1)), MAX_COPIES))
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

    # ── Termal printer (XP-58) to'g'ridan-to'g'ri chop etish ──
    if routing.get("type") == "thermal":
        try:
            printer_service.print_to_thermal(file_path, copies=copies)
            msg = f"Shablon [{template['name']}] termal printerda muvaffaqiyatli chop etildi!"
        except Exception as e:
            logger.error(f"Termal shablon chop etish xatosi: {e}")
            return jsonify({"success": False, "message": f"Termal printer xatosi: {str(e)}"}), 500
    # CUPS orqali chop etish (Lazer / Rangli)
    elif shutil.which("lp"):
        try:
            ready_file = prepare_printable_file(file_path)  # DOCX → PDF (LibreOffice)
        except Exception as e:
            logger.error(f"Shablonni PDF ga aylantirishda xatolik: {e}")
            return jsonify({"success": False, "message": f"Shablonni tayyorlashda xatolik: {e}"}), 500
        cmd = ["lp", "-d", printer, "-n", str(copies),
               "-o", f"media={routing['media']}", str(ready_file)]
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


# ── Raspberry Pi Print Agent API (Bulut va Kiosk aloqasi) ──────
@app.route("/api/agent/queue", methods=["GET"])
def agent_get_queue():
    """Raspberry Pi agenti uchun chop etilishi kerak bo'lgan buyurtmalar navbati."""
    if not _agent_allowed(request):
        return _agent_denied()
    jobs = []
    for o in list(payments.orders.values()):
        if o.get("status") == "PAID" and o.get("ready_file"):
            jobs.append({
                "id": o["id"],
                "filename": o["filename"],
                "copies": o.get("copies", 1),
                "pages": o.get("pages", 1),
                "amount": o.get("amount", 0),
                "color_mode": o.get("color_mode", "gray"),
                "printer_type": o.get("printer_type", "laser_bw"),
                "orientation": o.get("orientation", "portrait"),
                "duplex": o.get("duplex", "one-sided"),
                "page_ranges": o.get("page_ranges", ""),
            })
    return jsonify({"success": True, "jobs": jobs})


@app.route("/api/dev/test_print", methods=["POST"])
def dev_test_print():
    """Dasturchi testi: To'lovsiz darhol test cheki/hujjatini navbatga qo'yadi (faqat admin)."""
    if not payments.is_admin(request):
        msg = ("Admin paroli noto'g'ri" if payments.ADMIN_TOKEN
               else "Serverda ADMIN_TOKEN o'rnatilmagan — sinov o'chiq")
        return jsonify({"success": False, "message": msg}), 401
    data = request.get_json(silent=True) or {}
    target = data.get("target", "thermal")  # "thermal" (XP-58) yoki "laser_bw" (Canon)
    order_id = uuid.uuid4().hex[:6].upper()

    # Dasturchi test buyurtmasi
    test_file = UPLOAD_FOLDER / f"dev_test_{order_id}.txt"
    test_file.write_text(f"SMART PRINTCHI TEST - {target}\nID: #{order_id}\nAuthor: Ravshanov Muhammad Ali", encoding="utf-8")

    order = {
        "id": order_id,
        "kind": "dev_test",
        "filename": f"Sinov_{target}.receipt" if target == "thermal" else "Sinov_Canon.pdf",
        "saved_path": str(test_file),
        "ready_file": str(test_file),
        "copies": 1,
        "pages": 1,
        "amount": 0,
        "color_mode": "gray",
        "printer_type": target,
        "orientation": "portrait",
        "duplex": "one-sided",
        "page_ranges": "",
        "status": "PAID",  # Darhol Raspberry Pi ga beriladi
        "created_at": time.time(),
        "updated_at": time.time(),
    }
    payments.add_order(order)
    logger.info(f"Dasturchi sinovi navbatga qo'yildi: #{order_id} ({target})")
    return jsonify({"success": True, "order_id": order_id, "message": f"{target} uchun test navbatga qo'yildi!"})


@app.route("/api/agent/download/<order_id>", methods=["GET"])
def agent_download_file(order_id):
    """Raspberry Pi agenti chop etish uchun tayyor PDF faylni yuklab oladi."""
    if not _agent_allowed(request):
        return _agent_denied()
    order = payments.get_order(order_id)
    if not order or not order.get("ready_file"):
        return jsonify({"success": False, "message": "Fayl topilmadi"}), 404
    ready_path = Path(order["ready_file"])
    if not ready_path.exists():
        return jsonify({"success": False, "message": "Fayl mavjud emas"}), 404
    # Kengaytma haqiqiy fayl turiga mos bo'lsin (CUPS turini nomidan aniqlaydi)
    suffix = ready_path.suffix.lower() or ".pdf"
    return send_file(str(ready_path), as_attachment=True, download_name=f"job_{order_id}{suffix}")


@app.route("/api/agent/status/<order_id>", methods=["POST"])
def agent_update_status(order_id):
    """Raspberry Pi agenti chop etish holatini xabar qiladi."""
    if not _agent_allowed(request):
        return _agent_denied()
    order = payments.get_order(order_id)
    if not order:
        return jsonify({"success": False, "message": "Buyurtma topilmadi"}), 404
    data = request.get_json(silent=True) or {}
    st = data.get("status")
    if st == "PRINTED":
        was_stuck = order.get("stuck")
        payments.set_status(order, "PRINTED", printed_at=time.time(), stuck=False, note="")
        payments.tg_send(f"✅ <b>#{order['id']} Raspberry Pi orqali chop etildi!</b>"
                         f"{' (kutishdan keyin)' if was_stuck else ''}\n💰 {order['amount']} so'm")
    elif st == "FAILED":
        _fail_order(order, data.get("error", "Chop etishda xatolik"))
    elif st == "PRINTING":
        stuck = bool(data.get("stuck"))
        if stuck and not order.get("stuck"):
            payments.tg_send(f"🟠 <b>#{order['id']} printerda kutib qoldi</b>\n"
                             f"Canon LBP3010 ga qog'oz soling yoki USB kabelni tekshiring — ish o'zi davom etadi.")
        payments.set_status(order, "PRINTING", stuck=stuck,
                            note=data.get("note") or "Printer qog'oz chiqarmoqda…")
    return jsonify({"success": True, "status": order["status"]})


# ── Zaxira: Render bepul tarifida disk vaqtinchalik. Pi agenti buyurtmalarni o'ziga
#    nusxalaydi va server qayta yonsa (BOOT_ID o'zgarsa) ularni qaytarib yuklaydi. ──
BACKUP_STATES = payments.ACTIVE_STATES + ("FAILED",)
BACKUP_HISTORY_S = 24 * 3600


def _backup_file_path(o: dict):
    p = o.get("saved_path")
    if not p:
        return None
    p = Path(p)
    # Shablonlar repoda turadi — ularni nusxalash shart emas
    try:
        if p.resolve().is_relative_to(TEMPLATES_DIR.resolve()):
            return None
    except Exception:
        pass
    return p if p.exists() else None


@app.route("/api/agent/backup", methods=["GET"])
def agent_backup():
    if not _agent_token_valid(request):
        return _agent_denied()
    now = time.time()
    out = []
    for o in list(payments.orders.values()):
        if o.get("status") in BACKUP_STATES or now - o.get("updated_at", 0) < BACKUP_HISTORY_S:
            item = dict(o)
            item["_has_file"] = bool(o.get("status") in BACKUP_STATES and _backup_file_path(o))
            out.append(item)
    return jsonify({"success": True, "boot_id": BOOT_ID, "orders": out[-300:]})


@app.route("/api/agent/backup/file/<order_id>", methods=["GET"])
def agent_backup_file(order_id):
    if not _agent_token_valid(request):
        return _agent_denied()
    order = payments.get_order(order_id)
    path = _backup_file_path(order) if order else None
    if not path:
        return jsonify({"success": False, "message": "Fayl topilmadi"}), 404
    return send_file(str(path), as_attachment=True, download_name=path.name)


@app.route("/api/agent/restore", methods=["POST"])
def agent_restore():
    """Pi'dagi zaxiradan buyurtmalarni tiklaydi. Serverda bor buyurtmalarga tegmaydi (idempotent)."""
    if not _agent_token_valid(request):
        return _agent_denied()
    try:
        items = json.loads(request.form.get("orders", "[]"))
    except Exception:
        return jsonify({"success": False, "message": "orders JSON noto'g'ri"}), 400
    restored, to_prepare = 0, []
    with payments._lock:
        for o in items:
            oid = str(o.get("id", "")).upper()
            if not oid or oid in payments.orders:
                continue
            o.pop("_has_file", None)
            up = request.files.get(f"file_{oid}")
            if up:
                name = secure_filename(Path(o.get("saved_path") or f"{oid}.bin").name) or f"{oid}.bin"
                dest = UPLOAD_FOLDER / name
                up.save(str(dest))
                was_same = o.get("ready_file") == o.get("saved_path")
                o["saved_path"] = str(dest)
                o["ready_file"] = str(dest) if was_same else ""
            elif o.get("status") in BACKUP_STATES and not (o.get("saved_path") and Path(o["saved_path"]).exists()):
                o["status"] = "FAILED"
                o["error"] = "Server qayta ishga tushdi va fayl tiklanmadi"
                o["ready_file"] = ""
            o["restored_at"] = time.time()
            payments.orders[oid] = o
            restored += 1
            if o.get("status") == "PAID" and not o.get("ready_file"):
                to_prepare.append(o)
        payments.save_state()
    for o in to_prepare:          # DOCX/rasmni qayta PDF ga aylantiradi, so'ng agent navbatiga
        threading.Thread(target=_start_print, args=(o,), daemon=True).start()
    if restored:
        logger.warning(f"Zaxiradan {restored} ta buyurtma tiklandi (Pi agenti)")
        payments.tg_send(f"♻️ Server qayta ishga tushdi: Pi zaxirasidan <b>{restored}</b> ta buyurtma tiklandi")
    return jsonify({"success": True, "restored": restored, "boot_id": BOOT_ID})


if __name__ == "__main__":
    logger.info("Smart Web-Printchi serveri ishga tushmoqda...")
    logger.info(f"Manzil: http://{SERVER_HOST}:{SERVER_PORT}")
    start_background_workers()
    app.run(host=SERVER_HOST, port=SERVER_PORT, debug=False)
