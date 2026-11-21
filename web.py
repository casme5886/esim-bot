"""Mini App uchun veb-server: sahifa + API (bot bilan bitta jarayonda ishlaydi)."""
import json
import re
import math
import logging
import mimetypes
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.types import LabeledPrice
from aiogram.utils.web_app import safe_parse_webapp_init_data

import db
import keyboards as kb
from utils import order_card
import services
from config import (ADMIN_IDS, BOT_USERNAME, BOT_TOKEN, CLICK_PROVIDER_TOKEN, PAYME_PROVIDER_TOKEN, PAYMENT_PROVIDER_TOKEN,
                    SUPPORT_USERNAME)


def provider_tokens() -> dict:
    """Mavjud onlayn to'lov usullari: {"click": token, "payme": token} (bo'shlari chiqarib tashlanadi)."""
    out = {"click": CLICK_PROVIDER_TOKEN, "payme": PAYME_PROVIDER_TOKEN}
    if PAYMENT_PROVIDER_TOKEN and not (CLICK_PROVIDER_TOKEN or PAYME_PROVIDER_TOKEN):
        out["online"] = PAYMENT_PROVIDER_TOKEN   # bitta umumiy token — "Click / Payme" deb ko'rsatiladi
    return {k: v for k, v in out.items() if v}
import i18n
from handlers.user import invoice_texts, start_card_order

log = logging.getLogger(__name__)
WEBAPP_DIR = Path(__file__).parent / "webapp"
REGIONS = {"asia", "europe", "mideast", "america", "africa", "global", ""}


def _err(status, msg):
    cls = {400: web.HTTPBadRequest, 401: web.HTTPUnauthorized, 403: web.HTTPForbidden, 404: web.HTTPNotFound}[status]
    return cls(text=json.dumps({"error": msg}), content_type="application/json")


def _auth(request: web.Request):
    """Telegram initData imzosini tekshiradi — soxta so'rovlardan himoya."""
    try:
        return safe_parse_webapp_init_data(BOT_TOKEN, request.headers.get("X-Init-Data", ""))
    except ValueError:
        raise _err(401, "Telegram orqali oching")


def _admin(request: web.Request):
    data = _auth(request)
    if data.user.id not in ADMIN_IDS:
        raise _err(403, "Faqat admin uchun")
    return data


@web.middleware
async def no_cache(request, handler):
    resp = await handler(request)
    resp.headers.setdefault("Cache-Control", "no-cache")
    return resp


# ================= Mijoz =================
# ================= Statik fayllar: xotirada kesh + gzip + uzoq muddatli brauzer keshi =================
_STATIC_CACHE: dict = {}
_COMPRESS = {".js", ".css", ".html", ".svg", ".json", ".txt"}


def _load_static(path):
    """Fayl -> (raw, gz, etag, ctype); fayl o'zgarsa (mtime) qayta o'qiladi."""
    import gzip
    import hashlib
    st = path.stat()
    hit = _STATIC_CACHE.get(path)
    if hit and hit[0] == (st.st_mtime_ns, st.st_size):
        return hit[1]
    raw = path.read_bytes()
    gz = gzip.compress(raw, 7) if path.suffix in _COMPRESS and len(raw) > 1024 else None
    etag = '"' + hashlib.md5(raw).hexdigest()[:16] + '"'
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    if path.suffix == ".webp":
        ctype = "image/webp"
    if ctype.startswith("text/") or ctype in ("application/javascript", "application/json"):
        ctype += "; charset=utf-8"
    val = (raw, gz, etag, ctype)
    _STATIC_CACHE[path] = ((st.st_mtime_ns, st.st_size), val)
    return val


def _send_cached(request, raw, gz, etag, ctype, cache_control):
    headers = {"ETag": etag, "Cache-Control": cache_control, "Vary": "Accept-Encoding"}
    if request.headers.get("If-None-Match") == etag:
        return web.Response(status=304, headers=headers)
    body = raw
    if gz and "gzip" in request.headers.get("Accept-Encoding", ""):
        body = gz
        headers["Content-Encoding"] = "gzip"
    return web.Response(body=body, headers=headers, content_type=ctype.split(";")[0],
                        charset="utf-8" if "charset" in ctype else None)


async def static_file(request):
    rel = request.match_info["path"]
    base = (WEBAPP_DIR / "static").resolve()
    path = (base / rel).resolve()
    if base not in path.parents or not path.is_file():
        raise web.HTTPNotFound()
    raw, gz, etag, ctype = _load_static(path)
    if request.query.get("v"):
        cc = "public, max-age=31536000, immutable"    # versiyali fayl: o'zgarsa ?v= raqami o'zgaradi
    elif rel.startswith(("flags/", "banners/")):
        cc = "public, max-age=2592000"                # bayroqlar va bannerlar (nomi noyob) o'zgarmaydi: 30 kun
    else:
        cc = "no-cache"
    return _send_cached(request, raw, gz, etag, ctype, cc)


async def index(request):
    raw, gz, etag, ctype = _load_static(WEBAPP_DIR / "index.html")
    return _send_cached(request, raw, gz, etag, ctype, "no-cache")


_CATALOG = {"ver": -1, "day": ""}


async def catalog(request):
    """Katalog xotirada saqlanadi (paket/sozlama o'zgarsa qayta yig'iladi), gzip + ETag: o'zgarmagan bo'lsa 304."""
    import promo
    day = promo.datetime.now(promo.TZ).strftime("%Y-%m-%d")      # aksiya muddati tugasa ertasi kuni o'zi o'chadi
    if _CATALOG["ver"] != db.CATALOG_VER or _CATALOG["day"] != day:
        import gzip
        import hashlib
        ver = db.CATALOG_VER
        data = await _build_catalog()
        raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode()
        _CATALOG.update(ver=ver, day=day, raw=raw, gz=gzip.compress(raw, 6), etag='"c' + hashlib.md5(raw).hexdigest()[:16] + '"')
    return _send_cached(request, _CATALOG["raw"], _CATALOG["gz"], _CATALOG["etag"], "application/json; charset=utf-8",
                        "no-cache")


# ================= Katalog bannerlari (admin rasm yuklaydi) =================
BANNER_DIR = WEBAPP_DIR / "static" / "banners"
MAX_BANNERS = 6


