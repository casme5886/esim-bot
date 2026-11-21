"""Buyurtma ustidagi amallar — chat admin paneli ham, Mini App ham shu yerdan foydalanadi."""
from aiogram import Bot
from aiogram.types import BufferedInputFile

import db
import i18n
import logging

log = logging.getLogger("services")


class OrderError(Exception):
    pass


async def _order(oid, *statuses):
    o = await db.get_order(oid)
    if not o:
        raise OrderError("Buyurtma topilmadi")
    if statuses and o["status"] not in statuses:
        raise OrderError(f"Buyurtma holati: {db.STATUS_UZ.get(o['status'], o['status'])}")
    return o


def after_paid(bot: Bot, oid: int):
    """To'lov tasdiqlangach: paketda Trip.com havolasi bo'lsa avto-xaridni boshlaydi."""
    import asyncio
    asyncio.get_running_loop().create_task(_ref_reward(bot, oid))
    from config import TRIP_AUTOBUY
    if TRIP_AUTOBUY:
        import trip_buyer
        trip_buyer.start(bot, oid)


async def _ref_reward(bot: Bot, oid: int):
    """Taklif qilingan do'st birinchi marta to'ladi -> taklif qilganning balansiga bonus va xabar."""
    import promo
    try:
        r = await promo.credit_referrer(oid)
        if not r:
            return
        ref_id, bonus, balance = r
        lang = await db.user_lang(ref_id)
        await bot.send_message(ref_id, i18n.t(lang, "ref_bonus", sum=i18n.money(lang, bonus),
                                              bal=i18n.money(lang, balance)), reply_markup=_shop_kb(lang))
    except Exception as e:
        log.warning("Referal mukofoti #%s: %s", oid, e)


def _shop_kb(lang, query=""):
    """Mini App'ni ochadigan tugma (query: masalan 'buy=123')."""
    import keyboards as kb
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
    if not kb.WEBAPP_URL:
        return None
    url = kb.webapp_url(lang)
    if query:
        url += ("&" if "?" in url else "?") + query
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
        text=i18n.t(lang, "expiry_btn" if query.startswith("buy=") else "open_shop"), web_app=WebAppInfo(url=url))]])


async def expiry_watch(bot: Bot):
    """eSIM muddati tugashiga yaqin (yetkazilgandan keyin ~ kunlar-1) mijozga "Yana olish" eslatmasi. Har soatda."""
    import asyncio
    while True:
        try:
            rows = await db._fetchall(
                "SELECT o.id, o.user_id, o.package_id, p.country, p.flag, p.days, p.active FROM orders o "
                "JOIN packages p ON p.id=o.package_id WHERE o.status='delivered' AND o.delivered_at!='' "
                "AND COALESCE(o.expiry_reminded,0)=0 AND p.days>=2 "
                "AND datetime(o.delivered_at, '+' || (p.days - 1) || ' days') <= datetime('now') "
                "AND datetime(o.delivered_at, '+' || (p.days + 3) || ' days') > datetime('now')")
            for o in rows:
                await db.update_order(o["id"], expiry_reminded=1)
                # shu mijoz keyinroq yana xarid qilgan bo'lsa — eslatmaymiz
                if await db._fetchone("SELECT 1 FROM orders WHERE user_id=? AND id>? AND status IN "
                                      "('checking','paid','delivered')", (o["user_id"], o["id"])):
                    continue
                lang = await db.user_lang(o["user_id"])
                try:
                    await bot.send_message(o["user_id"], i18n.t(lang, "expiry_soon", oid=o["id"], flag=o["flag"],
                                                                country=i18n.country(lang, o["country"], o["flag"]),
                                                                days=i18n.days(lang, o["days"])),
                                           reply_markup=_shop_kb(lang, f"buy={o['package_id']}" if o["active"] else ""))
                except Exception as e:
                    log.warning("Muddat eslatmasi #%s: %s", o["id"], e)
        except Exception:
            log.exception("expiry_watch xato")
        await asyncio.sleep(3600)


