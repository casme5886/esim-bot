"""Ko'p tillilik: bot, Mini App va PDF matnlari locales/<til>.json fayllarida.

Yangi til qo'shish: locales/en.json dan nusxa olib tarjima qiling va LANGS ga kodini yozing.
"""
import json
from functools import lru_cache
from pathlib import Path

LOCALES = Path(__file__).with_name("locales")
# tartib — til tanlash tugmalarida shu tartibda chiqadi (birinchisi asosiy til)
LANGS = ["en", "ru", "uz", "uk", "tr", "es", "pt", "id", "hi", "ar"]
DEFAULT = "ru"
FALLBACK = ["en", "ru"]
RTL = {"ar"}
# PDF uchun murakkab yozuvlar (hind, arab) hozircha inglizcha chiqadi
PDF_LANGS = {"ru", "en", "uz", "uk", "tr", "es", "pt", "id"}


@lru_cache(None)
def _data(lang: str) -> dict:
    p = LOCALES / f"{lang}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def norm(lang: str | None) -> str:
    """Telegram language_code ('pt-br', 'en-US', 'id') -> qo'llanadigan til yoki asosiy til."""
    if not lang:
        return DEFAULT
    lang = lang.lower().replace("_", "-").split("-")[0]
    return lang if lang in LANGS else DEFAULT


def guess(language_code: str | None) -> str:
    """Telegram tilidan taxmin: qo'llanadigan bo'lsa o'sha, bo'lmasa asosiy til."""
    return norm(language_code)


def get(lang: str, section: str, key: str):
    for l in [lang, *FALLBACK]:
        v = _data(l).get(section, {}).get(key)
        if v is not None:
            return v
    return key


def t(lang: str, key: str, **kw) -> str:
    s = get(lang, "bot", key)
    return s.format(**kw) if kw and isinstance(s, str) else s


def pdf_lang(lang: str) -> str:
    return lang if lang in PDF_LANGS else "en"


def tp(lang: str, key: str, **kw):
    s = get(pdf_lang(lang), "pdf", key)
    return s.format(**kw) if kw and isinstance(s, str) else s


def lang_name(lang: str) -> str:
    d = _data(lang)
    return f"{d.get('flag', '')} {d.get('name', lang)}".strip()


# ---------- formatlash ----------
def money(lang: str, x) -> str:
    return f"{int(x):,}".replace(",", " ") + " " + t(lang, "cur")


def days(lang: str, n) -> str:
    return t(lang, "days_fmt", n=n)


def gb(lang: str, data_gb, daily=0) -> str:
    if not data_gb:
        return t(lang, "unlimited")
    return f"{data_gb:g} GB" + (t(lang, "per_day") if daily else "")


def _iso_from_flag(flag: str) -> str | None:
    cps = [ord(c) for c in (flag or "")]
    if len(cps) == 2 and all(0x1F1E6 <= c <= 0x1F1FF for c in cps):
        return "".join(chr(c - 0x1F1E6 + 65) for c in cps)
    return None


@lru_cache(None)
def _country_index():
    try:
        import countries
        return {c[0].lower(): c for c in countries.COUNTRIES}
    except Exception:
        return {}


def country(lang: str, name: str, flag: str = "") -> str:
    """Bazadagi o'zbekcha davlat nomini tanlangan tilga o'giradi."""
    if lang == "uz" or not name:
        return name
    try:
        import countries
        reg = countries.regional_by_name(name)
        if reg:
            return reg["ru"] if lang == "ru" else reg["names"].get(lang, reg["names"]["en"])
    except Exception:
        pass
    row = _country_index().get(name.lower())
    if lang == "ru" and row:
        return row[1]
    iso = (row[3].upper() if row else None) or _iso_from_flag(flag)
    if iso:
        try:
            from babel import Locale
            n = Locale.parse(lang).territories.get(iso)
            if n:
                # "(Bali)", "(Zanzibar)" kabi qo'shimchani saqlaymiz
                if "(" in name:
                    return f"{n} {name[name.index('('):]}"
                return n
        except Exception:
            pass
    if row and row[2]:
        return row[2][0]
    return name


def build_webapp_js() -> Path:
    """Mini App tarjimalari: webapp/static/i18n.js (kichik: tillar ro'yxati) + i18n/<til>.js (har til alohida).
    Mijoz faqat o'z tilini yuklaydi. Yetishmagan kalitlar en/ru dan to'ldiriladi."""
    import hashlib
    static = Path(__file__).parent / "webapp" / "static"
    (static / "i18n").mkdir(exist_ok=True)
    langs = [l for l in LANGS if _data(l)]
    files = {}
    for l in langs:
        merged = {}
        for fb in reversed([l, *FALLBACK]):
            merged.update(_data(fb).get("app", {}))
        files[l] = f"I18N[{json.dumps(l)}]={json.dumps(merged, ensure_ascii=False, separators=(',', ':'))};\n"
    ver = hashlib.md5("".join(files[l] for l in langs).encode()).hexdigest()[:10]
    meta = [[l, _data(l).get("name", l), _data(l).get("flag", "")] for l in langs]
    core = ("/* Avtomatik yaratilgan — tahrirlamang, locales/*.json ni o'zgartiring */\n"
            "const I18N = {};\n"
            f"const I18N_LANGS = {json.dumps(meta, ensure_ascii=False)};\n"
            f"const I18N_DEFAULT = {json.dumps(DEFAULT)};\n"
            f"const I18N_RTL = {json.dumps(sorted(RTL))};\n"
            f"const I18N_VER = {json.dumps(ver)};\n")

    def write(path, text):
        if not path.exists() or path.read_text(encoding="utf-8") != text:
            path.write_text(text, encoding="utf-8")
    for l, js in files.items():
        write(static / "i18n" / f"{l}.js", js)
    out = static / "i18n.js"
    write(out, core)
    return out