async def _banners() -> list:
    try:
        out = json.loads(await db.get_setting("banners") or "[]")
    except ValueError:
        out = []
    return [b for b in out if (BANNER_DIR / b.get("file", "")).is_file()]


def _banner_public(b):
    return {"id": b["id"], "img": "/static/banners/" + b["file"], "w": b["w"], "h": b["h"],
            "link": b.get("link") or {"type": "", "value": ""}}


async def admin_banners(request):
    _admin(request)
    return web.json_response([_banner_public(b) for b in await _banners()])


def _clean_link(t, v):
    t, v = str(t or ""), (json.dumps(v) if isinstance(v, list) else str(v or "")).strip()[:6000]
    if t == "url":
        if v and not v.startswith(("http://", "https://")):
            v = "https://" + v
        if not v or " " in v or "." not in v or len(v) > 500:
            raise _err(400, "Havola noto'g'ri")
        return {"type": "url", "value": v}
    if t == "country":
        if not v:
            raise _err(400, "Davlatni tanlang")
        return {"type": "country", "value": v}
    if t == "countries":
        try:
            names = [str(x).strip()[:80] for x in json.loads(v) if str(x).strip()][:60]
        except (ValueError, TypeError):
            names = [x.strip() for x in v.split("|") if x.strip()][:60]
        if not names:
            raise _err(400, "Kamida bitta davlatni belgilang")
        if len(names) == 1:
            return {"type": "country", "value": names[0]}
        return {"type": "countries", "value": names}
    return {"type": "", "value": ""}


async def admin_banner_add(request):
    """multipart: image + link_type (''/country/url) + link_value. Rasm 1200px gacha kichraytiriladi, WebP."""
    import io
    import secrets
    from PIL import Image, ImageOps
    _admin(request)
    items = await _banners()
    if len(items) >= MAX_BANNERS:
        raise _err(400, f"Ko'pi bilan {MAX_BANNERS} ta banner")
    raw, lt, lv = None, "", ""
    reader = await request.multipart()
    while True:
        part = await reader.next()
        if part is None:
            break
        if part.name == "image":
            raw = await part.read(decode=False)
        elif part.name == "link_type":
            lt = await part.text()
        elif part.name == "link_value":
            lv = await part.text()
    if not raw:
        raise _err(400, "Rasm tanlanmagan")
    if len(raw) > 10 * 1024 * 1024:
        raise _err(400, "Rasm 10 MB dan kichik bo'lsin")
    link = _clean_link(lt, lv)
    try:
        im = ImageOps.exif_transpose(Image.open(io.BytesIO(raw)))
        im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    except Exception:
        raise _err(400, "Bu fayl rasm emas (JPG, PNG yoki WebP yuklang)")
    if im.width > 1200:
        im = im.resize((1200, round(im.height * 1200 / im.width)), Image.LANCZOS)
    BANNER_DIR.mkdir(parents=True, exist_ok=True)
    fn = secrets.token_hex(8) + ".webp"
    im.save(BANNER_DIR / fn, "WEBP", quality=86, method=6)
    items.append({"id": secrets.token_hex(4), "file": fn, "w": im.width, "h": im.height, "link": link})
    await db.set_setting("banners", json.dumps(items))
    return web.json_response([_banner_public(b) for b in items])


async def admin_banner_action(request):
    _admin(request)
    bid, action = request.match_info["bid"], request.match_info["action"]
    items = await _banners()
    i = next((k for k, b in enumerate(items) if b["id"] == bid), None)
    if i is None:
        raise _err(404, "Banner topilmadi")
    if action == "delete":
        b = items.pop(i)
        try:
            (BANNER_DIR / b["file"]).unlink()
        except OSError:
            pass
    elif action in ("up", "down"):
        j = i - 1 if action == "up" else i + 1
        if 0 <= j < len(items):
            items[i], items[j] = items[j], items[i]
    elif action == "link":
        body = await request.json()
        items[i]["link"] = _clean_link(body.get("type"), body.get("value"))
    else:
        raise _err(400, "unknown action")
    await db.set_setting("banners", json.dumps(items))
    return web.json_response([_banner_public(b) for b in items])


async def _build_catalog():
    import promo
    rows = await db._fetchall("SELECT * FROM packages WHERE active=1 ORDER BY country, price")
    smap = await promo.sale_map()
    rate = (await _pricing())["rate"]
    countries = {}
    for p in rows:
        pct = promo.sale_pct(smap, p["country"])
        if pct:   # aksiya: [.., narx, kunlik, eski_narx]
            floor = int(max(1000, math.ceil((p.get("cost_usd") or 0) * rate / 1000) * 1000))
            new = promo.sale_price(p["price"], pct, floor)
            if new < p["price"]:
                p = {**p, "old_price": p["price"], "price": new}
        c = countries.setdefault(p["country"], {
            "country": p["country"], "flag": p["flag"], "region": p["region"] or "",
            "popular": bool(p["popular"]), "min_price": p["price"], "packages": []})
        c["min_price"] = min(c["min_price"], p["price"])
        c["popular"] = c["popular"] or bool(p["popular"])
        if p.get("old_price"):
            c["sale"] = max(c.get("sale", 0), round((1 - p["price"] / p["old_price"]) * 100))
        c["region"] = c["region"] or p["region"] or ""
        # ixcham: [id, GB, kun, narx, kunlik] — Mini App o'zi obyektga aylantiradi
        g = p["data_gb"]
        row = [p["id"], int(g) if g == int(g) else g, p["days"], p["price"], 1 if p["daily"] else 0]
        if p.get("old_price"):
            row.append(p["old_price"])
        c["packages"].append(row)
    # mintaqaviy eSIM'lar (Yevropa, Global) — qaysi davlatlarda ishlashi
    import json as _json
    from countries import REGIONAL
    for r in REGIONAL:
        if r["uz"] in countries:
            try:
                countries[r["uz"]]["covers"] = [x for x in _json.loads(await db.get_setting("coverage_" + r["iso"]) or "[]")
                                                if x not in ("EU", "EZ", "UN")]
            except ValueError:
                countries[r["uz"]]["covers"] = []
            countries[r["uz"]]["regional"] = True
    return {
        "v": 2,
        "banners": [_banner_public(b) for b in await _banners()],
        "telegram_pay": bool(provider_tokens()),
        "pay_methods": {"online": list(provider_tokens()), "links": list(await db.pay_links()),
                        "cards": [c["type"] for c in await db.cards()]},
        "support": SUPPORT_USERNAME,
        "countries": sorted(countries.values(), key=lambda c: c["country"]),
    }


