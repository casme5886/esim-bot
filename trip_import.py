"""Trip.com'dan davlatlar va paketlarni import qilish (oddiy sahifalarni ochib, ekrandagi narxni o'qiydi).

Har bir davlat uchun:
  1. trip.com/things-to-do/experiences/<davlat>-simcard/ ro'yxatini ochadi,
     shu davlatga tegishli birinchi (eng mashhur) eSIM mahsulotini tanlaydi;
  2. mahsulot sahifasida "Total ... GB" paketlaridan 4 tasini tanlaydi (3/5/10/20 GB),
     kun va GB tugmalarini bosib, ekranda chiqqan narxni o'qiydi;
  3. sotuv narxini (narx × ustama × kurs) hisoblab, bazaga yozadi (bor bo'lsa yangilaydi).
Sahifalar orasida pauza qilinadi — saytga ortiqcha yuk tushmasin.
"""
import asyncio
import logging
import math
import re

from aiogram import Bot

import db
from countries import as_dicts, regional_dicts, slug

log = logging.getLogger("trip_import")

SCAN_OPTS = {"maxDays": 30, "maxDailyGb": 3, "maxCombos": 260}  # 1–30 kun, kunlik 0.5–3 GB, jami barcha GB
WORKERS = 3   # parallel oynalar soni
POPULAR_ISO = {"tr", "ae", "sa", "ru", "cn", "kr", "th"}
PAUSE = 2.5  # sahifalar orasidagi pauza (sekund)

EN = "locale=en-US&curr=USD"   # sahifa doim inglizcha va dollarda ochilsin (IP bo'yicha rus/o'zbek tiliga o'tmasin)
_snaps = 0

STATE = {"running": False, "total": 0, "done": 0, "current": "", "added": 0, "updated": 0, "failed": []}

# ---------- sahifa ichida ishlaydigan skriptlar ----------
LIST_JS = """() => {
  const seen = new Set(), out = [];
  for (const a of document.querySelectorAll('a[href*="/things-to-do/detail/"]')) {
    const id = (a.href.match(/detail\\/(\\d+)/) || [])[1];
    const txt = (a.innerText || '').replace(/\\s+/g, ' ').trim();
    if (id && txt && !seen.has(id)) { seen.add(id); out.push({id, title: txt}); }
  }
  return out;
}"""

