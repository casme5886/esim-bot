"""Trip.com'dan eSIM'ni avtomatik sotib olish (sizning akkauntingiz orqali, brauzer robot).

Ishlash tartibi:
  1. Buyurtma "to'landi" bo'lganda bot paketning Trip.com havolasini ochadi va narxni o'qiydi.
  2. Adminga skrinshot + narx + «🛒 Sotib ol» tugmasi yuboriladi (bir tugma bilan tasdiqlash).
  3. Tasdiqlansa — «Pay» bosiladi, saqlangan karta bilan to'lanadi, buyurtma raqami olinadi.
  4. Buyurtma sahifasidan eSIM ma'lumoti (LPA / SM-DP+ + aktivatsiya kodi) o'qiladi,
     QR kod yasaladi va mijozga avtomatik yuboriladi.
  Har qanday kutilmagan holatda bot TO'XTAYDI va adminga skrinshot yuboradi. Qayta "Pay" bosilmaydi.

Har qadam skrinshoti: trip_logs/<buyurtma>_<qadam>.png (+ .html) — muammo bo'lsa shu fayllarni ko'ring.
"""
import asyncio
import io
import logging
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse, parse_qs, urlencode

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardMarkup, InlineKeyboardButton

import db
from config import ADMIN_IDS, TRIP_DAILY_LIMIT, TRIP_HEADLESS, TRIP_PRICE_TOLERANCE

log = logging.getLogger("trip")
BASE = Path(__file__).parent
PROFILE_DIR = BASE / "trip_profile"   # Trip.com'ga kirgan holatingiz shu yerda saqlanadi
LOG_DIR = BASE / "trip_logs"

CONFIRM_TIMEOUT = 15 * 60   # admin tasdiqlashini kutish (sekund)
QR_WAIT = 10 * 60           # eSIM ma'lumoti chiqishini kutish (sekund)

_playwright = None
_context = None
_lock = asyncio.Lock()
_ctx_lock = asyncio.Lock()   # bir vaqtda faqat bitta brauzer profili ochilsin
_pending: dict[int, asyncio.Future] = {}


class TripError(Exception):
    """Kutilmagan holat — xarid to'xtatiladi."""


# ---------------------------------------------------------------- havola
def normalize_url(url: str) -> str:
    """Admin yopishtirgan havoladan toza xarid havolasini yasaydi (bugungi sana, 1 dona)."""
    u = urlparse(url.strip())
    if "trip.com" not in u.netloc:
        raise ValueError("Havola trip.com dan bo'lishi kerak")
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    if not ("actid" in q and "optid" in q):
        raise ValueError("Havolada actid va optid yo'q. Paketni tanlab «Book now» bosing va ochilgan sahifa havolasini oling")
    clean = {k: q[k] for k in ("actid", "optid", "packageId") if k in q}
    return f"https://www.trip.com/xthings-to-do/booking-activity?{urlencode(clean)}&locale=en-US&curr=USD"


def _booking_url(trip_url: str) -> str:
    return normalize_url(trip_url) + f"&count=1&date={datetime.now():%Y-%m-%d}"  # inglizcha, USD


# ---------------------------------------------------------------- brauzer
async def _get_context():
    async with _ctx_lock:
        return await _get_context_unlocked()


async def _get_context_unlocked():
    global _playwright, _context
    if _context is not None:
        try:
            _ = _context.pages
            return _context
        except Exception:
            _context = None
    from playwright.async_api import async_playwright  # faqat kerak bo'lganda yuklanadi
    _playwright = _playwright or await async_playwright().start()
    PROFILE_DIR.mkdir(exist_ok=True)
    _context = await _playwright.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        headless=TRIP_HEADLESS,
        viewport={"width": 1280, "height": 900},
        locale="en-US",
        args=["--disable-blink-features=AutomationControlled"],
    )
    await _import_session(_context)
    return _context


