"""Narxlarni avtomatik yangilash: har kecha Trip.com'dan barcha davlatlar qayta tekshiriladi.
Tannarx o'zgargan paketning sotuv narxi joriy ustama bo'yicha qayta hisoblanadi (qimmatlagani zarar bilan sotilmaydi).
Tugagach adminlarga qisqa hisobot: nechta paket qimmatladi / arzonladi."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

import db

log = logging.getLogger("autoupdate")
TZ = timezone(timedelta(hours=5))
DEFAULTS = {"enabled": 1, "hour": 4}


async def settings() -> dict:
    out = dict(DEFAULTS)
    for k in out:
        v = await db.get_setting("auto_" + k)
        if v != "":
            try:
                out[k] = int(v)
            except ValueError:
                pass
    try:
        out["last"] = json.loads(await db.get_setting("auto_last") or "null")
    except ValueError:
        out["last"] = None
    import trip_import
    out["running"] = bool(trip_import.STATE.get("running"))
    return out


async def save_settings(enabled: bool, hour: int) -> dict:
    if not 0 <= hour <= 23:
        raise ValueError("hour")
    await db.set_setting("auto_enabled", "1" if enabled else "0")
    await db.set_setting("auto_hour", str(hour))
    return await settings()


def _fmt(n):
    return f"{int(n):,}".replace(",", " ")


async def run_once(bot: Bot) -> dict | None:
    import trip_import
    import trip_buyer
    if trip_import.STATE.get("running"):
        log.info("Avto-yangilash: import allaqachon ketmoqda, o'tkazib yuborildi")
        return None
    before = {r["id"]: (r["price"], r["country"], r["flag"]) for r in
              await db._fetchall("SELECT id, price, country, flag FROM packages WHERE active=1")}
    started = datetime.now(TZ)
    res = await trip_import.run_import(bot, quiet=True)
    if not isinstance(res, dict):   # to'xtatilgan bo'lsa run_import o'zi xabar beradi
        return None
    after = {r["id"]: r["price"] for r in await db._fetchall("SELECT id, price FROM packages WHERE active=1")}
    up, down = [], []
    for pid, (old, country, flag) in before.items():
        new = after.get(pid)
        if new is None or new == old:
            continue
        (up if new > old else down).append((new - old, old, new, country, flag))
    up.sort(reverse=True)
    summary = {"at": started.strftime("%Y-%m-%d %H:%M"), "minutes": int((datetime.now(TZ) - started).total_seconds() // 60),
               "ok": res["ok"], "total": res["total"], "added": res["added"], "up": len(up), "down": len(down),
               "failed": len(res["failed"])}
    await db.set_setting("auto_last", json.dumps(summary))
    text = (f"🔄 <b>Narxlar avtomatik yangilandi</b> ({summary['minutes']} daq)\n"
            f"Tekshirildi: {res['ok']}/{res['total']} davlat · ➕ {res['added']} yangi paket\n"
            f"📈 Qimmatladi: {len(up)} · 📉 Arzonladi: {len(down)}")
    if up:
        text += "\n\nEng ko'p qimmatlaganlar:\n" + "\n".join(
            f"{flag} {country}: {_fmt(old)} → <b>{_fmt(new)}</b> so'm" for _, old, new, country, flag in up[:5])
    if res["failed"]:
        text += f"\n\n⚠️ Tekshirib bo'lmadi: {len(res['failed'])} ta (narxi o'zgarmadi)"
    await trip_buyer._tell(bot, text)
    log.info("Avto-yangilash tugadi: %s", summary)
    return summary


async def loop(bot: Bot):
    """Har kuni belgilangan soatda (Toshkent vaqti) — yoqilgan bo'lsa."""
    while True:
        s = await settings()
        now = datetime.now(TZ)
        nxt = now.replace(hour=s["hour"], minute=0, second=0, microsecond=0)
        if nxt <= now:
            nxt += timedelta(days=1)
        # soat sozlamasi o'zgarsa ham kechikmaslik uchun ko'pi bilan 30 daqiqa uxlaymiz
        wait = (nxt - now).total_seconds()
        if wait > 1800:
            await asyncio.sleep(1800)
            continue
        await asyncio.sleep(wait)
        s = await settings()
        if s["enabled"] and datetime.now(TZ).hour == s["hour"]:
            try:
                await run_once(bot)
            except Exception:
                log.exception("Avto-yangilashda xato")
        await asyncio.sleep(3700)
