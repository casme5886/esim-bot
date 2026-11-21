"""Promo-kodlar, referal (do'st taklif qilish) va bonus balans.

Narx hisobi (quote):
  asl narx -> chegirma (promo-kod YOKI taklif chegirmasi, qaysi biri katta bo'lsa) -> balansdan to'lov
  Yakuniy narx hech qachon Trip.com tannarxidan (va 1 000 so'mdan) past tushmaydi — zarar bo'lmaydi.
"""
import math
import re
from datetime import datetime, timedelta, timezone

import aiosqlite

import db

TZ = timezone(timedelta(hours=5))   # Toshkent
REF_DEFAULTS = {"enabled": 1, "new_pct": 10, "bonus_pct": 10, "cashback_pct": 1.0}
CODE_RE = re.compile(r"^[A-Z0-9_-]{3,20}$")


class PromoError(Exception):
    """key — tarjima kaliti (app bo'limi)"""
    def __init__(self, key):
        super().__init__(key)
        self.key = key


# ================= sozlamalar =================
async def ref_settings() -> dict:
    out = dict(REF_DEFAULTS)
    for k in out:
        v = await db.get_setting("ref_" + k)
        if v != "":
            try:
                out[k] = round(float(v), 1) if k == "cashback_pct" else int(float(v))
            except ValueError:
                pass
    return out


async def save_ref_settings(enabled, new_pct, bonus_pct, cashback_pct=None):
    await db.set_setting("ref_enabled", "1" if enabled else "0")
    await db.set_setting("ref_new_pct", str(max(0, min(50, int(new_pct)))))
    await db.set_setting("ref_bonus_pct", str(max(0, min(50, int(bonus_pct)))))
    if cashback_pct is not None:
        await db.set_setting("ref_cashback_pct", str(max(0.0, min(20.0, round(float(cashback_pct), 1)))))
    return await ref_settings()


