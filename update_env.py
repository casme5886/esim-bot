"""start.ps1 chaqiradi: .env dagi WEBAPP_URL ni yangi tunnel manziliga almashtiradi."""
import io
import re
import sys

url = sys.argv[1]
s = io.open(".env", encoding="utf-8-sig").read()
if re.search(r"(?m)^WEBAPP_URL=", s):
    s = re.sub(r"(?m)^WEBAPP_URL=.*$", "WEBAPP_URL=" + url, s)
else:
    s = s.rstrip() + "\nWEBAPP_URL=" + url + "\n"
io.open(".env", "w", encoding="utf-8").write(s)
print("      .env: WEBAPP_URL=" + url)
