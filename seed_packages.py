"""Boshlang'ich paketlarni esim.db ga yozadi (bir marta). Takroriy ishga tushirilsa, mavjudlarini qayta qo'shmaydi."""
import json, sqlite3, sys
rows = json.load(open(sys.argv[1], encoding="utf-8"))
db = sqlite3.connect(sys.argv[2])
cols = {r[1] for r in db.execute("PRAGMA table_info(packages)")}
for col, ddl in [("region", "TEXT DEFAULT ''"), ("popular", "INTEGER DEFAULT 0"), ("trip_url", "TEXT DEFAULT ''")]:
    if col not in cols:
        db.execute(f"ALTER TABLE packages ADD COLUMN {col} {ddl}")
added = 0
for x in rows:
    if db.execute("SELECT 1 FROM packages WHERE country=? AND data_gb=? AND days=?", (x["country"], x["data_gb"], x["days"])).fetchone():
        continue
    db.execute("INSERT INTO packages(country, flag, data_gb, days, price, cost_usd, region, popular, trip_url) VALUES(?,?,?,?,?,?,?,?,?)",
               (x["country"], x["flag"], x["data_gb"], x["days"], x["price"], x["cost_usd"], x["region"], x["popular"], x["trip_url"]))
    added += 1
db.commit()
print("qo'shildi:", added, "| jami paketlar:", db.execute("SELECT COUNT(*) FROM packages").fetchone()[0])
