"""
generate_templates.py — Tayyor shablon PDF larni yaratish
==========================================================
python-docx bilan standart akademik va rasmiy shablonlar yaratadi.
Raspberry Pi da bir marta ishga tushiring:
  python3 generate_templates.py
"""

import sys
from pathlib import Path

try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

try:
    from docx import Document
    from docx.shared import Pt, Cm, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    print("❌ python-docx o'rnatilmagan: pip install python-docx")
    sys.exit(1)

OUT = Path(__file__).parent / "templates_files"
OUT.mkdir(exist_ok=True)


def _new_doc():
    doc = Document()
    sec = doc.sections[0]
    sec.page_width    = Cm(21)
    sec.page_height   = Cm(29.7)
    sec.top_margin    = Cm(2.0)
    sec.bottom_margin = Cm(2.0)
    sec.left_margin   = Cm(3.0)
    sec.right_margin  = Cm(1.5)
    style = doc.styles["Normal"]
    style.font.name = "Times New Roman"
    style.font.size = Pt(12)
    return doc


def _para(doc, text="", bold=False, size=12, align="left", space_before=0, space_after=6):
    p   = doc.add_paragraph()
    run = p.add_run(text)
    run.font.name = "Times New Roman"
    run.font.size = Pt(size)
    run.bold      = bold
    aligns = {
        "left":    WD_ALIGN_PARAGRAPH.LEFT,
        "center":  WD_ALIGN_PARAGRAPH.CENTER,
        "right":   WD_ALIGN_PARAGRAPH.RIGHT,
        "justify": WD_ALIGN_PARAGRAPH.JUSTIFY,
    }
    p.alignment = aligns.get(align, WD_ALIGN_PARAGRAPH.LEFT)
    p.paragraph_format.space_before = Pt(space_before)
    p.paragraph_format.space_after  = Pt(space_after)
    return p


def _line(doc):
    _para(doc, "─" * 60, size=9, align="center", space_before=0, space_after=0)


# ──────────────────────────────────────────────────────────
# 1. Mustaqil Ish Muqovasi
# ──────────────────────────────────────────────────────────
def gen_mustaqil_yuzi():
    doc = _new_doc()

    _para(doc, "O'ZBEKISTON RESPUBLIKASI OLIY TA'LIM, FAN VA", bold=True, align="center", size=11)
    _para(doc, "INNOVATSIYALAR VAZIRLIGI", bold=True, align="center", size=11, space_after=2)
    _line(doc)
    _para(doc, "_" * 40, align="center", size=12, space_before=4)
    _para(doc, "(Universitet nomi)", align="center", size=10, space_after=2)
    _para(doc, "_" * 30 + " FAKULTETI", align="center", size=12)
    _para(doc, "_" * 30 + " KAFEDRASI", align="center", size=12, space_after=20)

    _para(doc, "MUSTAQIL ISH", bold=True, align="center", size=16, space_before=20)
    _para(doc, "Mavzu:", bold=True, align="center", size=13, space_before=10)
    _para(doc, '"_' * 25 + '"', align="center", size=13, space_after=20)

    _para(doc, "Fan: " + "_" * 30, align="left", size=12, space_before=20)
    _para(doc, "Bajardi: " + "_" * 25, align="left", size=12, space_after=2)
    _para(doc, "Guruh: " + "_" * 28, align="left", size=12, space_after=2)
    _para(doc, "Qabul qildi: " + "_" * 22, align="left", size=12, space_after=2)
    _para(doc, "Baho: " + "_" * 30, align="left", size=12, space_after=40)

    _line(doc)
    _para(doc, "Toshkent — " + str(__import__("datetime").date.today().year),
          align="center", size=12, space_before=10)

    path = OUT / "mustaqil_yuzi.docx"
    doc.save(str(path))
    print(f"✅ {path.name}")