async def approve(bot: Bot, oid: int):
    """Karta to'lovi chekini tasdiqlash."""
    o = await _order(oid, "checking")
    await db.update_order(oid, status="paid")
    await bot.send_message(o["user_id"], i18n.t(await db.user_lang(o["user_id"]), "approve_ok", oid=oid))
    after_paid(bot, oid)
    return await db.get_order(oid)


async def reject(bot: Bot, oid: int):
    o = await _order(oid, "checking")
    await db.update_order(oid, status="cancelled")
    await bot.send_message(o["user_id"], i18n.t(await db.user_lang(o["user_id"]), "reject", oid=oid))


async def cancel_paid(bot: Bot, oid: int):
    o = await _order(oid, "paid")
    await db.update_order(oid, status="cancelled")
    await bot.send_message(o["user_id"], i18n.t(await db.user_lang(o["user_id"]), "cancel_paid", oid=oid))


async def _download(bot: Bot, file_id: str) -> bytes | None:
    try:
        buf = await bot.download(file_id)
        return buf.read() if buf else None
    except Exception:
        return None


def _esim_kb(lpa: str | None, usage: str | None, lang: str = "ru"):
    from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
    import esim_info
    rows = []
    if lpa:
        rows.append([InlineKeyboardButton(text=i18n.t(lang, "btn_ios"), url=esim_info.ios_url(lpa))])
        rows.append([InlineKeyboardButton(text=i18n.t(lang, "btn_android"), url=esim_info.android_url(lpa))])
    if usage:
        rows.append([InlineKeyboardButton(text=i18n.t(lang, "btn_usage"), url=usage)])
    return InlineKeyboardMarkup(inline_keyboard=rows) if rows else None


async def deliver(bot: Bot, oid: int, *, photo=None, document=None, upload: tuple | None = None,
                  lpa: str | None = None, note: str | None = None, usage: str | None = None) -> dict:
    """eSIM'ni mijozga yetkazish.
    photo/document — Telegram file_id; upload — (bytes, fayl_nomi) Mini App'dan;
    lpa — tayyor kod. Fayl (PDF vaucher / QR rasm / skrinshot) bo'lsa, koddan avtomatik ajratib olinadi
    va mijozga toza QR + "1 bosishda o'rnatish" tugmalari yuboriladi.
    Qaytaradi: {"lpa_found": bool}"""
    import esim_info
    o = await _order(oid, "paid")
    if not (photo or document or upload or lpa):
        raise OrderError("QR rasm, PDF yoki LPA kod kerak")

    # fayldan kodni ajratamiz
    data, name = None, ""
    if upload:
        data, name = upload
    elif photo or document:
        data, name = await _download(bot, photo or document), ("file.pdf" if document else "qr.jpg")
    if data and not lpa:
        try:
            info = esim_info.analyze(data, name)
            lpa, usage = info.get("lpa"), usage or info.get("usage")
        except Exception:
            pass
    if lpa and not lpa.upper().startswith("LPA:"):
        lpa = esim_info.from_text(lpa) or lpa

    lang = await db.user_lang(o["user_id"])
    caption = i18n.t(lang, "esim_ready", oid=oid, flag=o["flag"], country=i18n.country(lang, o["country"], o["flag"]),
                     data=i18n.gb(lang, o["data_gb"], o.get("daily")), days=i18n.days(lang, o["days"]))
    file_id = None
    if lpa:
        smdp, code = esim_info.split_lpa(lpa)
        caption += "\n\n" + i18n.t(lang, "esim_install")
        if smdp and code:
            caption += "\n\n" + i18n.t(lang, "esim_manual", smdp=smdp, code=code)
        if note:
            caption += f"\n\n{note}"
        msg = await bot.send_photo(o["user_id"], BufferedInputFile(esim_info.make_qr_png(lpa), "esim_qr.png"),
                                   caption=caption[:1024], reply_markup=_esim_kb(lpa, usage, lang))
        file_id = msg.photo[-1].file_id if getattr(msg, "photo", None) else None
    else:
        # kod topilmadi — faylni o'zini yuboramiz
        if note:
            caption += f"\n\n{note}"
        if upload:
            data, name = upload
            if name.lower().rsplit(".", 1)[-1] in ("jpg", "jpeg", "png", "webp"):
                msg = await bot.send_photo(o["user_id"], BufferedInputFile(data, name), caption=caption,
                                           reply_markup=_esim_kb(None, usage, lang))
                file_id = msg.photo[-1].file_id if getattr(msg, "photo", None) else None
            else:
                msg = await bot.send_document(o["user_id"], BufferedInputFile(data, name), caption=caption,
                                              reply_markup=_esim_kb(None, usage, lang))
                file_id = msg.document.file_id if getattr(msg, "document", None) else None
        elif photo:
            await bot.send_photo(o["user_id"], photo, caption=caption, reply_markup=_esim_kb(None, usage, lang))
            file_id = photo
        elif document:
            await bot.send_document(o["user_id"], document, caption=caption, reply_markup=_esim_kb(None, usage, lang))
            file_id = document

    await bot.send_message(o["user_id"], i18n.t(lang, "install_guide"))
    await db.update_order(oid, status="delivered", qr_file_id=file_id, note=lpa or o.get("note"), usage_url=usage or "")
    if lpa:
        try:
            await send_voucher(bot, oid)
        except Exception:
            pass
    await _cashback(bot, oid)
    return {"lpa_found": bool(lpa)}


