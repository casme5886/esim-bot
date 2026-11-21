"""Booking eSIM brendidagi PDF vaucher: QR, kodlar, 1 bosishda o'rnatish havolalari va yo'riqnoma."""
import io
from datetime import datetime
from pathlib import Path

from reportlab.lib.colors import Color, HexColor, white
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import esim_info
import i18n

BRAND = "Booking eSIM"
BLUE = HexColor("#0001E7")
DARK = HexColor("#111827")
GREY = HexColor("#6B7280")
LIGHT = HexColor("#F2F4FF")
LINE = HexColor("#E5E7EB")
LOGO = Path(__file__).parent / "webapp" / "static" / "logo.png"

# Kirill, turk, o'zbek harflari uchun Unicode shrift: loyiha fonts/ papkasi -> Windows Arial -> Linux DejaVu
_FONT_CANDIDATES = [
    (Path(__file__).parent / "fonts" / "Sans.ttf", Path(__file__).parent / "fonts" / "Sans-Bold.ttf"),
    (Path("C:/Windows/Fonts/arial.ttf"), Path("C:/Windows/Fonts/arialbd.ttf")),
    (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")),
    (Path("/Library/Fonts/Arial Unicode.ttf"), Path("/Library/Fonts/Arial Unicode.ttf")),
]
REG, BOLD = "Helvetica", "Helvetica-Bold"
for _r, _b in _FONT_CANDIDATES:
    try:
        if _r.exists() and _b.exists():
            pdfmetrics.registerFont(TTFont("VSans", str(_r)))
            pdfmetrics.registerFont(TTFont("VSans-Bold", str(_b)))
            REG, BOLD = "VSans", "VSans-Bold"
            break
    except Exception:
        continue

APPLE_C = HexColor("#111827")
ANDROID_C = HexColor("#16A34A")


def _wrap(c, text, font, size, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if c.stringWidth(t, font, size) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def _chunk(s, n):
    return [s[i:i + n] for i in range(0, len(s), n)]


def build(order: dict, lpa: str, usage: str | None = None, support: str = "",
          bot_username: str = "Booking_eSIM_bot", lang: str = "ru") -> bytes:
    """Bir sahifali A4 vaucher. order: id, country, data_text, days, created_at. Qaytaradi: PDF bytes.
    lang — mijoz tili (hind/arab tillarida PDF inglizcha chiqadi)."""
    T = lambda k, **kw: i18n.tp(lang, k, **kw)  # noqa: E731

    def fit(text, font, size, width, minsize=6.5):
        while c.stringWidth(text, font, size) > width and size > minsize:
            size -= 0.25
        return size
    buf = io.BytesIO()
    W, H = A4
    M = 32  # chet
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"{BRAND} - {T('order', id=order['id'])}")
    c.setAuthor(BRAND)

    # --- sarlavha
    c.setFillColor(BLUE)
    c.roundRect(M, H - 24 - 74, W - 2 * M, 74, 14, stroke=0, fill=1)
    if LOGO.exists():
        c.drawImage(ImageReader(str(LOGO)), M + 14, H - 24 - 64, 54, 54, mask="auto")
    c.setFillColor(white)
    c.setFont(BOLD, 21)
    c.drawString(M + 80, H - 24 - 34, BRAND)
    c.setFont(REG, fit(T("subtitle"), REG, 10.5, W - 2 * M - 80 - 150))
    c.drawString(M + 80, H - 24 - 52, T("subtitle"))
    c.setFont(BOLD, 11)
    c.drawRightString(W - M - 16, H - 24 - 34, T("order", id=order["id"]))
    c.setFont(REG, 9.5)
    c.drawRightString(W - M - 16, H - 24 - 52, (order.get("created_at") or datetime.now().strftime("%Y-%m-%d"))[:10])

    top = H - 24 - 74 - 12

    # --- o'ng: QR + tugmalar
    boxw, qs = 200, 150
    bx = W - M - boxw
    boxh = 24 + qs + 10 + 34 + 30
    c.setFillColor(LIGHT)
    c.roundRect(bx, top - boxh, boxw, boxh, 12, stroke=0, fill=1)
    c.setFillColor(BLUE)
    c.setFont(BOLD, fit(T("scan"), BOLD, 10.5, boxw - 16))
    c.drawCentredString(bx + boxw / 2, top - 17, T("scan"))
    qx, qy = bx + (boxw - qs) / 2, top - 24 - qs
    c.drawImage(ImageReader(io.BytesIO(esim_info.make_qr_png(lpa))), qx, qy, qs, qs)

    def pill(x_, y_, w_, text, sub, url, color):
        c.setFillColor(color)
        c.roundRect(x_, y_, w_, 34, 9, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont(BOLD, 10.5)
        c.drawCentredString(x_ + w_ / 2, y_ + 19, text)
        c.setFont(REG, fit(sub, REG, 7.3, w_ - 6, 5.5))
        c.drawCentredString(x_ + w_ / 2, y_ + 8, sub)
        c.linkURL(url, (x_, y_, x_ + w_, y_ + 34), relative=0)

    py = qy - 10 - 34
    bw = (boxw - 24 - 6) / 2
    pill(bx + 12, py, bw, "iPhone", T("one_tap"), esim_info.ios_url(lpa), APPLE_C)
    pill(bx + 12 + bw + 6, py, bw, "Android", T("one_tap"), esim_info.android_url(lpa), ANDROID_C)
    c.setFillColor(GREY)
    c.setFont(REG, fit(T("tap_hint"), REG, 7.6, boxw - 4, 5.5))
    c.drawCentredString(bx + boxw / 2, py - 13, T("tap_hint"))

    # --- chap: ma'lumotlar (plitkalar + kod qutilari + "Muhim" bloki)
    smdp, code = esim_info.split_lpa(lpa)
    lx, lw = M, bx - M - 14
    y = top

    def tile(x_, y_top, w_, label, value):
        c.setFillColor(LIGHT)
        c.roundRect(x_, y_top - 46, w_, 46, 10, stroke=0, fill=1)
        c.setFillColor(BLUE)
        c.roundRect(x_, y_top - 46, 4, 46, 2, stroke=0, fill=1)
        c.setFillColor(GREY)
        c.setFont(REG, 7.6)
        c.drawString(x_ + 14, y_top - 16, label.upper())
        c.setFillColor(DARK)
        fs = 12.5
        while c.stringWidth(value, BOLD, fs) > w_ - 24 and fs > 8:
            fs -= 0.5
        c.setFont(BOLD, fs)
        c.drawString(x_ + 14, y_top - 34, value)

    tw = (lw - 8) / 2
    tile(lx, y, tw, T("country"), order.get("country", ""))
    tile(lx + tw + 8, y, tw, T("package"), f"{order.get('data_text', '')}  ·  {T('days', n=order.get('days', ''))}")
    y -= 46 + 12

    def code_box(label, value, y_top):
        c.setFillColor(GREY)
        c.setFont(BOLD, 7.4)
        c.drawString(lx + 2, y_top - 8, label.upper())
        font, fs = "Courier-Bold", 9.2
        per = max(10, int((lw - 20) / c.stringWidth("M", font, fs)))
        lines = _chunk(value, per)[:3]
        bh_ = 10 + 11.5 * len(lines)
        c.setFillColor(HexColor("#F6F7F9"))
        c.setStrokeColor(LINE)
        c.roundRect(lx, y_top - 13 - bh_, lw, bh_, 7, stroke=1, fill=1)
        c.setFillColor(DARK)
        c.setFont(font, fs)
        for i, ln in enumerate(lines):
            c.drawString(lx + 10, y_top - 13 - 14 - i * 11.5, ln)
        return 13 + bh_ + 9

    y -= code_box(T("smdp"), smdp, y)
    y -= code_box(T("act_ios"), code, y)
    y -= code_box(T("act_android"), lpa, y)

    NFS = 8.4
    notes = []  # har bir eslatma kerak bo'lsa 2 qatorga bo'linadi
    for it in T("notes"):
        notes.append(_wrap(c, it, REG, NFS, lw - 30))
    nh = 24 + 12 * sum(len(n) for n in notes) + 6
    y -= 2
    c.setFillColor(HexColor("#FFF7E6"))
    c.setStrokeColor(HexColor("#FDE3B0"))
    c.roundRect(lx, y - nh, lw, nh, 9, stroke=1, fill=1)
    c.setFillColor(HexColor("#F59E0B"))
    c.circle(lx + 15, y - 14, 6, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont(BOLD, 9)
    c.drawCentredString(lx + 15, y - 17, "!")
    c.setFillColor(HexColor("#92400E"))
    c.setFont(BOLD, 10)
    c.drawString(lx + 27, y - 17.5, T("important"))
    yy = y - 32
    for lines_ in notes:
        c.setFillColor(HexColor("#B45309"))
        c.circle(lx + 15, yy + 3, 1.7, stroke=0, fill=1)
        c.setFillColor(DARK)
        c.setFont(REG, NFS)
        for ln in lines_:
            c.drawString(lx + 23, yy, ln)
            yy -= 12
    y -= nh

    # --- iPhone | Android kartalari
    FS, LH = 8.6, 10.8

    def card_height(w_, items):
        h = 30
        for name, text in items:
            h += 13 + LH * len(_wrap(c, text, REG, FS, w_ - 24)) + 6
        return h + 2

    def card(x_, top_, w_, h_, title, color, items):
        c.setFillColor(white)
        c.setStrokeColor(LINE)
        c.roundRect(x_, top_ - h_, w_, h_, 11, stroke=1, fill=1)
        c.setFillColor(color)
        c.roundRect(x_, top_ - 24, w_, 24, 11, stroke=0, fill=1)
        c.rect(x_, top_ - 24, w_, 11, stroke=0, fill=1)
        c.setFillColor(white)
        c.setFont(BOLD, 11.5)
        c.drawString(x_ + 12, top_ - 16.5, title)
        yy = top_ - 39
        for name, text in items:
            c.setFillColor(color)
            c.setFont(BOLD, 9.2)
            c.drawString(x_ + 12, yy, name)
            yy -= 12.5
            c.setFillColor(DARK)
            c.setFont(REG, FS)
            for ln in _wrap(c, text, REG, FS, w_ - 24):
                c.drawString(x_ + 12, yy, ln)
                yy -= LH
            yy -= 6

    ctop = min(y, top - boxh) - 12

    # --- "Internet qoldig'ini tekshirish" banneri (Trip.com'dagi "Check Data Usage" kabi)
    if usage:
        bh = 46
        by = ctop - bh
        # brend ko'kidan binafsharangga silliq gradient (yumaloq burchaklar bilan)
        c.saveState()
        clip = c.beginPath()
        clip.roundRect(M, by, W - 2 * M, bh, 13)
        c.clipPath(clip, stroke=0, fill=0)
        c.linearGradient(M, by, W - M, by + bh, (BLUE, HexColor("#3A2BFF"), HexColor("#6D3BFF")),
                         positions=(0, 0.55, 1), extend=False)
        c.restoreState()
        # belgi: yarim shaffof kvadrat ichida grafik chizig'i
        ix, iy = M + 12, by + 8
        c.setFillColor(Color(1, 1, 1, alpha=0.2))
        c.roundRect(ix, iy, 30, 30, 8, stroke=0, fill=1)
        c.setStrokeColor(white)
        c.setLineWidth(2)
        c.setLineCap(1)
        c.setLineJoin(1)
        p = c.beginPath()
        p.moveTo(ix + 7, iy + 9)
        p.lineTo(ix + 13, iy + 17)
        p.lineTo(ix + 18, iy + 13)
        p.lineTo(ix + 24, iy + 22)
        c.drawPath(p, stroke=1, fill=0)
        c.setLineWidth(1)
        c.setFillColor(white)
        btw = 112
        tw_ = W - 2 * M - 12 - btw - 54 - 10
        c.setFont(BOLD, fit(T("usage_title"), BOLD, 11.5, tw_))
        c.drawString(ix + 42, by + 27, T("usage_title"))
        c.setFont(REG, fit(T("usage_sub"), REG, 8.4, tw_, 6))
        c.setFillColor(Color(1, 1, 1, alpha=0.85))
        c.drawString(ix + 42, by + 13, T("usage_sub"))
        # oq tugma
        btx = W - M - 12 - btw
        c.setFillColor(white)
        c.roundRect(btx, by + 10, btw, 26, 13, stroke=0, fill=1)
        c.setFillColor(BLUE)
        c.setFont(BOLD, fit(T("usage_btn"), BOLD, 9.5, btw - 34))
        c.drawCentredString(btx + btw / 2 - 5, by + 19.5, T("usage_btn"))
        # "tashqi havola" belgisi
        ax, ay = btx + btw / 2 - 5 + c.stringWidth(T("usage_btn"), BOLD, fit(T("usage_btn"), BOLD, 9.5, btw - 34)) / 2 + 5, by + 18
        c.setStrokeColor(BLUE)
        c.setLineWidth(1.3)
        c.line(ax, ay, ax + 6, ay + 6)
        c.line(ax + 2.5, ay + 6, ax + 6, ay + 6)
        c.line(ax + 6, ay + 6, ax + 6, ay + 2.5)
        c.setLineWidth(1)
        c.linkURL(usage, (M, by, W - M, by + bh), relative=0)
        ctop = by - 10

    cw = (W - 2 * M - 10) / 2
    IPHONE, ANDROID = T("iphone"), T("android")
    # matn uzun tillarda (ru, es...) kartalar sig'guncha shriftni kichraytiramiz
    room = ctop - (24 + 70 + 6) - 16
    while max(card_height(cw, IPHONE), card_height(cw, ANDROID)) > room and FS > 6.8:
        FS -= 0.2
        LH = FS * 1.26
    hh = max(card_height(cw, IPHONE), card_height(cw, ANDROID))
    card(M, ctop, cw, hh, T("for_iphone"), APPLE_C, IPHONE)
    card(M + cw + 10, ctop, cw, hh, T("for_android"), ANDROID_C, ANDROID)
    y = ctop - hh - 16

    _cards_bottom = y + 16  # pastki blok bilan ustma-ust tushmasligini tekshirish uchun
    # --- pastki qism: Telegram bot QR kodi va havolasi
    bot_url = f"https://t.me/{bot_username}"
    fy, fh = 24, 70
    assert _cards_bottom > fy + fh + 6, "vaucher bir sahifaga sig'madi"
    c.setFillColor(LIGHT)
    c.roundRect(M, fy, W - 2 * M, fh, 12, stroke=0, fill=1)
    qsz = 58
    c.setFillColor(white)
    c.roundRect(M + 10, fy + 8, qsz, qsz, 6, stroke=0, fill=1)
    c.drawImage(ImageReader(io.BytesIO(esim_info.make_qr_png(bot_url))), M + 12, fy + 10, qsz - 4, qsz - 4)
    tx = M + 10 + qsz + 14
    c.setFillColor(GREY)
    c.setFont(REG, 7.8)
    c.drawString(tx, fy + fh - 16, T("bot_title"))
    c.setFillColor(BLUE)
    c.setFont(BOLD, 13)
    c.drawString(tx, fy + fh - 32, f"@{bot_username}")
    c.setFillColor(DARK)
    c.setFont(REG, 9)
    c.drawString(tx, fy + 24, f"t.me/{bot_username}")
    c.setFillColor(GREY)
    c.setFont(REG, 8)
    c.setFont(REG, fit(T("bot_line"), REG, 8, W - 2 * M - 14 - 120 - 14 - (tx - M)))
    c.drawString(tx, fy + 11, T("bot_line"))
    c.linkURL(bot_url, (M, fy, M + 330, fy + fh), relative=0)
    # o'ng tomon: ochish tugmasi va eslatmalar
    btw = 120
    btx = W - M - 14 - btw
    c.setFillColor(BLUE)
    c.roundRect(btx, fy + fh - 36, btw, 24, 12, stroke=0, fill=1)
    c.setFillColor(white)
    c.setFont(BOLD, 9.5)
    c.setFont(BOLD, fit(T("open_bot"), BOLD, 9.5, btw - 12))
    c.drawCentredString(btx + btw / 2, fy + fh - 27.5, T("open_bot"))
    c.linkURL(bot_url, (btx, fy + fh - 36, btx + btw, fy + fh - 12), relative=0)
    c.setFillColor(GREY)
    c.setFont(REG, 7.6)
    if support:
        c.drawRightString(W - M - 14, fy + 22, T("support", u=support))
    c.setFont(REG, fit(T("dont_share"), REG, 7.6, 170))
    c.drawRightString(W - M - 14, fy + 11, T("dont_share"))
    c.showPage()
    c.save()
    return buf.getvalue()