async def me(request):
    data = _auth(request)
    return web.json_response({"is_admin": data.user.id in ADMIN_IDS, "lang": await db.get_lang(data.user.id),
                              "currency": await db.get_currency(data.user.id),
                              "support_unread": await _sup_unread(data.user.id),
                              "bot": BOT_USERNAME, "support": SUPPORT_USERNAME,
                              # Cloudflare tunnel foydalanuvchi IP manzilidan mamlakatni beradi (UZ, RU, ...)
                              "country": request.headers.get("CF-IPCountry", "").upper()})


async def _sup_unread(uid):
    import support
    return await support.unread_for_user(uid)


# ================= Yordam chati =================
async def _read_chat_post(request):
    """multipart (text + photo) yoki JSON {text}."""
    text, photo = "", None
    if request.content_type.startswith("multipart/"):
        reader = await request.multipart()
        while True:
            part = await reader.next()
            if part is None:
                break
            if part.name == "text":
                text = (await part.text())[:2000]
            elif part.name == "photo" and part.filename:
                raw = await part.read(decode=False)
                if len(raw) > 10 * 1024 * 1024:
                    raise _err(400, "10 MB")
                ctype = (part.headers.get("Content-Type") or "").lower()
                if not ctype.startswith("image/"):
                    raise _err(400, "image only")
                photo = (raw, part.filename)
    else:
        text = str((await request.json()).get("text", ""))[:2000]
    if not text.strip() and not photo:
        raise _err(400, "empty")
    return text, photo


def _msg_json(m):
    return {"id": m["id"], "admin": bool(m["from_admin"]), "text": m["text"], "photo": bool(m["photo"]),
            "at": m["created_at"]}


async def support_get(request):
    import support
    data = _auth(request)
    after = int(request.query.get("after", 0) or 0)
    msgs = await support.history(data.user.id, after)
    await support.mark_seen(data.user.id, by_admin=False)
    return web.json_response({"msgs": [_msg_json(m) for m in msgs]})


async def support_post(request):
    import support
    data = _auth(request)
    u = data.user
    await db.save_user(u.id, u.username, " ".join(x for x in [u.first_name, u.last_name] if x))
    text, photo = await _read_chat_post(request)
    m = await support.add(u.id, False, text, photo, source="app")
    await support.notify_admins(request.app["bot"], m)
    return web.json_response(_msg_json(m))


async def support_file(request):
    """Chatdagi surat: faqat o'z suhbatidagi (yoki admin)."""
    import support
    data = _auth(request)
    m = await support.get(int(request.match_info["mid"]))
    if not m or not m["photo"] or (m["user_id"] != data.user.id and data.user.id not in ADMIN_IDS):
        raise _err(404, "not found")
    p = support.photo_path(m["photo"])
    if not p:
        raise _err(404, "not found")
    return web.FileResponse(p, headers={"Cache-Control": "private, max-age=86400"})


async def admin_chats(request):
    import support
    _admin(request)
    return web.json_response({"chats": await support.chats(), "unread": await support.unread_for_admin()})


async def admin_chat_get(request):
    import support
    _admin(request)
    uid = int(request.match_info["uid"])
    after = int(request.query.get("after", 0) or 0)
    msgs = await support.history(uid, after)
    await support.mark_seen(uid, by_admin=True)
    out = {"msgs": [_msg_json(m) for m in msgs]}
    if not after:
        out["user"] = await support.user_brief(uid)
    return web.json_response(out)


async def admin_chat_post(request):
    import support
    _admin(request)
    uid = int(request.match_info["uid"])
    if not await db._fetchone("SELECT 1 FROM users WHERE id=?", (uid,)):
        raise _err(404, "Foydalanuvchi topilmadi")
    text, photo = await _read_chat_post(request)
    m = await support.add(uid, True, text, photo)
    await support.mark_seen(uid, by_admin=True)
    try:
        await support.deliver_to_user(request.app["bot"], m)
        delivered = True
    except Exception as e:
        log.warning("Chat javobi %s ga yetmadi: %s", uid, e)
        delivered = False
    return web.json_response({**_msg_json(m), "delivered": delivered})


async def set_lang(request):
    """Mini App'da til almashtirilganda — bot xabarlari ham shu tilda bo'ladi."""
    data = _auth(request)
    body = await request.json()
    u = data.user
    await db.save_user(u.id, u.username, " ".join(x for x in [u.first_name, u.last_name] if x))
    cur = str(body.get("currency", "")).upper()
    if cur:                                   # valyuta tanlovi ham saqlanadi (boshqa qurilmada ham shu bo'ladi)
        if cur not in ("USD", "EUR", "RUB", "CNY", "UZS"):
            raise _err(400, "unknown currency")
        await db.set_currency(u.id, cur)
    lang = str(body.get("lang", ""))
    if lang:
        if lang not in i18n.LANGS:
            raise _err(400, "unknown language")
        if lang != await db.get_lang(u.id):
            await db.set_lang(u.id, lang)
            from handlers.user import apply_lang_ui
            await apply_lang_ui(request.app["bot"], u.id, lang)   # bot menyusi va xabarlari ham shu tilda
    return web.json_response({"ok": True})


async def my_orders(request):
    data = _auth(request)
    orders = await db.user_orders(data.user.id, limit=30, include_new=True)
    return web.json_response([
        {"id": o["id"], "country": o["country"], "flag": o["flag"], "data_gb": o["data_gb"], "daily": o.get("daily") or 0,
         "has_esim": o["status"] == "delivered" and "LPA:" in (o.get("note") or ""),
         "days": o["days"], "price": o["price"], "status": o["status"], "created_at": o["created_at"],
         "package_id": o["package_id"], "pkg_active": bool(o.get("pkg_active"))}
        for o in orders
    ])


async def _my_order(request):
    data = _auth(request)
    o = await db.get_order(int(request.match_info["oid"]))
    if not o or o["user_id"] != data.user.id:
        raise _err(404, "Buyurtma topilmadi")
    return o