async def _cashback(bot: Bot, oid: int):
    """eSIM yetkazildi -> har bir xarid uchun keshbek (admin panelda foizi belgilanadi)."""
    import promo
    try:
        r = await promo.credit_cashback(oid)
        if not r:
            return
        uid, cb, bal = r
        lang = await db.user_lang(uid)
        await bot.send_message(uid, i18n.t(lang, "cashback_msg", oid=oid, sum=i18n.money(lang, cb), bal=i18n.money(lang, bal)))
    except Exception as e:
        log.warning("Keshbek #%s: %s", oid, e)


async def send_voucher(bot: Bot, oid: int):
    """Booking eSIM brendidagi PDF vaucherni mijozning chatiga yuboradi."""
    import esim_info
    import voucher
    from config import BOT_USERNAME, SUPPORT_USERNAME
    o = await db.get_order(oid)
    lpa = esim_info.from_text(o.get("note") or "")
    if not o or o["status"] != "delivered" or not lpa:
        raise OrderError("Bu buyurtma uchun eSIM ma'lumoti yo'q")
    lang = await db.user_lang(o["user_id"])
    pl = i18n.pdf_lang(lang)
    pdf = voucher.build({"id": oid, "country": i18n.country(pl, o["country"], o["flag"]),
                         "data_text": i18n.gb(pl, o["data_gb"], o.get("daily")),
                         "days": o["days"], "created_at": o.get("updated_at") or o.get("created_at")},
                        lpa, o.get("usage_url") or None, SUPPORT_USERNAME or BOT_USERNAME, BOT_USERNAME, lang=lang)
    await bot.send_document(o["user_id"], BufferedInputFile(pdf, f"Booking-eSIM-{oid}.pdf"),
                            caption=i18n.t(lang, "voucher_caption", oid=oid))


# ---------- to'lanmagan buyurtmalar: eslatma va avtomatik bekor qilish ----------
REMIND_AFTER_MIN = 15     # shuncha daqiqadan keyin chek kelmasa — eslatma
EXPIRE_AFTER_MIN = 60     # shuncha daqiqadan keyin — bekor qilinadi


