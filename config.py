import os
from pathlib import Path

# Loyihaning asosiy yo'llari
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_FOLDER = BASE_DIR / "uploads"
UPLOAD_FOLDER.mkdir(exist_ok=True)

# Veb-server sozlamalari
SERVER_HOST = os.environ.get("SERVER_HOST", "0.0.0.0")
SERVER_PORT = int(os.environ.get("SERVER_PORT", 5000))
SECRET_KEY = os.environ.get("SECRET_KEY", "smart-printchi-secret-key-2026")
MAX_CONTENT_LENGTH = 64 * 1024 * 1024  # 64 MB

# Ruxsat etilgan fayl turlari
ALLOWED_EXTENSIONS = {"pdf", "docx", "png", "jpg", "jpeg"}

# Hardware: GPIO sozlamalari
BUTTON_GPIO_PIN = int(os.environ.get("BUTTON_GPIO_PIN", 17))
BUTTON_TIMEOUT = int(os.environ.get("BUTTON_TIMEOUT", 60))  # soniya

# Hardware: I2C LCD sozlamalari
I2C_BUS = int(os.environ.get("I2C_BUS", 1))
# LCD manzillari: odatda 0x27 yoki 0x3F bo'ladi (avtomatik tekshiriladi)
POSSIBLE_LCD_ADDRESSES = [0x27, 0x3F]
LCD_COLS = 16  # LCD1602 uchun 16, LCD2004 uchun 20
LCD_ROWS = 2   # LCD1602 uchun 2, LCD2004 uchun 4

# CUPS Printer sozlamalari
# Agar printer nomi bo'sh qoldirilsa, tizimdagi standart (default) printer olinadi
PRINTER_NAME = os.environ.get("PRINTER_NAME", "")
DEFAULT_MEDIA = "A4"

# Chop etishdan so'ng fayllarni tozalash (saqlash vaqti soniyalarda)
AUTO_CLEANUP_SECONDS = 300  # 5 daqiqadan so'ng yuklangan faylni o'chirish