SCAN_JS = r"""async (opts) => {
  const N = s => (s || '').replace(/\s+/g, ' ').trim();
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  let area = null;
  for (let i = 0; i < 30 && !area; i++) {
    area = document.querySelector('[testid="productdetail_sku_area"]');
    if (!area) { window.scrollBy(0, 400); await sleep(500); }
  }
  if (!area || !window.__NEXT_DATA__) return {err: 'paket bo\'limi topilmadi'};
  area.scrollIntoView({block: 'start'});
  const pi = window.__NEXT_DATA__.props.pageProps.initialState.__STATE_MAP__.PageModel.ds.getProductInfo[0];
  const parsePlan = v => {
    // "Total 3GB", "Total-3GB", "Total: 3 GB" — hammasi bir xil o'qilsin
    let m = v.match(/^Total[\s\-:]*([\d.]+) ?(GB|MB)$/i);
    if (m) return {gb: +m[1] / (m[2].toUpperCase() === 'MB' ? 1024 : 1), daily: 0};
    m = v.match(/^Daily[\s\-:]*([\d.]+) ?(GB|MB)$/i) || v.match(/^([\d.]+) ?(GB|MB) ?\/ ?day$/i);
    if (m) return {gb: +m[1] / (m[2].toUpperCase() === 'MB' ? 1024 : 1), daily: 1};
    return null;
  };
  const combos = [];
  for (const p of pi.basicInfo.packages) {
    const vals = (p.salesProperties || []).map(s => N(s.salePropertyValues[0].name));
    const d = vals.find(v => /^\d+ days?$/.test(v));
    if (!d || !(p.resourceIds || [])[0]) continue;
    for (const v of vals) {
      const pl = parsePlan(v);
      if (!pl) continue;
      const dn = parseInt(d);
      if (dn > opts.maxDays || (pl.daily && pl.gb > opts.maxDailyGb)) continue;
      combos.push({days: d, plan: v, dn, gb: Math.round(pl.gb * 100) / 100, daily: pl.daily, pkg: p.packageId, opt: p.resourceIds[0]});
    }
  }
  combos.sort((a, b) => a.dn - b.dn || a.daily - b.daily || a.gb - b.gb);
  const leaf = t => [...area.querySelectorAll('span,div')].find(e => e.children.length === 0 && N(e.innerText) === t);
  const isSel = e => !!e && !!e.closest('[testid$="_select"]');
  const price = () => document.querySelector('[testid="undefined-price"]')?.innerText || '';
  const waitChange = async prev => { for (let i = 0; i < 16; i++) { await sleep(100); const p = price(); if (p && p !== prev) break; } await sleep(250); };
  // 1-qadam: "Collection/Pickup Method" (QR code) kabi majburiy tanlovlar — tanlanmagan bo'lsa bosamiz
  const stepVals = new Set();
  for (const p of pi.basicInfo.packages)
    for (const s of (p.salesProperties || []))
      if (/pickup|collection|delivery|method|receiv/i.test(s.saleProperty?.name || '')) stepVals.add(N(s.salePropertyValues[0].name));
  for (const v of stepVals) { const el = leaf(v); if (el && !isSel(el)) { el.click(); await sleep(900); break; } }
  const out = [];
  for (const c of combos.slice(0, opts.maxCombos)) {
    const dc = leaf(c.days); if (!dc) continue;
    if (!isSel(dc)) { const pr = price(); dc.click(); await waitChange(pr); }
    const pc = leaf(c.plan); if (!pc) continue;
    if (!isSel(pc)) { const pr = price(); pc.click(); await waitChange(pr); }
    const txt = price();
    const m = txt.match(/(?:US)?\$\s?([\d,.]+)/);
    if (m && isSel(leaf(c.days)) && isSel(leaf(c.plan)))
      out.push({gb: c.gb, daily: c.daily, days: c.dn, pkg: c.pkg, opt: c.opt, cost: parseFloat(m[1].replace(/,/g, ''))});
  }
  return {title: document.title, items: out, total: combos.length};
}"""


def _title_matches(title: str, names: list[str]) -> bool:
    seg = title.split("|")[0]
    seg = re.sub(r"\[|\]", " ", seg)
    seg = re.sub(r"\b[45]G\s*/\s*[45]G\b", " ", seg, flags=re.I)
    seg = " ".join(seg.split()).lower()
    if "/" in seg or re.search(r"\d+\s*(countries|destinations)", seg):
        return False  # bir nechta davlatli mahsulot — o'tkazib yuboramiz
    return any(seg.startswith(n.lower()) for n in names) and "esim" in title.lower()


DEFAULT_PRICING = {"markup": 2.0, "rate": 12100.0, "min_price": 0}
PRICE_FORMULA = "v2"  # v2: minimal narx yo'q, 1 000 so'mga yaxlitlash


async def pricing() -> dict:
    """Admin panelda saqlangan narx sozlamalari (ustama, dollar kursi, minimal narx)."""
    out = dict(DEFAULT_PRICING)
    for k in out:
        v = await db.get_setting("price_" + k)
        try:
            if v:
                out[k] = float(v)
        except ValueError:
            pass
    out["min_price"] = int(out["min_price"])
    return out


def sell_price(cost, markup, rate, min_price=0):
    """Sotuv narxi = Trip.com narxi × ustama × kurs, yuqoriga 1 000 so'mgacha yaxlitlanadi (masalan 23 400 -> 24 000)."""
    v = cost * markup * rate
    return int(max(min_price, math.ceil(v / 1000) * 1000, 1000))


async def ensure_formula():
    """Narx formulasi o'zgargan bo'lsa (yangi versiya), barcha narxlarni bir marta qayta hisoblaydi."""
    if await db.get_setting("price_formula") != PRICE_FORMULA:
        await db.set_setting("price_min_price", "0")
        n = await reprice_all()
        await db.set_setting("price_formula", PRICE_FORMULA)
        log.info("Narx formulasi yangilandi (%s): %s ta paket narxi qayta hisoblandi", PRICE_FORMULA, n)


