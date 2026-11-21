# Booking eSIM bot — uy serveri (Coolify) uchun
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    TZ=Asia/Tashkent \
    TRIP_HEADLESS=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

WORKDIR /app-src
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && playwright install --with-deps chromium
COPY . .

EXPOSE 8080
# Kod har ishga tushganda /data ga ko'chiriladi; baza, rasmlar, Trip.com profili
# esa /data da (Persistent Storage) saqlanib qoladi.
CMD ["sh", "-c", "mkdir -p /data && cp -a /app-src/. /data/ && cd /data && rm -f bot.pid && exec python main.py"]