# ──────────────────────────────────────────────────────────
# 2. Laboratoriya Ishi Muqovasi
# ──────────────────────────────────────────────────────────
def gen_laboratoriya_yuzi():
    doc = _new_doc()

    _para(doc, "O'ZBEKISTON RESPUBLIKASI", bold=True, align="center", size=11)
    _para(doc, "_" * 40, align="center", size=12, space_before=4)
    _para(doc, "(Universitet nomi)", align="center", size=10, space_after=2)
    _para(doc, "_" * 30 + " KAFEDRASI", align="center", size=12, space_after=20)

    _para(doc, "LABORATORIYA ISHI", bold=True, align="center", size=16, space_before=20)
    _para(doc, "№ ___", bold=True, align="center", size=14, space_before=4)
    _para(doc, "Mavzu:", bold=True, align="center", size=13, space_before=10)
    _para(doc, '"_' * 25 + '"', align="center", size=13, space_after=20)

    _para(doc, "Fan: " + "_" * 30, align="left", size=12, space_before=20)
    _para(doc, "Bajardi: " + "_" * 25, align="left", size=12, space_after=2)
    _para(doc, "Guruh: " + "_" * 28, align="left", size=12, space_after=2)
    _para(doc, "Qabul qildi: " + "_" * 22, align="left", size=12, space_after=2)
    _para(doc, "Sana: " + "_" * 30, align="left", size=12, space_after=40)

    _line(doc)
    _para(doc, str(__import__("datetime").date.today().year),
          align="center", size=12, space_before=10)

    path = OUT / "laboratoriya_yuzi.docx"
    doc.save(str(path))
    print(f"✅ {path.name}")


# ──────────────────────────────────────────────────────────
# 3. Ariza blanki
# ──────────────────────────────────────────────────────────
def gen_ariza_blank():
    doc = _new_doc()

    # Yuqori o'ng burchak
    _para(doc, "_" * 30, align="right", size=12)
    _para(doc, "(Lavozim va familiya)", align="right", size=10, space_after=2)
    _para(doc, "_" * 30, align="right", size=12)
    _para(doc, "(F.I.O.)", align="right", size=10, space_after=20)

    _para(doc, "ARIZA", bold=True, align="center", size=16, space_before=20, space_after=20)

    # Asosiy matn
    for _ in range(8):
        _para(doc, "_" * 65, align="justify", size=12, space_after=4)

    _para(doc, "", space_before=20)
    _para(doc, "Sana: «___» _________ 20___ y.",  align="left", size=12, space_before=20)
    _para(doc, "Imzo: _____________",              align="left", size=12, space_after=2)

    path = OUT / "ariza_blank.docx"
    doc.save(str(path))
    print(f"✅ {path.name}")


# ──────────────────────────────────────────────────────────
# 4. Qayta o'zlashtirish varaqasi
# ──────────────────────────────────────────────────────────
def gen_qayta_ozlashtirish():
    doc = _new_doc()

    _para(doc, "_" * 30, align="right", size=12)
    _para(doc, "Dekan / O'quv bo'limi boshlig'iga", align="right", size=10, space_after=2)
    _para(doc, "_" * 30, align="right", size=12)
    _para(doc, "(F.I.O.)", align="right", size=10, space_after=20)

    _para(doc, "ARIZA", bold=True, align="center", size=16, space_before=20)
    _para(doc, "(Qayta o'zlashtirish to'g'risida)", align="center", size=11, space_after=20)

    _para(doc, "Men, _____________________________ (F.I.O.),", align="justify", size=12)
    _para(doc, "_____ - kurs, _______ guruh talabasi,", align="justify", size=12)
    _para(doc, "\"___________________________\" fanidan", align="justify", size=12)
    _para(doc, "qayta o'zlashtirish imtihonini topshirishim uchun", align="justify", size=12)
    _para(doc, "ruxsat berishingizni so'rayman.", align="justify", size=12)
    _para(doc, "", space_before=4)
    _para(doc, "Sabab: " + "_" * 50, align="justify", size=12)
    for _ in range(3):
        _para(doc, "_" * 65, align="justify", size=12, space_after=4)

    _para(doc, "", space_before=20)
    _para(doc, "Sana: «___» _________ 20___ y.",  align="left", size=12, space_before=20)
    _para(doc, "Imzo: _____________",              align="left", size=12)

    path = OUT / "qayta_ozlashtirish.docx"
    doc.save(str(path))
    print(f"✅ {path.name}")


