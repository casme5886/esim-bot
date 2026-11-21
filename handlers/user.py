"""Mijoz tomoni: katalog, to'lov, buyurtmalar."""
import logging
from aiogram import Router, F, Bot
from html import escape

from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, LabeledPrice, PreCheckoutQuery, MenuButtonWebApp, WebAppInfo

import db
import i18n
import keyboards as kb
from config import ADMIN_IDS, CLICK_PROVIDER_TOKEN, PAYME_PROVIDER_TOKEN, PAYMENT_PROVIDER_TOKEN, SUPPORT_USERNAME, WEBAPP_URL
from utils import notify_admins, order_card

router = Router()


class Receipt(StatesGroup):
    waiting = State()


# ---------- start / til / menyu ----------
LANG_PROMPT = "🌐 Выберите язык · Choose your language · Tilni tanlang"


async def apply_lang_ui(bot: Bot, user_id: int, lang: str):
    """Chap pastdagi Mini App tugmasini foydalanuvchi tiliga moslaydi."""
    if not WEBAPP_URL:
        return
    try:
        await bot.set_chat_menu_button(chat_id=user_id, menu_button=MenuButtonWebApp(
            text=i18n.t(lang, "menu_btn"), web_app=WebAppInfo(url=kb.webapp_url(lang))))
    except Exception:
        pass


async def track(user_id: int, *msgs):
    """Salomlashuv / til / /start xabarlarini eslab qolamiz — keyingi /start da o'chiriladi."""
    ids = [m if isinstance(m, int) else getattr(m, "message_id", None) for m in msgs]
    ids = [i for i in ids if i]
    if ids:
        await db.set_ui_msgs(user_id, await db.ui_msgs(user_id) + ids)


async def clean_ui(bot: Bot, user_id: int):
    """Oldingi /start va salomlashuv xabarlarini o'chiradi (chatda faqat oxirgisi qoladi).
    Telegram 48 soatdan eski xabarni o'chirishga ruxsat bermasa — jim o'tkazib yuboriladi."""
    ids = await db.ui_msgs(user_id)
    if not ids:
        return
    await db.set_ui_msgs(user_id, [])
    try:
        for i in range(0, len(ids), 100):
            await bot.delete_messages(user_id, ids[i:i + 100])
        logging.info("/start: %s ning %s ta eski xabari o'chirildi", user_id, len(ids))
    except Exception as e:
        ok = 0
        for mid in ids:
            try:
                await bot.delete_message(user_id, mid)
                ok += 1
            except Exception:
                pass
        logging.info("/start: %s — %s/%s eski xabar o'chirildi (%s)", user_id, ok, len(ids), e)


def welcome_text(lang: str, first_name: str) -> str:
    return i18n.t(lang, "welcome", name=escape(first_name or ""))


async def send_welcome(bot: Bot, chat_id: int, first_name: str, lang: str):
    """Bitta xabar: salomlashuv + tagida [eSIM do'konini ochish] [🌐 Til] tugmalari."""
    m = await bot.send_message(chat_id, welcome_text(lang, first_name), reply_markup=kb.open_shop_kb(lang))
    await track(chat_id, m)


@router.message(CommandStart())
async def start(msg: Message, state: FSMContext, bot: Bot, command: CommandObject):
    await state.clear()
    u = msg.from_user
    await db.save_user(u.id, u.username, u.full_name)
    lang = await db.get_lang(u.id)
    ref_note = None
    arg = (command.args or "").strip()
    if arg.startswith("ref_") and arg[4:].isdigit():   # do'st taklif havolasi: t.me/bot?start=ref_123
        import promo
        if await promo.set_referrer(u.id, int(arg[4:])):
            s = await promo.ref_settings()
            if s["enabled"] and s["new_pct"]:
                ref_note = s["new_pct"]
    await clean_ui(bot, u.id)          # eski /start va salomlashuv xabarlari o'chadi
    await track(u.id, msg)              # shu /start ham keyingi safar o'chiriladi
    if not lang:
        await track(u.id, await msg.answer(LANG_PROMPT, reply_markup=kb.lang_kb()))
    else:
        await send_welcome(bot, u.id, u.first_name, lang)
    if ref_note:
        await msg.answer(i18n.t(i18n.norm(lang or u.language_code or ""), "ref_joined", p=ref_note))