async def reprice_all() -> int:
    """Tannarxi ma'lum barcha paketlar narxini joriy sozlamalar bo'yicha qayta hisoblaydi (import qilmasdan)."""
    p = await pricing()
    rows = await db._fetchall("SELECT id, cost_usd, price FROM packages WHERE cost_usd > 0")
    n = 0
    for r in rows:
        new = sell_price(r["cost_usd"], p["markup"], p["rate"], p["min_price"])
        if new != r["price"]:
            await db.update_package(r["id"], price=new)
            n += 1
    return n


async def _snap(page, c, step):
    """Dastlabki xatolarning skrinshoti: trip_logs/import_<davlat>_<qadam>.png"""
    global _snaps
    if _snaps >= 6:
        return
    _snaps += 1
    try:
        from pathlib import Path
        d = Path(__file__).with_name("trip_logs")
        d.mkdir(exist_ok=True)
        await page.screenshot(path=str(d / f"import_{c['iso']}_{step}.png"))
        txt = await page.evaluate("() => document.title + '\\n' + document.body.innerText.slice(0, 1500)")
        (d / f"import_{c['iso']}_{step}.txt").write_text(page.url + "\n" + txt, encoding="utf-8")
    except Exception as e:
        log.warning("snap xato: %s", e)


async def _find_regional(page, c):
    """Mintaqaviy eSIM: avval ma'lum mahsulotlar, keyin davlat sahifalaridan nomi mos kelganlari."""
    import re
    out = [{"id": pid, "title": ""} for pid in c.get("product_ids", [])]
    rx = re.compile(c["title_re"], re.I)
    for pg in c.get("list_pages", []):
        if len(out) >= 4:
            break
        for kind in ("simcard", "connectivity-solutions"):
            url = f"https://www.trip.com/things-to-do/experiences/{pg}-{kind}/?{EN}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                items = await page.evaluate(LIST_JS)
            except Exception as e:
                log.warning("%s: %s ochilmadi: %s", c["uz"], url, e)
                continue
            for it in items:
                hits = sum(n.lower() in it["title"].lower() for n in c.get("title_any", []))
                ok = rx.search(it["title"]) or (c.get("title_any") and hits >= c.get("title_min", 3))
                if ok and all(it["id"] != o["id"] for o in out):
                    out.append(it)
            await asyncio.sleep(PAUSE)
    return out[:4]


def _country_names_en() -> dict:
    """Inglizcha davlat nomi -> ISO (qamrov ro'yxatini sahifa matnidan topish uchun)."""
    names = {}
    try:
        from babel import Locale
        for code, n in Locale.parse("en").territories.items():
            if len(code) == 2 and code.isalpha() and code not in ("EU", "EZ", "UN", "ZZ", "QO", "XA", "XB"):
                names[n] = code
    except Exception:
        pass
    from countries import COUNTRIES
    for _uz, _ru, ens, iso, _r in COUNTRIES:
        for n in ens:
            names[n] = iso.upper()
    names.update({"Czech Republic": "CZ", "Turkey": "TR", "Russia": "RU", "South Korea": "KR", "Macau": "MO",
                  "Macao": "MO", "Vatican": "VA", "Bosnia and Herzegovina": "BA", "North Macedonia": "MK",
                  "Hong Kong": "HK", "Taiwan": "TW", "Vietnam": "VN", "Laos": "LA", "Kosovo": "XK", "UK": "GB",
                  "United Kingdom": "GB", "USA": "US", "United States": "US", "UAE": "AE", "Mainland China": "CN",
                  "Ivory Coast": "CI", "Moldova": "MD", "Palestine": "PS", "Brunei": "BN", "Cape Verde": "CV"})
    return names


NOT_COUNTRIES = {"EU", "EZ", "UN", "XA", "XB", "QO", "ZZ"}

COVER_JS = r"""(names) => {
  let txt = document.body.innerText || '';
  // izohlar (Reviews) bo'limini kesib tashlaymiz — u yerda tasodifiy davlat nomlari bo'lishi mumkin
  const pk = txt.indexOf('Package'), rv = txt.indexOf('Reviews', pk > 0 ? pk : 0);
  if (rv > 0) txt = txt.slice(0, rv);
  // "Ko'proq" ostida yashiringan tavsif ham bo'lishi mumkin — mahsulot ma'lumotini (izohlarsiz) qo'shamiz
  try {
    const pi = window.__NEXT_DATA__.props.pageProps.initialState.__STATE_MAP__.PageModel.ds.getProductInfo[0];
    txt += '\n' + JSON.stringify(pi).replace(/\\n/g, '\n');
  } catch (e) {}
  const found = new Set();
  for (const [n, iso] of Object.entries(names)) {
    const re = new RegExp('(^|[^A-Za-z])' + n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') + '(?![A-Za-z])');
    if (re.test(txt)) found.add(iso);
  }
  return [...found];
}"""


