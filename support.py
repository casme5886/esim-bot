"""Yordam chati: mijoz <-> admin.

Mijoz Mini App'dagi "Yordam" chatidan yoki botning o'ziga yozadi -> hammasi bitta suhbatda saqlanadi.
Admin Mini App admin panelidagi "Chat" bo'limida javob beradi (matn / surat) -> mijozga bot orqali ham boradi.
Har bir xabar/javobda bot bildirishnoma yuboradi, shu suhbatning oldingi bildirishnomasi o'chiriladi.
Suratlar diskda: support_files/<id>.<ext>
"""
import logging
import secrets
from html import escape
from pathlib import Path

from aiogram import Bot
from aiogram.types import BufferedInputFile, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

import db
import i18n

log = logging.getLogger("support")
FILES = Path(__file__).with_name("support_files")
MAX_TEXT = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS support_msgs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    from_admin INTEGER DEFAULT 0,
    text TEXT DEFAULT '',
    photo TEXT DEFAULT '',
    seen INTEGER DEFAULT 0,          -- qabul qiluvchi o'qiganmi (mijoz xabari -> admin, admin xabari -> mijoz)
    source TEXT DEFAULT 'app',       -- app / bot
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_support_user ON support_msgs(user_id, id);
"""


async def init():
    import aiosqlite
    async with aiosqlite.connect(db.DB_PATH) as con:
        await con.executescript(SCHEMA)
        await con.commit()


def _save_photo(data: bytes, name: str = "") -> str:
    FILES.mkdir(exist_ok=True)
    ext = (name.rsplit(".", 1)[-1].lower() if "." in name else "jpg")
    if ext not in ("jpg", "jpeg", "png", "webp", "gif", "heic"):
        ext = "jpg"
    fn = f"{secrets.token_hex(10)}.{ext}"
    (FILES / fn).write_bytes(data)
    return fn


def photo_path(fn: str) -> Path | None:
    if not fn or "/" in fn or "\\" in fn or ".." in fn:
        return None
    p = FILES / fn
    return p if p.exists() else None


async def add(uid: int, from_admin: bool, text: str = "", photo: tuple | None = None, source: str = "app") -> dict:
    """photo: (bytes, fayl_nomi)"""
    text = (text or "").strip()[:MAX_TEXT]
    fn = _save_photo(*photo) if photo else ""
    if not text and not fn:
        raise ValueError("empty")
    mid = await db._execute("INSERT INTO support_msgs(user_id, from_admin, text, photo, source) VALUES(?,?,?,?,?)",
                            (uid, 1 if from_admin else 0, text, fn, source))
    return await get(mid)


async def get(mid):
    return await db._fetchone("SELECT * FROM support_msgs WHERE id=?", (mid,))


async def history(uid: int, after: int = 0, limit: int = 300):
    rows = await db._fetchall("SELECT id, from_admin, text, photo, created_at FROM support_msgs "
                              "WHERE user_id=? AND id>? ORDER BY id DESC LIMIT ?", (uid, after, limit))
    return list(reversed(rows))


async def mark_seen(uid: int, by_admin: bool):
    """by_admin=True: admin mijoz xabarlarini o'qidi; False: mijoz admin javoblarini o'qidi."""
    await db._execute("UPDATE support_msgs SET seen=1 WHERE user_id=? AND from_admin=? AND seen=0",
                      (uid, 0 if by_admin else 1))


async def unread_for_user(uid: int) -> int:
    r = await db._fetchone("SELECT COUNT(*) AS n FROM support_msgs WHERE user_id=? AND from_admin=1 AND seen=0", (uid,))
    return r["n"] if r else 0


async def unread_for_admin() -> int:
    r = await db._fetchone("SELECT COUNT(DISTINCT user_id) AS n FROM support_msgs WHERE from_admin=0 AND seen=0")
    return r["n"] if r else 0


async def chats(limit: int = 100):
    return await db._fetchall(
        "SELECT m.user_id, u.username, u.full_name, u.lang, "
        " (SELECT text FROM support_msgs WHERE user_id=m.user_id ORDER BY id DESC LIMIT 1) AS last_text, "
        " (SELECT photo FROM support_msgs WHERE user_id=m.user_id ORDER BY id DESC LIMIT 1) AS last_photo, "
        " (SELECT from_admin FROM support_msgs WHERE user_id=m.user_id ORDER BY id DESC LIMIT 1) AS last_admin, "
        " MAX(m.created_at) AS last_at, MAX(m.id) AS last_id, "
        " SUM(CASE WHEN m.from_admin=0 AND m.seen=0 THEN 1 ELSE 0 END) AS unread "
        "FROM support_msgs m LEFT JOIN users u ON u.id=m.user_id "
        "GROUP BY m.user_id ORDER BY unread>0 DESC, last_id DESC LIMIT ?", (limit,))


async def user_brief(uid: int) -> dict:
    u = await db._fetchone("SELECT id, username, full_name, lang, created_at, COALESCE(balance,0) AS balance FROM users WHERE id=?",
                           (uid,)) or {"id": uid}
    o = await db._fetchone("SELECT COUNT(*) AS n, SUM(CASE WHEN status IN ('paid','delivered') THEN price ELSE 0 END) AS spent "
                           "FROM orders WHERE user_id=?", (uid,))
    last = await db._fetchall("SELECT o.id, o.status, o.price, p.country, p.flag, p.data_gb, p.daily, p.days FROM orders o "
                              "JOIN packages p ON p.id=o.package_id WHERE o.user_id=? ORDER BY o.id DESC LIMIT 3", (uid,))
    return {**u, "orders": o["n"] if o else 0, "spent": (o or {}).get("spent") or 0, "last_orders": last}


def _admin_kb(uid: int):
    import keyboards as kb
    if not kb.WEBAPP_URL:
        return None
    url = kb.webapp_url("uz")
    url += ("&" if "?" in url else "?") + f"chat={uid}"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💬 Javob berish", web_app=WebAppInfo(url=url))]])


async def _replace_notice(bot: Bot, chat_id: int, key: str, send):
    """Oldingi bildirishnomani o'chirib, yangisini yuboradi — botda faqat oxirgisi qoladi."""
    sk = f"supn_{chat_id}_{key}"
    old = await db.get_setting(sk)
    msg = await send()
    if old and old.isdigit():
        try:
            await bot.delete_message(chat_id, int(old))
        except Exception:
            pass   # 48 soatdan eski yoki allaqachon o'chirilgan
    if msg is not None:
        await db.set_setting(sk, str(msg.message_id))
    return msg


