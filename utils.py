import logging
from aiogram import Bot
from config import ADMIN_IDS
from texts import gb, money

log = logging.getLogger(__name__)


def order_card(o, with_buy_hint=False):
    """Buyurtma haqida admin uchun qisqa matn."""
    user = f"@{o['username']}" if o.get("username") else (o.get("full_name") or "")
    text = (
        f"🧾 <b>Buyurtma #{o['id']}</b>\n"
        f"{o['flag']} {o['country']} — {gb(o['data_gb'], o.get('daily'))} / {o['days']} kun\n"
        f"💰 {money(o['price'])} ({o.get('payment_method') or '-'})\n"
        f"👤 {user} (<code>{o['user_id']}</code>)"
    )
    extra = []
    if o.get("discount"):
        extra.append(("🎁 do'st taklifi" if o.get("promo") == "REF" else f"🎟 {o.get('promo')}") + f" −{money(o['discount'])}")
    if o.get("balance_used"):
        extra.append(f"💰 balansdan −{money(o['balance_used'])}")
    if extra:
        text += f"\n<i>{' · '.join(extra)} (asl narx {money(o.get('orig_price') or o['price'])})</i>"
    if with_buy_hint:
        cost = f" (tannarx ~${o['cost_usd']:g})" if o.get("cost_usd") else ""
        text += (
            f"\n\n🛒 Trip.com'dan sotib oling: <b>{o['country']} {gb(o['data_gb'], o.get('daily'))} / {o['days']} kun</b>{cost}\n"
            f"So'ng «📤 QR yuborish» ni bosing."
        )
    return text


async def notify_admins(bot: Bot, text, kb=None, photo=None, document=None):
    for admin_id in ADMIN_IDS:
        try:
            if photo:
                await bot.send_photo(admin_id, photo, caption=text, reply_markup=kb)
            elif document:
                await bot.send_document(admin_id, document, caption=text, reply_markup=kb)
            else:
                await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception as e:  # admin botni bloklagan bo'lishi mumkin
            log.warning("Admin %s ga yuborib bo'lmadi: %s", admin_id, e)