async def _find_products(page, c):
    """Shu davlatga mos mahsulotlar ro'yxati (mashhurlik tartibida, ko'pi bilan 3 ta)."""
    if c.get("regional"):
        return await _find_regional(page, c)
    for kind in ("simcard", "connectivity-solutions"):
        for name in c["en"][:2]:
            url = f"https://www.trip.com/things-to-do/experiences/{slug(name)}-{kind}/?{EN}"
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30000)
                await page.wait_for_timeout(3000)
                items = await page.evaluate(LIST_JS)
            except Exception as e:
                log.warning("%s: %s ochilmadi: %s", c["uz"], url, e)
                continue
            log.info("%s: %s -> %s ta havola", c["uz"], url, len(items))
            found = [it for it in items if _title_matches(it["title"], c["en"])][:3]
            if found:
                return found
            await asyncio.sleep(PAUSE)
    return []


async def import_country(page, c, markup=None, rate=None):
    prods = await _find_products(page, c)
    if not prods:
        await _snap(page, c, "list")
        raise RuntimeError(f"alohida eSIM topilmadi (sahifa: {page.url[:70]})")
    res, prod, last_err = None, None, ""
    for cand in prods:  # birinchisida "Total GB" paketlar bo'lmasa keyingisini sinaymiz
        await asyncio.sleep(PAUSE)
        await page.goto(f"https://www.trip.com/things-to-do/detail/{cand['id']}/?{EN}", wait_until="domcontentloaded",
                        timeout=40000)
        await page.wait_for_timeout(4000)
        r = await page.evaluate(SCAN_JS, SCAN_OPTS)
        if r.get("items"):
            res, prod = r, cand
            break
        last_err = r.get("err") or "Total GB paketlari yo'q"
    if not res:
        await _snap(page, c, "scan")
        raise RuntimeError(last_err or "narxlar o'qilmadi")
    if c.get("regional"):
        cover = [x for x in await page.evaluate(COVER_JS, _country_names_en()) if x not in NOT_COUNTRIES]
        if len(cover) < 5:
            raise RuntimeError(f"qamrov ro'yxati topilmadi ({len(cover)} ta davlat)")
        import json as _json
        await db.set_setting("coverage_" + c["iso"], _json.dumps(sorted(cover)))
        log.info("%s qamrovi: %s ta davlat", c["uz"], len(cover))
    if len(res["items"]) < res.get("total", 0) * 0.5:
        log.warning("%s: %s/%s narx o'qildi", c["uz"], len(res["items"]), res.get("total"))

    items = res["items"]
    exists_country = await db._fetchone("SELECT popular FROM packages WHERE country=? LIMIT 1", (c["uz"],))
    popular = exists_country["popular"] if exists_country else (1 if c["iso"] in POPULAR_ISO else 0)
    added = updated = 0
    touched = []
    p = await pricing()  # admin panelda import paytida o'zgartirilsa ham yangi qiymat ishlatiladi
    mk = markup or p["markup"]
    rt = rate or p["rate"]
    for it in items:
        price = sell_price(it["cost"], mk, rt, p["min_price"])
        url = (f"https://www.trip.com/xthings-to-do/booking-activity?actid={prod['id']}"
               f"&optid={it['opt']}&packageId={it['pkg']}")
        row = await db._fetchone("SELECT id FROM packages WHERE country=? AND data_gb=? AND days=? AND daily=?",
                                 (c["uz"], it["gb"], it["days"], it["daily"]))
        if row:
            await db.update_package(row["id"], price=price, cost_usd=it["cost"], trip_url=url, flag=c["flag"],
                                    region=c["region"], active=1)
            touched.append(row["id"])
            updated += 1
        else:
            pid = await db.add_package(c["uz"], c["flag"], it["gb"], it["days"], price, it["cost"], c["region"],
                                       popular, it["daily"])
            await db.update_package(pid, trip_url=url)
            touched.append(pid)
            added += 1
    # shu davlatning eski (bu safar Trip.com'da topilmagan) import paketlarini yashiramiz
    if touched:
        q = ",".join("?" * len(touched))
        await db._execute(f"UPDATE packages SET active=0 WHERE country=? AND trip_url!='' AND id NOT IN ({q})",
                          (c["uz"], *touched))
    return added, updated, prod