async def order_esim(request):
    """Mijozning o'z buyurtmasi bo'yicha eSIM ma'lumoti (QR rasm base64 bilan)."""
    import base64
    import esim_info
    o = await _my_order(request)
    lpa = esim_info.from_text(o.get("note") or "")
    if o["status"] != "delivered" or not lpa:
        raise _err(404, "eSIM hali tayyor emas")
    smdp, code = esim_info.split_lpa(lpa)
    return web.json_response({
        "id": o["id"], "country": o["country"], "flag": o["flag"], "data_gb": o["data_gb"],
        "daily": o.get("daily") or 0, "days": o["days"], "date": (o.get("updated_at") or "")[:10],
        "lpa": lpa, "smdp": smdp, "code": code, "ios": esim_info.ios_url(lpa), "android": esim_info.android_url(lpa),
        "usage": o.get("usage_url") or None,
        "qr": "data:image/png;base64," + base64.b64encode(esim_info.make_qr_png(lpa)).decode(),
    })


async def order_send_pdf(request):
    o = await _my_order(request)
    try:
        await services.send_voucher(request.app["bot"], o["id"])
    except services.OrderError as e:
        raise _err(400, str(e))
    return web.json_response({"ok": True})


async def _new_order(uid, p, body):
    """Buyurtma: promo-kod / taklif chegirmasi / balans hisobga olinadi (server o'zi qayta hisoblaydi)."""
    import promo
    try:
        q = await promo.quote(uid, p, body.get("promo", ""), bool(body.get("use_balance")))
    except promo.PromoError as e:
        raise _err(400, i18n.t(await db.user_lang(uid), e.key))
    if not await promo.reserve(uid, q):
        raise _err(400, i18n.t(await db.user_lang(uid), "promo_expired"))
    rate = (await _pricing())["rate"]
    oid = await db.create_order(uid, p["id"], q["final"])
    await db.update_order(oid, orig_price=q["orig"], discount=q["discount"] + q.get("sale_off", 0), promo=q["promo"],
                          balance_used=q["balance_used"], cost_uzs=int(round((p.get("cost_usd") or 0) * rate)))
    return oid


async def _pricing():
    import trip_import
    return await trip_import.pricing()


async def quote_api(request):
    """Checkout sahifasi: chegirma va balans bilan yakuniy narx."""
    import promo
    data = _auth(request)
    body = await request.json()
    p = await db.get_package(int(body.get("package_id", 0)))
    if not p or not p["active"]:
        raise _err(400, i18n.t(await db.user_lang(data.user.id), "pkg_unavailable"))
    try:
        q = await promo.quote(data.user.id, p, body.get("promo", ""), bool(body.get("use_balance")))
    except promo.PromoError as e:
        q = await promo.quote(data.user.id, p, "", bool(body.get("use_balance")))
        q["promo_error"] = i18n.t(await db.user_lang(data.user.id), e.key)
    return web.json_response(q)


async def ref_api(request):
    """Mini App: taklif havolasi, balans, statistika."""
    import promo
    data = _auth(request)
    info = await promo.ref_info(data.user.id)
    info["link"] = f"https://t.me/{BOT_USERNAME}?start=ref_{data.user.id}"
    return web.json_response(info)


async def create_order(request):
    data = _auth(request)
    body = await request.json()
    bot: Bot = request.app["bot"]
    dp: Dispatcher = request.app["dp"]
    u = data.user
    await db.save_user(u.id, u.username, " ".join(x for x in [u.first_name, u.last_name] if x))

    p = await db.get_package(int(body.get("package_id", 0)))
    if not p or not p["active"]:
        return web.json_response({"error": i18n.t(await db.user_lang(u.id), "pkg_unavailable")}, status=400)

    tokens = provider_tokens()
    method = body.get("method")
    if method == "telegram" and tokens:
        method = next(iter(tokens))
    if method in tokens:
        oid = await _new_order(u.id, p, body)
        await db.update_order(oid, payment_method=method)
        title, desc, label = invoice_texts(await db.user_lang(u.id), p, oid)
        link = await bot.create_invoice_link(
            title=title, description=desc,
            payload=f"order:{oid}",
            provider_token=tokens[method],
            currency="UZS",
            prices=[LabeledPrice(label=label, amount=(await db.get_order(oid))["price"] * 100)],
        )
        return web.json_response({"order_id": oid, "invoice_link": link})

    if method == "link":
        # To'lov havolasi (Click / Payme / Uzum hamyon): mijoz havola orqali to'laydi, keyin chek yuklaydi
        kind = body.get("link")
        if kind not in await db.pay_links():
            return web.json_response({"error": "Bu to'lov usuli hozir mavjud emas"}, status=400)
        oid = await _new_order(u.id, p, body)
        await db.update_order(oid, payment_method=f"{kind}_link")
        return web.json_response({"order_id": oid, "pay": await _pay_info(oid)})

    if body.get("in_app"):
        # Karta orqali, hammasi Mini App ichida: karta ko'rsatiladi, chek shu yerga yuklanadi (chatga hech narsa ketmaydi)
        oid = await _new_order(u.id, p, body)
        await db.update_order(oid, payment_method="card")
        return web.json_response({"order_id": oid, "pay": await _pay_info(oid)})

    # Eski usul (chat orqali): karta ma'lumotlari chatga yuboriladi, chek chatda qabul qilinadi
    state = dp.fsm.get_context(bot=bot, chat_id=u.id, user_id=u.id)
    text, markup, oid = await start_card_order(u.id, p, state)
    await bot.send_message(u.id, text, reply_markup=markup)
    return web.json_response({"order_id": oid, "card": True})


async def _pay_info(oid):
    o = await db.get_order(oid)
    cards = await db.cards()
    number, holder = (cards[0]["number"], cards[0]["holder"]) if cards else ("", "")
    return {"order_id": oid, "amount": o["price"], "status": o["status"], "card_number": number, "card_holder": holder,
            "cards": cards, "method": o.get("payment_method") or "card",
            "links": {k: v.replace("{amount}", str(o["price"])) for k, v in (await db.pay_links()).items()},
            "country": o["country"], "flag": o["flag"], "data_gb": o["data_gb"], "daily": o.get("daily") or 0,
            "days": o["days"]}


