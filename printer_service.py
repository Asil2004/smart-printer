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
    XP-58 IIL termal printer uchun moslashtirilgan (58mm, 203 DPI).
    Fayllarni (PDF, DOCX, Rasm) chop etishga tayyorlaydi va
    Linux CUPS tizimining 'lp' buyrug'i yoki ESC/POS orqali yuboradi.
    """

    def __init__(self, printer_name=None):
        self.printer_name = printer_name or config.PRINTER_NAME
        self.print_mode = config.PRINT_MODE  # "cups" yoki "escpos"

    # ──────────────────────────────────────────────────────
    # Printer holati
    # ──────────────────────────────────────────────────────

    def get_system_default_printer(self):
        """Tizimdagi standart printer nomini 'lpstat -d' orqali oladi."""
        try:
            res = subprocess.run(
                ["lpstat", "-d"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True
            )
            for line in res.stdout.splitlines():
                if "system default destination:" in line:
                    return line.split(":", 1)[1].strip()
        except Exception as e:
            logger.warning(f"Standart printerni aniqlashda xatolik: {e}")
        return ""

    # ──────────────────────────────────────────────────────
    # Fayl konvertatsiya (CUPS rejimi uchun)
    # ──────────────────────────────────────────────────────

    def convert_image_to_pdf(self, image_path: Path) -> Path:
        """
        Rasmni (PNG/JPG) termal 58mm formatdagi PDF fayliga aylantiradi.
        Rasmni 384px kenglikka (XP-58 IIL 203DPI standart) moslaydi.
        """
        output_pdf = image_path.with_suffix(".pdf")

        # XP-58 IIL: 58mm x 297mm lenta, 203 DPI
        # Kenglik: config.THERMAL_WIDTH_PX (= 384 px)
        # Balandlik: cheksiz (termal lenta uzunligi cheklangan emas)
        thermal_width = config.THERMAL_WIDTH_PX
        # Balandlik nisbati: A5 taxminan: 297mm/58mm ≈ 5.12 → 384*5.12 ≈ 1966px
        thermal_height = int(thermal_width * (297 / 58))

        with Image.open(image_path) as img:
            # RGBA → RGB konvertatsiya
            if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
                rgb_img = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "P":
                    img = img.convert("RGBA")
                rgb_img.paste(img, mask=img.split()[3] if len(img.split()) >= 4 else None)
            else:
                rgb_img = img.convert("RGB")

            # Rasmni termal kenglikka moslashtirish (proporsiyani saqlash)
            img_w, img_h = rgb_img.size
            ratio = min(thermal_width / img_w, thermal_height / img_h)
            new_w = int(img_w * ratio)
            new_h = int(img_h * ratio)

            resized_img = rgb_img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            # Termal qog'oz "kanvas" yaratish (oq fon)
            canvas = Image.new("RGB", (thermal_width, new_h + 40), (255, 255, 255))
            # Chapga hizalaish (termal printerlar chapdan boshlaydi)
            canvas.paste(resized_img, (0, 20))

            # 203 DPI da saqlash
            canvas.save(output_pdf, "PDF", resolution=float(config.THERMAL_DPI))

        logger.info(f"Rasm termal PDF ga o'tkazildi ({thermal_width}px kenglik): {output_pdf}")
        return output_pdf

    def convert_docx_to_pdf(self, docx_path: Path) -> Path:
        """
        DOCX faylni LibreOffice headless orqali PDF ga aylantiradi.
        """
        out_dir = docx_path.parent
        expected_pdf = out_dir / (docx_path.stem + ".pdf")

        libreoffice_cmd = shutil.which("libreoffice") or shutil.which("soffice")
        if not libreoffice_cmd:
            raise RuntimeError(
                "LibreOffice topilmadi! Iltimos, Raspberry Pi da o'rnating: sudo apt install -y libreoffice"
            )

        cmd = [
            libreoffice_cmd,
            "--headless",
            "--convert-to", "pdf",
            "--outdir", str(out_dir),
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

    # ──────────────────────────────────────────────────────
    # CUPS orqali chop etish
    # ──────────────────────────────────────────────────────

    def _print_via_cups(self, ready_file: Path, options: dict) -> dict:
        """CUPS 'lp' buyrug'i orqali XP-58 IIL termal printerga yuboradi."""
        copies = int(options.get("copies", 1))
        copies = max(1, min(copies, 10))

        page_ranges = str(options.get("page_ranges", "")).strip()

        printer = self.printer_name or self.get_system_default_printer()

        cmd = ["lp"]
        if printer:
            cmd.extend(["-d", printer])

        cmd.extend(["-n", str(copies)])

        # XP-58 IIL: 58mm termal lenta formati
        cmd.extend(["-o", f"media={config.DEFAULT_MEDIA}"])

        # Termal printer — har doim kulrang (rangli termal lentalar kam uchraydi)
        cmd.extend(["-o", "ColorModel=Gray"])

        # Bir tomonlama (termal printerda duplex yo'q)
        cmd.extend(["-o", "sides=one-sided"])

        # Portrait (termal uchun standart)
        cmd.extend(["-o", "portrait"])

        if page_ranges and page_ranges.lower() not in ("all", "barchasi"):
            cmd.extend(["-o", f"page-ranges={page_ranges}"])

        cmd.append(str(ready_file))

        cmd_str = " ".join(cmd)
        logger.info(f"CUPS chop etish buyrug'i: {cmd_str}")

        if not shutil.which("lp"):
            logger.warning("CUPS 'lp' buyrug'i topilmadi. Simulyatsiya rejimi.")
            return {
                "success": True,
                "message": f"[SIMULYATSIYA] {cmd_str}",
                "job_id": "SIMULATED-JOB-1"
            }

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if res.returncode != 0:
            error_msg = res.stderr.strip() or "Noma'lum xatolik"
            logger.error(f"CUPS xatolik: {error_msg}")
            raise RuntimeError(f"Chop etish xatosi: {error_msg}")

        output_msg = res.stdout.strip()
        logger.info(f"CUPS javobi: {output_msg}")
        return {"success": True, "message": output_msg, "job_output": output_msg}

    # ──────────────────────────────────────────────────────
    # Termal printer (XP-58 / 58mm) to'g'ridan-to'g'ri chop etish
    # ──────────────────────────────────────────────────────

    def print_to_thermal(self, target, copies: int = 1) -> dict:
        """
        XP-58 / 58mm termal printer uchun to'g'ridan-to'g'ri ESC/POS chop etish.
        Matn, PDF, DOCX va Rasmlarni 384px termal lentaga moslab chiqaradi.
        """
        import time
        import glob
        import uuid
        try:
            from escpos.printer import File
        except ImportError:
            raise RuntimeError("python-escpos o'rnatilmagan!")

        # /dev/usb/lp0 ruxsatlarini tekshirish
        dev_file = "/dev/usb/lp0"
        if not os.path.exists(dev_file):
            raise RuntimeError(f"Termal printer {dev_file} ulanmagan! USB kabelni tekshiring.")

        try:
            os.chmod(dev_file, 0o666)
        except Exception:
            pass

        printer = File(dev_file)
        copies = max(1, min(copies, 10))

        for _ in range(copies):
            # 1. Agar target matn bo'lsa (yoki .txt fayl)
            if isinstance(target, str) and (not Path(target).exists() or Path(target).suffix == ".txt"):
                text_content = target
                if Path(target).exists() and Path(target).suffix == ".txt":
                    text_content = Path(target).read_text(encoding="utf-8")
                    
                printer.set(align="center", bold=True)
                printer.text("================================\n")
                printer.text("       SMART WEB-PRINTCHI       \n")
                printer.text("================================\n\n")
                printer.set(align="left", bold=False)
                printer.text(text_content + "\n\n")
                printer.set(align="center", bold=False)
                printer.text("--------------------------------\n")
                printer.text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                printer.text("================================\n\n\n")
                printer.cut()
                continue

            # 2. Agar target fayl bo'lsa (PDF, DOCX, Rasm)
            fpath = Path(target)
            ready_pdf = fpath
            if fpath.suffix.lower() == ".docx":
                ready_pdf = self.convert_docx_to_pdf(fpath)

            if ready_pdf.suffix.lower() == ".pdf":
                tmp_prefix = f"/tmp/thermal_{uuid.uuid4().hex[:6]}"
                subprocess.run(["pdftoppm", "-png", "-r", "150", str(ready_pdf), tmp_prefix], check=True)
                pages = sorted(glob.glob(f"{tmp_prefix}-*.png"))

                printer.set(align="center", bold=True)
                printer.text("================================\n")
                printer.text("       SMART WEB-PRINTCHI       \n")
                printer.text("================================\n\n")

                for page in pages:
                    img = Image.open(page).convert("RGB")
                    w, h = img.size
                    new_w = 384
                    new_h = int(h * (384 / w))
                    img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                    bw_img = img.convert("1")
                    tmp_p = f"{tmp_prefix}_p.png"
                    bw_img.save(tmp_p)
                    printer.image(tmp_p, impl="bitImageColumn")
                    printer.text("\n")
                    Path(page).unlink(missing_ok=True)
                    Path(tmp_p).unlink(missing_ok=True)

                printer.set(align="center", bold=False)
                printer.text("\n--------------------------------\n")
                printer.text(time.strftime("%Y-%m-%d %H:%M:%S") + "\n")
                printer.text("================================\n\n\n")
                printer.cut()

            elif fpath.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                img = Image.open(fpath).convert("RGB")
                w, h = img.size
                new_w = 384
                new_h = int(h * (384 / w))
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
                bw_img = img.convert("1")
                tmp_p = f"/tmp/thermal_img_{uuid.uuid4().hex[:6]}.png"
                bw_img.save(tmp_p)

                printer.set(align="center", bold=True)
                printer.text("================================\n\n")
                printer.image(tmp_p, impl="bitImageColumn")
                printer.text("\n\n")
                printer.text("================================\n\n\n")
                printer.cut()
                Path(tmp_p).unlink(missing_ok=True)

        printer.close()
        return {
            "success": True,
            "message": f"Termal printerda muvaffaqiyatli chop etildi (x{copies})",
            "job_output": "thermal-direct"
        }

    # ──────────────────────────────────────────────────────
    # Asosiy chop etish funksiyasi
    # ──────────────────────────────────────────────────────

    def print_job(self, file_path: str, options: dict) -> dict:
        """
        Faylni chop etadi. PRINT_MODE sozlamasiga qarab CUPS yoki ESC/POS ishlatiladi.
        """
        if self.print_mode == "escpos" or options.get("printer_type") == "thermal":
            logger.info("Termal ESC/POS rejimida chop etilmoqda...")
            copies = int(options.get("copies", 1))
            return self.print_to_thermal(file_path, copies=copies)
        else:
            ready_file = self.prepare_file(file_path)
            logger.info("CUPS rejimida chop etilmoqda...")
            return self._print_via_cups(ready_file, options)