async def run_import(bot: Bot, markup: float | None = None, rate: float | None = None, only: list[str] | None = None, quiet=False):
    """Fon vazifasi. only — faqat shu ISO kodlar (masalan ['id','cn']); None — hammasi."""
    import trip_buyer
    if STATE["running"]:
        return
    countries = [c for c in as_dicts() + regional_dicts() if not only or c["iso"] in only]
    global _snaps
    _snaps = 0
    STATE.update(running=True, total=len(countries), done=0, current="", added=0, updated=0, failed=[])
    if markup is None or rate is None:
        p = await pricing()
        markup, rate = markup or p["markup"], rate or p["rate"]
    rate_txt = f"{rate:,.0f}".replace(",", " ")
    if not quiet:
        await trip_buyer._tell(bot, f"📥 Trip.com'dan import boshlandi: {len(countries)} ta davlat "
                                    f"(ustama ×{markup:g}, kurs {rate_txt}). Har davlatdan 1–30 kun, barcha GB variantlari. "
                                    f"Taxminan {max(1, len(countries) * 4 // WORKERS)} daqiqa…")
    queue = asyncio.Queue()
    for c in countries:
        queue.put_nowait(c)

    async def worker():
        try:
            page = await trip_buyer._new_page()
        except Exception as e:
            log.warning("Oyna ochilmadi: %s", e)
            return
        try:
            while not queue.empty():
                c = queue.get_nowait()
                STATE["current"] = c["uz"]
                try:
                    a, u, prod = await import_country(page, c, markup, rate)
                    STATE["added"] += a
                    STATE["updated"] += u
                    log.info("Import %s: +%s, yangilandi %s (%s)", c["uz"], a, u, prod["id"])
                except Exception as e:
                    STATE["failed"].append(f"{c['uz']}: {str(e)[:80]}")
                    log.warning("Import %s xato: %s", c["uz"], e)
                STATE["done"] += 1
                if STATE["done"] >= 9 and len(STATE["failed"]) == STATE["done"]:
                    STATE["aborted"] = True
                    while not queue.empty():
                        queue.get_nowait()
                    break
                if STATE["done"] % 15 == 0 and not quiet:
                    await trip_buyer._tell(bot, f"📥 Import: {STATE['done']}/{STATE['total']} · "
                                                f"+{STATE['added']} yangi, {STATE['updated']} yangilandi")
                await asyncio.sleep(PAUSE)
        finally:
            try:
                await page.close()
            except Exception:
                pass

    try:
        await asyncio.gather(*(worker() for _ in range(min(WORKERS, len(countries)))))
    finally:
        STATE.update(running=False, current="")
    if STATE.pop("aborted", False):
        return await trip_buyer._tell(bot, "⛔️ Import to'xtatildi: dastlabki davlatlarning hammasi xato bilan tugadi.\n\n"
                                           + "\n".join(STATE["failed"][:9])
                                           + "\n\nSkrinshotlar: E:\\project\\esim-bot\\trip_logs\\import_*.png")
    ok = STATE["total"] - len(STATE["failed"])
    if quiet:
        return {"ok": ok, "total": STATE["total"], "added": STATE["added"], "updated": STATE["updated"],
                "failed": list(STATE["failed"])}
    text = (f"✅ Import tugadi: {ok}/{STATE['total']} davlat.\n"
            f"➕ Yangi paketlar: {STATE['added']}\n🔄 Yangilangan: {STATE['updated']}")
    if STATE["failed"]:
        text += "\n\n⚠️ Topilmadi / xato:\n" + "\n".join(STATE["failed"][:40])
    await trip_buyer._tell(bot, text)


def start(bot: Bot, **kw):
    asyncio.create_task(run_import(bot, **kw))