@router.message(Command("lang", "language", "til", "yazyk"))
async def lang_cmd(msg: Message):
    await track(msg.from_user.id, msg, await msg.answer(LANG_PROMPT, reply_markup=kb.lang_kb()))


@router.callback_query(F.data == "lang:menu")
async def lang_menu(cb: CallbackQuery):
    """[🌐 Til] bosildi: shu xabarning o'zida tugmalar til tugmalariga almashadi (yangi xabar yo'q)."""
    lang = await db.user_lang(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.lang_kb(back_lang=lang))
    except Exception:
        await track(cb.from_user.id, await cb.message.answer(LANG_PROMPT, reply_markup=kb.lang_kb()))
    await cb.answer()


@router.callback_query(F.data == "lang:back")
async def lang_back(cb: CallbackQuery):
    lang = await db.user_lang(cb.from_user.id)
    try:
        await cb.message.edit_reply_markup(reply_markup=kb.open_shop_kb(lang))
    except Exception:
        pass
    await cb.answer()


@router.callback_query(F.data.startswith("lang:"))
async def lang_pick(cb: CallbackQuery, bot: Bot):
    lang = cb.data[5:]
    if lang not in i18n.LANGS:
        return await cb.answer()
    u = cb.from_user
    await db.set_lang(u.id, lang)
    await apply_lang_ui(bot, u.id, lang)
    await cb.answer(i18n.t(lang, "lang_set"))
    # shu xabarning o'zi salomlashuvga aylanadi (yangi tilda) — chatga yangi xabar qo'shilmaydi
    try:
        await cb.message.edit_text(welcome_text(lang, u.first_name), reply_markup=kb.open_shop_kb(lang))
    except Exception as e:
        if "not modified" not in str(e):
            await send_welcome(bot, u.id, u.first_name, lang)


@router.message(Command("help"))
@router.message(F.text == kb.BTN_HELP)
async def help_(msg: Message):
    await msg.answer(i18n.t(await db.user_lang(msg.from_user.id), "help"))


@router.message(F.text == kb.BTN_SUPPORT)
async def support_btn(msg: Message):
    import support
    lang = await db.user_lang(msg.from_user.id)
    text = i18n.t(lang, "support_chat")
    if SUPPORT_USERNAME:
        text += "\n" + i18n.t(lang, "support_user", u=SUPPORT_USERNAME)
    await msg.answer(text, reply_markup=support._user_kb(lang))


# ---------- katalog (Mini App yo'q bo'lsa chat orqali) ----------
async def _show_countries(target, lang, page=0, edit=False):
    countries = await db.countries()
    if not countries:
        text = i18n.t(lang, "no_packages")
        markup = None
    else:
        text = i18n.t(lang, "choose_country")
        markup = kb.countries_kb(countries, page, lang)
    if edit:
        await target.edit_text(text, reply_markup=markup)
    else:
        await target.answer(text, reply_markup=markup)


@router.message(F.text == kb.BTN_BUY)
async def buy(msg: Message, state: FSMContext):
    await state.clear()
    await _show_countries(msg, await db.user_lang(msg.from_user.id))


@router.callback_query(F.data.startswith("cp:"))
async def countries_page(cb: CallbackQuery):
    await _show_countries(cb.message, await db.user_lang(cb.from_user.id), int(cb.data[3:]), edit=True)
    await cb.answer()


@router.callback_query(F.data.startswith("c:"))
async def country(cb: CallbackQuery):
    lang = await db.user_lang(cb.from_user.id)
    p = await db.get_package(int(cb.data[2:]))
    if not p:
        return await cb.answer(i18n.t(lang, "pkg_not_found"), show_alert=True)
    pkgs = await db.packages_by_country(p["country"])
    await cb.message.edit_text(i18n.t(lang, "choose_pkg", flag=p["flag"], country=i18n.country(lang, p["country"], p["flag"])),
                               reply_markup=kb.packages_kb(pkgs, lang))
    await cb.answer()


