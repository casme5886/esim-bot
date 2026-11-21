"""Admin paneli: to'lovni tasdiqlash, QR yuborish, paketlar, statistika."""
from aiogram import Router, F, Bot
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery

import db
import keyboards as kb
import services
from config import ADMIN_IDS
from texts import money, gb
from utils import order_card

router = Router()
router.message.filter(F.from_user.id.in_(ADMIN_IDS))
router.callback_query.filter(F.from_user.id.in_(ADMIN_IDS))


class Deliver(StatesGroup):
    waiting_qr = State()


ADD_HELP = (
    "➕ <b>Paket qo'shish</b>\n\n"
    "Format (har bir qator — bitta paket):\n"
    "<code>/add Davlat;Bayroq;GB;Kun;Narx_som;Tannarx_usd</code>\n\n"
    "Misol:\n"
    "<code>/add Turkiya;🇹🇷;10;30;150000;12.5\n"
    "Turkiya;🇹🇷;20;30;230000;19\n"
    "BAA;🇦🇪;5;7;99000;8</code>\n\n"
    "Cheksiz internet uchun GB = 0.\n\n"
    "Boshqa buyruqlar:\n"
    "<code>/off 5</code> — 5-paketni yashirish\n"
    "<code>/on 5</code> — qayta yoqish\n"
    "<code>/price 5 160000</code> — narxni o'zgartirish\n"
    "<code>/reply USER_ID matn</code> — mijozga javob\n"
    "<code>/trip_login</code> — Trip.com'ga kirish oynasi\n"
    "<code>/trip_test PAKET_ID</code> — Trip.com sahifasini sinash (sotib olmaydi)\n"
    "<code>/trip_buy BUYURTMA_ID</code> — avto-xaridni qayta boshlash\n"
    "<code>/import</code> — Trip.com'dan barcha davlatlarni import qilish (<code>/import id cn</code> — faqat tanlanganlar)\n"
    "<code>/cancel</code> — joriy amalni bekor qilish"
)


async def _edit_markup(cb: CallbackQuery, extra: str, markup=None):
    """Xabar rasm (caption) yoki matn bo'lishidan qat'i nazar, oxiriga izoh qo'shadi."""
    m = cb.message
    try:
        if m.photo or m.document:
            await m.edit_caption(caption=(m.html_text or "") + "\n\n" + extra, reply_markup=markup)
        else:
            await m.edit_text((m.html_text or "") + "\n\n" + extra, reply_markup=markup)
    except Exception:
        await m.answer(extra, reply_markup=markup)


