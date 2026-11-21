# Esim_On bot (1-bosqich: yarim avtomat)

Mijoz botda davlat va paketni tanlaydi va to'laydi. Siz Trip.com'dan eSIM sotib olib, QR kodni botga yuborasiz. Bot uni mijozga o'rnatish yo'riqnomasi bilan birga yetkazadi.

## Ishga tushirish (Windows, PowerShell)

```powershell
cd E:\project\esim-bot
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
notepad .env        # BOT_TOKEN, ADMIN_IDS, karta ma'lumotlarini yozing
python main.py
```

- **BOT_TOKEN**: @BotFather → /mybots → bot → API Token
- **ADMIN_IDS**: o'zingizning Telegram ID'ingiz (@userinfobot ga /start yozing)

## Mini App (do'kon oynasi)

Mini App bot bilan bitta dasturda ishlaydi (`python main.py` 8080-portda veb-server ham ochadi). Telegram faqat **HTTPS** manzilni qabul qiladi, shuning uchun kompyuteringizni internetga Cloudflare tunnel orqali chiqaramiz (bepul):

```powershell
winget install Cloudflare.cloudflared
cloudflared tunnel --url http://localhost:8080
```
Chiqqan `https://....trycloudflare.com` manzilni `.env` dagi `WEBAPP_URL` ga yozing va botni qayta ishga tushiring. Shunda botda chap pastda **eSIM** tugmasi, /start ostida esa «🛍 eSIM do'konini ochish» tugmasi paydo bo'ladi.

Diqqat: bepul tunnel manzili har safar o'zgaradi. Doimiy ishlash uchun keyin serverga (VPS + domen) ko'chiramiz, o'shanda `WEBAPP_URL` bir marta yoziladi.

Mini App'da: davlat qidirish, paketlar, Click/Payme yoki karta orqali to'lov, buyurtmalar holati, eSIM yo'riqnomasi. Karta to'lovida karta raqami chatga keladi va chek o'sha yerda qabul qilinadi.

## Mini App admin paneli (⚙️ Admin)

Faqat `ADMIN_IDS` dagi odamlarga ko'rinadi:
- **📊 Hisobot** — bugungi/jami tushum, sotuvlar, kutilayotgan buyurtmalar, eng ko'p sotilgan davlatlar.
- **🧾 Buyurtma** — chekni ko'rish, «✅ To'lov keldi» / «❌ Rad etish»; to'langan buyurtmaga Trip.com'dan olingan QR rasmini yuklab «📤 Mijozga yuborish».
- **📦 Paket** — davlat va paket qo'shish, tahrirlash, yoqish/yashirish (tugmacha), o'chirish, ⭐ «Mashhur» bo'limiga chiqarish. Formada dollar kursini yozsangiz foyda avtomatik hisoblanadi.
- **💳 Karta** — mijozlarga ko'rsatiladigan karta raqami va egasi.

Mijoz tomoni: davlat qidirish, mintaqalar bo'yicha filtr, «Mashhur» davlatlar, o'zbek/rus tili, telefon eSIM'ni qo'llashini tekshirish, iPhone/Android o'rnatish yo'riqnomasi, savol-javoblar.

## 🤖 Trip.com'dan avtomatik sotib olish

Bot sizning Trip.com akkauntingiz orqali eSIM'ni o'zi sotib oladi (API kerak emas — brauzer robot).

**Bir martalik sozlash:**
```powershell
pip install -r requirements.txt
playwright install chromium
```
1. Botni ishga tushiring va Telegram'da `/trip_login` yuboring — kompyuteringizda Trip.com oynasi ochiladi. Akkauntingizga kiring. Kontakt ma'lumotlari va karta Trip.com'da saqlangan bo'lsin, valyuta **USD** bo'lsin.
2. Mini App → ⚙️ Admin → 📦 Paket → paketni tahrirlang → **«Trip.com havola»**: Trip.com'da shu paketni (kun + GB) tanlab «Book now» bosing, ochilgan sahifa havolasini qo'ying. **Tannarx $** ni ham yozing (narx himoyasi uchun).
3. Sinov: `/trip_test PAKET_ID` — bot sahifani ochib narxni o'qiydi, skrinshot yuboradi. **Hech narsa sotib olinmaydi.**

**Har buyurtmada:**
1. To'lov tasdiqlanadi (karta cheki yoki Click/Payme).
2. Bot Trip.com'da paketni ochadi va sizga skrinshot + narx + «🛒 Sotib ol» tugmasini yuboradi.
3. Bossangiz — bot to'laydi, buyurtma raqamini oladi, eSIM ma'lumotidan QR yasab mijozga yuboradi.

**Himoyalar:** Trip.com narxi tannarxdan 30% (+$1) qimmat bo'lsa sotib olmaydi; kuniga ko'pi bilan 20 ta xarid; bitta buyurtma uchun hech qachon ikki marta «Pay» bosilmaydi; har qadam skrinshoti `trip_logs/` papkasida. Biror narsa noto'g'ri bo'lsa bot to'xtaydi va Telegram'da yozadi — o'shanda QR'ni Mini App orqali qo'lda yuborasiz.

Sozlamalar (`.env`): `TRIP_AUTOBUY=0` — o'chirish; `TRIP_DAILY_LIMIT=20`; `TRIP_PRICE_TOLERANCE=1.3`.
Qayta boshlash: `/trip_buy BUYURTMA_ID` yoki Mini App'dagi «🤖 Trip.com'dan avto-sotib olish».

## Birinchi paketlarni qo'shish (chat orqali ham ishlaydi)

Botga (admin sifatida) yozing:

```
/add Turkiya;🇹🇷;10;30;150000;12.5
Turkiya;🇹🇷;20;30;230000;19
BAA;🇦🇪;5;7;99000;8
```
Format: `Davlat;Bayroq;GB;Kun;Narx_so'm;Trip.com_tannarx_$`. Cheksiz internet uchun GB = 0.

## Kundalik ish

1. Mijoz to'laydi:
   - **Karta orqali** — chek sizga keladi, «✅ To'lov tasdiqlandi» ni bosasiz.
   - **Click/Payme orqali** — to'lov avtomatik tasdiqlanadi.
2. Bot qaysi paketni sotib olish kerakligini yozadi. Siz Trip.com'dan sotib olasiz.
3. «📤 QR yuborish» ni bosib, QR rasmini (yoki `LPA:1$...` kodini) yuborasiz.
4. Mijoz QR kodni va o'rnatish yo'riqnomasini oladi.

Admin buyruqlari: `/admin`, `/add`, `/off ID`, `/on ID`, `/price ID narx`, `/reply USER_ID matn`, `/cancel`.

## Click / Payme ulash (ixtiyoriy)

@BotFather → bot → Payments → Click yoki Payme ni tanlang → merchant shartnomasi orqali token oling → `.env` dagi `PAYMENT_PROVIDER_TOKEN` ga yozing. Token bo'lmasa, faqat karta orqali to'lov ishlaydi.

## 2-bosqich (keyin)

Trip.com o'rniga ulgurji eSIM API (eSIM.tech, eSIM Access, Airalo Partners) ulanadi. Shunda «QR yuborish» qadami avtomatik bo'ladi.

## Muhim

- Bot kompyuter yoqiq va `python main.py` ishlab turgan paytdagina ishlaydi. 24/7 ishlashi uchun keyinroq serverga (VPS) qo'yamiz.
- `.env` va `esim.db` fayllarini hech kimga bermang.