async def _import_session(ctx):
    """Boshqa kompyuterdan ko'chirilgan Trip.com sessiyasini (trip_state.json) bir marta yuklaydi.
    Windows profili Linux'da ochilmaydi (cookie'lar shifrlangan), shuning uchun cookie'lar shu fayl orqali o'tadi."""
    f = BASE / "trip_state.json"
    if not f.exists():
        return
    try:
        import json
        state = json.loads(f.read_text(encoding="utf-8"))
        cookies = [c for c in state.get("cookies", []) if "trip" in c.get("domain", "")]
        if cookies:
            await ctx.add_cookies(cookies)
        f.rename(f.with_suffix(".imported.json"))
        log.info("Trip.com sessiyasi yuklandi: %s ta cookie", len(cookies))
    except Exception as e:
        log.warning("trip_state.json yuklanmadi: %s", e)


async def _new_page():
    ctx = await _get_context()
    page = await ctx.new_page()
    page.set_default_timeout(30000)
    return page


async def open_login_window():
    """Trip.com'ga qo'lda kirish uchun brauzer oynasini ochadi (/trip_login)."""
    page = await _new_page()
    await page.goto("https://www.trip.com/account/signin")
    return page


async def _snap(page, oid, step) -> bytes:
    LOG_DIR.mkdir(exist_ok=True)
    png = await page.screenshot(full_page=False)
    name = f"{oid}_{datetime.now():%H%M%S}_{step}"
    (LOG_DIR / f"{name}.png").write_bytes(png)
    try:
        (LOG_DIR / f"{name}.html").write_text(await page.content(), encoding="utf-8")
    except Exception:
        pass
    return png


# Sahifadan matn bo'yicha element topib bosish (sayt klasslari tez-tez o'zgaradi, matn esa kamroq)
_CLICK_JS = """(patterns) => {
  const res = patterns.map(p => new RegExp(p, 'i'));
  const vis = e => { const r = e.getBoundingClientRect(); const s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const cands = [...document.querySelectorAll('button,a,[role=button],div,span')]
    .filter(e => vis(e) && res.some(r => r.test((e.innerText || '').trim())));
  // eng ichki (eng kichik) elementni tanlaymiz
  cands.sort((a, b) => (a.innerText || '').length - (b.innerText || '').length);
  const el = cands[0];
  if (!el) return null;
  const btn = el.closest('button,a,[role=button]') || el;
  btn.scrollIntoView({block: 'center'}); btn.click();
  return (el.innerText || '').trim().slice(0, 60);
}"""


async def _click_text(page, *patterns) -> str | None:
    return await page.evaluate(_CLICK_JS, list(patterns))


async def _visible_text(page, text) -> bool:
    try:
        return await page.get_by_text(text, exact=False).first.is_visible(timeout=1500)
    except Exception:
        return False


async def _needs_login(page) -> bool:
    return await _visible_text(page, "Continue with email") or "signin" in page.url


_PRICE_RE = re.compile(r"(?:US)?\$\s?([\d,]+(?:\.\d+)?)")


async def _read_total(page) -> float | None:
    """«Pay» tugmasi atrofidagi (yoki Price Details'dagi) yakuniy narxni o'qiydi."""
    txt = await page.evaluate("""() => {
      const pay = [...document.querySelectorAll('button,div,span,a')].find(e =>
        /^pay( now)?$/i.test((e.innerText || '').trim()) && e.getBoundingClientRect().width > 0);
      let box = pay; for (let i = 0; i < 6 && box; i++) { if (/\\$\\s?\\d/.test(box.innerText)) break; box = box.parentElement; }
      if (box && /\\$\\s?\\d/.test(box.innerText)) return box.innerText;
      const pd = [...document.querySelectorAll('div')].find(e => (e.innerText || '').startsWith('Price Details'));
      return pd ? pd.innerText : document.body.innerText;
    }""")
    amounts = [float(a.replace(",", "")) for a in _PRICE_RE.findall(txt or "")]
    return amounts[-1] if amounts else None


