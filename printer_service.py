import os
import shutil
import subprocess
import logging
from pathlib import Path
from PIL import Image

import config

logger = logging.getLogger("smart_printchi.printer")


class PrinterService:
    """
    CUPS va fayl konvertatsiya xizmati.
    Fayllarni (PDF, DOCX, Rasm) chop etishga tayyorlaydi va
    Linux CUPS tizimining 'lp' buyrug'i orqali yuboradi.
    """

    def __init__(self, printer_name=None):
        self.printer_name = printer_name or config.PRINTER_NAME

    def get_system_default_printer(self):
        """Tizimdagi standart printer nomini 'lpstat -d' orqali oladi."""
        try:
            res = subprocess.run(["lpstat", "-d"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            # Natija: 'system default destination: HP_LaserJet_1020'
            for line in res.stdout.splitlines():
                if "system default destination:" in line:
                    return line.split(":", 1)[1].strip()
        except Exception as e:
            logger.warning(f"Standart printerni aniqlashda xatolik: {e}")
        return ""

    def convert_image_to_pdf(self, image_path: Path) -> Path:
        """
        Rasmni (PNG/JPG) A4 formatidagi oq fonli PDF fayliga aylantiradi.
        Rasmni markazlashtiradi va proporsiyasini saqlaydi.
        """
        output_pdf = image_path.with_suffix(".pdf")
        
        # A4 o'lchami 300 DPI da: 2480 x 3508 piksel
        a4_width, a4_height = 2480, 3508
        
        with Image.open(image_path) as img:
            # RGBA bo'lsa RGB ga o'tkazish
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[3] if len(img.split()) >= 4 else None)
            else:
                rgb_img = img.convert("RGB")

            # Rasmni A4 chegaralariga moslashtirish
            img_w, img_h = rgb_img.size
            ratio = min(a4_width / img_w, a4_height / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)
            
            resized_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)
            
            # A4 oq qog'oz varag'ini yaratish
            canvas = Image.new("RGB", (a4_width, a4_height), (255, 255, 255))
            # Markazga qo'yish
            pos_x = (a4_width - new_w) // 2
            pos_y = (a4_height - new_h) // 2
            canvas.paste(resized_img, (pos_x, pos_y))
            
            canvas.save(output_pdf, "PDF", resolution=300.0)

        logger.info(f"Rasm muvaffaqiyatli PDF ga o'tkazildi: {output_pdf}")
        return output_pdf

    def convert_docx_to_pdf(self, docx_path: Path) -> Path:
        """
        DOCX faylni LibreOffice headless orqali PDF ga aylantiradi.
        """
        out_dir = docx_path.parent
        expected_pdf = out_dir / (docx_path.stem + ".pdf")

        # LibreOffice o'rnatilganligini tekshirish
        libreoffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
        if not libreoffice_cmd:
            raise RuntimeError(
                "LibreOffice topilmadi! Iltimos, Raspberry Pi da o'rnating: sudo apt install -y libreoffice"
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

    def prepare_file(self, file_path_str: str) -> Path:
        """
        Chop etish uchun kelgan faylni tekshiradi va kerak bo'lsa PDF ga aylantiradi.
        """
        path = Path(file_path_str)
        if not path.exists():
            raise FileNotFoundError(f"Fayl topilmadi: {file_path_str}")

        suffix = path.suffix.lower()
        if suffix == ".pdf":
            return path
        elif suffix == ".docx":
            return self.convert_docx_to_pdf(path)
        elif suffix in [".png", ".jpg", ".jpeg"]:
            return self.convert_image_to_pdf(path)
        else:
            raise ValueError(f"Qo'llab-quvvatlanmaydigan fayl formati: {suffix}")

    def print_job(self, file_path: str, options: dict) -> dict:
        """
        Faylni CUPS 'lp' buyrug'i orqali chop etadi.
        options parametrlari:
          - copies: int (1-10)
          - color_mode: 'gray' | 'color'
          - orientation: 'portrait' | 'landscape'
          - duplex: 'one-sided' | 'two-sided'
          - page_ranges: str (masalan: '1-3' yoki '')
        """
        ready_file = self.prepare_file(file_path)

        copies = int(options.get("copies", 1))
        copies = max(1, min(copies, 10))  # Cheklov 1 dan 10 gacha

        color_mode = options.get("color_mode", "gray")
        orientation = options.get("orientation", "portrait")
        duplex = options.get("duplex", "one-sided")
        page_ranges = str(options.get("page_ranges", "")).strip()

        # Printer nomini aniqlash
        printer = self.printer_name
        if not printer:
            printer = self.get_system_default_printer()

        # lp buyrug'i argumentlarini shakllantirish
        cmd = ["lp"]
        if printer:
            cmd.extend(["-d", printer])

        cmd.extend(["-n", str(copies)])
        cmd.extend(["-o", f"media={config.DEFAULT_MEDIA}"])

        # Rang sozlamasi
        if color_mode == "gray":
            cmd.extend(["-o", "ColorModel=Gray"])
        else:
            cmd.extend(["-o", "ColorModel=CMYK"])

        # Ikki tomonlama chop etish
        if duplex == "two-sided":
            cmd.extend(["-o", "sides=two-sided-long-edge"])
        else:
            cmd.extend(["-o", "sides=one-sided"])

        # Orientatsiya
        if orientation == "landscape":
            cmd.extend(["-o", "landscape"])
        else:
            cmd.extend(["-o", "portrait"])

        # Sahifalar oralig'i (agar kiritilgan bo'lsa)
        if page_ranges and page_ranges.lower() != "all" and page_ranges.lower() != "barchasi":
            cmd.extend(["-o", f"page-ranges={page_ranges}"])

        # Fayl yo'lini qo'shish
        cmd.append(str(ready_file))

        cmd_str = " ".join(cmd)
        logger.info(f"Chop etish buyrug'i: {cmd_str}")

        # Agar tizimda 'lp' buyrug'i bo'lmasa (masalan Windows sinov paytida)
        if not shutil.which("lp"):
            logger.warning("CUPS 'lp' buyrug'i topilmadi. Simulyatsiya rejimida chop etildi deb hisoblandi.")
            return {
                "success": True,
                "message": f"Simulyatsiya rejimida muvaffaqiyatli bajarildi: {cmd_str}",
                "job_id": "SIMULATED-JOB-1"
            }

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            error_msg = res.stderr.strip() or "Noma'lum xatolik"
            logger.error(f"CUPS chop etishda xatolik: {error_msg}")
            raise RuntimeError(f"Chop etish xatosi: {error_msg}")

        # Chiqish: "request id is HP_LaserJet_1020-42 (1 file(s))"
        output_msg = res.stdout.strip()
        logger.info(f"Printer javobi: {output_msg}")
        return {
            "success": True,
            "message": output_msg,
            "job_output": output_msg
        }