async def _own_order(request):
    data = _auth(request)
    o = await db.get_order(int(request.match_info["oid"]))
    if not o or o["user_id"] != data.user.id:
        raise _err(404, "Buyurtma topilmadi")
    return data, o


async def order_pay_info(request):
    """To'lanmagan buyurtmani Mini App'da qayta ochish (Buyurtmalarim -> To'lash)."""
    _, o = await _own_order(request)
    return web.json_response(await _pay_info(o["id"]))


async def order_receipt(request):
    """Mijoz Mini App'dan chek rasmini yuklaydi -> adminlarga tasdiqlash tugmalari bilan boradi."""
    data, o = await _own_order(request)
    lang = await db.user_lang(data.user.id)
    if o["status"] != "new":
        raise _err(400, i18n.t(lang, "order_expired") if o["status"] == "cancelled" else "Chek allaqachon yuborilgan")
    reader = await request.multipart()
    part = await reader.next()
    if part is None or part.name != "receipt":
        raise _err(400, "Fayl yo'q")
    raw = await part.read(decode=False)
    if len(raw) > 10 * 1024 * 1024:
        raise _err(400, "Fayl juda katta (10 MB gacha)")
    fname = part.filename or "receipt.jpg"
    ctype = (part.headers.get("Content-Type") or "").lower()
    bot: Bot = request.app["bot"]
    o_full = await db.get_order(o["id"])
    pm = (o_full.get("payment_method") or "card")
    how = pm[:-5].capitalize() + " havolasi" if pm.endswith("_link") else "KARTA"
    text = f"🏦 <b>{how} TO'LOVI (Mini App) — chekni tekshiring</b>\n\n" + order_card(o_full)
    file_id, is_photo = None, ctype.startswith("image/") and not ctype.endswith("heic")
    from aiogram.types import BufferedInputFile
    for i, admin_id in enumerate(ADMIN_IDS):
        try:
            media = file_id or BufferedInputFile(raw, fname)
            if is_photo:
                m = await bot.send_photo(admin_id, media, caption=text, reply_markup=kb.admin_receipt_kb(o["id"]))
                file_id = file_id or m.photo[-1].file_id
            else:
                m = await bot.send_document(admin_id, media, caption=text, reply_markup=kb.admin_receipt_kb(o["id"]))
                file_id = file_id or m.document.file_id
        except Exception as e:
            log.warning("Chekni admin %s ga yuborib bo'lmadi: %s", admin_id, e)
    if not file_id:
        raise _err(500, "Chekni yuborib bo'lmadi, qayta urinib ko'ring")
    await db.update_order(o["id"], status="checking", receipt_file_id=file_id)
    return web.json_response({"ok": True, "status": "checking"})


async def order_cancel(request):
    """Mijoz to'lanmagan buyurtmani bekor qiladi."""
    _, o = await _own_order(request)
    if o["status"] != "new":
        raise _err(400, "Bu buyurtmani bekor qilib bo'lmaydi")
    await db.update_order(o["id"], status="cancelled")
    return web.json_response({"ok": True})


# ================= Admin: karta =================
async def admin_get_card(request):
    _admin(request)
    number, holder = await db.card_info()
    return web.json_response({"card_number": number, "card_holder": holder, "cards": await db.cards(),
                              "online": list(provider_tokens()), "links": await db.pay_links()})


async def admin_set_links(request):
    """Click / Payme / Uzum hamyon havolalarini saqlash (token emas, oddiy to'lov havolasi)."""
    from urllib.parse import urlparse
    data = _admin(request)
    body = await request.json()
    out = {}
    for k in db.PAY_LINK_KINDS:
        url = str(body.get(k) or "").strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        url = "https://" + url.split("://", 1)[1]
        u = urlparse(url)
        if not u.netloc or "." not in u.netloc or " " in url or len(url) > 500:
            return web.json_response({"error": f"{k.capitalize()} havolasi noto'g'ri"}, status=400)
        out[k] = url
    await db.set_setting("pay_links", json.dumps(out))
    log.info("To'lov havolalari yangilandi: %s (admin %s)", ", ".join(out) or "yo'q", data.user.id)
    return web.json_response({"links": await db.pay_links()})


async def admin_set_card(request):
    data = _admin(request)
    body = await request.json()
    if "cards" in body:  # yangi: bir nechta karta (Humo, Uzcard, ...)
        cards = []
        for c in body["cards"][:3]:
            digits = "".join(ch for ch in str(c.get("number", "")) if ch.isdigit())
            holder = " ".join(str(c.get("holder", "")).split())[:60].upper()
            if not digits and not holder:
                continue
            if len(digits) != 16:
                return web.json_response({"error": "Karta raqami 16 ta raqamdan iborat bo'lishi kerak"}, status=400)
            if len(holder) < 3:
                return web.json_response({"error": "Karta egasining ismini yozing"}, status=400)
            cards.append({"number": " ".join(digits[i:i + 4] for i in range(0, 16, 4)), "holder": holder})
        if not cards:
            return web.json_response({"error": "Kamida bitta karta kiriting"}, status=400)
        await db.set_setting("cards", json.dumps(cards))
        await db.set_setting("card_number", cards[0]["number"])
        await db.set_setting("card_holder", cards[0]["holder"])
        log.info("Kartalar yangilandi: %s ta (admin %s)", len(cards), data.user.id)
        return web.json_response({"cards": await db.cards()})
    digits = "".join(ch for ch in str(body.get("card_number", "")) if ch.isdigit())
    holder = " ".join(str(body.get("card_holder", "")).split())[:60]
    if len(digits) != 16:
        return web.json_response({"error": "Karta raqami 16 ta raqamdan iborat bo'lishi kerak"}, status=400)
    if len(holder) < 3:
        return web.json_response({"error": "Karta egasining ismini yozing"}, status=400)
    number = " ".join(digits[i:i + 4] for i in range(0, 16, 4))
    await db.set_setting("card_number", number)
    await db.set_setting("card_holder", holder.upper())
    log.info("Karta ma'lumotlari yangilandi (admin %s)", data.user.id)
    return web.json_response({"card_number": number, "card_holder": holder.upper()})


# ================= Admin: paketlar =================
class BadInput(ValueError):
    pass