# ---------------------------------------------------------------- Telegram
def _confirm_kb(oid, price):
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=f"🛒 Sotib ol (${price:g})", style="success", callback_data=f"tb:{oid}"),
        InlineKeyboardButton(text="✋ Qo'lda qilaman", callback_data=f"tn:{oid}"),
    ]])


async def _tell(bot: Bot, text, png: bytes | None = None, kb=None):
    for admin_id in ADMIN_IDS:
        try:
            if png:
                await bot.send_photo(admin_id, BufferedInputFile(png, "trip.png"), caption=text[:1024], reply_markup=kb)
            else:
                await bot.send_message(admin_id, text, reply_markup=kb)
        except Exception as e:
            log.warning("Adminga yuborilmadi: %s", e)


def resolve_confirm(oid: int, yes: bool) -> bool:
    """Admin «Sotib ol» / «Qo'lda» bosganda chaqiriladi."""
    fut = _pending.get(oid)
    if fut and not fut.done():
        fut.set_result(yes)
        return True
    return False


# ---------------------------------------------------------------- eSIM ma'lumotini o'qish
_LPA_RE = re.compile(r"LPA:1\$[A-Za-z0-9.\-]+\$[A-Za-z0-9\-]+")
_SMDP_RE = re.compile(r"SM-?DP\+?\s*(?:address|server)?\s*[:：]?\s*([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", re.I)
_CODE_RE = re.compile(r"activation\s*code\s*[:：]?\s*([A-Za-z0-9\-]{8,})", re.I)


def extract_lpa(text: str) -> str | None:
    m = _LPA_RE.search(text or "")
    if m:
        return m.group(0)
    a, c = _SMDP_RE.search(text or ""), _CODE_RE.search(text or "")
    if a and c:
        return f"LPA:1${a.group(1)}${c.group(1)}"
    return None


