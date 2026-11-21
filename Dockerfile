# Smart Printchi - Cloud Web & Conversion Server
FROM python:3.11-slim

# LibreOffice va shriftlar (Word fayllarni PDF ga 0.3 soniyada aylantirish uchun)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice-writer-nogui \
    fonts-dejavu-core \
    fonts-freefont-ttf \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Bog'liqliklar
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Loyiha kodlari
COPY . .

# Papkalar
RUN mkdir -p uploads data/templates

# Port
EXPOSE 5000

ENV PYTHONUNBUFFERED=1
ENV IS_CLOUD_SERVER=1
ENV DEMO_AUTO_CONFIRM=1

# Gunicorn bilan yuqori tezlikda ishga tushirish (1 worker, 8 threads — barcha oqimlar bir xil xotirani ko'radi)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "120", "app:app"]
