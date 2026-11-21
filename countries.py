"""Davlatlar ro'yxati: o'zbekcha/ruscha nom, Trip.com'dagi inglizcha nomlar, ISO kod, mintaqa.
Import shu ro'yxat bo'yicha Trip.com'dan eSIM qidiradi. Yangi davlat qo'shish uchun qator qo'shing."""

# (uz, ru, [Trip.com'dagi inglizcha nomlar], iso, region)
COUNTRIES = [
    # --- Osiyo ---
    ("Xitoy", "Китай", ["Mainland China", "China"], "cn", "asia"),
    ("Yaponiya", "Япония", ["Japan"], "jp", "asia"),
    ("Janubiy Koreya", "Южная Корея", ["South Korea", "Korea"], "kr", "asia"),
    ("Tailand", "Таиланд", ["Thailand"], "th", "asia"),
    ("Vyetnam", "Вьетнам", ["Vietnam"], "vn", "asia"),
    ("Malayziya", "Малайзия", ["Malaysia"], "my", "asia"),
    ("Indoneziya (Bali)", "Индонезия (Бали)", ["Indonesia", "Bali"], "id", "asia"),
    ("Singapur", "Сингапур", ["Singapore"], "sg", "asia"),
    ("Filippin", "Филиппины", ["Philippines"], "ph", "asia"),
    ("Hindiston", "Индия", ["India"], "in", "asia"),
    ("Shri-Lanka", "Шри-Ланка", ["Sri Lanka"], "lk", "asia"),
    ("Maldiv orollari", "Мальдивы", ["Maldives"], "mv", "asia"),
    ("Nepal", "Непал", ["Nepal"], "np", "asia"),
    ("Kambodja", "Камбоджа", ["Cambodia"], "kh", "asia"),
    ("Laos", "Лаос", ["Laos"], "la", "asia"),
    ("Tayvan", "Тайвань", ["Taiwan"], "tw", "asia"),
    ("Gonkong", "Гонконг", ["Hong Kong"], "hk", "asia"),
    ("Makao", "Макао", ["Macau", "Macao"], "mo", "asia"),
    ("Mo'g'uliston", "Монголия", ["Mongolia"], "mn", "asia"),
    ("O'zbekiston", "Узбекистан", ["Uzbekistan"], "uz", "asia"),
    ("Qozog'iston", "Казахстан", ["Kazakhstan"], "kz", "asia"),
    ("Qirg'iziston", "Киргизия", ["Kyrgyzstan"], "kg", "asia"),
    ("Tojikiston", "Таджикистан", ["Tajikistan"], "tj", "asia"),
    ("Ozarbayjon", "Азербайджан", ["Azerbaijan"], "az", "asia"),
    ("Armaniston", "Армения", ["Armenia"], "am", "asia"),
    ("Pokiston", "Пакистан", ["Pakistan"], "pk", "asia"),
    ("Bangladesh", "Бангладеш", ["Bangladesh"], "bd", "asia"),
    # --- Yaqin Sharq ---
    ("BAA (Dubay)", "ОАЭ (Дубай)", ["United Arab Emirates", "UAE", "Dubai"], "ae", "mideast"),
    ("Saudiya Arabistoni", "Саудовская Аравия", ["Saudi Arabia"], "sa", "mideast"),
    ("Qatar", "Катар", ["Qatar"], "qa", "mideast"),
    ("Ummon", "Оман", ["Oman"], "om", "mideast"),
    ("Quvayt", "Кувейт", ["Kuwait"], "kw", "mideast"),
    ("Bahrayn", "Бахрейн", ["Bahrain"], "bh", "mideast"),
    ("Iordaniya", "Иордания", ["Jordan"], "jo", "mideast"),
    ("Isroil", "Израиль", ["Israel"], "il", "mideast"),
    # --- Yevropa ---
    ("Turkiya", "Турция", ["Turkey", "Türkiye", "Turkiye"], "tr", "europe"),
    ("Gruziya", "Грузия", ["Georgia"], "ge", "europe"),
    ("Rossiya", "Россия", ["Russia"], "ru", "europe"),
    ("Buyuk Britaniya", "Великобритания", ["United Kingdom", "UK"], "gb", "europe"),
    ("Germaniya", "Германия", ["Germany"], "de", "europe"),
    ("Fransiya", "Франция", ["France"], "fr", "europe"),
    ("Italiya", "Италия", ["Italy"], "it", "europe"),
    ("Ispaniya", "Испания", ["Spain"], "es", "europe"),
    ("Portugaliya", "Португалия", ["Portugal"], "pt", "europe"),
    ("Niderlandiya", "Нидерланды", ["Netherlands"], "nl", "europe"),
    ("Belgiya", "Бельгия", ["Belgium"], "be", "europe"),
    ("Shveytsariya", "Швейцария", ["Switzerland"], "ch", "europe"),
    ("Avstriya", "Австрия", ["Austria"], "at", "europe"),
    ("Chexiya", "Чехия", ["Czech Republic", "Czechia", "Czech"], "cz", "europe"),
    ("Polsha", "Польша", ["Poland"], "pl", "europe"),
    ("Vengriya", "Венгрия", ["Hungary"], "hu", "europe"),
    ("Gretsiya", "Греция", ["Greece"], "gr", "europe"),
    ("Xorvatiya", "Хорватия", ["Croatia"], "hr", "europe"),
    ("Serbiya", "Сербия", ["Serbia"], "rs", "europe"),
    ("Chernogoriya", "Черногория", ["Montenegro"], "me", "europe"),
    ("Ruminiya", "Румыния", ["Romania"], "ro", "europe"),
    ("Bolgariya", "Болгария", ["Bulgaria"], "bg", "europe"),
    ("Latviya", "Латвия", ["Latvia"], "lv", "europe"),
    ("Litva", "Литва", ["Lithuania"], "lt", "europe"),
    ("Estoniya", "Эстония", ["Estonia"], "ee", "europe"),
    ("Finlyandiya", "Финляндия", ["Finland"], "fi", "europe"),
    ("Shvetsiya", "Швеция", ["Sweden"], "se", "europe"),
    ("Norvegiya", "Норвегия", ["Norway"], "no", "europe"),
    ("Daniya", "Дания", ["Denmark"], "dk", "europe"),
    ("Irlandiya", "Ирландия", ["Ireland"], "ie", "europe"),
    ("Islandiya", "Исландия", ["Iceland"], "is", "europe"),
    ("Ukraina", "Украина", ["Ukraine"], "ua", "europe"),
    ("Moldova", "Молдова", ["Moldova"], "md", "europe"),
    ("Kipr", "Кипр", ["Cyprus"], "cy", "europe"),
    ("Malta", "Мальта", ["Malta"], "mt", "europe"),
    ("Albaniya", "Албания", ["Albania"], "al", "europe"),
    ("Slovakiya", "Словакия", ["Slovakia"], "sk", "europe"),
    ("Sloveniya", "Словения", ["Slovenia"], "si", "europe"),
    ("Lyuksemburg", "Люксембург", ["Luxembourg"], "lu", "europe"),
    # --- Amerika ---
    ("AQSh", "США", ["United States", "USA"], "us", "america"),
    ("Kanada", "Канада", ["Canada"], "ca", "america"),
    ("Meksika", "Мексика", ["Mexico"], "mx", "america"),
    ("Braziliya", "Бразилия", ["Brazil"], "br", "america"),
    ("Argentina", "Аргентина", ["Argentina"], "ar", "america"),
    ("Chili", "Чили", ["Chile"], "cl", "america"),
    ("Peru", "Перу", ["Peru"], "pe", "america"),
    ("Kolumbiya", "Колумбия", ["Colombia"], "co", "america"),
    ("Dominikan Respublikasi", "Доминикана", ["Dominican Republic"], "do", "america"),
    # --- Afrika ---
    ("Misr", "Египет", ["Egypt"], "eg", "africa"),
    ("Marokash", "Марокко", ["Morocco"], "ma", "africa"),
    ("Tunis", "Тунис", ["Tunisia"], "tn", "africa"),
    ("Janubiy Afrika", "ЮАР", ["South Africa"], "za", "africa"),
    ("Keniya", "Кения", ["Kenya"], "ke", "africa"),
    ("Tanzaniya (Zanzibar)", "Танзания (Занзибар)", ["Tanzania", "Zanzibar"], "tz", "africa"),
    ("Seyshel orollari", "Сейшелы", ["Seychelles"], "sc", "africa"),
    ("Mavrikiy", "Маврикий", ["Mauritius"], "mu", "africa"),
    # --- Okeaniya ---
    ("Avstraliya", "Австралия", ["Australia"], "au", "asia"),
    ("Yangi Zelandiya", "Новая Зеландия", ["New Zealand"], "nz", "asia"),
]


