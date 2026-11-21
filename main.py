"""Booking eSIM bot + Mini App — ishga tushirish: python main.py"""
import asyncio
import logging
import os
from pathlib import Path

from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand, MenuButtonWebApp, MenuButtonCommands, WebAppInfo

import db
import i18n
from config import BOT_TOKEN, WEB_PORT, WEBAPP_URL
from handlers import admin, user
from web import build_app


async def setup_profile(bot: Bot):
    """Bot nomi, tavsifi va buyruqlari — har bir til uchun (Telegram foydalanuvchi tiliga qarab ko'rsatadi).
    Rasmni @BotFather -> /setuserpic orqali qo'yasiz.
    Telegram bu so'rovlarni cheklaydi, shuning uchun faqat matn o'zgarganda yuboriladi."""
    import hashlib
    import json
    stamp = Path(__file__).with_name("profile.stamp")
    digest = hashlib.md5(json.dumps([[i18n.t(l, k) for k in ("cmd_start", "cmd_lang", "short_description", "description")]
                                     for l in i18n.LANGS]).encode()).hexdigest()
    if stamp.exists() and stamp.read_text().strip() == digest:
        return
    ok = True
    try:
        await bot.set_my_name(name="Booking eSIM")
    except Exception as e:
        logging.warning("Bot nomini o'rnatib bo'lmadi: %s", e)
    for lang in [None, *i18n.LANGS]:
        code = lang or i18n.DEFAULT  # tilsiz (standart) variant — asosiy til
        kw = {"language_code": lang} if lang else {}
        for call in (
            bot.set_my_commands([BotCommand(command="start", description=i18n.t(code, "cmd_start")),
                                 BotCommand(command="lang", description=i18n.t(code, "cmd_lang")),
                                 BotCommand(command="help", description=i18n.get(code, "app", "nav_help"))], **kw),
            bot.set_my_short_description(short_description=i18n.t(code, "short_description"), **kw),
            bot.set_my_description(description=i18n.t(code, "description"), **kw),
        ):
            try:
                await call
            except Exception as e:
                ok = False
                logging.warning("Bot profilini yangilab bo'lmadi (%s): %s", lang, e)
            await asyncio.sleep(0.4)
    if ok:
        stamp.write_text(digest)
        logging.info("Bot nomi/tavsifi %s tilda yangilandi", len(i18n.LANGS))


async def refresh_user_menus(bot: Bot):
    """Har bir foydalanuvchining chap pastdagi "eSIM" tugmasi o'z tilida, lekin eski tunnel manzili bilan qolib ketadi.
    Cloudflare manzili har ishga tushganda o'zgargani uchun ularni yangi manzilga yangilaymiz."""
    from handlers.user import apply_lang_ui
    rows = await db._fetchall("SELECT id, lang FROM users WHERE lang IS NOT NULL AND lang != ''")
    for r in rows:
        await apply_lang_ui(bot, r["id"], r["lang"])
        await asyncio.sleep(0.05)  # Telegram limitiga tushmaslik uchun
    if rows:
        logging.info("%s ta foydalanuvchining Mini App tugmasi yangi manzilga yangilandi", len(rows))


async def main():
    # start.ps1 keyingi safar faqat shu nusxani yopishi uchun
    Path(__file__).with_name("bot.pid").write_text(str(os.getpid()))
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
                        handlers=[logging.StreamHandler(),
                                  logging.FileHandler(Path(__file__).with_name("bot.log"), encoding="utf-8")])
    await db.init_db()
    import support
    await support.init()
    i18n.build_webapp_js()
    seed = Path(__file__).with_name("seed_packages.json")
    if seed.exists():
        n = await db.import_seed(seed)
        seed.replace(seed.with_name("seed_packages.imported.json"))
        logging.info("Boshlang'ich paketlar qo'shildi: %s ta", n)

    bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(admin.router)  # admin birinchi: admin xabarlari mijoz handlerlariga tushmasin
    dp.include_router(user.router)

    # Mini App veb-serveri (bot bilan bir jarayonda)
    runner = web.AppRunner(build_app(bot, dp))
    await runner.setup()
    await web.TCPSite(runner, "0.0.0.0", WEB_PORT).start()
    logging.info("Mini App serveri: http://localhost:%s", WEB_PORT)

    asyncio.create_task(setup_profile(bot))
    import trip_import
    await trip_import.ensure_formula()
    if WEBAPP_URL:
        await bot.set_chat_menu_button(menu_button=MenuButtonWebApp(text="eSIM", web_app=WebAppInfo(url=WEBAPP_URL)))
        logging.info("Mini App tugmasi: %s", WEBAPP_URL)
        asyncio.create_task(refresh_user_menus(bot))
    else:
        await bot.set_chat_menu_button(menu_button=MenuButtonCommands())
        logging.warning("WEBAPP_URL bo'sh — Mini App tugmasi o'rnatilmadi (bot chat orqali ishlaydi)")
    import services
    asyncio.create_task(services.pending_watch(bot))  # to'lanmagan buyurtmalar: eslatma / bekor qilish
    asyncio.create_task(services.expiry_watch(bot))   # eSIM muddati tugashiga yaqin "Yana olish" eslatmasi
    import autoupdate
    asyncio.create_task(autoupdate.loop(bot))         # har kecha narxlarni Trip.com'dan yangilash
    asyncio.create_task(services.backup_loop(bot))    # har kuni 03:00 da bazaning zaxira nusxasi adminlarga

    # run_import.flag bo'lsa — Trip.com'dan to'liq import avtomatik boshlanadi (bir marta)
    flag = Path(__file__).with_name("run_import.flag")
    if flag.exists():
        import json
        import trip_import
        try:
            opts = json.loads(flag.read_text(encoding="utf-8") or "{}")
        except ValueError:
            opts = {}
        flag.replace(flag.with_name("run_import.started"))  # Windows: bor bo'lsa ustidan yozadi

        async def _delayed():
            await asyncio.sleep(15)
            await trip_import.run_import(bot, markup=float(opts["markup"]) if opts.get("markup") else None,
                                         rate=float(opts["rate"]) if opts.get("rate") else None)
        asyncio.create_task(_delayed())
        logging.info("Trip.com import 15 soniyadan keyin boshlanadi")

    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot ishga tushdi")
    try:
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()


if __name__ == "__main__":
    asyncio.run(main())
