"""
Admin katalogi: shablon rasmlari (preview) va promokodlar ombori.

- Preview: har qanday formatdagi shablonning 1-sahifasi JPG rasmga aylantiriladi.
    PDF          → pypdfium2
    rasm         → Pillow
    DOCX/ODT/... → LibreOffice → PDF → pypdfium2
    LibreOffice yo'q bo'lsa (masalan Windows'da lokal demo) — DOCX/TXT matni oq varaqqa chiziladi,
    boshqa formatlar uchun fayl turini ko'rsatuvchi varaq rasmi.
- Promokodlar: data/promo_codes.json (admin paneldan yaratiladi) + PROMO_CODES env (faqat o'qish).
"""
import json
import logging
import secrets
import threading
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger("SmartPrintchi")

BASE_DIR = Path(__file__).resolve().parent
PREVIEW_WIDTH = 640
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tif", ".tiff"}
TEXT_EXTS = {".txt", ".md", ".csv"}

# ─────────────────────────────────────────────────────────────
# Preview
# ─────────────────────────────────────────────────────────────
_preview_locks: dict = {}
_preview_locks_guard = threading.Lock()


def _lock_for(key: str) -> threading.Lock:
    with _preview_locks_guard:
        return _preview_locks.setdefault(key, threading.Lock())


