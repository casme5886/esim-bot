"""Sozlamalar .env faylidan o'qiladi."""
import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
# Bir nechta admin bo'lsa vergul bilan: 123456,789012
ADMIN_IDS = {int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x}

# Click/Payme orqali Telegram to'lovi (BotFather -> Payments). Bo'sh bo'lsa karta orqali qo'lda to'lov ishlaydi.
PAYMENT_PROVIDER_TOKEN = os.getenv("PAYMENT_PROVIDER_TOKEN", "")   # umumiy (eski) — Click yoki Payme
# @BotFather -> Payments: alohida Click va Payme tokenlari (ikkalasi ham bo'lsa mijoz tanlaydi)
CLICK_PROVIDER_TOKEN = os.getenv("CLICK_PROVIDER_TOKEN", "")
PAYME_PROVIDER_TOKEN = os.getenv("PAYME_PROVIDER_TOKEN", "")

# Qo'lda to'lov uchun karta ma'lumotlari
CARD_NUMBER = os.getenv("CARD_NUMBER", "8600 0000 0000 0000")
CARD_HOLDER = os.getenv("CARD_HOLDER", "ISM FAMILIYA")

SUPPORT_USERNAME = os.getenv("SUPPORT_USERNAME", "")  # masalan: esim_on_support
DB_PATH = os.getenv("DB_PATH", "esim.db")

# Mini App: veb-server porti va tashqi HTTPS manzil (cloudflared/ngrok yoki server domeni)
WEB_PORT = int(os.getenv("WEB_PORT", "8080"))
WEBAPP_URL = os.getenv("WEBAPP_URL", "").rstrip("/")  # masalan: https://abc.trycloudflare.com

if not BOT_TOKEN:
    raise SystemExit("BOT_TOKEN .env faylida ko'rsatilmagan")
if not ADMIN_IDS:
    raise SystemExit("ADMIN_IDS .env faylida ko'rsatilmagan")

# Trip.com avto-xarid
TRIP_AUTOBUY = os.getenv("TRIP_AUTOBUY", "1") == "1"        # 0 = o'chirish (qo'lda ishlash)
TRIP_DAILY_LIMIT = int(os.getenv("TRIP_DAILY_LIMIT", "100"))  # kuniga ko'pi bilan nechta xarid
TRIP_PRICE_TOLERANCE = float(os.getenv("TRIP_PRICE_TOLERANCE", "1.3"))  # tannarxdan necha baravar qimmat bo'lsa to'xtasin
TRIP_HEADLESS = os.getenv("TRIP_HEADLESS", "0") == "1"      # 1 = brauzer oynasi ko'rinmasin

# Botning username'i (@ belgisisiz) — PDF vaucher pastidagi QR va havola uchun
BOT_USERNAME = os.getenv("BOT_USERNAME", "Booking_eSIM_bot").lstrip("@")