@router.callback_query(F.data.startswith("p:"))
async def package(cb: CallbackQuery):
    lang = await db.user_lang(cb.from_user.id)
    p = await db.get_package(int(cb.data[2:]))
    if not p or not p["active"]:
        return await cb.answer(i18n.t(lang, "pkg_unavailable"), show_alert=True)
    text = i18n.t(lang, "pkg_card", flag=p["flag"], country=i18n.country(lang, p["country"], p["flag"]),
                  data=i18n.gb(lang, p["data_gb"], p.get("daily")), days=i18n.days(lang, p["days"]),
                  price=i18n.money(lang, p["price"]))
    await cb.message.edit_text(text, reply_markup=kb.confirm_kb(p["id"], bool(PAYMENT_PROVIDER_TOKEN or CLICK_PROVIDER_TOKEN or PAYME_PROVIDER_TOKEN), lang))
    await cb.answer()


def invoice_texts(lang, p, oid):
    c = i18n.country(lang, p["country"], p["flag"])
    data = i18n.gb(lang, p["data_gb"], p.get("daily"))
    return (i18n.t(lang, "invoice_title", country=c, data=data)[:32],
            i18n.t(lang, "invoice_desc", country=c, data=data, days=i18n.days(lang, p["days"]), oid=oid)[:255],
            f"eSIM {c}")


# ---------- Telegram to'lovi (Click / Payme) ----------
@router.callback_query(F.data.startswith("pay:tg:"))
async def pay_telegram(cb: CallbackQuery, bot: Bot):
    lang = await db.user_lang(cb.from_user.id)
    p = await db.get_package(int(cb.data.split(":")[2]))
    if not p or not p["active"]:
        return await cb.answer(i18n.t(lang, "pkg_unavailable"), show_alert=True)
    oid = await db.create_order(cb.from_user.id, p["id"], p["price"])
    await db.update_order(oid, payment_method="telegram")
    title, desc, label = invoice_texts(lang, p, oid)
    await bot.send_invoice(
        chat_id=cb.from_user.id, title=title, description=desc,
        payload=f"order:{oid}",
        provider_token=PAYMENT_PROVIDER_TOKEN or CLICK_PROVIDER_TOKEN or PAYME_PROVIDER_TOKEN,
        currency="UZS",
        prices=[LabeledPrice(label=label, amount=p["price"] * 100)],
    )
    await cb.answer()


@router.pre_checkout_query()
async def pre_checkout(q: PreCheckoutQuery):
    oid = int(q.invoice_payload.split(":")[1])
    o = await db.get_order(oid)
    if not o or o["status"] != "new" or o["price"] * 100 != q.total_amount:
        return await q.answer(ok=False, error_message=i18n.t(await db.user_lang(q.from_user.id), "order_expired"))
    await q.answer(ok=True)


@router.message(F.successful_payment)
async def paid(msg: Message, bot: Bot):
    oid = int(msg.successful_payment.invoice_payload.split(":")[1])
    await db.update_order(oid, status="paid", note=msg.successful_payment.provider_payment_charge_id)
    await msg.answer(i18n.t(await db.user_lang(msg.from_user.id), "paid_ok", oid=oid))
    o = await db.get_order(oid)
    await notify_admins(bot, "💳 <b>YANGI TO'LANGAN BUYURTMA</b>\n\n" + order_card(o, with_buy_hint=True),
                        kb.admin_deliver_kb(oid))
    import services
    services.after_paid(bot, oid)


# ---------- Kartaga o'tkazma ----------
async def start_card_order(user_id: int, p: dict, state: FSMContext):
    """Karta orqali buyurtma ochadi, chek kutish holatiga o'tkazadi. (matn, klaviatura, order_id) qaytaradi.
    Chat tugmasi ham, Mini App ham shu funksiyadan foydalanadi."""
    oid = await db.create_order(user_id, p["id"], p["price"])
    await db.update_order(oid, payment_method="card")
    await state.set_state(Receipt.waiting)
    await state.update_data(order_id=oid)
    card_number, card_holder = await db.card_info()
    lang = await db.user_lang(user_id)
    line = (f"{p['flag']} {i18n.country(lang, p['country'], p['flag'])} — {i18n.gb(lang, p['data_gb'], p.get('daily'))}"
            f" / {i18n.days(lang, p['days'])}")
    text = i18n.t(lang, "card_order", oid=oid, line=line, price=i18n.money(lang, p["price"]),
                  card=card_number, holder=card_holder)
    return text, kb.cancel_receipt_kb(oid, lang), oid