def _num(v, cast=float):
    try:
        return cast(str(v).replace(" ", "").replace(",", ".") or 0)
    except ValueError:
        raise BadInput("Raqamlarni to'g'ri kiriting")


def _clean_package(body: dict, partial=False):
    out = {}
    try:
        if "country" in body or not partial:
            out["country"] = " ".join(str(body["country"]).split())[:40]
            if not out["country"]:
                raise BadInput("Davlat nomini yozing")
        if "flag" in body:
            out["flag"] = str(body["flag"]).strip()[:8] or "🌍"
        if "region" in body:
            out["region"] = body["region"] if body["region"] in REGIONS else ""
        if "popular" in body:
            out["popular"] = 1 if body["popular"] else 0
        if "active" in body:
            out["active"] = 1 if body["active"] else 0
        if "daily" in body:
            out["daily"] = 1 if body["daily"] else 0
        if "data_gb" in body or not partial:
            out["data_gb"] = _num(body["data_gb"])
            if out["data_gb"] < 0:
                raise BadInput("GB manfiy bo'lmaydi")
        if "days" in body or not partial:
            out["days"] = int(_num(body["days"]))
            if not 1 <= out["days"] <= 365:
                raise BadInput("Kun 1–365 oralig'ida bo'lsin")
        if "price" in body or not partial:
            out["price"] = int(_num(body["price"]))
            if out["price"] < 1000:
                raise BadInput("Narx juda kichik")
        if "cost_usd" in body:
            out["cost_usd"] = _num(body["cost_usd"] or 0)
        if "trip_url" in body:
            url = str(body["trip_url"] or "").strip()
            if url:
                import trip_buyer
                try:
                    url = trip_buyer.normalize_url(url)
                except ValueError as e:
                    raise BadInput(str(e))
            out["trip_url"] = url
    except KeyError as e:
        raise _err(400, f"Maydon yetishmaydi: {e.args[0]}")
    except BadInput as e:
        raise _err(400, str(e))
    return out


async def admin_packages(request):
    _admin(request)
    resp = web.json_response(await db.all_packages())
    resp.enable_compression()
    return resp


async def admin_add_package(request):
    _admin(request)
    p = _clean_package(await request.json())
    pid = await db.add_package(p["country"], p.get("flag", "🌍"), p["data_gb"], p["days"], p["price"],
                               p.get("cost_usd", 0), p.get("region", ""), p.get("popular", 0), p.get("daily", 0))
    if p.get("trip_url"):
        await db.update_package(pid, trip_url=p["trip_url"])
    # Shu davlatning boshqa paketlariga ham bir xil bayroq/mintaqa/mashhurlik
    await db.set_country_meta(p["country"], **{k: p[k] for k in ("flag", "region", "popular") if k in p})
    return web.json_response(await db.get_package(pid))


async def admin_update_package(request):
    _admin(request)
    pid = int(request.match_info["pid"])
    old = await db.get_package(pid)
    if not old:
        raise _err(404, "Paket topilmadi")
    p = _clean_package(await request.json(), partial=True)
    await db.update_package(pid, **p)
    meta = {k: p[k] for k in ("flag", "region", "popular") if k in p}
    if meta:
        await db.set_country_meta(p.get("country", old["country"]), **meta)
    return web.json_response(await db.get_package(pid))


async def admin_delete_package(request):
    _admin(request)
    result = await db.delete_package(int(request.match_info["pid"]))
    return web.json_response({"result": result})


# ================= Admin: buyurtmalar =================
def _order_json(o):
    return {k: o.get(k) for k in ("id", "user_id", "username", "full_name", "country", "flag", "data_gb", "daily", "days",
                                  "price", "cost_usd", "status", "payment_method", "created_at", "updated_at",
                                  "trip_status", "trip_order_no", "trip_price")} | {
        "has_receipt": bool(o.get("receipt_file_id")), "has_trip": bool(o.get("trip_url"))}


async def admin_orders(request):
    _admin(request)
    rows = await db.admin_orders(request.query.get("group", "pending"))
    return web.json_response([_order_json(o) for o in rows])


async def admin_receipt(request):
    _admin(request)
    o = await db.get_order(int(request.match_info["oid"]))
    if not o or not o["receipt_file_id"]:
        raise _err(404, "Chek yo'q")
    bot: Bot = request.app["bot"]
    f = await bot.get_file(o["receipt_file_id"])
    buf = await bot.download_file(f.file_path)
    ctype = mimetypes.guess_type(f.file_path or "")[0] or "application/octet-stream"
    return web.Response(body=buf.read(), content_type=ctype)


async def admin_order_action(request):
    _admin(request)
    bot: Bot = request.app["bot"]
    oid, action = int(request.match_info["oid"]), request.match_info["action"]
    try:
        if action == "approve":
            await services.approve(bot, oid)
        elif action == "reject":
            await services.reject(bot, oid)
        elif action == "cancel":
            await services.cancel_paid(bot, oid)
        elif action == "autobuy":
            import trip_buyer
            o = await db.get_order(oid)
            if not o or o["status"] != "paid":
                raise services.OrderError("Faqat to'langan buyurtma uchun")
            if not o.get("trip_url"):
                raise services.OrderError("Paketga Trip.com havolasi qo'shilmagan")
            if o.get("trip_status") in ("paying", "bought", "done"):
                raise services.OrderError("Trip.com'da to'lov allaqachon bosilgan — qayta sotib olinmaydi")
            await db.update_order(oid, trip_status="")
            trip_buyer.start(bot, oid)
        elif action == "deliver":
            o = await db.get_order(oid)
            if not o or o["status"] != "paid":
                raise services.OrderError("Avval to'lov tasdiqlanishi kerak")
            if not request.content_type.startswith("multipart/"):
                raise _err(400, "QR rasm yoki LPA kod kerak")
            upload, lpa, note = None, None, None
            reader = await request.multipart()
            async for part in reader:
                if part.name == "file" and part.filename:
                    data = await part.read(decode=False)
                    if len(data) > 10 * 1024 * 1024:
                        raise _err(400, "Fayl 10 MB dan katta")
                    upload = (bytes(data), part.filename)
                elif part.name == "lpa":
                    lpa = (await part.text()).strip() or None
                elif part.name == "note":
                    note = (await part.text()).strip() or None
            if lpa and not lpa.upper().startswith("LPA:"):
                raise _err(400, "Aktivatsiya kodi LPA: bilan boshlanishi kerak")
            r = await services.deliver(bot, oid, upload=upload, lpa=lpa, note=note)
            return web.json_response({**_order_json(await db.get_order(oid)), **r})
        else:
            raise _err(404, "Noma'lum amal")
    except services.OrderError as e:
        raise _err(400, str(e))
    return web.json_response(_order_json(await db.get_order(oid)))