def make_qr_png(lpa: str) -> bytes:
    import qrcode
    img = qrcode.make(lpa, box_size=10, border=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


async def _find_esim_info(page, oid) -> dict | None:
    """Buyurtma sahifasidan eSIM kodini oladi: havolalar (carddata=LPA...), PDF vaucher yoki matn.
    eSIM kechiksa sahifani yangilab QR_WAIT davomida kutadi."""
    import esim_info
    deadline = asyncio.get_event_loop().time() + QR_WAIT
    while asyncio.get_event_loop().time() < deadline:
        await _click_text(page, r"^(view|show) (qr|esim)", r"^esim (details|info)", r"^(install|activate)( esim)?$",
                          r"^manual(ly)? (install|entry)")
        await page.wait_for_timeout(2500)
        htmls = [await page.content()]
        for fr in page.frames[1:]:
            try:
                htmls.append(await fr.content())
            except Exception:
                pass
        for html in htmls:
            info = esim_info.from_html(html)
            if info.get("lpa"):
                return info
            if info.get("pdf"):  # vaucher PDF havolasi bo'lsa — yuklab olib ichidan o'qiymiz
                try:
                    resp = await page.context.request.get(info["pdf"])
                    r = esim_info.analyze(await resp.body(), "voucher.pdf")
                    if r.get("lpa"):
                        return r
                except Exception as e:
                    log.warning("PDF yuklanmadi: %s", e)
        # "Voucher / Download" tugmasi orqali yuklab olinadigan PDF
        try:
            async with page.expect_download(timeout=8000) as dl:
                clicked = await _click_text(page, r"^(download|view) (voucher|e-?voucher|pdf)", r"^voucher$")
                if not clicked:
                    raise TimeoutError
            path = await (await dl.value).path()
            r = esim_info.analyze(open(path, "rb").read(), "voucher.pdf")
            if r.get("lpa"):
                return r
        except Exception:
            pass
        await _snap(page, oid, "waitqr")
        await page.wait_for_timeout(30000)
        await page.reload()
    return None


# ---------------------------------------------------------------- asosiy jarayon
async def prepare_and_buy(bot: Bot, oid: int, dry_run: bool = False):
    """dry_run=True — faqat narxni o'qib skrinshot yuboradi, hech narsa sotib olmaydi (/trip_test)."""
    async with _lock:
        o = await db.get_order(oid) if not dry_run else None
        if not dry_run:
            if not o or o["status"] != "paid":
                return
            if o.get("trip_status") in ("paying", "bought", "done"):
                return  # hech qachon ikki marta sotib olmaymiz
            if not o.get("trip_url"):
                await db.update_order(oid, trip_status="skipped")
                return
            if await db.trip_bought_today() >= TRIP_DAILY_LIMIT:
                await db.update_order(oid, trip_status="failed")
                return await _tell(bot, f"⛔️ #{oid}: kunlik avto-xarid limiti ({TRIP_DAILY_LIMIT}) tugadi. Qo'lda qiling.")
        page = None
        try:
            if dry_run:
                p = await db.get_package(oid)  # dry_run'da oid = paket ID
                if not p or not p.get("trip_url"):
                    raise TripError("Bu paketga Trip.com havolasi qo'shilmagan")
                url, cost, title = _booking_url(p["trip_url"]), p["cost_usd"], f"Paket {p['id']}: {p['country']}"
            else:
                await db.update_order(oid, trip_status="preparing")
                url, cost, title = _booking_url(o["trip_url"]), o["cost_usd"], f"#{oid}: {o['country']}"

            page = await _new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await page.wait_for_timeout(5000)

            if await _needs_login(page):
                png = await _snap(page, oid, "login")
                if not dry_run:
                    await db.update_order(oid, trip_status="login")
                raise TripError("Trip.com akkauntiga kirilmagan. /trip_login yuboring, ochilgan oynada kiring, "
                                "keyin buyurtmani qayta boshlang.", png)

            price = None
            for _ in range(10):
                price = await _read_total(page)
                if price:
                    break
                await page.wait_for_timeout(1500)
            png = await _snap(page, oid, "booking")
            if not price:
                raise TripError("Narx o'qilmadi (valyuta USD emasmi yoki sahifa o'zgarganmi?)", png)

            limit = cost * TRIP_PRICE_TOLERANCE + 1 if cost else None
            info = f"🧾 <b>{title}</b>\n💵 Trip.com narxi: <b>${price:g}</b>"
            if cost:
                info += f" (tannarx ${cost:g})"
            if limit and price > limit:
                if not dry_run:
                    await db.update_order(oid, trip_status="failed", trip_price=str(price))
                raise TripError(f"Narx kutilganidan qimmat: ${price:g} > ${limit:.2f}. Sotib olinmadi.", png)

            if dry_run:
                await page.close()
                return await _tell(bot, info + "\n\n✅ Sinov: sahifa ochildi, narx o'qildi. Hech narsa sotib olinmadi.", png)

            # ---- adminning tasdig'i
            await db.update_order(oid, trip_status="confirm", trip_price=str(price))
            fut = asyncio.get_event_loop().create_future()
            _pending[oid] = fut
            await _tell(bot, info + "\n\nSkrinshotni tekshiring. Sotib olaymi?", png, _confirm_kb(oid, price))
            try:
                yes = await asyncio.wait_for(fut, CONFIRM_TIMEOUT)
            except asyncio.TimeoutError:
                yes = False
            finally:
                _pending.pop(oid, None)
            if not yes:
                await db.update_order(oid, trip_status="skipped")
                await page.close()
                return await _tell(bot, f"✋ #{oid}: avto-xarid bekor qilindi — Mini App orqali qo'lda QR yuboring.")

            # ---- to'lov (bu nuqtadan keyin hech qachon qayta urinilmaydi)
            await db.update_order(oid, trip_status="paying")
            clicked = await _click_text(page, r"^pay$", r"^pay now$", r"^book now$", r"^submit$")
            if not clicked:
                raise TripError("«Pay» tugmasi topilmadi", await _snap(page, oid, "nopay"))
            await page.wait_for_timeout(8000)
            await _snap(page, oid, "payment")

            # To'lov sahifasi: saqlangan karta bilan yakuniy tugma
            if re.search(r"pay|payment|cashier", page.url, re.I) or await _visible_text(page, "Payment method"):
                if await _visible_text(page, "CVV") or await _visible_text(page, "Security code"):
                    raise TripError("To'lov sahifasi CVV kodni so'rayapti. Bot oynasida to'lovni o'zingiz yakunlang, "
                                    "keyin QR'ni Mini App orqali yuboring.", await _snap(page, oid, "cvv"))
                await _click_text(page, r"^pay (now|us\$)", r"^pay\s?us\$[\d.,]+$", r"^confirm (and )?pay", r"^pay$")
                await page.wait_for_timeout(10000)

            # ---- natija
            success = False
            for _ in range(12):
                body = await page.evaluate("() => document.body.innerText")
                if re.search(r"(booking|payment|order) (confirmed|successful|complete)|thank you|booked successfully", body, re.I):
                    success = True
                    break
                await page.wait_for_timeout(5000)
            png = await _snap(page, oid, "result")
            body = await page.evaluate("() => document.body.innerText")
            m = re.search(r"(?:booking|order)\s*(?:no\.?|number|id)\s*[:：]?\s*(\d{8,})", body, re.I)
            order_no = m.group(1) if m else ""
            if not success and not order_no:
                await db.update_order(oid, trip_status="failed")
                raise TripError("To'lov natijasi aniq emas. Trip.com'da «My bookings»ni tekshiring — "
                                "sotib olingan bo'lsa QR'ni qo'lda yuboring. Bot qayta urinmaydi.", png)
            await db.update_order(oid, trip_status="bought", trip_order_no=order_no)
            await _tell(bot, f"✅ #{oid} Trip.com'da sotib olindi (buyurtma {order_no or '—'}). eSIM ma'lumoti kutilmoqda…", png)

            # ---- eSIM ma'lumotini olish
            await _click_text(page, r"^view (booking|order)", r"^(booking|order) details$", r"^manage booking$")
            await page.wait_for_timeout(5000)
            info = await _find_esim_info(page, oid)
            lpa = info.get("lpa") if info else None
            if not lpa:
                png = await _snap(page, oid, "noqr")
                raise TripError(f"#{oid}: sotib olindi, lekin eSIM ma'lumoti sahifada topilmadi. Trip.com ilova/emailidan "
                                "QR'ni olib, Mini App orqali yuboring.", png)

            import services  # aylana importdan qochish
            await services.deliver(bot, oid, lpa=lpa, usage=info.get("usage"))
            await db.update_order(oid, trip_status="done")
            await _tell(bot, f"🎉 #{oid} — eSIM avtomatik ravishda mijozga yuborildi.")
            await page.close()

        except TripError as e:
            msg, png = e.args[0], (e.args[1] if len(e.args) > 1 else None)
            o2 = await db.get_order(oid) if not dry_run else None
            if o2 and o2.get("trip_status") in ("preparing", "confirm"):
                await db.update_order(oid, trip_status="failed")
            await _tell(bot, f"⚠️ {msg}", png)
        except Exception as e:
            log.exception("Trip.com xatosi")
            png = None
            try:
                png = await _snap(page, oid, "error") if page else None
            except Exception:
                pass
            o2 = await db.get_order(oid) if not dry_run else None
            if o2 and o2.get("trip_status") in ("preparing", "confirm"):
                await db.update_order(oid, trip_status="failed")
            note = " To'lov bosilgan bo'lishi mumkin — Trip.com'da tekshiring!" if o2 and o2.get("trip_status") == "paying" else ""
            await _tell(bot, f"⚠️ #{oid}: avto-xarid to'xtadi: {e}.{note}", png)


def start(bot: Bot, oid: int):
    """Fon vazifasi sifatida ishga tushiradi (bot javob berishda davom etadi)."""
    asyncio.create_task(prepare_and_buy(bot, oid))