def cashback_of(price, pct) -> int:
    """Keshbek: to'langan summaning pct foizi, 10 so'mga pastga yaxlitlab."""
    return int(price * pct / 100 // 10 * 10) if pct > 0 else 0


async def credit_cashback(oid):
    """eSIM yetkazilgach: mijozga to'lagan summasining cashback_pct% i bonus balansga (bir marta).
    Qaytaradi: (user_id, keshbek, yangi_balans) yoki None."""
    s = await ref_settings()
    o = await db._fetchone("SELECT id, user_id, price, cashback FROM orders WHERE id=? AND status='delivered'", (oid,))
    if not o or o["cashback"]:
        return None
    cb = cashback_of(o["price"], s["cashback_pct"])
    if cb <= 0:
        return None
    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute("UPDATE orders SET cashback=? WHERE id=? AND COALESCE(cashback,0)=0", (cb, oid))
        if not cur.rowcount:
            return None
        await con.execute("UPDATE users SET balance=COALESCE(balance,0)+? WHERE id=?", (cb, o["user_id"]))
        await con.commit()
    u = await user_row(o["user_id"])
    return o["user_id"], cb, u["balance"]


# ================= foydalanuvchi =================
async def user_row(uid) -> dict:
    return await db._fetchone("SELECT id, ref_by, balance FROM users WHERE id=?", (uid,)) or \
        {"id": uid, "ref_by": 0, "balance": 0}


async def paid_count(uid) -> int:
    r = await db._fetchone("SELECT COUNT(*) AS n FROM orders WHERE user_id=? AND status IN ('checking','paid','delivered')",
                           (uid,))
    return r["n"] if r else 0


async def set_referrer(uid, ref_id) -> bool:
    """/start ref_<id>: faqat hali xarid qilmagan va taklifchisi yo'q foydalanuvchiga yoziladi."""
    if not ref_id or ref_id == uid:
        return False
    if not await db._fetchone("SELECT 1 FROM users WHERE id=?", (ref_id,)):
        return False
    u = await user_row(uid)
    if u["ref_by"] or await db._fetchone("SELECT 1 FROM orders WHERE user_id=?", (uid,)):
        return False
    await db._execute("UPDATE users SET ref_by=? WHERE id=? AND COALESCE(ref_by,0)=0", (ref_id, uid))
    return True


async def ref_info(uid) -> dict:
    s = await ref_settings()
    u = await user_row(uid)
    inv = await db._fetchone("SELECT COUNT(*) AS n FROM users WHERE ref_by=?", (uid,))
    buyers = await db._fetchone(
        "SELECT COUNT(DISTINCT o.user_id) AS n FROM orders o JOIN users u ON u.id=o.user_id "
        "WHERE u.ref_by=? AND o.status IN ('paid','delivered')", (uid,))
    earned = await db.get_setting(f"ref_earned_{uid}", "0")
    return {"enabled": bool(s["enabled"]), "new_pct": s["new_pct"], "bonus_pct": s["bonus_pct"], "cashback_pct": s["cashback_pct"],
            "balance": u["balance"] or 0, "invited": inv["n"] if inv else 0, "buyers": buyers["n"] if buyers else 0,
            "earned": int(earned or 0)}


# ================= promo-kodlar =================
def norm_code(code) -> str:
    return re.sub(r"\s+", "", str(code or "")).upper()


async def get_promo(code):
    return await db._fetchone("SELECT * FROM promos WHERE code=?", (norm_code(code),))


async def check_promo(code, uid) -> dict:
    p = await get_promo(code)
    if not p or not p["active"]:
        raise PromoError("promo_invalid")
    if p["expires"]:
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        if today > p["expires"]:
            raise PromoError("promo_expired")
    if await db._fetchone("SELECT 1 FROM orders WHERE user_id=? AND promo=? AND status!='cancelled'", (uid, p["code"])):
        raise PromoError("promo_used")
    if p["max_uses"] and p["used"] >= p["max_uses"]:
        raise PromoError("promo_expired")
    return p


def _disc(kind, value, price) -> int:
    if kind == "fixed":
        return int(value)
    return int(math.floor(price * value / 100 / 100) * 100)   # 100 so'mgacha pastga


async def floor_price(pkg) -> int:
    """Zarar chegarasi: Trip.com tannarxi (so'mda, 1 000 ga yuqoriga yaxlitlab), kamida 1 000 so'm."""
    import trip_import
    rate = (await trip_import.pricing())["rate"]
    cost = (pkg.get("cost_usd") or 0) * rate
    return int(max(1000, math.ceil(cost / 1000) * 1000))


async def quote(uid, pkg, code="", use_balance=False) -> dict:
    """Mijozga ko'rsatiladigan va buyurtmada ishlatiladigan yakuniy narx."""
    list_price = int(pkg["price"])
    floor = min(list_price, await floor_price(pkg))
    spct = sale_pct(await sale_map(), pkg["country"])
    price = sale_price(list_price, spct, floor)        # davlat aksiyasi (bo'lsa)
    sale_off = list_price - price
    disc, promo, kind = 0, "", ""
    code = norm_code(code)
    if code:
        p = await check_promo(code, uid)          # xato bo'lsa PromoError
        disc, promo, kind = _disc(p["kind"], p["value"], price), p["code"], "promo"
    s = await ref_settings()
    u = await user_row(uid)
    if s["enabled"] and s["new_pct"] and u["ref_by"] and not await paid_count(uid):
        rd = _disc("percent", s["new_pct"], price)
        if rd > disc:
            disc, promo, kind = rd, "REF", "ref"
    disc = max(0, min(disc, price - floor))
    after = price - disc
    bal = int(u["balance"] or 0)
    used = max(0, min(bal, after - floor)) if use_balance else 0
    return {"orig": list_price, "sale_pct": spct if sale_off else 0, "sale_off": sale_off,
            "discount": disc, "promo": promo, "kind": kind, "ref_pct": s["new_pct"] if kind == "ref" else 0,
            "balance": bal, "balance_used": used, "final": after - used, "floor": floor,
            "cashback": cashback_of(after - used, s["cashback_pct"]), "cashback_pct": s["cashback_pct"]}


async def reserve(uid, q) -> bool:
    """Buyurtma yaratishdan oldin: balansni yechib, promo hisobini oshiradi (atomik)."""
    async with aiosqlite.connect(db.DB_PATH) as con:
        if q["balance_used"]:
            cur = await con.execute("UPDATE users SET balance=balance-? WHERE id=? AND balance>=?",
                                    (q["balance_used"], uid, q["balance_used"]))
            if not cur.rowcount:
                return False
        if q["promo"] and q["promo"] != "REF":
            cur = await con.execute("UPDATE promos SET used=used+1 WHERE code=? AND (max_uses=0 OR used<max_uses)",
                                    (q["promo"],))
            if not cur.rowcount:
                await con.rollback()
                return False
        await con.commit()
    return True


# ================= referal mukofoti =================
async def credit_referrer(oid):
    """Taklif qilingan do'stning BIRINCHI to'langan xaridi: taklif qilganning balansiga bonus_pct%.
    Qaytaradi: (referrer_id, bonus, yangi_balans) yoki None."""
    s = await ref_settings()
    if not s["enabled"] or not s["bonus_pct"]:
        return None
    o = await db._fetchone("SELECT o.id, o.user_id, o.price, o.ref_paid, u.ref_by FROM orders o "
                           "JOIN users u ON u.id=o.user_id WHERE o.id=?", (oid,))
    if not o or not o["ref_by"] or o["ref_paid"]:
        return None
    prev = await db._fetchone("SELECT COUNT(*) AS n FROM orders WHERE user_id=? AND id!=? AND ref_paid=1",
                              (o["user_id"], oid))
    if prev and prev["n"]:
        return None
    bonus = _disc("percent", s["bonus_pct"], o["price"])
    if bonus <= 0:
        return None
    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute("UPDATE orders SET ref_paid=1, ref_bonus=? WHERE id=? AND ref_paid=0", (bonus, oid))
        if not cur.rowcount:
            return None
        await con.execute("UPDATE users SET balance=COALESCE(balance,0)+? WHERE id=?", (bonus, o["ref_by"]))
        await con.commit()
    earned = int(await db.get_setting(f"ref_earned_{o['ref_by']}", "0") or 0) + bonus
    await db.set_setting(f"ref_earned_{o['ref_by']}", str(earned))
    u = await user_row(o["ref_by"])
    return o["ref_by"], bonus, u["balance"]


# ================= davlatlarga chegirma (aksiya) =================
async def sales(active_only=False) -> list:
    """[{id, countries: [...] yoki ["*"], pct, until: 'YYYY-MM-DD' | ''}]"""
    import json as _json
    try:
        out = _json.loads(await db.get_setting("sales") or "[]")
    except ValueError:
        out = []
    if active_only:
        today = datetime.now(TZ).strftime("%Y-%m-%d")
        out = [x for x in out if not x.get("until") or x["until"] >= today]
    return out


async def save_sales(items):
    import json as _json
    await db.set_setting("sales", _json.dumps(items, ensure_ascii=False))


async def sale_map() -> dict:
    """{davlat_nomi: foiz}; "*" — barcha davlatlar. Bir davlat bir nechta aksiyada bo'lsa — eng kattasi."""
    m = {}
    for x in await sales(active_only=True):
        for c in x.get("countries") or []:
            m[c] = max(m.get(c, 0), int(x.get("pct") or 0))
    return m


def sale_pct(smap: dict, country: str) -> int:
    return max(smap.get(country, 0), smap.get("*", 0))


def sale_price(price: int, pct: int, floor: int) -> int:
    """Aksiya narxi: 100 so'mga yuqoriga yaxlitlab, Trip.com tannarxidan past emas."""
    if pct <= 0:
        return price
    new = int(math.ceil(price * (100 - pct) / 100 / 100) * 100)
    return max(min(new, price), min(floor, price))


# ================= admin: mijoz bonus balansi =================
async def find_users(q: str = "", limit: int = 40):
    q = (q or "").strip().lstrip("@")
    base = ("SELECT u.id, u.username, u.full_name, COALESCE(u.balance,0) AS balance, "
            "(SELECT COUNT(*) FROM orders o WHERE o.user_id=u.id AND o.status IN ('paid','delivered')) AS orders "
            "FROM users u ")
    if not q:
        return await db._fetchall(base + "WHERE COALESCE(u.balance,0)>0 ORDER BY u.balance DESC LIMIT ?", (limit,))
    if q.isdigit():
        return await db._fetchall(base + "WHERE u.id=? OR CAST(u.id AS TEXT) LIKE ? LIMIT ?", (int(q), q + "%", limit))
    like = f"%{q.lower()}%"
    return await db._fetchall(base + "WHERE lower(COALESCE(u.username,'')) LIKE ? OR lower(COALESCE(u.full_name,'')) LIKE ? "
                              "ORDER BY u.balance DESC LIMIT ?", (like, like, limit))


async def adjust_balance(uid: int, delta: int | None = None, set_to: int | None = None, reason: str = "", admin_id: int = 0):
    """Admin balansni o'zgartiradi: delta (+/-) yoki aniq qiymat. Balans manfiy bo'lmaydi. Tarixga yoziladi."""
    async with aiosqlite.connect(db.DB_PATH) as con:
        cur = await con.execute("SELECT COALESCE(balance,0) FROM users WHERE id=?", (uid,))
        row = await cur.fetchone()
        if not row:
            raise ValueError("Foydalanuvchi topilmadi")
        old = row[0]
        new = max(0, int(set_to) if set_to is not None else old + int(delta or 0))
        if new > 100_000_000:
            raise ValueError("Juda katta summa")
        await con.execute("UPDATE users SET balance=? WHERE id=?", (new, uid))
        await con.execute("INSERT INTO balance_log(user_id, delta, balance, reason, admin_id) VALUES(?,?,?,?,?)",
                          (uid, new - old, new, (reason or "")[:200], admin_id))
        await con.commit()
    return old, new


async def balance_log(uid: int, limit: int = 10):
    return await db._fetchall("SELECT delta, balance, reason, created_at FROM balance_log WHERE user_id=? "
                              "ORDER BY id DESC LIMIT ?", (uid, limit))


# ================= admin =================
async def list_promos():
    return await db._fetchall("SELECT * FROM promos ORDER BY active DESC, created_at DESC")


async def save_promo(code, kind, value, max_uses=0, expires=""):
    code = norm_code(code)
    if not CODE_RE.match(code) or code == "REF":
        raise ValueError("Kod 3–20 ta lotin harfi/raqamdan iborat bo'lsin (masalan SALE10)")
    if kind not in ("percent", "fixed"):
        raise ValueError("Turi noto'g'ri")
    value = int(value)
    if kind == "percent" and not 1 <= value <= 90:
        raise ValueError("Foiz 1–90 oralig'ida bo'lsin")
    if kind == "fixed" and not 1000 <= value <= 10_000_000:
        raise ValueError("Summa 1 000 so'mdan katta bo'lsin")
    expires = str(expires or "").strip()
    if expires and not re.match(r"^\d{4}-\d{2}-\d{2}$", expires):
        raise ValueError("Muddat YYYY-MM-DD ko'rinishida bo'lsin")
    await db._execute(
        "INSERT INTO promos(code, kind, value, max_uses, expires, active) VALUES(?,?,?,?,?,1) "
        "ON CONFLICT(code) DO UPDATE SET kind=excluded.kind, value=excluded.value, max_uses=excluded.max_uses, "
        "expires=excluded.expires, active=1",
        (code, kind, value, max(0, int(max_uses or 0)), expires))
    return await get_promo(code)


async def set_promo_active(code, active):
    await db._execute("UPDATE promos SET active=? WHERE code=?", (1 if active else 0, norm_code(code)))


async def delete_promo(code):
    await db._execute("DELETE FROM promos WHERE code=?", (norm_code(code),))
