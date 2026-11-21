# Eski kompyuterni server qilish (Booking eSIM bot, 24/7)

Bot eski kompyuterda doim ishlaydi: Windows yonganda o'zi ishga tushadi,
yiqilsa qayta yoqiladi, tunnel o'lsa yangisi ochiladi, har kecha 03:00 da
baza nusxasi sizga Telegram orqali keladi.

## 1. Asosiy kompyuterda botni to'xtatish va papkani ko'chirish

1. Asosiy kompyuterdagi bot oynasini (start.bat) **yoping**. Ikkala kompyuterda bir vaqtda
   ishlamasin — bir xil token bilan ikkita bot to'qnashadi.
2. `E:\project\esim-bot` papkasini **butunligicha** fleshkaga ko'chiring
   (`.env`, `esim.db`, `trip_profile` papkasi ham bo'lsin — Trip.com'ga kirish shu yerda saqlangan).
3. Eski kompyuterda istalgan joyga qo'ying, masalan `C:\esim-bot`.
   Yo'lda ruscha harf yoki bo'sh joy bo'lmasin.

## 2. Eski kompyuterga dasturlarni o'rnatish

1. **Python 3.12**: python.org → Downloads → Windows.
   O'rnatishda **"Add python.exe to PATH"** belgisini albatta qo'ying.
2. **Cloudflared**: Start tugmasini o'ng bosing → "Terminal (Admin)" → yozing:
   ```
   winget install Cloudflare.cloudflared
   ```
3. Terminalni yopib qayta oching va tekshiring: `python --version` va `cloudflared --version`.

## 3. Server sozlamalari (bitta fayl)

Papkadagi **`server_setup.bat`** ni o'ng tugma bilan bosing → **"Run as administrator"**.
U quyidagilarni o'zi qiladi:
- uxlash va gibernatsiyani o'chiradi (ekran 10 daqiqada o'chadi, kompyuter esa ishlayveradi);
- Windows yangilanishi 08:00–02:00 orasida qayta yoqmaydigan qiladi;
- Windows'ga kirganda bot o'zi ishga tushadigan qiladi ("BookingEsimBot" vazifasi);
- botni darhol ishga tushiradi.

1–2 daqiqadan keyin botga /start yozib, Mini App ochilishini tekshiring.

## 4. Ikki ishni o'zingiz qilasiz

**a) Windows parolsiz o'zi kirsin** (svet o'chib yonganda bot o'zi ishga tushishi uchun):
1. Windows 11 bo'lsa: Sozlamalar → Hisoblar → Kirish parametrlari →
   "Faqat Windows Hello orqali kirish" ni **o'chiring**.
2. `Win + R` → `netplwiz` → Enter.
3. "Пользователи должны вводить имя пользователя и пароль" / "Users must enter a user name
   and password" belgisini olib tashlang → OK → parolingizni ikki marta yozing.

**b) Svet kelganda kompyuter o'zi yonsin (BIOS):**
1. Kompyuterni yoqayotganda `Del` yoki `F2` ni bosib turing (BIOS ochiladi).
2. "Power" yoki "Advanced" bo'limida **"Restore on AC Power Loss"** (yoki "AC Back",
   "After Power Failure") → **"Power On"**.
3. `F10` → Save & Exit.

Tekshirish: kompyuterni rozetkadan sug'urib, qayta tiqing. U o'zi yonib, Windows'ga kirib,
2–3 daqiqada bot ishlashi kerak.

## Kundalik foydalanish

| Nima | Qanday |
|---|---|
| Botni to'xtatish | `server_stop.bat` |
| Qayta yoqish | kompyuterni qayta yoqing (yoki `server_setup.bat` ni yana ishga tushiring) |
| Nima bo'layotganini ko'rish | `server.log` (server), `bot.log` (bot) fayllari |
| Zaxira nusxa hoziroq | botda `/backup` (admin) |
| Zaxiralar | har kecha 03:00 da Telegram'ga keladi, oxirgi 14 tasi `backups` papkasida |
| Kod yangilansa | yangi fayllarni papkaga ko'chiring → `server_stop.bat` → kompyuterni qayta yoqing |

**Bazani tiklash:** Telegram'dagi zaxira faylni yuklab oling → `server_stop.bat` →
faylni `esim.db` deb nomlab papkadagi eskisining o'rniga qo'ying → qayta yoqing.

**Maslahat:** kompyuter va internet routerini UPS'ga (650 VA yetadi) ulang, internetni
iloji bo'lsa kabel bilan ulang. Kompyuterni yopiq shkafga emas, havo aylanadigan joyga qo'ying.