def flag(iso: str) -> str:
    return "".join(chr(0x1F1E6 + ord(c) - 97) for c in iso.lower())


def slug(en: str) -> str:
    return "".join(ch for ch in en.lower() if ch.isalnum())


def as_dicts():
    return [{"uz": uz, "ru": ru, "en": en, "iso": iso, "flag": flag(iso), "region": region}
            for uz, ru, en, iso, region in COUNTRIES]


# Trip.com'da alohida eSIM bo'lmagan davlatlar uchun ko'p davlatli (mintaqaviy) eSIM'lar.
# product_ids — ma'lum yaxshi mahsulotlar; list_pages — qo'shimcha qidirish sahifalari; title_re — nom shabloni.
REGIONAL = [
    {"key": "europe", "iso": "eu", "flag": "🇪🇺", "region": "europe",
     "uz": "Yevropa (30+ davlat)", "ru": "Европа (30+ стран)",
     "names": {"en": "Europe (30+ countries)", "uk": "Європа (30+ країн)", "tr": "Avrupa (30+ ülke)",
               "es": "Europa (30+ países)", "pt": "Europa (30+ países)", "id": "Eropa (30+ negara)",
               "hi": "यूरोप (30+ देश)", "ar": "أوروبا (+30 دولة)"},
     "product_ids": ["40019044", "57490720"], "list_pages": ["poland", "greece"], "title_re": r"^Europe\b"},
    {"key": "global", "iso": "global", "flag": "🌍", "region": "global",
     "uz": "Global (70+ davlat)", "ru": "Весь мир (70+ стран)",
     "names": {"en": "Global (70+ countries)", "uk": "Весь світ (70+ країн)", "tr": "Global (70+ ülke)",
               "es": "Global (70+ países)", "pt": "Global (70+ países)", "id": "Global (70+ negara)",
               "hi": "ग्लोबल (70+ देश)", "ar": "عالمي (+70 دولة)"},
     "product_ids": [], "list_pages": ["greece", "jordan", "poland"], "title_re": r"^Global\b"},
    {"key": "asia", "iso": "asia", "flag": "🌏", "region": "asia",
     "uz": "Osiyo (10+ davlat)", "ru": "Азия (10+ стран)",
     "names": {"en": "Asia (10+ countries)", "uk": "Азія (10+ країн)", "tr": "Asya (10+ ülke)",
               "es": "Asia (10+ países)", "pt": "Ásia (10+ países)", "id": "Asia (10+ negara)",
               "hi": "एशिया (10+ देश)", "ar": "آسيا (+10 دول)"},
     "product_ids": [], "list_pages": ["indonesia", "thailand", "japan"],
     "title_re": r"^(Asia\b|\d+G/\d+G eSIM in \d+ Asian)(?!.*Southeast)"},
    {"key": "sea", "iso": "sea", "flag": "🌏", "region": "asia",
     "uz": "Janubi-Sharqiy Osiyo", "ru": "Юго-Восточная Азия",
     "names": {"en": "Southeast Asia", "uk": "Південно-Східна Азія", "tr": "Güneydoğu Asya",
               "es": "Sudeste Asiático", "pt": "Sudeste Asiático", "id": "Asia Tenggara",
               "hi": "दक्षिण-पूर्व एशिया", "ar": "جنوب شرق آسيا"},
     "product_ids": [], "list_pages": ["indonesia", "thailand", "malaysia", "singapore"],
     "title_re": r"Southeast Asia",
     # nomida kamida 3 ta JSO davlati sanalgan bo'lsa ham mos ("Brunei/Malaysia/Singapore/Thailand/Indonesia")
     "title_any": ["Singapore", "Malaysia", "Thailand", "Indonesia", "Brunei", "Vietnam", "Philippines", "Cambodia"],
     "title_min": 3},
    {"key": "me", "iso": "me", "flag": "🌍", "region": "mideast",
     "uz": "Yaqin Sharq (ko'p davlat)", "ru": "Ближний Восток",
     "names": {"en": "Middle East", "uk": "Близький Схід", "tr": "Orta Doğu",
               "es": "Oriente Medio", "pt": "Oriente Médio", "id": "Timur Tengah",
               "hi": "मध्य पूर्व", "ar": "الشرق الأوسط"},
     "product_ids": [], "list_pages": ["unitedarabemirates", "saudiarabia", "qatar"],
     "title_re": r"Middle East|\bGCC\b|Gulf"},
]


def regional_dicts():
    return [{**r, "en": [], "regional": True} for r in REGIONAL]


def regional_by_name(name: str):
    return next((r for r in REGIONAL if r["uz"] == name), None)
