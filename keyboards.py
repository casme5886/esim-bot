from aiogram.types import (
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton, WebAppInfo,
    ReplyKeyboardRemove,
)
import i18n
from config import WEBAPP_URL


def webapp_url(lang: str | None = None) -> str:
    """Mini App manzili; til parametri bilan (Mini App shu tilda ochiladi)."""
    if not WEBAPP_URL or not lang:
        return WEBAPP_URL
    return WEBAPP_URL + ("&" if "?" in WEBAPP_URL else "?") + f"lang={lang}"


def lang_kb(back_lang: str | None = None):
    """Til tanlash tugmalari (2 tadan qatorda). back_lang — "‹ Orqaga" tugmasi (salomlashuv xabaridan ochilganda)."""
    rows, row = [], []
    for code in i18n.LANGS:
        row.append(InlineKeyboardButton(text=i18n.lang_name(code), callback_data=f"lang:{code}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    if back_lang:
        rows.append([InlineKeyboardButton(text=i18n.t(back_lang, "back_btn"), callback_data="lang:back")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def open_shop_kb(lang: str):
    """/start xabari ostidagi katta tugma + til tugmasi."""
    rows = []
    if WEBAPP_URL:
        rows.append([InlineKeyboardButton(text=i18n.t(lang, "open_shop"), web_app=WebAppInfo(url=webapp_url(lang)))])
    rows.append([InlineKeyboardButton(text=i18n.t(lang, "lang_btn"), callback_data="lang:menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


BTN_BUY = "🌍 eSIM sotib olish"
BTN_ORDERS = "📦 Buyurtmalarim"
BTN_HELP = "ℹ️ Yordam"
BTN_SUPPORT = "💬 Qo'llab-quvvatlash"


def main_menu():
    # Mini App bor bo'lsa pastki tugmalar kerak emas — hammasi Mini App ichida
    if WEBAPP_URL:
        return ReplyKeyboardRemove()
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BUY)],
            [KeyboardButton(text=BTN_ORDERS), KeyboardButton(text=BTN_HELP)],
            [KeyboardButton(text=BTN_SUPPORT)],
        ],
        resize_keyboard=True,
    )


PER_PAGE = 10


def countries_kb(countries, page=0, lang="ru"):
    start = page * PER_PAGE
    chunk = countries[start:start + PER_PAGE]
    rows, row = [], []
    for c in chunk:
        row.append(InlineKeyboardButton(text=f"{c['flag']} {i18n.country(lang, c['country'], c['flag'])}",
                                        callback_data=f"c:{c['pid']}"))
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️", callback_data=f"cp:{page - 1}"))
    if start + PER_PAGE < len(countries):
        nav.append(InlineKeyboardButton(text="➡️", callback_data=f"cp:{page + 1}"))
    if nav:
        rows.append(nav)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def packages_kb(packages, lang="ru"):
    packages = [p for p in packages if not p.get("daily")][:40]  # chat menyusida faqat asosiylari (Telegram limiti)
    rows = [
        [InlineKeyboardButton(
            text=f"{i18n.gb(lang, p['data_gb'], p.get('daily'))} · {i18n.days(lang, p['days'])} · {i18n.money(lang, p['price'])}",
            callback_data=f"p:{p['id']}",
        )]
        for p in packages
    ]
    rows.append([InlineKeyboardButton(text=i18n.t(lang, "countries_btn"), callback_data="cp:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_kb(pid, telegram_pay: bool, lang="ru"):
    rows = []
    if telegram_pay:
        rows.append([InlineKeyboardButton(text=i18n.t(lang, "pay_tg_btn"), callback_data=f"pay:tg:{pid}")])
    rows.append([InlineKeyboardButton(text=i18n.t(lang, "pay_card_btn"), callback_data=f"pay:card:{pid}")])
    rows.append([InlineKeyboardButton(text=i18n.t(lang, "back_btn"), callback_data="cp:0")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_receipt_kb(oid, lang="ru"):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=i18n.t(lang, "cancel_btn"), callback_data=f"uc:{oid}")]
    ])


# --- admin ---
def admin_receipt_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✅ To'lov tasdiqlandi", callback_data=f"ap:{oid}"),
        InlineKeyboardButton(text="❌ Rad etish", callback_data=f"ar:{oid}"),
    ]])


def admin_deliver_kb(oid):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="📤 QR yuborish", callback_data=f"ad:{oid}"),
        InlineKeyboardButton(text="↩️ Bekor (pul qaytarildi)", callback_data=f"ax:{oid}"),
    ]])


def admin_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Kutilayotgan buyurtmalar", callback_data="adm:pending")],
        [InlineKeyboardButton(text="📋 Paketlar", callback_data="adm:pkgs"),
         InlineKeyboardButton(text="📊 Statistika", callback_data="adm:stats")],
        [InlineKeyboardButton(text="➕ Paket qo'shish (yo'riqnoma)", callback_data="adm:addhelp")],
    ])
