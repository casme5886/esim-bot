"""SQLite baza: foydalanuvchilar, paketlar, buyurtmalar."""
import aiosqlite
from config import DB_PATH

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS packages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    country TEXT NOT NULL,
    flag TEXT DEFAULT '🌍',
    data_gb REAL NOT NULL,          -- 0 = cheksiz
    days INTEGER NOT NULL,
    price INTEGER NOT NULL,         -- mijoz uchun narx, so'm
    cost_usd REAL DEFAULT 0,        -- Trip.com'dagi tannarx (foyda hisobi uchun)
    active INTEGER DEFAULT 1
);
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    package_id INTEGER NOT NULL,
    price INTEGER NOT NULL,
    status TEXT DEFAULT 'new',      -- new, checking, paid, delivered, cancelled
    payment_method TEXT,            -- telegram / card
    receipt_file_id TEXT,
    qr_file_id TEXT,
    note TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS promos (
    code TEXT PRIMARY KEY,          -- katta harflarda, masalan SALE10
    kind TEXT DEFAULT 'percent',    -- percent / fixed (so'm)
    value INTEGER NOT NULL,
    max_uses INTEGER DEFAULT 0,     -- 0 = cheksiz
    used INTEGER DEFAULT 0,
    expires TEXT DEFAULT '',        -- YYYY-MM-DD (shu kun oxirigacha), bo'sh = muddatsiz
    active INTEGER DEFAULT 1,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS balance_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    delta INTEGER NOT NULL,
    balance INTEGER NOT NULL,       -- o'zgarishdan keyingi balans
    reason TEXT DEFAULT '',
    admin_id INTEGER DEFAULT 0,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""

STATUS_UZ = {
    "new": "🆕 To'lov kutilmoqda",
    "checking": "🔎 To'lov tekshirilmoqda",
    "paid": "⏳ To'landi, eSIM tayyorlanmoqda",
    "delivered": "✅ Yetkazildi",
    "cancelled": "❌ Bekor qilindi",
}


# Eski bazaga yangi ustunlarni qo'shish (ma'lumot o'chmaydi)
MIGRATIONS = {
    "packages": {
        "region": "TEXT DEFAULT ''",     # asia, europe, mideast, america, africa, global
        "popular": "INTEGER DEFAULT 0",  # 1 = "Mashhur" bo'limida chiqadi
        "trip_url": "TEXT DEFAULT ''",   # Trip.com "Book now" havolasi (avto-xarid uchun)
        "daily": "INTEGER DEFAULT 0",    # 1 = data_gb kunlik limit (masalan 1 GB/kun)
    },
    "users": {
        "lang": "TEXT DEFAULT ''",         # tanlangan til (ru, en, uz, ...); bo'sh = hali tanlamagan
        "ref_by": "INTEGER DEFAULT 0",     # kim taklif qilgan (referal)
        "balance": "INTEGER DEFAULT 0",    # bonus balans, so'm (referal mukofoti)
        "ui_msgs": "TEXT DEFAULT ''",      # /start, salomlashuv, til xabarlari id'lari (keyingi /start da o'chiriladi)
        "currency": "TEXT DEFAULT ''",     # Mini App'da tanlangan valyuta (USD, EUR, RUB, CNY, UZS)
    },
    "orders": {
        "reminded": "INTEGER DEFAULT 0",   # to'lov eslatmasi yuborilganmi
        "trip_status": "TEXT DEFAULT ''",  # preparing, confirm, paying, bought, done, failed, login, skipped
        "trip_order_no": "TEXT DEFAULT ''",
        "trip_price": "TEXT DEFAULT ''",
        "usage_url": "TEXT DEFAULT ''",    # internet qoldig'ini tekshirish havolasi
        "orig_price": "INTEGER DEFAULT 0", # chegirmagacha narx
        "discount": "INTEGER DEFAULT 0",   # promo / referal chegirmasi, so'm
        "promo": "TEXT DEFAULT ''",        # qo'llangan promo-kod (REF = taklif chegirmasi)
        "balance_used": "INTEGER DEFAULT 0",
        "refunded": "INTEGER DEFAULT 0",   # bekor qilinganda balans/promo qaytarilganmi
        "ref_paid": "INTEGER DEFAULT 0",   # taklif qilganga mukofot berilganmi
        "ref_bonus": "INTEGER DEFAULT 0",  # berilgan mukofot, so'm (bekor bo'lsa qaytarib olinadi)
        "cashback": "INTEGER DEFAULT 0",   # shu buyurtma uchun berilgan keshbek, so'm
        "cost_uzs": "INTEGER DEFAULT 0",   # buyurtma paytidagi tannarx, so'm (foyda hisobi uchun)
        "delivered_at": "TEXT DEFAULT ''",
        "expiry_reminded": "INTEGER DEFAULT 0",
    },
}


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript(SCHEMA)
        for table, cols in MIGRATIONS.items():
            cur = await db.execute(f"PRAGMA table_info({table})")
            have = {r[1] for r in await cur.fetchall()}
            for col, ddl in cols.items():
                if col not in have:
                    await db.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        # eski "Yevropa (ko'p davlat)" yozuvi o'rniga endi "Yevropa (30+ davlat)" (qamrov ro'yxati bilan) ishlatiladi
        await db.execute("UPDATE packages SET active=0 WHERE country=? AND active=1", ("Yevropa (ko'p davlat)",))
        await db.commit()


async def _fetchall(sql, args=()):
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        cur = await db.execute(sql, args)
        return [dict(r) for r in await cur.fetchall()]


async def _fetchone(sql, args=()):
    rows = await _fetchall(sql, args)
    return rows[0] if rows else None


# Katalog keshi versiyasi: paket yoki katalogga oid sozlama o'zgarsa oshadi -> Mini App katalogi qayta yig'iladi
CATALOG_VER = 0
_NOT_CATALOG = ("supn_", "ref_earned_", "auto_last", "profile", "fx_rates")


def bump_catalog():
    global CATALOG_VER
    CATALOG_VER += 1


async def _execute(sql, args=()):
    head = sql.lstrip()[:6].upper()
    if head in ("INSERT", "UPDATE", "DELETE") and " packages" in sql.lower():
        bump_catalog()
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute(sql, args)
        await db.commit()
        return cur.lastrowid


async def import_seed(path):
    """seed_packages.json dagi paketlarni qo'shadi (bor bo'lsa takrorlamaydi). Qo'shilganlar sonini qaytaradi."""
    import json
    rows = json.load(open(path, encoding="utf-8"))
    added = 0
    for x in rows:
        if await _fetchone("SELECT 1 FROM packages WHERE country=? AND data_gb=? AND days=? AND daily=?",
                           (x["country"], x["data_gb"], x["days"], 1 if x.get("daily") else 0)):
            continue
        pid = await add_package(x["country"], x["flag"], x["data_gb"], x["days"], x["price"], x["cost_usd"],
                                x.get("region", ""), x.get("popular", 0), x.get("daily", 0))
        if x.get("trip_url"):
            await update_package(pid, trip_url=x["trip_url"])
        added += 1
    return added


# --- settings (admin panelda o'zgartiriladigan sozlamalar) ---
async def get_setting(key, default=""):
    row = await _fetchone("SELECT value FROM settings WHERE key=?", (key,))
    return row["value"] if row and row["value"] else default


async def set_setting(key, value):
    if not str(key).startswith(_NOT_CATALOG):
        bump_catalog()
    await _execute(
        "INSERT INTO settings(key, value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )


async def card_info():
    """Joriy karta: avval admin panelda saqlangani, bo'lmasa .env dagisi."""
    from config import CARD_NUMBER, CARD_HOLDER
    return await get_setting("card_number", CARD_NUMBER), await get_setting("card_holder", CARD_HOLDER)


def card_type(number: str) -> str:
    """Karta raqamidan turi: humo / uzcard / visa / mastercard."""
    n = "".join(ch for ch in str(number) if ch.isdigit())
    if n.startswith("9860"):
        return "humo"
    if n.startswith(("8600", "5614", "6262")):
        return "uzcard"
    if n.startswith("4"):
        return "visa"
    if n.startswith(("5", "2")):
        return "mastercard"
    return "card"


async def cards() -> list[dict]:
    """Mijozga ko'rsatiladigan kartalar (Humo, Uzcard, ...). Admin panelda 3 tagacha saqlanadi."""
    import json as _json
    raw = await get_setting("cards")
    out = []
    if raw:
        try:
            out = [c for c in _json.loads(raw) if c.get("number")]
        except ValueError:
            out = []
    if not out:
        number, holder = await card_info()
        if number:
            out = [{"number": number, "holder": holder}]
    for c in out:
        c["type"] = card_type(c["number"])
    return out


PAY_LINK_KINDS = ("click", "payme", "uzum")


async def pay_links() -> dict:
    """Admin panelda saqlangan to'lov havolalari: {"click": url, "payme": url, "uzum": url}."""
    import json as _json
    try:
        raw = _json.loads(await get_setting("pay_links") or "{}")
    except ValueError:
        raw = {}
    return {k: raw[k] for k in PAY_LINK_KINDS if isinstance(raw.get(k), str) and raw[k].startswith("https://")}


# --- users ---
async def save_user(user_id, username, full_name):
    await _execute(
        "INSERT INTO users(id, username, full_name) VALUES(?,?,?) "
        "ON CONFLICT(id) DO UPDATE SET username=excluded.username, full_name=excluded.full_name",
        (user_id, username, full_name),
    )


_LANG_CACHE: dict[int, str] = {}


async def get_lang(user_id) -> str:
    """Foydalanuvchi tanlagan til ('' — hali tanlamagan)."""
    if user_id in _LANG_CACHE:
        return _LANG_CACHE[user_id]
    rows = await _fetchall("SELECT lang FROM users WHERE id=?", (user_id,))
    lang = (rows[0]["lang"] or "") if rows else ""
    _LANG_CACHE[user_id] = lang
    return lang


async def user_lang(user_id) -> str:
    """Xabar yuborish uchun til: tanlangani, bo'lmasa asosiy til."""
    import i18n
    return i18n.norm(await get_lang(user_id))


async def set_lang(user_id, lang):
    await _execute("INSERT INTO users(id, lang) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET lang=excluded.lang",
                   (user_id, lang))
    _LANG_CACHE[user_id] = lang


async def ui_msgs(user_id) -> list[int]:
    r = await _fetchone("SELECT ui_msgs FROM users WHERE id=?", (user_id,))
    raw = (r or {}).get("ui_msgs") or ""
    return [int(x) for x in raw.split(",") if x.strip().isdigit()]


async def set_ui_msgs(user_id, ids):
    ids = list(dict.fromkeys(int(i) for i in ids))[-60:]
    await _execute("UPDATE users SET ui_msgs=? WHERE id=?", (",".join(map(str, ids)), user_id))


async def get_currency(user_id) -> str:
    r = await _fetchone("SELECT currency FROM users WHERE id=?", (user_id,))
    return (r or {}).get("currency") or ""


async def set_currency(user_id, cur):
    await _execute("INSERT INTO users(id, currency) VALUES(?,?) ON CONFLICT(id) DO UPDATE SET currency=excluded.currency",
                   (user_id, cur))


# --- packages ---
async def countries():
    return await _fetchall(
        "SELECT country, MIN(flag) AS flag, MIN(id) AS pid, COUNT(*) AS n FROM packages "
        "WHERE active=1 GROUP BY country ORDER BY country"
    )


async def packages_by_country(country):
    return await _fetchall(
        "SELECT * FROM packages WHERE active=1 AND country=? ORDER BY daily, data_gb, days", (country,)
    )


async def get_package(pid):
    return await _fetchone("SELECT * FROM packages WHERE id=?", (pid,))


async def all_packages():
    return await _fetchall("SELECT * FROM packages ORDER BY country, price")


async def add_package(country, flag, data_gb, days, price, cost_usd, region="", popular=0, daily=0):
    return await _execute(
        "INSERT INTO packages(country, flag, data_gb, days, price, cost_usd, region, popular, daily) "
        "VALUES(?,?,?,?,?,?,?,?,?)",
        (country, flag, data_gb, days, price, cost_usd, region, popular, 1 if daily else 0),
    )


PACKAGE_FIELDS = {"country", "flag", "data_gb", "days", "price", "cost_usd", "region", "popular", "active", "trip_url", "daily"}


async def update_package(pid, **fields):
    fields = {k: v for k, v in fields.items() if k in PACKAGE_FIELDS}
    if not fields:
        return
    keys = ", ".join(f"{k}=?" for k in fields)
    await _execute(f"UPDATE packages SET {keys} WHERE id=?", (*fields.values(), pid))


async def set_country_meta(country, **fields):
    """Davlatning barcha paketlari uchun bayroq/mintaqa/mashhurlikni birga o'zgartiradi."""
    fields = {k: v for k, v in fields.items() if k in {"flag", "region", "popular"}}
    if fields:
        keys = ", ".join(f"{k}=?" for k in fields)
        await _execute(f"UPDATE packages SET {keys} WHERE country=?", (*fields.values(), country))


async def delete_package(pid):
    """Buyurtmasi bor paket o'chirilmaydi, faqat yashiriladi (tarix buzilmasin)."""
    used = await _fetchone("SELECT COUNT(*) AS n FROM orders WHERE package_id=?", (pid,))
    if used and used["n"]:
        await set_package_active(pid, False)
        return "hidden"
    await _execute("DELETE FROM packages WHERE id=?", (pid,))
    return "deleted"


async def set_package_active(pid, active):
    await _execute("UPDATE packages SET active=? WHERE id=?", (1 if active else 0, pid))


async def update_package_price(pid, price):
    await _execute("UPDATE packages SET price=? WHERE id=?", (price, pid))


# --- orders ---
async def create_order(user_id, package_id, price):
    return await _execute(
        "INSERT INTO orders(user_id, package_id, price) VALUES(?,?,?)",
        (user_id, package_id, price),
    )


async def get_order(oid):
    return await _fetchone(
        "SELECT o.*, p.country, p.flag, p.data_gb, p.daily, p.days, p.cost_usd, p.trip_url, "
        "u.username, u.full_name FROM orders o "
        "JOIN packages p ON p.id=o.package_id LEFT JOIN users u ON u.id=o.user_id WHERE o.id=?",
        (oid,),
    )


async def update_order(oid, **fields):
    if fields.get("status") == "delivered" and "delivered_at" not in fields:
        fields["delivered_at"] = _now()
    keys = ", ".join(f"{k}=?" for k in fields)
    await _execute(
        f"UPDATE orders SET {keys}, updated_at=CURRENT_TIMESTAMP WHERE id=?",
        (*fields.values(), oid),
    )
    if fields.get("status") == "cancelled":
        await _refund(oid)


def _now():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


async def _refund(oid):
    """Bekor qilingan buyurtma: ishlatilgan balans va promo-kod qaytariladi (bir marta)."""
    async with aiosqlite.connect(DB_PATH) as db:
        cur = await db.execute("UPDATE orders SET refunded=1 WHERE id=? AND refunded=0 AND status='cancelled'", (oid,))
        if not cur.rowcount:
            return
        cur = await db.execute("SELECT user_id, balance_used, promo FROM orders WHERE id=?", (oid,))
        uid, bal, promo = await cur.fetchone()
        if bal:
            await db.execute("UPDATE users SET balance=balance+? WHERE id=?", (bal, uid))
        if promo and promo != "REF":
            await db.execute("UPDATE promos SET used=MAX(used-1,0) WHERE code=?", (promo,))
        cur = await db.execute("SELECT u.ref_by, o.ref_bonus FROM orders o JOIN users u ON u.id=o.user_id "
                               "WHERE o.id=? AND o.ref_paid=1", (oid,))
        row = await cur.fetchone()
        if row and row[0] and row[1]:
            await db.execute("UPDATE users SET balance=MAX(COALESCE(balance,0)-?,0) WHERE id=?", (row[1], row[0]))
            await db.execute("UPDATE orders SET ref_paid=0, ref_bonus=0 WHERE id=?", (oid,))
            await db.execute("UPDATE settings SET value=CAST(MAX(CAST(value AS INTEGER)-?,0) AS TEXT) WHERE key=?",
                             (row[1], f"ref_earned_{row[0]}"))
        await db.commit()


async def user_orders(user_id, limit=10, include_new=False):
    """include_new — to'lanmagan buyurtmalar ham (Mini App'da "To'lash" tugmasi bilan ko'rinadi)."""
    cond = "" if include_new else "AND o.status!='new' "
    return await _fetchall(
        "SELECT o.*, p.country, p.flag, p.data_gb, p.daily, p.days, p.active AS pkg_active FROM orders o "
        "JOIN packages p ON p.id=o.package_id WHERE o.user_id=? " + cond +
        "ORDER BY o.id DESC LIMIT ?",
        (user_id, limit),
    )


async def pending_orders():
    return await _fetchall(
        "SELECT o.*, p.country, p.flag, p.data_gb, p.daily, p.days FROM orders o "
        "JOIN packages p ON p.id=o.package_id WHERE o.status IN ('checking','paid') ORDER BY o.id"
    )


ORDER_GROUPS = {
    "pending": "o.status IN ('checking','paid')",
    "delivered": "o.status='delivered'",
    "cancelled": "o.status='cancelled'",
    "all": "o.status!='new'",
}


async def admin_orders(group="pending", limit=100):
    where = ORDER_GROUPS.get(group, ORDER_GROUPS["pending"])
    order = "o.id" if group == "pending" else "o.id DESC"
    return await _fetchall(
        "SELECT o.*, p.country, p.flag, p.data_gb, p.daily, p.days, p.cost_usd, p.trip_url, u.username, u.full_name "
        "FROM orders o JOIN packages p ON p.id=o.package_id LEFT JOIN users u ON u.id=o.user_id "
        f"WHERE {where} ORDER BY {order} LIMIT ?",
        (limit,),
    )


async def trip_bought_today():
    row = await _fetchone("SELECT COUNT(*) AS n FROM orders WHERE trip_status IN ('paying','bought','done') "
                          "AND date(updated_at)=date('now')")
    return row["n"] if row else 0


async def full_stats(days=30, rate=12100.0):
    """Admin hisobot. days=0 — butun davr. Sotilgan = to'langan (paid) + yetkazilgan (delivered).
    Vaqtlar Toshkent bo'yicha (UTC+5). Tannarx: buyurtma paytida saqlangani, bo'lmasa paketning hozirgi narxi."""
    days = max(0, int(days))
    SOLD = "o.status IN ('paid','delivered')"
    LOCAL = "datetime(o.created_at,'+5 hours')"
    COST = f"(CASE WHEN o.cost_uzs>0 THEN o.cost_uzs ELSE p.cost_usd*{float(rate)} END)"
    J = "FROM orders o JOIN packages p ON p.id=o.package_id"

    def start(n):
        return f"datetime('now','+5 hours','start of day','-{n} days')"

    since = f"AND {LOCAL} >= {start(days - 1)}" if days else ""
    prev = f"AND {LOCAL} >= {start(2 * days - 1)} AND {LOCAL} < {start(days - 1)}" if days else "AND 0"
    today = f"AND date({LOCAL}) = date('now','+5 hours')"
    users_cond = f"datetime(created_at,'+5 hours') >= {start(days - 1)}" if days else "1"

    async def agg(cond):
        r = await _fetchone(f"SELECT COUNT(*) AS sold, COALESCE(SUM(o.price),0) AS revenue, "
                            f"COALESCE(SUM({COST}),0) AS cost, COALESCE(SUM(o.discount),0) AS discount, "
                            f"COUNT(DISTINCT o.user_id) AS buyers {J} WHERE {SOLD} {cond}")
        r["cost"] = int(round(r["cost"]))
        r["profit"] = r["revenue"] - r["cost"]
        return r

    cur = await agg(since)
    span = days if days else 30
    daily = await _fetchall(
        f"SELECT date({LOCAL}) AS d, COUNT(*) AS sold, SUM(o.price) AS revenue, SUM(o.price - {COST}) AS profit "
        f"{J} WHERE {SOLD} AND {LOCAL} >= {start(span - 1)} GROUP BY d ORDER BY d")
    top = await _fetchall(
        f"SELECT p.country, MIN(p.flag) AS flag, COUNT(*) AS n, SUM(o.price) AS revenue, SUM(o.price - {COST}) AS profit "
        f"{J} WHERE {SOLD} {since} GROUP BY p.country ORDER BY n DESC, revenue DESC LIMIT 8")
    methods = await _fetchall(
        f"SELECT COALESCE(NULLIF(o.payment_method,''),'card') AS m, COUNT(*) AS n, SUM(o.price) AS revenue "
        f"{J} WHERE {SOLD} {since} GROUP BY m ORDER BY n DESC")
    promos = await _fetchall(
        f"SELECT o.promo, COUNT(*) AS n, SUM(o.discount) AS discount {J} "
        f"WHERE {SOLD} AND o.promo!='' {since} GROUP BY o.promo ORDER BY n DESC LIMIT 10")
    for rows in (daily, top):
        for r in rows:
            r["profit"] = int(round(r["profit"] or 0))
    misc = await _fetchone(
        "SELECT (SELECT COUNT(*) FROM users) AS users, "
        f"(SELECT COUNT(*) FROM users WHERE {users_cond}) AS new_users, "
        "(SELECT COUNT(*) FROM orders WHERE status IN ('checking','paid')) AS pending, "
        "(SELECT COUNT(*) FROM orders WHERE status='new') AS unpaid, "
        f"(SELECT COUNT(*) FROM orders o WHERE o.status='cancelled' {since}) AS cancelled, "
        "(SELECT COUNT(*) FROM users WHERE ref_by>0) AS ref_invited, "
        "(SELECT COALESCE(SUM(ref_bonus),0) FROM orders WHERE ref_paid=1) AS ref_bonus, "
        "(SELECT COALESCE(SUM(balance),0) FROM users) AS balance_total, "
        "(SELECT COALESCE(SUM(cashback),0) FROM orders) AS cashback_total, "
        "(SELECT COUNT(*) FROM (SELECT user_id FROM orders WHERE status IN ('paid','delivered') "
        " GROUP BY user_id HAVING COUNT(*)>1)) AS repeat_buyers")
    return {"days": days, **cur, "avg": cur["revenue"] // cur["sold"] if cur["sold"] else 0,
            "today": await agg(today), "prev": await agg(prev) if days else None,
            "daily": daily, "top": top, "methods": methods, "promos": promos, **misc}


async def stats():
    return await _fetchone(
        "SELECT "
        "(SELECT COUNT(*) FROM users) AS users, "
        "(SELECT COUNT(*) FROM orders WHERE status='delivered') AS delivered, "
        "(SELECT COALESCE(SUM(price),0) FROM orders WHERE status='delivered') AS revenue, "
        "(SELECT COUNT(*) FROM orders WHERE status='delivered' AND date(created_at)=date('now')) AS today, "
        "(SELECT COUNT(*) FROM orders WHERE status IN ('checking','paid')) AS pending"
    )