# ──────────────────────────────────────────────────────────
# 5. Dalolatnoma blanki
# ──────────────────────────────────────────────────────────
def gen_dalolatnoma():
    doc = _new_doc()

    _para(doc, "TASDIQLANDI", bold=True, align="right", size=12)
    _para(doc, "Rahbar: ______________",           align="right", size=12, space_after=2)
    _para(doc, "«___» _______ 20___ y.",           align="right", size=12, space_after=20)

    _para(doc, "DALOLATNOMA", bold=True, align="center", size=16, space_before=20)
    _para(doc, "№ _____",                          align="center", size=12)
    _para(doc, "«___» _________ 20___ yil",        align="center", size=12, space_after=20)

    _para(doc, "Biz, quyida imzo qo'ygan komissiya a'zolari:", align="justify", size=12)
    for i in range(1, 4):
        _para(doc, f"{i}. ________________________________________", align="justify", size=12, space_after=2)

    _para(doc, "ushbu dalolatnomani tuzib, quyidagilarni aniqladik:", align="justify", size=12, space_before=10)
    for _ in range(5):
        _para(doc, "_" * 65, align="justify", size=12, space_after=4)

    _para(doc, "Xulosa:", bold=True, align="left", size=12, space_before=10)
    for _ in range(3):
        _para(doc, "_" * 65, align="justify", size=12, space_after=4)

    _para(doc, "Imzolar:", bold=True, align="left", size=12, space_before=15)
    for i in range(1, 4):
        _para(doc, f"{i}. _________________   ________________", align="left", size=12, space_after=2)

    path = OUT / "dalolatnoma.docx"
    doc.save(str(path))
    print(f"✅ {path.name}")


# ──────────────────────────────────────────────────────────
# templates.json ni yangilash
# ──────────────────────────────────────────────────────────
def update_templates_json():
    import json
    json_path = Path(__file__).parent / "template_data" / "templates.json"
    json_path.parent.mkdir(exist_ok=True)

    new_entries = [
        {
            "id": "mustaqil_yuzi",
            "name": "Mustaqil Ish Yuzi",
            "description": "Akademik mustaqil ish uchun standart muqova sahifasi",
            "category": "academic",
            "pages": 1,
            "preview": "",
            "file": "mustaqil_yuzi.docx",
            "price_per_page": 500,
            "color": False,
            "tags": ["mustaqil ish", "muqova", "akademik"]
        },
        {
            "id": "laboratoriya_yuzi",
            "name": "Laboratoriya Ishi Yuzi",
            "description": "Laboratoriya ishi uchun standart muqova",
            "category": "academic",
            "pages": 1,
            "preview": "",
            "file": "laboratoriya_yuzi.docx",
            "price_per_page": 500,
            "color": False,
            "tags": ["laboratoriya", "muqova", "akademik"]
        },
        {
            "id": "ariza_blank",
            "name": "Ariza Blanki",
            "description": "To'ldiriladigan bo'sh ariza blanki",
            "category": "official",
            "pages": 1,
            "preview": "",
            "file": "ariza_blank.docx",
            "price_per_page": 500,
            "color": False,
            "tags": ["ariza", "blank", "rasmiy"]
        },
        {
            "id": "qayta_ozlashtirish",
            "name": "Qayta O'zlashtirish",
            "description": "Qayta o'zlashtirish imtihoni uchun ariza blanki",
            "category": "academic",
            "pages": 1,
            "preview": "",
            "file": "qayta_ozlashtirish.docx",
            "price_per_page": 500,
            "color": False,
            "tags": ["qayta", "imtihon", "akademik"]
        },
        {
            "id": "dalolatnoma",
            "name": "Dalolatnoma Blanki",
            "description": "Rasmiy dalolatnoma (akt) blanki",
            "category": "official",
            "pages": 1,
            "preview": "",
            "file": "dalolatnoma.docx",
            "price_per_page": 500,
            "color": False,
            "tags": ["dalolatnoma", "akt", "rasmiy"]
        },
    ]

    # Mavjud custom shablonlarni saqlash (faqat auto-generate qilinganlarni almashtirish)
    existing = []
    if json_path.exists():
        with open(json_path, "r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_ids = {e["id"] for e in new_entries}
    kept = [e for e in existing if e.get("id") not in existing_ids]
    final = new_entries + kept

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"✅ templates.json yangilandi ({len(final)} ta shablon)")


if __name__ == "__main__":
    print("🖨️  Tayyor shablonlar generatsiyasi...\n")
    gen_mustaqil_yuzi()
    gen_laboratoriya_yuzi()
    gen_ariza_blank()
    gen_qayta_ozlashtirish()
    gen_dalolatnoma()
    update_templates_json()
    print("\n✅ Barcha shablonlar yaratildi!")
    print(f"📁 Joylashuv: {OUT}")