@router.message(Command("admin"))
async def admin(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("🛠 <b>Admin panel</b>", reply_markup=kb.admin_menu())


@router.message(Command("cancel"))
async def cancel(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("Bekor qilindi.", reply_markup=kb.admin_menu())


# ---------- karta to'lovini tasdiqlash ----------
@router.callback_query(F.data.startswith("ap:"))
async def approve(cb: CallbackQuery, bot: Bot):
    try:
        o = await services.approve(bot, int(cb.data[3:]))
    except services.OrderError as e:
        return await cb.answer(str(e), show_alert=True)
    await _edit_markup(cb, "✅ To'lov tasdiqlandi.\n\n" + order_card(o, with_buy_hint=True).split("\n\n", 1)[-1],
                       kb.admin_deliver_kb(o["id"]))
    await cb.answer("Tasdiqlandi")


@router.callback_query(F.data.startswith("ar:"))
async def reject(cb: CallbackQuery, bot: Bot):
    try:
        await services.reject(bot, int(cb.data[3:]))
    except services.OrderError as e:
        return await cb.answer(str(e), show_alert=True)
    await _edit_markup(cb, "❌ Rad etildi.")
    await cb.answer()


# ---------- QR yuborish ----------
@router.callback_query(F.data.startswith("ad:"))
async def deliver_start(cb: CallbackQuery, state: FSMContext):
    oid = int(cb.data[3:])
    o = await db.get_order(oid)
    if not o or o["status"] != "paid":
        return await cb.answer(f"Holati: {o['status'] if o else 'yoq'}", show_alert=True)
    await state.set_state(Deliver.waiting_qr)
    await state.update_data(order_id=oid)
    await cb.message.answer(
        f"📤 Buyurtma <b>#{oid}</b> uchun Trip.com'dan olingan <b>PDF vaucher, QR rasm yoki skrinshotni</b> yuboring — "
        "bot kodni o'zi ajratib oladi.\n"
        "Rasm izohiga (caption) aktivatsiya kodi yoki qo'shimcha ma'lumot yozishingiz mumkin "
        "— u ham mijozga boradi.\n\nBekor qilish: /cancel"
    )
    await cb.answer()


@router.message(Deliver.waiting_qr, F.photo | F.document)
async def deliver_qr(msg: Message, state: FSMContext, bot: Bot):
    oid = (await state.get_data())["order_id"]
    try:
        r = await services.deliver(
            bot, oid,
            photo=msg.photo[-1].file_id if msg.photo else None,
            document=msg.document.file_id if msg.document else None,
            note=msg.caption,
        )
    except services.OrderError as e:
        await state.clear()
        return await msg.answer(str(e))
    await state.clear()
    extra = ("Kod avtomatik ajratildi — mijozga toza QR va «1 bosishda o'rnatish» tugmalari ketdi ✔️"
             if r.get("lpa_found") else "⚠️ Fayldan kod o'qilmadi — faylning o'zi yuborildi.")
    await msg.answer(f"✅ #{oid} mijozga yetkazildi.\n{extra}", reply_markup=kb.admin_menu())


@router.message(Deliver.waiting_qr)
async def deliver_text(msg: Message, state: FSMContext, bot: Bot):
    """QR rasm o'rniga faqat matn (masalan LPA:1$... kod) yuborilsa ham qabul qilamiz."""
    if not msg.text or not msg.text.strip().upper().startswith("LPA:"):
        return await msg.answer("QR kod rasmini yoki <code>LPA:1$...</code> kodini yuboring. Bekor qilish: /cancel")
    oid = (await state.get_data())["order_id"]
    try:
        await services.deliver(bot, oid, lpa=msg.text.strip())
    except services.OrderError as e:
        await state.clear()
        return await msg.answer(str(e))
    await state.clear()
    await msg.answer(f"✅ #{oid} mijozga yetkazildi.", reply_markup=kb.admin_menu())


@router.callback_query(F.data.startswith("ax:"))
async def cancel_paid(cb: CallbackQuery, bot: Bot):
    try:
        await services.cancel_paid(bot, int(cb.data[3:]))
    except services.OrderError as e:
        return await cb.answer(str(e), show_alert=True)
    await _edit_markup(cb, "↩️ Bekor qilindi (pulni qaytarishni unutmang).")
    await cb.answer()


# ---------- Trip.com avto-xarid ----------
@router.callback_query(F.data.startswith("tb:") | F.data.startswith("tn:"))
async def trip_confirm(cb: CallbackQuery):
    import trip_buyer
    oid, yes = int(cb.data[3:]), cb.data.startswith("tb:")
    if not trip_buyer.resolve_confirm(oid, yes):
        return await cb.answer("Bu so'rov eskirgan", show_alert=True)
    await _edit_markup(cb, "🛒 Sotib olinmoqda…" if yes else "✋ Qo'lda qilinadi")
    await cb.answer()


@router.message(Command("trip_login"))
async def trip_login(msg: Message):
    import trip_buyer
    try:
        await trip_buyer.open_login_window()
    except Exception as e:
        return await msg.answer(f"Brauzer ochilmadi: {e}\n\n<code>pip install playwright</code> va "
                                "<code>playwright install chromium</code> bajarilganini tekshiring.")
    await msg.answer("🌐 Kompyuteringizda Trip.com oynasi ochildi. Akkauntingizga kiring "
                     "(kontakt ma'lumotlari va karta saqlangan bo'lsin), oynani <b>yopmang</b>.\n\n"
                     "Keyin sinab ko'ring: <code>/trip_test PAKET_ID</code>")


@router.message(Command("trip_test"))
async def trip_test(msg: Message, command: CommandObject, bot: Bot):
    import trip_buyer
    try:
        pid = int(command.args)
    except (TypeError, ValueError):
        return await msg.answer("Misol: <code>/trip_test 5</code> — 5-paketning Trip.com sahifasini ochib narxni o'qiydi "
                                "(hech narsa sotib olinmaydi).")
    await msg.answer("⏳ Trip.com ochilmoqda…")
    await trip_buyer.prepare_and_buy(bot, pid, dry_run=True)


@router.message(Command("trip_buy"))
async def trip_buy(msg: Message, command: CommandObject, bot: Bot):
    """To'langan buyurtma uchun avto-xaridni qo'lda (qayta) boshlash."""
    import trip_buyer
    try:
        oid = int(command.args)
    except (TypeError, ValueError):
        return await msg.answer("Misol: <code>/trip_buy 12</code>")
    o = await db.get_order(oid)
    if not o or o["status"] != "paid":
        return await msg.answer("Faqat to'langan (QR kutilayotgan) buyurtma uchun.")
    if o.get("trip_status") in ("paying", "bought", "done"):
        return await msg.answer("⚠️ Bu buyurtma uchun Trip.com'da to'lov allaqachon bosilgan. Qayta sotib olinmaydi.")
    await db.update_order(oid, trip_status="")
    trip_buyer.start(bot, oid)
    await msg.answer(f"⏳ #{oid} uchun Trip.com tayyorlanmoqda…")


@router.message(Command("import"))
async def trip_import_cmd(msg: Message, command: CommandObject, bot: Bot):
    """/import — hammasi; /import id cn — faqat shu davlatlar (ISO kod)."""
    import trip_import
    if trip_import.STATE["running"]:
        s = trip_import.STATE
        return await msg.answer(f"⏳ Import ishlayapti: {s['done']}/{s['total']} ({s['current']})")
    only = (command.args or "").lower().split() or None
    trip_import.start(bot, only=only)


# ---------- menyu bo'limlari ----------
@router.callback_query(F.data == "adm:pending")
async def pending(cb: CallbackQuery):
    orders = await db.pending_orders()
    if not orders:
        await cb.message.answer("✨ Kutilayotgan buyurtma yo'q.")
    for o in orders:
        full = await db.get_order(o["id"])
        if o["status"] == "paid":
            await cb.message.answer(order_card(full, with_buy_hint=True), reply_markup=kb.admin_deliver_kb(o["id"]))
        else:
            text = "🏦 Chek tekshirilishi kerak\n\n" + order_card(full)
            if full["receipt_file_id"]:
                try:
                    await cb.message.answer_photo(full["receipt_file_id"], caption=text,
                                                  reply_markup=kb.admin_receipt_kb(o["id"]))
                    continue
                except Exception:
                    await cb.message.answer_document(full["receipt_file_id"], caption=text,
                                                     reply_markup=kb.admin_receipt_kb(o["id"]))
                    continue
            await cb.message.answer(text, reply_markup=kb.admin_receipt_kb(o["id"]))
    await cb.answer()


@router.callback_query(F.data == "adm:pkgs")
async def pkgs(cb: CallbackQuery):
    rows = await db.all_packages()
    if not rows:
        await cb.message.answer("Paketlar yo'q.\n\n" + ADD_HELP)
        return await cb.answer()
    lines = ["📋 <b>Paketlar</b> (ID · holat)\n"]
    for p in rows:
        mark = "🟢" if p["active"] else "⚪️"
        cost = f" · tannarx ${p['cost_usd']:g}" if p["cost_usd"] else ""
        lines.append(f"{mark} <code>{p['id']}</code> {p['flag']} {p['country']} {gb(p['data_gb'], p.get('daily'))}/{p['days']}k"
                     f" · {money(p['price'])}{cost}")
    text = "\n".join(lines)
    for i in range(0, len(text), 3800):  # Telegram xabar limiti
        await cb.message.answer(text[i:i + 3800])
    await cb.answer()


@router.callback_query(F.data == "adm:addhelp")
async def addhelp(cb: CallbackQuery):
    await cb.message.answer(ADD_HELP)
    await cb.answer()


@router.callback_query(F.data == "adm:stats")
async def stats(cb: CallbackQuery):
    s = await db.stats()
    await cb.message.answer(
        "📊 <b>Statistika</b>\n\n"
        f"👥 Foydalanuvchilar: {s['users']}\n"
        f"✅ Sotilgan eSIM: {s['delivered']} (bugun: {s['today']})\n"
        f"💰 Tushum: {money(s['revenue'])}\n"
        f"⏳ Kutilmoqda: {s['pending']}"
    )
    await cb.answer()


# ---------- buyruqlar ----------
@router.message(Command("add"))
async def add(msg: Message, command: CommandObject):
    if not command.args:
        return await msg.answer(ADD_HELP)
    added, errors = [], []
    for line in command.args.strip().splitlines():
        parts = [x.strip() for x in line.split(";")]
        try:
            country, flag, data_gb, days, price = parts[:5]
            cost = float(parts[5].replace(",", ".")) if len(parts) > 5 and parts[5] else 0
            pid = await db.add_package(country, flag or "🌍", float(data_gb.replace(",", ".")),
                                       int(days), int(price.replace(" ", "")), cost)
            added.append(f"<code>{pid}</code> {flag} {country} {data_gb}GB/{days}k")
        except Exception:
            errors.append(line)
    text = ""
    if added:
        text += "✅ Qo'shildi:\n" + "\n".join(added)
    if errors:
        text += "\n\n⚠️ Xato format:\n" + "\n".join(errors)
    await msg.answer(text or ADD_HELP)


@router.message(Command("backup"))
async def backup_now(msg: Message, bot: Bot):
    await msg.answer("💾 Zaxira nusxa olinmoqda...")
    try:
        await services.send_backup(bot, [msg.chat.id])
    except Exception as e:
        await msg.answer(f"❌ Xato: {e}")


@router.message(Command("off", "on"))
async def toggle(msg: Message, command: CommandObject):
    try:
        pid = int(command.args)
    except (TypeError, ValueError):
        return await msg.answer("Misol: <code>/off 5</code>")
    await db.set_package_active(pid, command.command == "on")
    await msg.answer(f"Paket {pid}: {'🟢 yoqildi' if command.command == 'on' else '⚪️ yashirildi'}")


@router.message(Command("price"))
async def price(msg: Message, command: CommandObject):
    try:
        pid, new_price = command.args.split()
        await db.update_package_price(int(pid), int(new_price))
    except Exception:
        return await msg.answer("Misol: <code>/price 5 160000</code>")
    await msg.answer(f"✅ Paket {pid} narxi: {money(new_price)}")


@router.message(Command("reply"))
async def reply(msg: Message, command: CommandObject, bot: Bot):
    try:
        uid, text = command.args.split(maxsplit=1)
        import support
        m = await support.add(int(uid), True, text)
        await support.mark_seen(int(uid), by_admin=True)
        await support.deliver_to_user(bot, m)
    except Exception as e:
        return await msg.answer(f"Yuborilmadi. Misol: <code>/reply 123456 Salom!</code>\n{e}")
    await msg.answer("✅ Yuborildi")