async def admin_import_status(request):
    _admin(request)
    import trip_import
    from countries import COUNTRIES
    return web.json_response({**trip_import.STATE, "countries_total": len(COUNTRIES)})


async def admin_import_start(request):
    _admin(request)
    import trip_import
    body = await request.json()
    if trip_import.STATE["running"]:
        raise _err(400, "Import allaqachon ishlayapti")
    only = [x.strip().lower() for x in body.get("only", []) if x.strip()] or None
    trip_import.start(request.app["bot"], only=only)  # narx sozlamalari admin paneldan olinadi
    return web.json_response({"ok": True})


def _pnum(v, name):
    try:
        return float(str(v).replace(" ", "").replace("\u00a0", "").replace(",", "."))
    except ValueError:
        raise _err(400, f"{name}: raqam kiriting")


async def rates_api(request):
    """Mini App'da narxni boshqa valyutada ko'rsatish uchun kurslar (ochiq, avtorizatsiyasiz)."""
    import rates
    data = await rates.get_rates()
    return web.json_response(data or {"UZS": 1})


async def admin_pricing_get(request):
    _admin(request)
    import trip_import
    p = await trip_import.pricing()
    st = await db._fetchone("SELECT COUNT(*) n, AVG(price) avg_price, AVG(cost_usd) avg_cost "
                            "FROM packages WHERE cost_usd > 0 AND active=1")
    return web.json_response({**p, "packages": st["n"] or 0, "avg_price": round(st["avg_price"] or 0),
                              "avg_cost": round(st["avg_cost"] or 0, 2)})


async def admin_pricing_save(request):
    """Ustama / kurs / minimal narxni saqlaydi va barcha paketlar narxini darhol qayta hisoblaydi."""
    _admin(request)
    import trip_import
    body = await request.json()
    markup = _pnum(body.get("markup"), "Ustama")
    rate = _pnum(body.get("rate"), "Dollar kursi")
    min_price = _pnum(body.get("min_price", 0) or 0, "Minimal narx")
    if not 1.0 <= markup <= 10:
        raise _err(400, "Ustama 1.0 dan 10 gacha bo'lsin (1.0 = foydasiz, tannarxda)")
    if not 5000 <= rate <= 50000:
        raise _err(400, "Dollar kursi 5 000 – 50 000 oralig'ida bo'lsin")
    if not 0 <= min_price <= 1_000_000:
        raise _err(400, "Minimal narx 0 – 1 000 000 so'm oralig'ida bo'lsin")
    await db.set_setting("price_markup", f"{markup:g}")
    await db.set_setting("price_rate", f"{rate:g}")
    await db.set_setting("price_min_price", str(int(min_price)))
    changed = await trip_import.reprice_all() if body.get("apply", True) else 0
    return web.json_response({"ok": True, "changed": changed})


async def admin_stats(request):
    _admin(request)
    try:
        days = int(request.query.get("days", 30))
    except ValueError:
        days = 30
    return web.json_response(await db.full_stats(days, (await _pricing())["rate"]))


# ================= Admin: promo-kodlar va referal =================
async def admin_promos(request):
    import promo
    _admin(request)
    return web.json_response({"promos": await promo.list_promos(), "ref": await promo.ref_settings()})


async def admin_promo_save(request):
    import promo
    data = _admin(request)
    b = await request.json()
    try:
        p = await promo.save_promo(b.get("code"), b.get("kind", "percent"), b.get("value", 0),
                                   b.get("max_uses", 0), b.get("expires", ""))
    except (ValueError, TypeError) as e:
        raise _err(400, str(e) or "Noto'g'ri qiymat")
    log.info("Promo-kod saqlandi: %s (admin %s)", p["code"], data.user.id)
    return web.json_response(p)


async def admin_promo_action(request):
    import promo
    _admin(request)
    code, action = request.match_info["code"], request.match_info["action"]
    if action in ("on", "off"):
        await promo.set_promo_active(code, action == "on")
    elif action == "delete":
        await promo.delete_promo(code)
    else:
        raise _err(400, "unknown action")
    return web.json_response({"ok": True})


async def admin_ref_get(request):
    import promo
    _admin(request)
    return web.json_response(await promo.ref_settings())


async def admin_ref_save(request):
    import promo
    _admin(request)
    b = await request.json()
    try:
        return web.json_response(await promo.save_ref_settings(bool(b.get("enabled")), b.get("new_pct", 0),
                                                               b.get("bonus_pct", 0), b.get("cashback_pct")))
    except (ValueError, TypeError):
        raise _err(400, "Foizlarni to'g'ri yozing (referal 0–50, keshbek 0–20)")


# ================= Admin: davlatlarga chegirma =================
async def admin_sales(request):
    import promo
    _admin(request)
    return web.json_response(await promo.sales())


async def admin_sale_add(request):
    import promo
    import secrets
    _admin(request)
    b = await request.json()
    try:
        pct = int(b.get("pct", 0))
    except (ValueError, TypeError):
        pct = 0
    if not 1 <= pct <= 90:
        raise _err(400, "Chegirma 1–90% oralig'ida bo'lsin")
    countries = ["*"] if b.get("all") else [str(x)[:80] for x in (b.get("countries") or []) if str(x).strip()][:200]
    if not countries:
        raise _err(400, "Davlatlarni belgilang yoki «Barcha davlatlar»ni tanlang")
    until = str(b.get("until") or "").strip()
    if until and not re.match(r"^\d{4}-\d{2}-\d{2}$", until):
        raise _err(400, "Sana noto'g'ri")
    items = await promo.sales()
    items.append({"id": secrets.token_hex(4), "countries": countries, "pct": pct, "until": until})
    await promo.save_sales(items)
    return web.json_response(items)