@router.callback_query(F.data.startswith("pay:card:"))
async def pay_card(cb: CallbackQuery, state: FSMContext):
    p = await db.get_package(int(cb.data.split(":")[2]))
    if not p or not p["active"]:
        return await cb.answer(i18n.t(await db.user_lang(cb.from_user.id), "pkg_unavailable"), show_alert=True)
    text, markup, _ = await start_card_order(cb.from_user.id, p, state)
    await cb.message.edit_text(text, reply_markup=markup)
    await cb.answer()


@router.message(Receipt.waiting, F.photo | F.document)
async def receipt(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    oid = data["order_id"]
    if msg.photo:
        file_id, kind = msg.photo[-1].file_id, "photo"
    else:
        file_id, kind = msg.document.file_id, "document"
    await db.update_order(oid, status="checking", receipt_file_id=file_id)
    await state.clear()
    await msg.answer(i18n.t(await db.user_lang(msg.from_user.id), "receipt_ok", oid=oid), reply_markup=kb.main_menu())
    o = await db.get_order(oid)
    text = "🏦 <b>KARTA TO'LOVI — chekni tekshiring</b>\n\n" + order_card(o)
    if kind == "photo":
        await notify_admins(bot, text, kb.admin_receipt_kb(oid), photo=file_id)
    else:
        await notify_admins(bot, text, kb.admin_receipt_kb(oid), document=file_id)


@router.message(Receipt.waiting)
async def receipt_wrong(msg: Message):
    await msg.answer(i18n.t(await db.user_lang(msg.from_user.id), "receipt_wrong"))


@router.callback_query(F.data.startswith("uc:"))
async def user_cancel(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data[3:])
    o = await db.get_order(oid)
    if o and o["user_id"] == cb.from_user.id and o["status"] == "new":
        await db.update_order(oid, status="cancelled")
    await state.clear()
    await cb.message.edit_text(i18n.t(await db.user_lang(cb.from_user.id), "order_cancelled"))
    await cb.answer()


# ---------- Buyurtmalarim ----------
@router.message(F.text == kb.BTN_ORDERS)
async def my_orders(msg: Message):
    lang = await db.user_lang(msg.from_user.id)
    orders = await db.user_orders(msg.from_user.id)
    if not orders:
        return await msg.answer(i18n.t(lang, "no_orders"))
    lines = [i18n.t(lang, "orders_title")]
    for o in orders:
        lines.append(
            f"#{o['id']} · {o['flag']} {i18n.country(lang, o['country'], o['flag'])} "
            f"{i18n.gb(lang, o['data_gb'], o.get('daily'))} / {i18n.days(lang, o['days'])} · "
            f"{i18n.money(lang, o['price'])}\n   {i18n.t(lang, 'st_' + o['status'])}"
        )
    await msg.answer("\n".join(lines))


# ---------- Boshqa xabarlar -> adminga ----------
@router.message(F.text & ~F.text.startswith("/"))
@router.message(F.photo)
async def to_support(msg: Message, bot: Bot):
    """Botga yozilgan matn / surat -> yordam chatiga (admin Mini App'dagi "Chat" bo'limida ko'radi va javob beradi)."""
    import support
    u = msg.from_user
    if u.id in ADMIN_IDS:
        return await msg.answer("🛠 Admin panel: /admin")
    await db.save_user(u.id, u.username, u.full_name)
    photo = None
    if msg.photo:
        try:
            buf = await bot.download(msg.photo[-1].file_id)
            photo = (buf.read(), "photo.jpg")
        except Exception:
            photo = None
    text = msg.text or msg.caption or ""
    if not text and not photo:
        return
    m = await support.add(u.id, False, text, photo, source="bot")
    await support.notify_admins(bot, m)
    await support.ack_user(bot, msg, await db.user_lang(u.id))