async def pending_watch(bot: Bot):
    """Har daqiqada: chek yubormagan mijozga eslatma, keyin buyurtmani bekor qilish."""
    import asyncio
    from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
    import keyboards as kb
    while True:
        try:
            rows = await db._fetchall(
                "SELECT id, user_id, payment_method FROM orders WHERE status='new' AND COALESCE(reminded,0)=0 "
                "AND (payment_method='card' OR payment_method LIKE '%_link') AND created_at <= datetime('now', ?) AND created_at > datetime('now', ?)",
                (f"-{REMIND_AFTER_MIN} minutes", f"-{EXPIRE_AFTER_MIN - 5} minutes"))
            for o in rows:
                await db.update_order(o["id"], reminded=1)
                lang = await db.user_lang(o["user_id"])
                markup = None
                if kb.WEBAPP_URL:
                    url = kb.webapp_url(lang) + ("&" if "?" in kb.webapp_url(lang) else "?") + f"pay={o['id']}"
                    markup = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(
                        text=i18n.t(lang, "pay_reminder_btn"), web_app=WebAppInfo(url=url))]])
                try:
                    await bot.send_message(o["user_id"], i18n.t(lang, "pay_reminder", oid=o["id"],
                                                                 min=EXPIRE_AFTER_MIN - REMIND_AFTER_MIN),
                                           reply_markup=markup)
                except Exception as e:
                    log.warning("Eslatma #%s yuborilmadi: %s", o["id"], e)
            rows = await db._fetchall(
                "SELECT id, user_id, payment_method FROM orders WHERE status='new' AND created_at <= datetime('now', ?)",
                (f"-{EXPIRE_AFTER_MIN} minutes",))
            for o in rows:
                await db.update_order(o["id"], status="cancelled")
                if o["payment_method"] == "card" or (o["payment_method"] or "").endswith("_link"):
                    try:
                        await bot.send_message(o["user_id"], i18n.t(await db.user_lang(o["user_id"]), "pay_expired",
                                                                    oid=o["id"]))
                    except Exception:
                        pass
                log.info("Buyurtma #%s to'lanmagani uchun bekor qilindi", o["id"])
        except Exception as e:
            log.warning("pending_watch xato: %s", e)
        await asyncio.sleep(60)


# ================= Kunlik zaxira nusxa =================
BACKUP_DIR = "backups"
BACKUP_KEEP = 14          # oxirgi 14 kunlik nusxa kompyuterda saqlanadi
BACKUP_HOUR = 3           # Toshkent vaqti bilan soat 03:00 da


def _make_backup() -> str:
    """Ishlab turgan bazadan xavfsiz nusxa (sqlite backup API) -> backups/esim-YYYY-MM-DD_HHMM.db"""
    import os
    import sqlite3
    from datetime import datetime
    os.makedirs(BACKUP_DIR, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f"esim-{datetime.now():%Y-%m-%d_%H%M}.db")
    src, dst = sqlite3.connect(db.DB_PATH), sqlite3.connect(path)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    files = sorted(f for f in os.listdir(BACKUP_DIR) if f.startswith("esim-") and f.endswith(".db"))
    for old in files[:-BACKUP_KEEP]:
        try:
            os.remove(os.path.join(BACKUP_DIR, old))
        except OSError:
            pass
    return path


async def send_backup(bot: Bot, chat_ids=None):
    """Nusxa olib, adminlarga Telegram orqali fayl qilib yuboradi."""
    import asyncio
    import os
    from config import ADMIN_IDS
    path = await asyncio.to_thread(_make_backup)
    with open(path, "rb") as f:
        raw = f.read()
    n = await db._fetchone("SELECT COUNT(*) AS n FROM orders")
    cap = (f"💾 <b>Zaxira nusxa</b> · {os.path.basename(path)[5:-3]}\n"
           f"Buyurtmalar: {n['n'] if n else '?'} · {len(raw) // 1024} KB\n"
           "Tiklash: faylni <code>esim.db</code> deb nomlab, bot papkasiga qo'ying.")
    for cid in (chat_ids or ADMIN_IDS):
        try:
            await bot.send_document(cid, BufferedInputFile(raw, os.path.basename(path)), caption=cap,
                                    disable_notification=True)
        except Exception as e:
            log.warning("Zaxira nusxani %s ga yuborib bo'lmadi: %s", cid, e)
    log.info("Zaxira nusxa olindi: %s", path)
    return path


async def backup_loop(bot: Bot):
    """Har kuni BACKUP_HOUR da (Toshkent vaqti) zaxira nusxa."""
    import asyncio
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=5))
    while True:
        now = datetime.now(tz)
        nxt = now.replace(hour=BACKUP_HOUR, minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        await asyncio.sleep((nxt - now).total_seconds())
        try:
            await send_backup(bot)
        except Exception:
            log.exception("Zaxira nusxa olishda xato")
        await asyncio.sleep(60)
