/* Booking eSIM — aqlli davlat qidiruvi.
   - 10 tildagi nomlar (Intl), o'zbekcha/ruscha ro'yxat, mashhur shahar va kurortlar (Dubay -> BAA, Bali -> Indoneziya)
   - kirill -> lotin (Турция = turtsiya ~ turkiya), apostrof va diakritikasiz (O'zbekiston = Ozbekiston = Uzbekiston)
   - imlo xatolariga chidamli (Tailad, Turkiy, Yaponya) */
(function () {
  const CYR = {а:'a',б:'b',в:'v',г:'g',ғ:'g',д:'d',е:'e',ё:'yo',ж:'j',з:'z',и:'i',й:'y',к:'k',қ:'q',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',
    с:'s',т:'t',у:'u',ў:'o',ф:'f',х:'x',ҳ:'h',ц:'ts',ч:'ch',ш:'sh',щ:'sh',ъ:'',ь:'',ы:'i',э:'e',ю:'yu',я:'ya',і:'i',ї:'i',є:'e',ґ:'g'};
  // asosiy normallashtirish: kichik harf, diakritika va apostroflarsiz, kirill -> lotin
  function norm(s) {
    s = String(s || '').toLowerCase().normalize('NFD').replace(/[̀-ͯ]/g, '');
    s = s.replace(/[ʻʼ'`’‘´]/g, '').replace(/[а-яёўқғҳіїєґ]/g, ch => CYR[ch] ?? ch);
    return s.replace(/[^\p{L}\p{N}]+/gu, ' ').trim();
  }
  // tovush jihatidan yaqin yozilishlarni birlashtirish (x/kh/h, ch/c, w/v, q/k, y/i ...)
  function sound(s) {
    return s.replace(/kh/g, 'x').replace(/h/g, 'x').replace(/sh/g, 's').replace(/ch/g, 'c').replace(/ts/g, 'c')
      .replace(/w/g, 'v').replace(/q/g, 'k').replace(/ph/g, 'f').replace(/j/g, 'dz').replace(/yo|yu|ya/g, m => m[1])
      .replace(/y/g, 'i').replace(/(.)\1+/g, '$1');
  }
  // Damerau-Levenshtein (qisqa so'zlar uchun yetarli)
  function dist(a, b, max) {
    if (Math.abs(a.length - b.length) > max) return max + 1;
    const d = Array.from({length: a.length + 1}, (_, i) => [i]);
    for (let j = 1; j <= b.length; j++) d[0][j] = j;
    for (let i = 1; i <= a.length; i++) {
      let rowMin = Infinity;
      for (let j = 1; j <= b.length; j++) {
        const c = a[i - 1] === b[j - 1] ? 0 : 1;
        d[i][j] = Math.min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + c);
        if (i > 1 && j > 1 && a[i - 1] === b[j - 2] && a[i - 2] === b[j - 1]) d[i][j] = Math.min(d[i][j], d[i - 2][j - 2] + 1);
        rowMin = Math.min(rowMin, d[i][j]);
      }
      if (rowMin > max) return max + 1;
    }
    return d[a.length][b.length];
  }

  // mashhur shaharlar, kurortlar va qisqa nomlar -> ISO
  const ALIAS = {
    AE: 'dubai dubay dubay abu dhabi abu dabi sharjah sharja emirates emirat oae uae baa amirliklar амирлики дубай эмираты',
    TR: 'istanbul antalya alanya bodrum kemer izmir ankara turkey turtsiya turkiye турция стамбул анталия',
    ID: 'bali jakarta lombok indonesia indonezia бали',
    TH: 'phuket pxuket puket bangkok pattaya samui krabi tailand thailand пхукет паттайя бангкок',
    EG: 'sharm sharm el sheikh hurghada xurgada cairo qohira misr egypt egipet египет хургада шарм',
    SA: 'mecca makka makkah madina medina umra umrah hajj haj jeddah jidda riyadh saudia saudiya мекка медина умра хадж',
    US: 'usa america amerika aqsh shtatlar new york nyu york los angeles miami сша америка штаты',
    GB: 'uk england angliya britain britaniya london scotland англия лондон британия',
    KR: 'korea koreya seoul seul busan корея сеул',
    JP: 'tokyo tokio osaka kyoto япония токио',
    CN: 'china xitoy kitay beijing pekin shanghai shanxay guangzhou urumqi китай пекин шанхай',
    HK: 'hong kong gonkong гонконг', MO: 'macau makao макао', TW: 'taiwan tayvan тайвань',
    FR: 'paris parij france fransiya франция париж', IT: 'rome rim roma milan venice italia италия рим',
    ES: 'madrid barcelona barselona spain испания', DE: 'berlin munich myunxen germany олмония германия',
    GE: 'georgia gruziya tbilisi batumi грузия тбилиси батуми', AZ: 'baku boku azerbaijan азербайджан баку',
    KZ: 'almaty olmaota astana kazakhstan казахстан алматы', KG: 'bishkek issyk kul issiqkol кыргызстан бишкек',
    MY: 'kuala lumpur langkawi malaysia малайзия', SG: 'singapore singapur сингапур', VN: 'vietnam hanoi nha trang danang вьетнам',
    IN: 'india goa delhi mumbai индия гоа', LK: 'sri lanka shri lanka шри ланка', MV: 'maldives maldiv мальдивы',
    QA: 'doha qatar katar катар доха', OM: 'muscat oman оман', IL: 'israel isroil tel aviv jerusalem quddus израиль',
    CY: 'cyprus kipr кипр', GR: 'athens afina greece gretsiya греция', ME: 'montenegro chernogoriya черногория',
    CZ: 'prague praga chexiya czech чехия', AU: 'australia avstraliya sydney сидней', CA: 'canada kanada toronto канада',
    UZ: 'uzbekistan ozbekiston uzbekiston toshkent tashkent samarkand samarqand buxoro bukhara узбекистан ташкент',
    PH: 'philippines filippin manila boracay филиппины', KH: 'cambodia kambodja камбоджа', NP: 'nepal kathmandu непал',
  };
  // mintaqaviy eSIM'lar uchun qo'shimcha so'zlar
  const REGION_ALIAS = [
    [/Yevropa/i, 'europe evropa yevropa schengen shengen shengen zona европа шенген евросоюз'],
    [/^Osiyo/i, 'asia aziya osiyo азия'],
    [/Janubi-Sharqiy/i, 'southeast asia jugo vostochnaya aziya юго восточная азия'],
    [/Yaqin Sharq/i, 'middle east gulf arab blijniy vostok arab davlatlari ближний восток персидский залив'],
    [/Global/i, 'global world dunyo butun dunyo all countries mir весь мир глобальный'],
  ];
  const LANGS = ['uz', 'en', 'ru', 'uk', 'tr', 'es', 'pt', 'id', 'hi', 'ar', 'de', 'fr'];
  const isoTokCache = {};
  function isoTokens(iso) {
    if (isoTokCache[iso]) return isoTokCache[iso];
    const names = [];
    LANGS.forEach(l => { const n = regionName(l, iso); if (n && n !== iso) names.push(n); });
    const p = PRESET_BY_ISO[iso]; if (p) names.push(p.uz, p.ru);
    if (ALIAS[iso]) names.push(ALIAS[iso]);
    names.push(iso);
    return (isoTokCache[iso] = tokens(names));
  }
  function tokens(names) {
    const out = new Set();
    names.forEach(n => {
      const s = norm(n); if (!s) return;
      out.add(s);                                     // to'liq ibora ("janubiy koreya")
      s.split(' ').forEach(w => w.length > 1 && out.add(w));
    });
    return [...out].map(t => ({t, s: sound(t)}));
  }

  // bitta so'z uchun ball: to'liq mos 100, boshlanishi 90, ichida 60, tovushi mos 55, imlo xatosi 40..30
  function wordScore(q, qs, toks) {
    let best = 0;
    const max = q.length >= 7 ? 2 : q.length >= 4 ? 1 : 0;
    for (const {t, s} of toks) {
      if (t === q) return 100;
      if (t.startsWith(q)) best = Math.max(best, 90);
      else if (q.length >= 4 && t.includes(q)) best = Math.max(best, 60);
      else if (q.length >= 3 && (s === qs || s.startsWith(qs))) best = Math.max(best, 55);
      else if (max) {
        const d = Math.min(dist(q, t.slice(0, q.length), max), dist(q, t, max), dist(qs, s.slice(0, qs.length), max));
        if (d <= max) best = Math.max(best, 40 - d * 5);
      }
    }
    return best;
  }
  function score(query, toks) {
    const words = norm(query).split(' ').filter(Boolean);
    if (!words.length) return 0;
    let total = 0;
    for (const w of words) {
      const sc = wordScore(w, sound(w), toks);
      if (!sc) return 0;            // har bir so'z biror nomga mos kelishi kerak
      total += sc;
    }
    return total / words.length;
  }

  // davlat kartochkasi uchun indeks (katalog o'zgarganda yangilanadi)
  const idx = new WeakMap();
  function countryTokens(c) {
    let t = idx.get(c);
    if (t) return t;
    const iso = isoOf(c.flag);
    const names = [c.country, countryName(c.country, c.flag), RU_NAME[c.country.toLowerCase()] || ''];
    const rg = typeof REGIONAL_NAMES !== 'undefined' && REGIONAL_NAMES[c.country];
    if (rg) names.push(...Object.values(rg));
    for (const [re, words] of REGION_ALIAS) if (re.test(c.country)) names.push(words);
    if (rg) {
      const t2 = tokens(names);
      idx.set(c, t2); return t2;
    }
    t = [...tokens(names), ...(iso ? isoTokens(iso) : [])];
    idx.set(c, t);
    return t;
  }

  /* qidiruv: [{c, score, via}] — via: mintaqaviy eSIM qaysi davlat orqali topilgani (ISO) */
  window.searchCountries = function (list, query) {
    const out = [];
    for (const c of list) {
      let sc = score(query, countryTokens(c)), via = '';
      if (sc < 50 && c.covers && c.covers.length) {
        let best = 0;
        for (const iso of c.covers) {
          const s2 = score(query, isoTokens(iso));
          if (s2 > best) { best = s2; via = iso; }
        }
        if (best >= 50 && best * 0.6 > sc) sc = best * 0.6; else via = '';
      }
      if (sc > 0) out.push({c, score: sc, via});
    }
    out.sort((a, b) => b.score - a.score || (!!a.c.regional - !!b.c.regional) || (b.c.popular - a.c.popular));
    // eng yaxshi natijadan ancha past (tasodifiy o'xshash) natijalarni tashlaymiz
    const top = out.length ? out[0].score : 0;
    // aniq moslik bo'lsa — kuchsizlarini, faqat imlo xatosi bilan topilgan bo'lsa — eng yaqinlarini qoldiramiz
    return out.filter(r => r.score >= (top >= 50 ? top * 0.55 : top - 1));
  };
  window.searchNorm = norm;
})();