async def admin_sale_delete(request):
    import promo
    _admin(request)
    sid = request.match_info["sid"]
    items = [x for x in await promo.sales() if x.get("id") != sid]
    await promo.save_sales(items)
    return web.json_response(items)


# ================= Admin: mijozlar bonus balansi =================
async def admin_balances(request):
    import promo
    _admin(request)
    return web.json_response(await promo.find_users(request.query.get("q", "")))


async def admin_balance_get(request):
    import promo
    _admin(request)
    uid = int(request.match_info["uid"])
    u = (await promo.find_users(str(uid), 1) or [None])[0]
    if not u or u["id"] != uid:
        raise _err(404, "Foydalanuvchi topilmadi")
    return web.json_response({**u, "log": await promo.balance_log(uid)})


async def admin_balance_set(request):
    """{"delta": 5000} yoki {"set": 0}, "reason", "notify": true — mijozga bot xabari (faqat qo'shilganda)."""
    import promo
    data = _admin(request)
    uid = int(request.match_info["uid"])
    b = await request.json()
    try:
        delta = int(b["delta"]) if b.get("delta") not in (None, "") else None
        set_to = int(b["set"]) if b.get("set") not in (None, "") else None
        if delta is None and set_to is None:
            raise ValueError("Summani yozing")
        old, new = await promo.adjust_balance(uid, delta, set_to, str(b.get("reason", "")), data.user.id)
    except (ValueError, TypeError) as e:
        raise _err(400, str(e) or "Noto'g'ri summa")
    log.info("Balans %s: %s -> %s (admin %s, %s)", uid, old, new, data.user.id, b.get("reason", ""))
    if b.get("notify") and new > old:
        try:
            lang = await db.user_lang(uid)
            reason = str(b.get("reason", "")).strip()
            text = i18n.t(lang, "bonus_added", sum=i18n.money(lang, new - old), bal=i18n.money(lang, new))
            if reason:
                from html import escape
                text += f"\n<i>{escape(reason[:200])}</i>"
            await request.app["bot"].send_message(uid, text)
        except Exception as e:
            log.warning("Bonus xabari %s ga yetmadi: %s", uid, e)
    return web.json_response({"old": old, "balance": new, "log": await promo.balance_log(uid)})


# ================= Admin: narxlarni avto-yangilash =================
async def admin_auto_get(request):
    import autoupdate
    _admin(request)
    return web.json_response(await autoupdate.settings())


async def admin_auto_save(request):
    import autoupdate
    _admin(request)
    b = await request.json()
    try:
        return web.json_response(await autoupdate.save_settings(bool(b.get("enabled")), int(b.get("hour", 4))))
    except (ValueError, TypeError):
        raise _err(400, "Soat 0–23 oralig'ida bo'lsin")


def build_app(bot: Bot, dp: Dispatcher) -> web.Application:
    app = web.Application(middlewares=[no_cache], client_max_size=12 * 1024 * 1024)
    app["bot"], app["dp"] = bot, dp
    r = app.router
    r.add_get("/", index)
    r.add_get("/static/{path:.+}", static_file)
    r.add_get("/api/catalog", catalog)
    r.add_get("/api/me", me)
    r.add_post("/api/lang", set_lang)
    r.add_get("/api/orders", my_orders)
    r.add_post("/api/order", create_order)
    r.add_get("/api/orders/{oid:\\d+}/esim", order_esim)
    r.add_post("/api/orders/{oid:\\d+}/pdf", order_send_pdf)
    r.add_get("/api/orders/{oid:\\d+}/pay", order_pay_info)
    r.add_post("/api/orders/{oid:\\d+}/receipt", order_receipt)
    r.add_post("/api/orders/{oid:\\d+}/cancel", order_cancel)
    r.add_get("/api/admin/card", admin_get_card)
    r.add_post("/api/admin/card", admin_set_card)
    r.add_post("/api/admin/paylinks", admin_set_links)
    r.add_get("/api/admin/packages", admin_packages)
    r.add_post("/api/admin/packages", admin_add_package)
    r.add_put("/api/admin/packages/{pid:\\d+}", admin_update_package)
    r.add_delete("/api/admin/packages/{pid:\\d+}", admin_delete_package)
    r.add_get("/api/admin/orders", admin_orders)
    r.add_get("/api/admin/orders/{oid:\\d+}/receipt", admin_receipt)
    r.add_post("/api/admin/orders/{oid:\\d+}/{action}", admin_order_action)
    r.add_get("/api/admin/stats", admin_stats)
    r.add_post("/api/quote", quote_api)
    r.add_get("/api/admin/banners", admin_banners)
    r.add_get("/api/admin/sales", admin_sales)
    r.add_post("/api/admin/sales", admin_sale_add)
    r.add_post("/api/admin/sales/{sid}/delete", admin_sale_delete)
    r.add_get("/api/admin/balances", admin_balances)
    r.add_get("/api/admin/balances/{uid:\\d+}", admin_balance_get)
    r.add_post("/api/admin/balances/{uid:\\d+}", admin_balance_set)
    r.add_post("/api/admin/banners", admin_banner_add)
    r.add_post("/api/admin/banners/{bid}/{action}", admin_banner_action)
    r.add_get("/api/support", support_get)
    r.add_post("/api/support", support_post)
    r.add_get("/api/support/file/{mid:\\d+}", support_file)
    r.add_get("/api/admin/chats", admin_chats)
    r.add_get("/api/admin/chats/{uid:\\d+}", admin_chat_get)
    r.add_post("/api/admin/chats/{uid:\\d+}", admin_chat_post)
    r.add_get("/api/ref", ref_api)
    r.add_get("/api/admin/promos", admin_promos)
    r.add_post("/api/admin/promos", admin_promo_save)
    r.add_post("/api/admin/promos/{code}/{action}", admin_promo_action)
    r.add_get("/api/admin/referral", admin_ref_get)
    r.add_post("/api/admin/referral", admin_ref_save)
    r.add_get("/api/admin/autoupdate", admin_auto_get)
    r.add_post("/api/admin/autoupdate", admin_auto_save)
    r.add_get("/api/admin/import", admin_import_status)
    r.add_post("/api/admin/import", admin_import_start)
    r.add_get("/api/admin/pricing", admin_pricing_get)
    r.add_get("/api/rates", rates_api)
    r.add_post("/api/admin/pricing", admin_pricing_save)
    return app