async def notify_admins(bot: Bot, m: dict):
    """Mijoz yozdi -> har bir xabarda adminlarga bildirishnoma (shu mijozning oldingisi o'chiriladi)."""
    from config import ADMIN_IDS
    u = await db._fetchone("SELECT username, full_name FROM users WHERE id=?", (m["user_id"],)) or {}
    who = f"@{u['username']}" if u.get("username") else escape(u.get("full_name") or str(m["user_id"]))
    first = not await db._fetchone("SELECT 1 FROM support_msgs WHERE user_id=? AND id<?", (m["user_id"], m["id"]))
    unread = (await db._fetchone("SELECT COUNT(*) AS n FROM support_msgs WHERE user_id=? AND from_admin=0 AND seen=0",
                                 (m["user_id"],)))["n"]
    head = "💬 <b>Mijoz chat boshladi</b>" if first else "💬 <b>Mijozdan yangi xabar</b>"
    if unread > 1:
        head += f" ({unread} ta o'qilmagan)"
    body = escape(m["text"][:500]) if m["text"] else ""
    if m["photo"]:
        body = ("📷 Surat" + ("\n" + body if body else ""))
    text = f"{head}: {who} (<code>{m['user_id']}</code>)\n\n{body}"
    for aid in ADMIN_IDS:
        try:
            await _replace_notice(bot, aid, f"u{m['user_id']}",
                                  lambda aid=aid: bot.send_message(aid, text, reply_markup=_admin_kb(m["user_id"])))
        except Exception as e:
            log.warning("Admin %s ga chat xabari yuborilmadi: %s", aid, e)


def _user_kb(lang: str):
    import keyboards as kb
    if not kb.WEBAPP_URL:
        return None
    url = kb.webapp_url(lang)
    url += ("&" if "?" in url else "?") + "support=1"
    return InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=i18n.t(lang, "sup_open"), web_app=WebAppInfo(url=url))]])


async def deliver_to_user(bot: Bot, m: dict):
    """Admin javobi -> mijozga bot orqali (Mini App yopiq bo'lsa ham ko'radi)."""
    lang = await db.user_lang(m["user_id"])
    cap = i18n.t(lang, "sup_reply", text=escape(m["text"])) if m["text"] else i18n.t(lang, "sup_reply_photo")
    kb_ = _user_kb(lang)
    uid = m["user_id"]
    if m["photo"]:
        p = photo_path(m["photo"])
        send = lambda: bot.send_photo(uid, BufferedInputFile(p.read_bytes(), p.name), caption=cap[:1024], reply_markup=kb_)
    else:
        send = lambda: bot.send_message(uid, cap, reply_markup=kb_)
    await _replace_notice(bot, uid, "reply", send)


async def ack_user(bot: Bot, msg, lang: str):
    """Mijoz botga yozganda "yuborildi" javobi — oldingisi o'chadi."""
    uid = msg.from_user.id
    await _replace_notice(bot, uid, "ack", lambda: msg.answer(i18n.t(lang, "msg_sent"), reply_markup=_user_kb(lang)))
