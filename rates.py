"""Valyuta kurslari (O'zbekiston Markaziy banki) — Mini App'da narxni USD/RUB/CNY/EUR da ko'rsatish uchun.
To'lov baribir so'mda; bu faqat mijozga tushunarli bo'lishi uchun taxminiy ko'rsatkich."""
import json
import logging
import time

import aiohttp

import db

CBU_URL = "https://cbu.uz/uz/arkhiv-kursov-valyut/json/"
CODES = ("USD", "RUB", "CNY", "EUR")
TTL = 6 * 3600
_cache = {"at": 0.0, "data": None}
log = logging.getLogger("rates")


async def _fetch() -> dict | None:
    try:
        async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=10)) as s:
            async with s.get(CBU_URL) as r:
                rows = await r.json(content_type=None)
        out, date = {}, ""
        for row in rows:
            ccy = row.get("Ccy")
            if ccy in CODES:
                nominal = float(row.get("Nominal") or 1)
                out[ccy] = float(str(row["Rate"]).replace(",", ".")) / nominal  # 1 birlik = N so'm
                date = row.get("Date", date)
        if len(out) == len(CODES):
            return {"UZS": 1, **out, "date": date, "source": "cbu.uz"}
    except Exception as e:
        log.warning("Kurslarni olib bo'lmadi: %s", e)
    return None


async def get_rates() -> dict | None:
    """1 USD/RUB/CNY/EUR necha so'm. Internet bo'lmasa oxirgi saqlangan kurs qaytadi."""
    if _cache["data"] and time.time() - _cache["at"] < TTL:
        return _cache["data"]
    data = await _fetch()
    if data:
        _cache.update(at=time.time(), data=data)
        await db.set_setting("fx_rates", json.dumps(data))
        return data
    saved = await db.get_setting("fx_rates")
    if saved:
        try:
            data = json.loads(saved)
            _cache.update(at=time.time() - TTL + 600, data=data)  # 10 daqiqadan keyin yana urinib ko'ramiz
            return data
        except ValueError:
            pass
    # hech qanday kurs yo'q — hech bo'lmasa admin paneldagi dollar kursi bilan USD'ni ko'rsatamiz
    try:
        usd = float(await db.get_setting("price_rate") or 0)
    except ValueError:
        usd = 0
    return {"UZS": 1, "USD": usd, "source": "admin"} if usd else None
