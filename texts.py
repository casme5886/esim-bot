"""Bot matnlari va formatlash yordamchilari."""


def money(x):
    return f"{int(x):,}".replace(",", " ") + " so'm"


def gb(data_gb, daily=0):
    if not data_gb:
        return "Cheksiz"
    return f"{data_gb:g} GB/kun" if daily else f"{data_gb:g} GB"


def package_line(p):
    return f"{p['flag']} {p['country']} — {gb(p['data_gb'], p.get('daily'))} / {p['days']} kun — {money(p['price'])}"


WELCOME = (
    "👋 Assalomu alaykum, <b>{name}</b>!\n\n"
    "🌍 <b>Booking eSIM</b> — chet elga sayohat uchun eSIM.\n"
    "• SIM karta almashtirmasdan internet\n"
    "• 60 soniyada QR kod telegramingizga keladi\n"
    "• Click / Payme yoki karta orqali to'lov\n\n"
    "Pastdagi tugma yoki chap pastdagi <b>eSIM</b> tugmasi orqali do'konni oching."
)

HELP = (
    "ℹ️ <b>eSIM qanday ishlaydi?</b>\n\n"
    "1. Telefoningiz eSIM'ni qo'llab-quvvatlashini tekshiring "
    "(iPhone XS va yangilari, Samsung S20+, Pixel 3+ va boshqalar). "
    "Tekshirish: <code>*#06#</code> terganda <b>EID</b> raqami chiqsa — eSIM bor.\n"
    "2. Botda davlat va paketni tanlang, to'lovni qiling.\n"
    "3. QR kodni olasiz — uni <b>sayohatdan oldin, Wi-Fi'da</b> o'rnating.\n"
    "4. Manzilga yetgach, eSIM liniyasida <b>Data Roaming</b>ni yoqing.\n\n"
    "❗ QR kodni faqat bir marta o'rnatish mumkin — o'chirib yubormang."
)

INSTALL_GUIDE = (
    "📲 <b>O'rnatish yo'riqnomasi</b>\n\n"
    "<b>iPhone:</b> Sozlamalar → Mobil aloqa → eSIM qo'shish → QR kodni skanerlash\n"
    "<b>Android (Samsung):</b> Sozlamalar → Ulanishlar → SIM menejeri → eSIM qo'shish → QR kod\n"
    "<b>Pixel:</b> Sozlamalar → Tarmoq va internet → SIM → eSIM yuklab olish\n\n"
    "QR kodni boshqa telefon/kompyuter ekranidan skanerlang yoki rasmni saqlab, "
    "\"Rasmdan skanerlash\" tugmasidan foydalaning.\n\n"
    "✈️ Manzilga yetgach: shu eSIM liniyasini <b>mobil internet uchun</b> tanlang va "
    "<b>Data Roaming</b>ni yoqing."
)
