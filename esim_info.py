"""eSIM ma'lumotini (LPA kod) PDF vaucher, QR rasm, havola yoki matndan ajratib olish.

Trip.com vaucheri (PDF) ichida "iOS/Android One-Tap Install" havolalari bor:
  https://esimsetup.apple.com/esim_qrcode_provisioning?carddata=LPA:1$smdp$KOD
Kodni shu havolalardan, bo'lmasa QR rasmdan (OpenCV), bo'lmasa matndan olamiz.
"""
import io
import re
from urllib.parse import unquote

LPA_RE = re.compile(r"LPA:1\$[A-Za-z0-9.\-]+\$[A-Za-z0-9\-]+")
SMDP_RE = re.compile(r"SM-?DP\+?\s*(?:address|server)?\s*[:：]?\s*([A-Za-z0-9.\-]+\.[A-Za-z]{2,})", re.I)
CODE_RE = re.compile(r"activation\s*code[^:：\n]*[:：]?\s*([A-Za-z0-9\-]{8,})", re.I)
USAGE_HOSTS = ("cardinfo.", "usage", "flow-consumer", "globalesimstore", "query")


def ios_url(lpa: str) -> str:
    return f"https://esimsetup.apple.com/esim_qrcode_provisioning?carddata={lpa}"


def android_url(lpa: str) -> str:
    return f"https://esimsetup.android.com/esim_qrcode_provisioning?carddata={lpa}"


def split_lpa(lpa: str):
    """LPA:1$smdp$kod -> (smdp, kod)"""
    parts = lpa.split("$")
    return (parts[1], parts[2]) if len(parts) >= 3 else ("", "")


def from_text(text: str) -> str | None:
    text = unquote(text or "")
    m = LPA_RE.search(text)
    if m:
        return m.group(0)
    a, c = SMDP_RE.search(text), CODE_RE.search(text)
    if a and c:
        return f"LPA:1${a.group(1)}${c.group(1)}"
    return None


def usage_link(urls) -> str | None:
    for u in urls:
        if u.startswith("http") and "esimsetup" not in u and any(h in u for h in USAGE_HOSTS):
            return u
    return None


def decode_qr(image_bytes: bytes) -> str | None:
    """Rasmdagi QR kodni o'qiydi (OpenCV o'rnatilgan bo'lsa)."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    img = cv2.imdecode(np.frombuffer(image_bytes, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return None
    det = cv2.QRCodeDetector()
    for im in (img, cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)):
        val, _, _ = det.detectAndDecode(im)
        if val:
            return from_text(val) or None
    return None


def from_pdf(pdf_bytes: bytes) -> dict:
    """PDF vaucherdan: lpa, usage (internet qoldig'i havolasi)."""
    out = {"lpa": None, "usage": None}
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return out
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    urls, text = [], ""
    for page in doc:
        urls += [lnk.get("uri", "") for lnk in page.get_links() if lnk.get("uri")]
        text += page.get_text()
    for u in urls:
        out["lpa"] = out["lpa"] or from_text(u)
    out["lpa"] = out["lpa"] or from_text(text)
    out["usage"] = usage_link(urls)
    if not out["lpa"]:  # havola yo'q — sahifani rasmga aylantirib QR'ni o'qiymiz
        for page in doc:
            out["lpa"] = decode_qr(page.get_pixmap(dpi=200).tobytes("png"))
            if out["lpa"]:
                break
    return out


def analyze(data: bytes, filename: str = "") -> dict:
    """Istalgan fayl (PDF yoki rasm) -> {'lpa','usage'}"""
    if data[:4] == b"%PDF" or filename.lower().endswith(".pdf"):
        return from_pdf(data)
    return {"lpa": decode_qr(data), "usage": None}


def from_html(html: str) -> dict:
    """Buyurtma sahifasining HTML'idan (havolalar ichida carddata=LPA... bo'ladi)."""
    urls = re.findall(r'https?://[^\s"\'<>]+', html or "")
    lpa = None
    for u in urls:
        if "carddata=" in u:
            lpa = from_text(u)
            if lpa:
                break
    return {"lpa": lpa or from_text(re.sub(r"<[^>]+>", " ", html or "")), "usage": usage_link(urls),
            "pdf": next((unquote(u) for u in urls if ".pdf" in u.lower()), None)}


def make_qr_png(lpa: str) -> bytes:
    import qrcode
    img = qrcode.make(lpa, box_size=10, border=3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