def _font(size: int):
    for name in ("DejaVuSans.ttf", "arial.ttf", "Arial.ttf", "FreeSans.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size=size)
    except TypeError:
        return ImageFont.load_default()


def _a4_canvas() -> Image.Image:
    return Image.new("RGB", (PREVIEW_WIDTH, int(PREVIEW_WIDTH * 297 / 210)), "white")


def _render_pdf(pdf_path: Path) -> Image.Image:
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page = pdf[0]
        w, _ = page.get_size()
        img = page.render(scale=PREVIEW_WIDTH / max(w, 1)).to_pil()
        page.close()
    finally:
        pdf.close()
    return img.convert("RGB")


def _render_image(path: Path) -> Image.Image:
    with Image.open(path) as im:
        im.seek(0)
        if im.mode in ("RGBA", "LA", "P"):
            im = im.convert("RGBA")
            bg = Image.new("RGB", im.size, "white")
            bg.paste(im, mask=im.split()[3])
            im = bg
        else:
            im = im.convert("RGB")
        im.thumbnail((PREVIEW_WIDTH, PREVIEW_WIDTH * 2))
        return im.copy()


def _wrap(draw, text: str, font, width: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= width:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines or [""]


def _render_text_page(paragraphs: list) -> Image.Image:
    """LibreOffice yo'q joyda: hujjat matnini oq varaqqa chizadi (taxminiy ko'rinish)."""
    img = _a4_canvas()
    d = ImageDraw.Draw(img)
    margin, y = 56, 64
    body, head = _font(15), _font(19)
    for para in paragraphs:
        align, bold, text = para.get("align", "left"), para.get("bold"), para.get("text", "")
        font = head if bold else body
        if not text.strip():
            y += 12
            continue
        for line in _wrap(d, text, font, img.width - 2 * margin):
            lw = d.textlength(line, font=font)
            x = (img.width - lw) / 2 if align == "center" else (img.width - margin - lw if align == "right" else margin)
            d.text((x, y), line, fill="#1B1F23", font=font)
            y += int(font.size * 1.45) if hasattr(font, "size") else 20
            if y > img.height - margin:
                return img
        y += 6
    return img


def _docx_paragraphs(path: Path) -> list:
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    doc = Document(str(path))
    out = []
    for p in doc.paragraphs:
        a = p.alignment
        align = "center" if a == WD_ALIGN_PARAGRAPH.CENTER else ("right" if a == WD_ALIGN_PARAGRAPH.RIGHT else "left")
        bold = bool(p.runs) and all(r.bold for r in p.runs if r.text.strip())
        out.append({"text": p.text, "align": align, "bold": bold})
    return out


def _render_placeholder(ext: str, name: str) -> Image.Image:
    img = _a4_canvas()
    d = ImageDraw.Draw(img)
    cx = img.width // 2
    d.rounded_rectangle((cx - 90, 260, cx + 90, 340), radius=40, fill="#1B1F23")
    f = _font(34)
    label = (ext.lstrip(".") or "FAYL").upper()[:5]
    d.text((cx - d.textlength(label, font=f) / 2, 280), label, fill="#C6F36B", font=f)
    nf = _font(22)
    y = 380
    for line in _wrap(d, name, nf, img.width - 120)[:3]:
        d.text((cx - d.textlength(line, font=nf) / 2, y), line, fill="#1B1F23", font=nf)
        y += 32
    return img


def render_preview(src: Path, out: Path, name: str = "", to_pdf=None) -> Path:
    """`src` ning 1-sahifasini `out` (JPG) ga chizadi. `to_pdf(path) -> Path` — LibreOffice konvertori."""
    src = Path(src)
    ext = src.suffix.lower()
    img = None
    try:
        if ext == ".pdf":
            img = _render_pdf(src)
        elif ext in IMAGE_EXTS:
            img = _render_image(src)
        else:
            if to_pdf is not None:
                try:
                    img = _render_pdf(to_pdf(src))
                except Exception as e:
                    logger.info(f"Preview: LibreOffice orqali bo'lmadi ({src.name}): {e}")
            if img is None and ext == ".docx":
                img = _render_text_page(_docx_paragraphs(src))
            if img is None and ext in TEXT_EXTS:
                text = src.read_text(encoding="utf-8", errors="replace")
                img = _render_text_page([{"text": t} for t in text.splitlines()[:80]])
    except Exception as e:
        logger.warning(f"Preview yaratib bo'lmadi ({src.name}): {e}")
    if img is None:
        img = _render_placeholder(ext, name or src.stem)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(".tmp.jpg")
    img.save(tmp, "JPEG", quality=82, optimize=True)
    tmp.replace(out)
    return out


def ensure_preview(src: Path, out: Path, name: str = "", to_pdf=None) -> Path:
    """Preview mavjud va fayldan yangi bo'lsa — o'shani, aks holda yaratadi (bir vaqtda bitta)."""
    with _lock_for(str(out)):
        if out.exists() and (not src.exists() or out.stat().st_mtime >= src.stat().st_mtime):
            return out
        return render_preview(src, out, name, to_pdf)


# ─────────────────────────────────────────────────────────────
# Promokodlar
# ─────────────────────────────────────────────────────────────
PROMO_FILE = BASE_DIR / "data" / "promo_codes.json"
_promo_lock = threading.Lock()
_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # 0/O, 1/I adashmasligi uchun


def load_promos() -> dict:
    try:
        data = json.loads(PROMO_FILE.read_text(encoding="utf-8"))
        return {str(k).upper(): v for k, v in data.items()}
    except FileNotFoundError:
        return {}
    except Exception as e:
        logger.error(f"promo_codes.json o'qilmadi: {e}")
        return {}


def save_promos(promos: dict):
    PROMO_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = PROMO_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(promos, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(PROMO_FILE)


def new_code(length: int = 8) -> str:
    return "".join(secrets.choice(_CODE_ALPHABET) for _ in range(length))


def normalize_code(code: str) -> str:
    return "".join(ch for ch in str(code).upper() if ch.isalnum() or ch in "-_")[:40]


def create_promo(code: str, percent: int, max_uses: int, days: int, note: str = "") -> dict:
    with _promo_lock:
        promos = load_promos()
        code = normalize_code(code) if code else ""
        if not code:
            code = new_code()
            while code in promos:
                code = new_code()
        if code in promos:
            raise ValueError("Bunday promokod allaqachon bor")
        item = {
            "percent": max(1, min(100, int(percent))),
            "max_uses": max(0, int(max_uses)),
            "expires_at": (time.time() + int(days) * 86400) if int(days) > 0 else 0,
            "created_at": time.time(),
            "note": str(note or "")[:80],
        }
        promos[code] = item
        save_promos(promos)
        return {"code": code, **item}


def delete_promo(code: str) -> bool:
    with _promo_lock:
        promos = load_promos()
        if normalize_code(code) not in promos:
            return False
        promos.pop(normalize_code(code))
        save_promos(promos)
        return True


def merge_promos(items: dict) -> int:
    """Zaxiradan tiklash: serverda yo'q kodlarni qo'shadi."""
    with _promo_lock:
        promos = load_promos()
        added = 0
        for code, item in (items or {}).items():
            code = normalize_code(code)
            if code and code not in promos and isinstance(item, dict):
                promos[code] = item
                added += 1
        if added:
            save_promos(promos)
        return added
