const ADMIN_VER = 47;   // admin.js o'zgarsa oshiriladi
/* Booking eSIM Mini App — mijoz qismi */
const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand();
const $ = s => document.querySelector(s);
const $$ = s => [...document.querySelectorAll(s)];
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const IN_TG = !!tg?.initData;
// har doim yorug' mavzu: Telegram tungi rejimda bo'lsa ham oq fon
try { tg?.setHeaderColor?.('#0001E7'); tg?.setBackgroundColor?.('#f2f3f5'); tg?.setBottomBarColor?.('#ffffff'); } catch (e) {}
try { tg?.disableVerticalSwipes?.(); } catch (e) {}
const SCROLLER = () => document.querySelector('main');
const scrollTop = (smooth) => SCROLLER().scrollTo({top: 0, behavior: smooth ? 'smooth' : 'auto'});

// Bayroq emojisi -> rasm (Windows bayroq emojilarini ko'rsatmaydi, harf chiqaradi)
function flagHtml(flag) {
  const cps = [...String(flag || '')].map(c => c.codePointAt(0));
  if (cps.length === 2 && cps.every(cp => cp >= 0x1F1E6 && cp <= 0x1F1FF)) {
    const code = cps.map(cp => String.fromCharCode(cp - 0x1F1E6 + 97)).join('');
    return `<img class="fl" src="/static/flags/${code}.webp" alt="${code.toUpperCase()}" loading="lazy" onerror="this.replaceWith(document.createTextNode('${esc(flag)}'))">`;
  }
  return esc(flag || '🌍');
}

// ---------------- tarjima (matnlar /static/i18n.js da, locales/*.json dan yaratiladi) ----------------
const SUPPORTED = I18N_LANGS.map(x => x[0]);
const pickLang = l => { l = String(l || '').toLowerCase().split(/[-_]/)[0]; return SUPPORTED.includes(l) ? l : ''; };
let LANG = pickLang(window.BOOT_LANG) || pickLang(new URLSearchParams(location.search).get('lang'));
try { LANG = LANG || pickLang(localStorage.getItem('lang')); } catch (e) {}
LANG = LANG || pickLang(tg?.initDataUnsafe?.user?.language_code) || I18N_DEFAULT;
const t = (k, vars = {}) => String(I18N[LANG]?.[k] ?? k).replace(/\{(\w+)\}/g, (_, v) => vars[v] ?? '');
const L = k => I18N[LANG]?.[k];
// boshqa til fayli faqat kerak bo'lganda yuklanadi
const loadLang = l => I18N[l] ? Promise.resolve() : new Promise((ok, no) => {
  const s = document.createElement('script'); s.src = `/static/i18n/${l}.js?v=${I18N_VER}`; s.onload = ok; s.onerror = no; document.head.append(s);
});
if (!I18N[LANG]) LANG = Object.keys(I18N)[0] || LANG;
// davlat nomi: uz — bazadagi nom, ru — tayyor ro'yxat, qolganlari — brauzerning o'z tarjimasi (Intl)
const isoOf = flag => { const cps = [...String(flag || '')].map(c => c.codePointAt(0));
  return cps.length === 2 && cps.every(cp => cp >= 0x1F1E6 && cp <= 0x1F1FF) ? cps.map(cp => String.fromCharCode(cp - 0x1F1E6 + 65)).join('') : ''; };
const _dn = {};
const regionName = (lang, iso) => { try { _dn[lang] ??= new Intl.DisplayNames([lang], {type: 'region'}); return _dn[lang].of(iso); } catch (e) { return ''; } };
const FLAG_OF = {};
function countryName(name, flag) {
  flag = flag || FLAG_OF[name];
  if (LANG === 'uz') return name;
  const rg = typeof REGIONAL_NAMES !== 'undefined' && REGIONAL_NAMES[name];
  if (rg) return rg[LANG] || rg.en || name;
  if (LANG === 'ru' && RU_NAME[name.toLowerCase()]) return RU_NAME[name.toLowerCase()];
  const iso = isoOf(flag);
  const n = iso && regionName(LANG, iso);
  if (n && n !== iso) { const extra = name.match(/\(.+\)$/); return extra ? `${n} ${extra[0]}` : n; }
  return (iso && regionName('en', iso)) || name;
}
// ISO -> o'zbekcha/ruscha nom (brauzerlarda o'zbek tili bo'lmasligi mumkin, shuning uchun o'z ro'yxatimizdan)
const PRESET_BY_ISO = {};
COUNTRY_PRESETS.forEach(p => { const iso = isoOf(p.flag); if (iso) PRESET_BY_ISO[iso] = p; });
function isoName(iso) {
  const p = PRESET_BY_ISO[iso];
  if (LANG === 'uz' && p) return p.uz.replace(/\s*\(.*\)$/, '');
  if (LANG === 'ru' && p) return p.ru;
  const n = regionName(LANG, iso);
  return (n && n !== iso) ? n : (regionName('en', iso) || iso);
}
const isoNames = iso => [isoName(iso), regionName('en', iso), PRESET_BY_ISO[iso]?.uz, PRESET_BY_ISO[iso]?.ru, regionName('ru', iso)]
  .filter(Boolean).join(' ').toLowerCase();
const searchNames = c => [c.country, countryName(c.country, c.flag), RU_NAME[c.country.toLowerCase()] || '',
  isoOf(c.flag) ? regionName('en', isoOf(c.flag)) : ''].join(' ').toLowerCase();
// mintaqaviy eSIM qidiruvga mos davlatni qamrab oladimi? (Gretsiya -> Yevropa eSIM)
const coverHit = (c, q) => q && (c.covers || []).find(iso => isoNames(iso).includes(q));
// ---- valyuta: narx so'mda saqlanadi, mijoz xohlasa USD/RUB/CNY/EUR da (Markaziy bank kursi bo'yicha) ko'radi ----
const CURRENCIES = [['USD', '$'], ['EUR', '€'], ['RUB', '₽'], ['CNY', '¥'], ['UZS', "so'm"]];
let RATES = {UZS: 1};
let CUR_SAVED = '';
try { CUR_SAVED = localStorage.getItem('cur') || ''; } catch (e) {}
let CUR = CUR_SAVED || 'USD';
const bidi = m => I18N_RTL.includes(LANG) ? '\u2066' + m + '\u2069' : m;  // arab tilida raqam teskari chiqmasin
const moneyUZS = n => bidi(Number(n).toLocaleString('ru-RU').replace(/[\s,]/g, '\u00a0') + '\u00a0' + t('cur'));
function money(n) {
  if (CUR === 'UZS' || !RATES[CUR]) return moneyUZS(n);
  const v = Number(n) / RATES[CUR];
  const digits = CUR === 'RUB' ? 0 : (v < 100 ? 2 : 0);
  try { return bidi(new Intl.NumberFormat(LANG, {style: 'currency', currency: CUR, minimumFractionDigits: digits, maximumFractionDigits: digits}).format(v)); }
  catch (e) { return bidi(v.toFixed(digits) + '\u00a0' + CUR); }
}
const fromTxt = c => esc(t('from_price', {p: money(c.min_price)}));
const perDay = () => t('per_day');
const gbText = g => g ? `${+g} <small>GB</small>` : `∞ <small>${t('unlimited')}</small>`;
const NOTE_KEY = {'Apple iPhone': 'note_china', 'Samsung': 'note_samsung', 'Xiaomi / Redmi / POCO': 'note_global', 'Honor / Huawei': 'note_global'};

function applyLang() {
  document.documentElement.lang = LANG;
  document.documentElement.dir = I18N_RTL.includes(LANG) ? 'rtl' : 'ltr';
  $$('[data-t]').forEach(el => el.textContent = t(el.dataset.t));
  $('#q').placeholder = t('search');
  const sel = $('#lang-sel');
  if (sel) {
    sel.innerHTML = I18N_LANGS.map(([c, n]) => `<option value="${c}" ${c === LANG ? 'selected' : ''}>${esc(n)}</option>`).join('');
    $('#lang-cur').textContent = LANG.toUpperCase();
  }
}
function saveLang() {
  try { localStorage.setItem('lang', LANG); } catch (e) {}
  if (IN_TG) api('/api/lang', {method: 'POST', body: JSON.stringify({lang: LANG})}).catch(() => {});
}
async function switchLang(l, save) {
  l = pickLang(l); if (!l) return;
  try { await loadLang(l); } catch (e) { return; }
  const changed = l !== LANG;
  LANG = l;
  if (save) saveLang(); else { try { localStorage.setItem('lang', LANG); } catch (e) {} }
  if (!changed) return;
  applyLang(); renderCatalog(); renderHelp(); renderPay();
  if (current && !$('#v-country').classList.contains('hidden')) openCountry(current.country, true);
  if (!$('#v-orders').classList.contains('hidden')) loadOrders();
}
$('#lang-sel')?.addEventListener('change', e => { haptic('sel'); switchLang(e.target.value, true); });

// ---------------- umumiy ----------------
async function api(path, opts = {}) {
  const headers = {'X-Init-Data': tg?.initData || '', ...(opts.headers || {})};
  if (opts.body && !(opts.body instanceof FormData)) headers['Content-Type'] = 'application/json';
  const r = await fetch(path, {...opts, headers});
  if (opts.raw) { if (!r.ok) throw new Error(t('err')); return r; }
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || t('err'));
  return j;
}
const alert_ = (m, cb) => tg?.showAlert ? tg.showAlert(m, cb) : (window.alert(m), cb && cb());
const confirm_ = (m) => new Promise(res => tg?.showConfirm ? tg.showConfirm(m, res) : res(window.confirm(m)));
const haptic = kind => { const h = tg?.HapticFeedback; if (!h) return;
  kind === 'sel' ? h.selectionChanged() : h.notificationOccurred(kind); };
function toast(msg) {
  const el = document.createElement('div'); el.className = 'toast'; el.textContent = msg; document.body.append(el);
  setTimeout(() => { el.style.opacity = 0; setTimeout(() => el.remove(), 300); }, 1800);
}

let DATA = {countries: [], telegram_pay: false, support: ''};
let current = null, selected = null, busy = false, region = '';
const VIEWS = ['catalog', 'country', 'orders', 'esim', 'pay', 'help', 'admin', 'chat', 'account', 'doc'];

function show(view) {
  VIEWS.forEach(v => $('#v-' + v).classList.toggle('hidden', v !== view));
  $$('nav button').forEach(b => b.classList.toggle('on', b.dataset.tab === ({country: 'catalog', esim: 'orders', pay: 'orders', chat: CHAT?.admin ? 'admin' : 'account', doc: 'account'}[view] || view)));
  if (view === 'country' || view === 'esim' || view === 'pay' || view === 'chat' || view === 'doc') tg?.BackButton.show(); else tg?.BackButton.hide();
  document.body.classList.toggle('no-nav', view === 'country' || view === 'chat');
  tg?.MainButton.hide();
  scrollTop();
}
$$('nav button').forEach(b => b.onclick = () => {
  haptic('sel'); show(b.dataset.tab);
  if (b.dataset.tab === 'orders') loadOrders();
  if (b.dataset.tab === 'account') renderAccount();
  if (b.dataset.tab === 'admin') window.Admin?.open();
});
tg?.BackButton.onClick(() => { if (!$('#v-chat').classList.contains('hidden')) return CHAT?.back();
  if (!$('#v-doc').classList.contains('hidden')) { show('account'); return renderAccount(); } if (!$('#v-esim').classList.contains('hidden') || !$('#v-pay').classList.contains('hidden')) { show('orders'); loadOrders(); } else show('catalog'); });

// ---------------- katalog ----------------
function renderCatalog() {
  const all = DATA.countries;
  // mashhur
  const pop = all.filter(c => c.popular);
  $('#popular-wrap').classList.add('hidden'); // mashhurlar to'r boshida TOP belgisi bilan chiqadi
  $('#popular').innerHTML = pop.map(c => `
    <div class="pop" data-c="${esc(c.country)}"><div class="flag">${flagHtml(c.flag)}</div>
      <div class="name">${esc(countryName(c.country, c.flag))}</div><div class="sub">${fromTxt(c)}</div></div>`).join('');
  // mintaqalar (faqat paketi borlari)
  const counts = {}; all.forEach(c => counts[c.region || ''] = (counts[c.region || ''] || 0) + 1);
  const regs = REGIONS.filter(r => r.id === '' || counts[r.id]);
  const nSale = all.filter(c => c.sale).length;
  if (nSale) { regs.splice(1, 0, {id: 'sale'}); counts.sale = nSale; }   // 🏷 Chegirmalar — "Hammasi"dan keyin
  if (region === 'sale' && !nSale) region = '';
  $('#regions').classList.toggle('hidden', regs.length <= 2);
  const keepX = $('#regions').scrollLeft;
  $('#regions').innerHTML = regs.map(r => `<button class="pill ${r.id === region ? 'on' : ''} ${r.id === 'sale' ? 'pill-sale' : ''}" data-r="${r.id}">${esc(r.id === 'sale' ? t('reg_sale') : t('reg_' + (r.id || 'all')))}${r.id ? `<span class="cnt">${counts[r.id]}</span>` : ''}</button>`).join('');
  $$('#regions .pill').forEach(p => p.onclick = () => { haptic('sel'); region = p.dataset.r; PICK = null; renderCatalog(); });
  $('#regions').scrollLeft = keepX;
  renderCountries();
  $$('#popular .pop').forEach(el => el.onclick = () => openCountry(el.dataset.c));
}

function renderCountries() {
  const q = $('#q').value.trim();
  $('#q-clear')?.classList.toggle('hidden', !q);
  const pool = DATA.countries.filter(c => (!region || c.region === region || (region === 'sale' && c.sale)) && (!PICK || PICK.includes(c.country)));
  const bar = $('#pick-bar');
  if (bar) {
    bar.classList.toggle('hidden', !PICK);
    if (PICK) bar.innerHTML = `<span>🎯 ${esc(t('banner_pick', {n: pool.length}))}</span><button id="pick-x">✕ ${esc(t('show_all'))}</button>`;
    $('#pick-x')?.addEventListener('click', () => { haptic('sel'); setPick(null); });
  }
  // qidiruv: aqlli (search.js) — imlo xatolari, kirill, shaharlar; bo'sh bo'lsa oddiy tartib
  const found = q && window.searchCountries ? window.searchCountries(pool, q) : null;
  const via = {};
  const list = found ? found.map(r => { if (r.via) via[r.c.country] = r.via; return r.c; })
    : pool.sort((a, b) => (!!b.regional - !!a.regional) || (b.popular - a.popular) ||
        countryName(a.country, a.flag).localeCompare(countryName(b.country, b.flag), LANG));
  $('#countries').innerHTML = list.length ? list.map(c => `
    <div class="ccard" data-c="${esc(c.country)}">
      ${c.sale ? `<span class="hot sale">−${c.sale}%</span>` : c.popular ? '<span class="hot">TOP</span>' : ''}
      <div class="flag">${flagHtml(c.flag)}</div>
      <div><div class="name">${esc(countryName(c.country, c.flag))}</div>
        <div class="sub">${esc(t('from_price', {p: '\u0000'})).replace('\u0000', `<b>${money(c.min_price)}</b>`)}</div>
        ${via[c.country] ? `<div class="cover-hit">${esc(t('covers_hit', {c: isoName(via[c.country])}))}</div>` : ''}</div>
    </div>`).join('')
    : `<div class="empty"><span class="big">${q ? '🔍' : '🌍'}</span>${q ? t('no_results') : t('no_packages')}</div>`;
  $$('#countries .ccard').forEach(r => r.onclick = () => openCountry(r.dataset.c));
}
let qTimer = null;
$('#q').oninput = () => { clearTimeout(qTimer); qTimer = setTimeout(renderCountries, 120); };

// ---- klaviaturani yopish: Enter/"Qidirish", boshqa joyga bosish yoki sahifani surish ----
function hideKeyboard() {
  const a = document.activeElement;
  if (a && /^(INPUT|TEXTAREA)$/.test(a.tagName)) a.blur();
  try { tg?.hideKeyboard?.(); } catch (e) {}
}
window.hideKeyboard = hideKeyboard;
$('#q').addEventListener('keydown', e => { if (e.key === 'Enter') { e.preventDefault(); hideKeyboard(); } });
$('#q').setAttribute('enterkeyhint', 'search');
document.addEventListener('pointerdown', e => {
  const a = document.activeElement;
  if (!a || !/^(INPUT|TEXTAREA)$/.test(a.tagName)) return;
  if (e.target.closest('input, textarea, select, label, .chat-bar, .promo-row, #q-clear')) return;
  hideKeyboard();
}, true);
let touchY = null;
document.addEventListener('touchstart', e => { touchY = e.touches[0]?.clientY ?? null; }, {passive: true});
document.addEventListener('touchmove', e => {   // ro'yxatni surganda klaviatura yopiladi (qidiruv maydonidan tashqarida)
  if (touchY === null || document.activeElement?.id !== 'q') return;
  if (Math.abs((e.touches[0]?.clientY ?? touchY) - touchY) > 12) { hideKeyboard(); touchY = null; }
}, {passive: true});
$('#q-clear')?.addEventListener('click', () => { $('#q').value = ''; renderCountries(); haptic('sel'); });
// matn yozilayotganda pastki menyuni yashirish (iPhone uni klaviatura ustiga ko'tarib qo'yadi)
const isField = el => el && (el.tagName === 'TEXTAREA' || (el.tagName === 'INPUT' && !/^(checkbox|radio|file|range|button|submit)$/.test(el.type)));
document.addEventListener('focusin', e => { if (isField(e.target)) document.body.classList.add('kb-open'); });
document.addEventListener('focusout', () => setTimeout(() => { if (!isField(document.activeElement)) document.body.classList.remove('kb-open'); }, 60));

let selDays = null, selGb = null;   // selGb — "GB|kunlik" kaliti, masalan "10|0" yoki "1|1"
const pkey = p => `${+p.data_gb}|${p.daily ? 1 : 0}`;
const keyLabel = k => { const [g, dl] = k.split('|'); return +g ? `${+g} GB${+dl ? perDay() : ''}` : t('unlimited_cap'); };
const gbLabel = g => g ? `${+g} GB` : t('unlimited_cap');
const findPkg = (d, k) => current.packages.find(p => p.days === d && pkey(p) === k);

function openCountry(name, keepSel = false) {
  if (!keepSel) haptic('sel');
  current = DATA.countries.find(c => c.country === name);
  if (!current) return;
  $('#c-flag').innerHTML = flagHtml(current.flag); $('#c-flagbg').innerHTML = flagHtml(current.flag);
  $('#c-name').textContent = countryName(current.country, current.flag);
  $('#c-sale').classList.toggle('hidden', !current.sale);
  if (current.sale) $('#c-sale').textContent = '🏷 ' + t('sale_badge', {p: current.sale});
  renderCover();
  renderAlt();
  if (!keepSel) {
    // Trip.com kabi: boshida mashhur variant tanlangan turadi (jami 10 GB atrofida, bo'lmasa o'rtachasi)
    const totals = current.packages.filter(p => !p.daily);
    const pool = totals.length ? totals : current.packages;
    const rec = pool.find(p => +p.data_gb === 10 && p.days >= 7 && p.days <= 15)
      || [...pool].sort((a, b) => a.price - b.price)[Math.floor((pool.length - 1) / 2)];
    selDays = rec?.days ?? null; selGb = rec ? pkey(rec) : null;
    show('country');
  }
  renderSku();
}

// shu davlatni ham qamrab oladigan ko'p davlatli eSIM'lar (Indoneziya -> Janubi-Sharqiy Osiyo, Global)
function renderAlt() {
  const box = $('#c-alt'), iso = isoOf(current.flag);
  const alts = current.regional || !iso ? [] : DATA.countries
    .filter(c => c.regional && (c.covers || []).includes(iso))
    .sort((a, b) => (a.covers.length - b.covers.length));
  box.classList.toggle('hidden', !alts.length);
  if (!alts.length) return;
  box.innerHTML = `<div class="sku-title">🌏 ${esc(t('alt_title'))}</div>` + alts.map(c => `
    <div class="alt-row" data-c="${esc(c.country)}">
      <div class="alt-ic">${flagHtml(c.flag)}</div>
      <div class="alt-mid"><b>${esc(countryName(c.country, c.flag))}</b><small>${esc(t('alt_sub', {n: c.covers.length}))}</small></div>
      <div class="alt-price">${esc(t('from_price', {p: '\u0000'})).replace('\u0000', `<b>${money(c.min_price)}</b>`)}</div>
      <span class="alt-go">›</span>
    </div>`).join('');
  $$('#c-alt .alt-row').forEach(r => r.onclick = () => { openCountry(r.dataset.c); scrollTop(true); });
}

function renderCover(all = false) {
  const box = $('#c-cover'), cov = (current.covers || []).slice()
    .sort((a, b) => isoName(a).localeCompare(isoName(b), LANG));
  box.classList.toggle('hidden', !cov.length);
  if (!cov.length) return;
  const show = all ? cov : cov.slice(0, 12);
  box.innerHTML = `<div class="sku-title">🗺 ${esc(t('covers_title', {n: cov.length}))}</div>
    <div class="cover-list">${show.map(iso => `<span class="cover-chip">${flagHtml(String.fromCodePoint(...[...iso.toUpperCase()].map(ch => 0x1F1E6 + ch.charCodeAt(0) - 65)))}${esc(isoName(iso))}</span>`).join('')}
    ${cov.length > show.length ? `<button class="cover-more" id="cover-more">${esc(t('covers_more', {n: cov.length - show.length}))}</button>` : ''}</div>`;
  $('#cover-more')?.addEventListener('click', () => renderCover(true));
}

function renderSku() {
  const pk = current.packages;
  const days = [...new Set(pk.map(p => p.days))].sort((a, b) => a - b);
  const keys = [...new Set(pk.map(pkey))].sort((a, b) => {
    const [ga, da] = a.split('|').map(Number), [gb_, db_] = b.split('|').map(Number);
    return (da - db_) || ((ga || 1e9) - (gb_ || 1e9));
  });
  $('#days').innerHTML = days.map(d => {
    const ok = selGb === null || findPkg(d, selGb);
    return `<div class="opt ${d === selDays ? 'on' : ''} ${ok ? '' : 'off'}" data-d="${d}">${d} ${t('days')}</div>`;
  }).join('');
  const hasDaily = keys.some(k => k.endsWith('|1')), hasTotal = keys.some(k => k.endsWith('|0'));
  const chip = k => {
    const ok = selDays === null || findPkg(selDays, k);
    return `<div class="opt ${k === selGb ? 'on' : ''} ${ok ? '' : 'off'}" data-g="${k}">${keyLabel(k)}</div>`;
  };
  $('#datas').innerHTML = (hasDaily && hasTotal)
    ? `<div class="sub-lbl">${t('total_plans')}</div><div class="chip-grid">${keys.filter(k => k.endsWith('|0')).map(chip).join('')}</div>
       <div class="sub-lbl">${t('daily_plans')}</div><div class="chip-grid">${keys.filter(k => k.endsWith('|1')).map(chip).join('')}</div>`
    : `<div class="chip-grid">${keys.map(chip).join('')}</div>`;
  $$('#days .opt').forEach(el => el.onclick = () => pick(+el.dataset.d, null));
  $$('#datas .opt').forEach(el => el.onclick = () => pick(null, el.dataset.g));

  selected = selDays !== null && selGb !== null ? findPkg(selDays, selGb) || null : null;
  const det = $('#detail');
  if (selected) {
    const g = +selected.data_gb, daily = !!selected.daily;
    const vol = daily ? `${g} GB × ${selected.days} ${t('days')}` : gbLabel(g);
    det.innerHTML = `<b>${keyLabel(pkey(selected))}${!daily && g ? ' ' + t('total') : ''} · ${selected.days} ${t('days')}</b>
      <div class="row2" style="margin-top:6px"><span>${t('d_data')}</span><span>${daily ? keyLabel(pkey(selected)) : gbLabel(g)}</span></div>
      ${daily ? `<div class="row2"><span>${t('d_total')}</span><span>${vol}</span></div>` : ''}
      <div class="row2"><span>${t('d_days')}</span><span>${selected.days} ${t('days')}</span></div>
      ${!daily && g ? `<div class="row2"><span>${t('d_pergb')}</span><span>≈ ${money(Math.round(selected.price / g / 100) * 100)}</span></div>` : ''}
      ${daily ? `<div class="row2"><span>${t('d_after')}</span><span>${t('d_after_v')}</span></div>` : ''}
      <div class="row2"><span>${t('d_start')}</span><span>${t('d_start_v')}</span></div>`;
    det.classList.remove('hidden');
    $('#bb-sel').textContent = `${countryName(current.country, current.flag)} · ${keyLabel(pkey(selected))} · ${selected.days} ${t('days')}`;
    $('#bb-price').innerHTML = (selected.old ? `<s class="bb-old">${money(selected.old)}</s>` : '') + money(selected.price)
      + (CUR !== 'UZS' && RATES[CUR] ? `<small class="bb-uzs">${esc(t('pay_uzs', {p: moneyUZS(selected.price)}))}</small>` : '');
  } else {
    det.classList.add('hidden');
    $('#bb-sel').textContent = t('select_pkg');
    $('#bb-price').innerHTML = esc(t('from_price', {p: '\u0000'})).replace('\u0000', `</small>${money(current.min_price)}<small>`).replace(/^/, '<small>') + '</small>';
  }
  $('#buy-btn').textContent = t('buy');
  $('#buy-btn').disabled = !selected;
}

function pick(d, k) {
  haptic('sel');
  if (d !== null) {
    selDays = d;
    if (selGb === null || !findPkg(d, selGb)) {
      const opts = current.packages.filter(p => p.days === d);
      selGb = opts.length === 1 ? pkey(opts[0]) : null;
    }
  } else {
    selGb = k;
    if (selDays === null || !findPkg(selDays, k)) {
      const opts = current.packages.filter(p => pkey(p) === k);
      selDays = opts.length === 1 ? opts[0].days : null;
    }
  }
  renderSku();
}

$('#c-back').onclick = () => show('catalog');

// ---------------- to'lov ----------------
const PM = {  // to'lov usullari ko'rinishi
  click: {name: 'Click', color: '#0098DA'}, payme: {name: 'Payme', color: '#1FB5AC'}, online: {name: 'Click / Payme', color: '#0098DA'},
  humo: {name: 'Humo', color: '#F28C00'}, uzcard: {name: 'Uzcard', color: '#1B4F9C'}, visa: {name: 'Visa', color: '#1A1F71'},
  mastercard: {name: 'Mastercard', color: '#EB5B25'}, card: {name: 'Bank', color: '#555'},
  uzum: {name: 'Uzum', color: '#7000FF'},
};
let PROMO = '', USE_BAL = false;   // checkout: qo'llangan promo-kod va bonus balans
function checkout() {
  if (!selected || busy) return;
  if (!IN_TG) return alert_(t('open_in_tg'));
  const pm = DATA.pay_methods || {online: DATA.telegram_pay ? ['online'] : [], cards: ['card']};
  const online = pm.online || [], links = pm.links || [], cards = [...new Set(pm.cards || [])];
  const el = $('#v-pay'), pkg0 = selected;
  const pkg = `${countryName(current.country, current.flag)} · ${keyLabel(pkey(selected))} · ${selected.days} ${t('days')}`;
  el.innerHTML = `
    <div class="pay-head"><div class="flag">${flagHtml(current.flag)}</div><div><h2>${t('pay_choose')}</h2><div class="sub">${esc(pkg)}</div></div></div>
    <div class="card pay-sum" id="q-box"><span>${t('pay_amount')}</span><div class="pay-amt"><b>${moneyUZS(selected.price)}</b></div></div>
    <div class="promo-row"><input id="q-code" placeholder="🎟 ${esc(t('promo_ph'))}" autocomplete="off" autocapitalize="characters" maxlength="20" value="${esc(PROMO)}">
      <button class="btn soft" id="q-apply">${t('promo_apply')}</button></div>
    <div class="pm-list">
      ${online.map(m => `<button class="pm" data-m="${m}"><span class="pm-logo" style="color:${PM[m].color}">${PM[m].name}</span>
        <span class="pm-sub">⚡ ${t('pay_instant')}</span><span class="pm-go">›</span></button>`).join('')}
      ${links.map(k => `<button class="pm" data-m="link" data-c="link:${k}"><span class="pm-logo" style="color:${PM[k].color}">${PM[k].name}</span>
        <span class="pm-sub"><b>${esc(t('pay_link', {t: PM[k].name}))}</b><br>${t('pay_link_sub')}</span><span class="pm-go">›</span></button>`).join('')}
      ${cards.map(c => `<button class="pm" data-m="card" data-c="${c}"><span class="pm-logo" style="color:${(PM[c] || PM.card).color}">${(PM[c] || PM.card).name}</span>
        <span class="pm-sub"><b>${esc(t('pay_transfer', {t: (PM[c] || PM.card).name}))}</b><br>${t('pay_transfer_sub')}</span><span class="pm-go">›</span></button>`).join('')}
    </div>`;
  show('pay');
  let seq = 0;
  const load = async (code) => {
    const my = ++seq;
    let q;
    try { q = await api('/api/quote', {method: 'POST', body: JSON.stringify({package_id: pkg0.id, promo: code, use_balance: USE_BAL})}); }
    catch (e) { return; }
    if (my !== seq || selected !== pkg0) return;
    if (q.promo_error) { haptic('error'); toast('⚠️ ' + q.promo_error); PROMO = ''; $('#q-code').value = ''; }
    else PROMO = q.kind === 'promo' ? q.promo : '';
    const line = (l, v, cls = '') => `<div class="q-line ${cls}"><span>${l}</span><b>${v}</b></div>`;
    const saleL = q.sale_off ? line('🏷 ' + esc(t('sale_line', {p: q.sale_pct})), '−' + moneyUZS(q.sale_off), 'minus') : '';
    const disc = q.discount ? line(q.kind === 'ref' ? '🎁 ' + esc(t('ref_discount', {p: q.ref_pct})) : '🎟 ' + esc(t('promo_applied', {code: q.promo})),
                                   '−' + moneyUZS(q.discount), 'minus') : '';
    const bal = q.balance > 0 ? `<label class="q-bal"><input type="checkbox" id="q-usebal" ${USE_BAL ? 'checked' : ''}>
        <span>💰 ${esc(t('use_balance'))}<small>${esc(t('balance_left', {b: moneyUZS(q.balance)}))}</small></span>
        <b>${q.balance_used ? '−' + moneyUZS(q.balance_used) : ''}</b></label>` : '';
    $('#q-box').innerHTML = `${q.discount || q.balance_used || q.sale_off ? line(t('pay_amount'), `<s>${moneyUZS(q.orig)}</s>`) + saleL + disc + bal : bal}
      <div class="q-total"><span>${t('to_pay')}</span><div class="pay-amt"><b>${moneyUZS(q.final)}</b></div></div>
      ${CUR !== 'UZS' && RATES[CUR] ? `<div class="pay-conv">≈ ${money(q.final)}</div>` : ''}
      ${q.cashback > 0 ? `<div class="q-cb">${esc(t('cashback_line', {c: moneyUZS(q.cashback)}))}</div>` : ''}`;
    $('#q-usebal')?.addEventListener('change', e => { USE_BAL = e.target.checked; haptic('sel'); load(PROMO); });
    $('#q-apply').textContent = PROMO ? t('promo_remove') : t('promo_apply');
  };
  $('#q-apply').onclick = () => {
    if (PROMO) { PROMO = ''; $('#q-code').value = ''; return load(''); }
    const c = $('#q-code').value.trim(); if (!c) return $('#q-code').focus();
    haptic('sel'); load(c);
  };
  $('#q-code').onkeydown = e => { if (e.key === 'Enter') { e.preventDefault(); $('#q-apply').click(); } };
  load(PROMO);
  $$('#v-pay .pm').forEach(b => b.onclick = () => { haptic('sel'); order(b.dataset.m, b.dataset.c); });
}
$('#buy-btn').onclick = checkout;

async function order(method, cardType) {
  busy = true; const btn = $('#buy-btn'); btn.disabled = true; btn.textContent = '…';
  try {
    const r = await api('/api/order', {method: 'POST', body: JSON.stringify({package_id: selected.id, method, in_app: true, promo: PROMO, use_balance: USE_BAL,
      link: method === 'link' ? String(cardType).slice(5) : undefined})});
    if (r.invoice_link) {
      tg.openInvoice(r.invoice_link, status => {
        if (status === 'paid') { haptic('success'); alert_(t('paid_ok', {id: r.order_id}), () => tg.close()); }
        else if (status === 'failed') { haptic('error'); alert_(t('pay_failed')); }
      });
    } else if (r.pay) { haptic('success'); openPay(r.pay, cardType); }
    PROMO = ''; USE_BAL = false;
  } catch (e) { haptic('error'); alert_(e.message); }
  finally { busy = false; btn.disabled = false; btn.textContent = t('buy'); }
}

// ---------------- buyurtmalar ----------------
async function loadOrders() {
  const box = $('#orders');
  if (!IN_TG) { box.innerHTML = `<div class="list"><div class="empty">${t('open_in_tg')}</div></div>`; return; }
  box.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
  try {
    // buyurtmalar va taklif kartasi birga yuklanadi — sahifa keyin "sakramasin"
    const list = await api('/api/orders');
    box.innerHTML = list.length ? '<div class="list">' + list.map(o => (o.status === 'new' ? `<div class="swipe" data-oid="${o.id}">
      <button class="swipe-del" data-cancel="${o.id}">🗑<span>${t('cancel_short')}</span></button>` : '') + `
      <div class="row ${o.has_esim ? 'clickable' : ''}" ${o.has_esim ? `data-esim="${o.id}"` : ''}><div class="flag">${flagHtml(o.flag)}</div>
        <div class="grow"><div class="name">${esc(countryName(o.country, o.flag))} · ${o.data_gb ? +o.data_gb + ' GB' + (o.daily ? perDay() : '') : '∞'} / ${o.days} ${t('days')}</div>
          <div class="sub">#${o.id} · ${moneyUZS(o.price)} · ${esc((o.created_at || '').slice(0, 10))}</div>
          ${(o.status === 'delivered' || o.status === 'cancelled') && o.pkg_active ? `<button class="rebuy" data-rebuy="${o.package_id}">🔁 ${t('rebuy')}</button>` : ''}</div>
        ${o.has_esim ? `<span class="go">${t('open_esim')} ›</span>` : o.status === 'new' ? `<button class="pay-again" data-pay="${o.id}">${t('pay_continue')} ›</button>` : `<span class="badge s-${o.status}">${t('st_' + o.status)}</span>`}</div>` + (o.status === 'new' ? '</div>' : '')).join('') + '</div>'
      : `<div class="list"><div class="empty"><span class="big">📭</span><b>${t('no_orders')}</b><br>${t('no_orders_sub')}
          <button class="btn" id="go-cat">${t('to_catalog')}</button></div></div>`;
    $('#go-cat')?.addEventListener('click', () => show('catalog'));
    $$('#orders [data-esim]').forEach(r => r.onclick = () => openEsim(+r.dataset.esim));
    $$('#orders [data-rebuy]').forEach(b => b.onclick = e => { e.stopPropagation(); haptic('sel'); openPackage(+b.dataset.rebuy); });
    $$('#orders .swipe').forEach(initSwipe);
    $$('#orders [data-cancel]').forEach(b => b.onclick = async e => { e.stopPropagation();
      if (!(await confirm_(t('pay_cancel_q')))) { closeSwipes(); return; }
      try { await api(`/api/orders/${b.dataset.cancel}/cancel`, {method: 'POST'}); haptic('success'); loadOrders(); }
      catch (err) { alert_(err.message); closeSwipes(); } });
    $$('#orders [data-pay]').forEach(b => b.onclick = async e => { e.stopPropagation();
      try { openPay(await api(`/api/orders/${b.dataset.pay}/pay`)); } catch (err) { alert_(err.message); } });
  } catch (e) { box.innerHTML = `<div class="list"><div class="empty">${esc(e.message)}</div></div>`; }
}

// ---------------- do'stlarni taklif qilish (referal) ----------------
let REF = null;
function loadRef() {
  // keshlangan bo'lsa darhol, orqada yangilanadi; o'zgargan bo'lsa (admin foizni almashtirsa) karta qayta chiziladi
  const old = REF;
  const fresh = api('/api/ref').then(r => {
    REF = r;
    if (old && JSON.stringify(old) !== JSON.stringify(r) && !$('#v-account').classList.contains('hidden')) renderRef(r, $('#acc-ref'));
    return r;
  }).catch(() => REF);
  return REF ? Promise.resolve(REF) : fresh;
}
window.resetRef = () => { REF = null; };
function renderRef(r, host) {
  if (!host) return;
  host.innerHTML = '';
  if (!r || !(r.enabled || r.balance > 0 || r.cashback_pct > 0)) return;
  const box = document.createElement('div');
  box.id = 'ref-card'; box.className = 'card ref-card';
  box.innerHTML = `
    ${r.enabled ? `<div class="ref-top"><span class="ref-ic">🎁</span><div><b>${esc(t('ref_title'))}</b>
      <p>${esc(t('ref_sub', {p: r.new_pct, b: r.bonus_pct}))}</p></div></div>` : ''}
    ${r.cashback_pct > 0 ? `<div class="ref-cb">${esc(t('cashback_info', {p: String(r.cashback_pct).replace(/\.0$/, '')}))}</div>` : ''}
    ${r.balance || r.invited ? `<div class="ref-bal"><div><small>${esc(t('ref_balance'))}</small><b>${moneyUZS(r.balance)}</b></div>
      <span>${esc(t('ref_stats', {n: r.invited, k: r.buyers}))}</span></div>` : ''}
    ${r.enabled ? `<div class="ref-btns"><button class="btn" id="ref-share">📤 ${esc(t('ref_share'))}</button>
      <button class="btn soft" id="ref-copy">⧉ ${esc(t('ref_copy'))}</button></div>` : ''}`;
  host.append(box);
  if ($('#ref-share')) $('#ref-share').onclick = () => {
    haptic('sel');
    const u = 'https://t.me/share/url?url=' + encodeURIComponent(r.link) + '&text=' + encodeURIComponent(t('share_text', {p: r.new_pct}));
    IN_TG ? tg.openTelegramLink(u) : window.open(u, '_blank');
  };
  if ($('#ref-copy')) $('#ref-copy').onclick = () => navigator.clipboard?.writeText(r.link).then(() => { haptic('success'); toast('✅ ' + t('copied')); }, () => alert_(r.link));
}

// ---------------- "Yana olish": paketni to'g'ridan-to'g'ri ochish (?buy=ID ham) ----------------
function openPackage(pid) {
  const c = (DATA?.countries || []).find(c => c.packages.some(p => p.id === pid));
  if (!c) return alert_(t('pkg_gone'));
  const p = c.packages.find(p => p.id === pid);
  openCountry(c.country);
  selDays = p.days; selGb = pkey(p);
  renderSku();
}

// ---------------- chapga surib bekor qilish (to'lanmagan buyurtma) ----------------
const SWIPE_W = 92;
let lastSwipe = 0;
// surishdan keyin "To'lash" tugmasi bosilib ketmasin
document.addEventListener('click', e => { if (Date.now() - lastSwipe < 350 && e.target.closest('#orders .swipe .row')) { e.stopPropagation(); e.preventDefault(); } }, true);
function closeSwipes(except) {
  $$('#orders .swipe.open').forEach(s => { if (s !== except) { s.classList.remove('open'); s.querySelector('.row').style.transform = ''; } });
}
function initSwipe(sw) {
  const row = sw.querySelector('.row');
  let x0 = 0, y0 = 0, dx = 0, base = 0, mode = '';   // mode: '' | 'h' (gorizontal) | 'v' (vertikal scroll)
  row.addEventListener('pointerdown', e => {
    x0 = e.clientX; y0 = e.clientY; dx = 0; mode = ''; base = sw.classList.contains('open') ? -SWIPE_W : 0;
    row.style.transition = 'none';
  });
  row.addEventListener('pointermove', e => {
    if (e.buttons === 0 && e.pointerType === 'mouse') return;
    const mx = e.clientX - x0, my = e.clientY - y0;
    if (!mode && (Math.abs(mx) > 8 || Math.abs(my) > 8)) {
      mode = Math.abs(mx) > Math.abs(my) ? 'h' : 'v';
      if (mode === 'h') { row.setPointerCapture?.(e.pointerId); closeSwipes(sw); }
    }
    if (mode !== 'h') return;
    dx = Math.max(-SWIPE_W - 30, Math.min(0, base + mx));
    row.style.transform = `translateX(${dx}px)`;
  });
  const end = () => {
    row.style.transition = '';
    if (mode !== 'h') { mode = ''; return; }
    const open = dx < -SWIPE_W / 2;
    sw.classList.toggle('open', open);
    row.style.transform = open ? `translateX(${-SWIPE_W}px)` : '';
    if (open) haptic('sel');
    lastSwipe = Date.now(); mode = '';
  };
  row.addEventListener('pointerup', end); row.addEventListener('pointercancel', end);
}

// ---------------- to'lov sahifasi (karta + chek yuklash, hammasi Mini App ichida) ----------------
function openPay(p, cardType) {
  const el = $('#v-pay');
  const cards = (p.cards && p.cards.length) ? p.cards.map(c => ({...c, key: c.type}))
    : p.card_number ? [{number: p.card_number, holder: p.card_holder, type: 'card', key: 'card'}] : [];
  const opts = [...Object.entries(p.links || {}).map(([k, url]) => ({key: 'link:' + k, type: k, url})), ...cards];
  if (!cardType && String(p.method || '').endsWith('_link')) cardType = 'link:' + p.method.slice(0, -5);
  const cur = opts.find(c => c.key === cardType) || opts.find(c => !c.url) || opts[0] || {type: 'card', key: 'card'};
  if (cur.number) p = {...p, card_number: cur.number, card_holder: cur.holder};
  const curName = (PM[cur.type] || PM.card).name;
  const tabs = opts.length > 1 ? `<div class="seg pay-tabs">${opts.map(c => `<button class="${c === cur ? 'on' : ''}" data-ct="${c.key}">${(PM[c.type] || PM.card).name}</button>`).join('')}</div>` : '';
  const card = String(p.card_number || '').replace(/\D/g, '').replace(/(\d{4})(?=\d)/g, '$1 ');
  const sum = String(p.amount);
  const conv = CUR !== 'UZS' && RATES[CUR] ? `<div class="pay-conv">≈ ${money(p.amount)}</div>` : '';
  const pkg = `${countryName(p.country, p.flag)} · ${p.data_gb ? +p.data_gb + ' GB' + (p.daily ? perDay() : '') : '∞'} · ${p.days} ${t('days')}`;
  const done = p.status === 'checking';
  el.innerHTML = `
    <div class="pay-head"><div class="flag">${flagHtml(p.flag)}</div><div><h2>${t('pay_title')} · #${p.order_id}</h2><div class="sub">${esc(pkg)}</div></div></div>
    ${done ? `<div class="card pay-done"><div class="big">✅</div><b>${t('pay_sent_t')}</b><p>${t('pay_sent')}</p>
        <button class="btn" id="pay-orders">${t('to_orders')}</button></div>` : `
    <div class="card pay-sum"><span>${t('pay_amount')}</span>
      <div class="pay-amt"><b>${moneyUZS(p.amount)}</b><button class="copy-mini" data-copy="${sum}">⧉ ${t('pay_copy')}</button></div>
      ${conv}<small>⚠️ ${t('pay_exact')}</small></div>
    ${tabs}
    ${cur.url ? `<div class="pay-step"><span class="num">1</span>${esc(t('pay_link_step1', {t: curName}))}</div>
    <button class="btn pay-link" id="pay-link" style="background:${(PM[cur.type] || PM.card).color}">${esc(t('pay_link_open', {t: curName}))} ↗</button>` : `
    <div class="pay-step"><span class="num">1</span>${t('pay_step1')}</div>
    <div class="bank-card pay-card">
      <div class="top">${t('pay_card')} · <b>${(PM[cur.type] || PM.card).name}</b></div>
      <div class="num-row"><span class="cardnum">${esc(card)}</span><button class="copy-mini light" data-copy="${esc(String(p.card_number || '').replace(/\D/g, ''))}">⧉ ${t('pay_copy')}</button></div>
      <div class="holder">${esc(p.card_holder || '')}</div>
    </div>`}
    <div class="pay-step"><span class="num">2</span>${t('pay_step2')}</div>
    <label class="pay-drop" id="pay-drop"><input type="file" id="pay-file" accept="image/*,application/pdf" hidden>
      <div id="pay-prev"><span class="big">🧾</span><span>${t('pay_pick')}</span></div></label>
    <button class="btn" id="pay-send" disabled>${t('pay_send')}</button>
    <button class="link-btn" id="pay-cancel">${t('pay_cancel')}</button>`}`;
  show('pay');
  $('#pay-orders')?.addEventListener('click', () => { show('orders'); loadOrders(); });
  $$('#v-pay [data-ct]').forEach(b => b.onclick = () => { haptic('sel'); openPay(p, b.dataset.ct); });
  $('#pay-link')?.addEventListener('click', () => {
    haptic('sel');
    if (/^https:\/\/t\.me\//.test(cur.url) && IN_TG) tg.openTelegramLink(cur.url);
    else if (IN_TG) tg.openLink(cur.url); else window.open(cur.url, '_blank');
  });
  $$('#v-pay [data-copy]').forEach(b => b.onclick = () => {
    navigator.clipboard?.writeText(b.dataset.copy).then(() => { haptic('success'); toast('✅ ' + t('copied')); }).catch(() => {});
  });
  let file = null;
  $('#pay-file')?.addEventListener('change', e => {
    file = e.target.files[0]; if (!file) return;
    if (file.size > 10 * 1024 * 1024) { file = null; return alert_(t('pay_file_big')); }
    const url = file.type.startsWith('image/') ? URL.createObjectURL(file) : '';
    $('#pay-prev').innerHTML = url ? `<img src="${url}" alt="">` : `<span class="big">📄</span><span>${esc(file.name)}</span>`;
    $('#pay-send').disabled = false; haptic('sel');
  });
  $('#pay-send')?.addEventListener('click', async e => {
    if (!file) return;
    e.target.disabled = true; e.target.textContent = '…';
    const fd = new FormData(); fd.append('receipt', file, file.name || 'receipt.jpg');
    try {
      await api(`/api/orders/${p.order_id}/receipt`, {method: 'POST', body: fd});
      haptic('success'); openPay({...p, status: 'checking'});
    } catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; e.target.textContent = t('pay_send'); }
  });
  $('#pay-cancel')?.addEventListener('click', async () => {
    if (!(await confirm_(t('pay_cancel_q')))) return;
    try { await api(`/api/orders/${p.order_id}/cancel`, {method: 'POST'}); haptic('success'); show('orders'); loadOrders(); }
    catch (err) { alert_(err.message); }
  });
}

// ---------------- mijozning eSIM'i (QR, o'rnatish, PDF) ----------------
async function openEsim(id) {
  haptic('sel'); show('esim');
  const box = $('#v-esim');
  box.innerHTML = '<div class="skeleton" style="height:180px"></div><div class="skeleton"></div>';
  let e;
  try { e = await api(`/api/orders/${id}/esim`); } catch (err) { box.innerHTML = `<div class="card">${esc(err.message)}</div>`; return; }
  const vol = keyLabel(`${+e.data_gb}|${e.daily ? 1 : 0}`);
  const copyRow = (k, v) => `<div class="kv"><div class="grow"><div class="k">${k}</div><div class="v">${esc(v)}</div></div>
    <button class="icon-btn" data-copy="${esc(v)}">📋</button></div>`;
  box.innerHTML = `
    <div class="banner">
      <button class="back" id="e-back">‹</button>
      <div class="bflag">${flagHtml(e.flag)}</div>
      <div class="flag">${flagHtml(e.flag)}</div>
      <h2>${esc(countryName(e.country, e.flag))}</h2>
      <div class="chips"><span class="chip">📶 ${vol}</span><span class="chip">📅 ${e.days} ${t('days')}</span><span class="chip">#${e.id} · ${esc(e.date)}</span></div>
    </div>
    <div class="sku center">
      <div class="sku-title">${t('esim_ready')}</div>
      <div class="esim-qr"><img src="${e.qr}" alt="QR"></div>
      <div class="sub">${t('scan_hint')}</div>
      <button class="btn" id="e-ios">🍎 ${t('install_ios')}</button>
      <button class="btn soft" id="e-android">🤖 ${t('install_android')}</button>
      ${e.usage ? `<button class="btn soft" id="e-usage">📊 ${t('check_usage')}</button>` : ''}
    </div>
    <div class="sku">
      <div class="sku-title">✍️ ${t('manual')}</div>
      ${copyRow('SM-DP+', e.smdp)}${copyRow(t('act_code'), e.code)}${copyRow(t('act_code_android'), e.lpa)}
    </div>
    <button class="btn" id="e-pdf">📄 ${t('send_pdf')}</button>
    <button class="btn soft" id="e-guide">🛠 ${t('h_install')}</button>
    <div class="note">⚠️ ${t('once_note')}</div>`;
  const open_ = u => IN_TG ? tg.openLink(u) : window.open(u, '_blank');
  $('#e-back').onclick = () => { show('orders'); loadOrders(); };
  $('#e-ios').onclick = () => open_(e.ios);
  $('#e-android').onclick = () => open_(e.android);
  $('#e-usage')?.addEventListener('click', () => open_(e.usage));
  $('#e-guide').onclick = () => { show('help'); helpTab('install'); };
  $$('#v-esim [data-copy]').forEach(b => b.onclick = () =>
    navigator.clipboard?.writeText(b.dataset.copy).then(() => { haptic('success'); toast(t('copied')); }, () => alert_(b.dataset.copy)));
  $('#e-pdf').onclick = async ev => {
    ev.target.disabled = true;
    try { await api(`/api/orders/${id}/pdf`, {method: 'POST'}); haptic('success'); alert_(t('pdf_sent')); }
    catch (err) { alert_(err.message); }
    ev.target.disabled = false;
  };
}

// ---------------- yordam: telefon tekshiruvi, o'rnatish, savollar ----------------
let devBrand = Object.keys(DEVICES)[0], devQuery = '', devPick = null, instOs = 'iphone';

function renderDevice() {
  const brands = Object.keys(DEVICES);
  const q = devQuery.trim().toLowerCase();
  const fmt = m => m.replace(/^\*/, '').replace('{older}', t('dev_older'));
  // qidiruvda barcha brendlar bo'yicha, aks holda tanlangan brend
  const pool = q ? brands : [devBrand];
  const rows = {y: [], m: [], n: []};
  pool.forEach(br => ['y', 'm', 'n'].forEach(s => (DEVICES[br][s] || []).forEach(raw => {
    const name = fmt(raw);
    if (!q || name.toLowerCase().includes(q) || br.toLowerCase().includes(q)) rows[s].push({name, s, br, isNew: raw.startsWith('*')});
  })));
  const total = rows.y.length + rows.m.length + rows.n.length;
  const icon = {y: '✓', m: '!', n: '✕'};
  let result = '';
  if (devPick) {
    const [m, s] = devPick;
    result = `<div class="dv-result r-${s}"><div class="dv-ic">${icon[s]}</div><div><div class="dv-rt">${esc(m)}</div>
      <div class="dv-rs"><b>${t('dev_' + s)}.</b> ${t('dev_' + s + '_text')}</div></div></div>`;
  }
  const row = r => `<button class="dv-row" data-m="${esc(r.name)}" data-s="${r.s}">
      <span class="dv-dot d-${r.s}">${icon[r.s]}</span>
      <span class="dv-name">${esc(r.name)}${q ? `<small>${esc(r.br)}</small>` : ''}</span>
</button>`;
  const group = s => rows[s].length ? `<div class="dv-group"><div class="dv-gh"><span class="dv-dot d-${s}">${icon[s]}</span>${t('dev_' + s)}
      <span class="dv-cnt">${rows[s].length}</span></div>${rows[s].map(row).join('')}</div>` : '';
  const keepScroll = $('#h-device .dv-brands')?.scrollLeft || 0;   // qayta chizilganda brendlar qatori boshiga qaytmasin
  $('#h-device').innerHTML = `
    <div class="dv-hero">
      <div class="dv-hero-t">${t('dev_title')}</div>
      <div class="dv-hero-s">${t('dev_dial_sub')}</div>
      <a class="dv-dial" href="tel:*%2306%23">📞 ${esc(t('dev_dial')).replace('*#06#', '<span class="dv-code">*#06#</span>')}</a>
    </div>
    <div class="dv-search"><input id="dev-q" type="search" placeholder="${t('dev_search')}" value="${esc(devQuery)}"></div>
    ${q ? '' : `<div class="pills dv-brands">${brands.map(b => `<button class="pill ${b === devBrand ? 'on' : ''}" data-b="${esc(b)}">${esc(b)}</button>`).join('')}</div>`}
    ${result}
    <div class="dv-hint">${total ? `${t('dev_pick')} · ${t('dev_count', {n: total})}` : ''}</div>
    ${total ? group('y') + group('m') + group('n') : `<div class="empty">${t('no_results')}<br><small>${t('not_found')}</small></div>`}
    ${!q && NOTE_KEY[devBrand] ? `<div class="note">ℹ️ ${esc(t(NOTE_KEY[devBrand]))}</div>` : ''}
    <div class="dv-foot">🔢 ${t('eid_alt')}</div>`;
  const strip = $('#h-device .dv-brands');
  if (strip) {
    strip.scrollLeft = keepScroll;
    const on = strip.querySelector('.pill.on');   // tanlangan brend ko'rinib tursin
    if (on) {
      const sr = strip.getBoundingClientRect(), r = on.getBoundingClientRect();
      if (r.left < sr.left || r.right > sr.right) strip.scrollLeft += r.left - sr.left - 12;
    }
  }
  $$('#h-device .dv-brands .pill').forEach(p => p.onclick = () => { haptic('sel'); devBrand = p.dataset.b; devPick = null; renderDevice(); });
  $$('#h-device .dv-row').forEach(r => r.onclick = () => {
    devPick = [r.dataset.m, r.dataset.s]; haptic(r.dataset.s === 'y' ? 'success' : r.dataset.s === 'n' ? 'error' : 'warning');
    renderDevice(); $('#h-device .dv-result')?.scrollIntoView({behavior: 'smooth', block: 'center'});
  });
  const inp = $('#dev-q');
  inp.oninput = () => { devQuery = inp.value; devPick = null; const pos = inp.selectionStart; renderDevice();
    const nq = $('#dev-q'); nq.focus(); nq.setSelectionRange(pos, pos); };
}

function renderInstall() {
  const steps = L(instOs === 'iphone' ? 'i_steps' : 'a_steps');
  $('#h-install').innerHTML = `
    <div class="pills"><button class="pill ${instOs === 'iphone' ? 'on' : ''}" data-os="iphone"> ${t('iphone')}</button>
      <button class="pill ${instOs === 'android' ? 'on' : ''}" data-os="android">🤖 ${t('android')}</button></div>
    <div class="note" style="margin:0 0 10px">📶 ${t('inst_before')}</div>
    <div class="card"><ol class="steps">${steps.map(([title, body, extra]) => `
      <li><div><b>${esc(title)}</b>
        ${Array.isArray(body) ? `<div class="path">${body.map(x => `<span>${esc(x)}</span>`).join('')}</div>` : `<p>${body}</p>`}
        ${extra ? `<p>${extra}</p>` : ''}</div></li>`).join('')}</ol></div>`;
  $$('#h-install .pill').forEach(p => p.onclick = () => { haptic('sel'); instOs = p.dataset.os; renderInstall(); });
}

function renderFaq() {
  $('#h-faq').innerHTML = L('faq').map(([q, a]) => `<details class="faq"><summary>${esc(q)}</summary><p>${esc(a)}</p></details>`).join('');
}
function renderHelp() { renderDevice(); renderInstall(); renderFaq(); }
function helpTab(h) {
  $$('#help-seg button').forEach(b => b.classList.toggle('on', b.dataset.h === h));
  ['device', 'install', 'faq'].forEach(x => $('#h-' + x).classList.toggle('hidden', x !== h));
}
$$('#help-seg button').forEach(b => b.onclick = () => { haptic('sel'); helpTab(b.dataset.h); });
$$('[data-go="device"]').forEach(a => a.onclick = () => { show('help'); helpTab('device'); });

$('#support-btn').onclick = () => { haptic('sel'); openSupport(); };

// ---------------- akkaunt (mijoz uchun) ----------------
let ME = {};
function renderAccount() {
  const el = $('#v-account'), u = tg?.initDataUnsafe?.user || {};
  const name = [u.first_name, u.last_name].filter(Boolean).join(' ').trim();
  const initial = ((name || u.username || 'B').replace(/[^\p{L}\p{N}]/gu, '')[0] || 'B').toUpperCase();
  const unread = +($('#help-dot').textContent || 0);
  const row = (id, ic, title, sub, right = '›') => `<button class="acc-row" data-acc="${id}"><span class="acc-ic">${ic}</span>
    <span class="acc-t"><b>${esc(title)}</b>${sub ? `<small>${esc(sub)}</small>` : ''}</span><span class="acc-r">${right}</span></button>`;
  const langName = (I18N_LANGS.find(x => x[0] === LANG) || [, LANG])[1];
  const curs = CURRENCIES.filter(([c]) => RATES[c]);
  el.innerHTML = `
    <div class="card acc-head">
      <div class="acc-ava">${u.photo_url ? `<img src="${esc(u.photo_url)}" alt="" referrerpolicy="no-referrer" onerror="this.remove()">` : ''}<span>${esc(initial)}</span></div>
      <div><b>${esc(name || (u.username ? '@' + u.username : 'Booking eSIM'))}</b>
        <small>${u.username && name ? '@' + esc(u.username) + ' · ' : ''}ID ${esc(u.id || '—')}</small></div>
    </div>
    <div id="acc-ref"></div>
    <div class="section-title">${t('acc_contact')}</div>
    <div class="acc-list">
      ${row('support', '💬', t('chat_title'), t('chat_sub'), unread ? `<span class="cnt">${unread}</span>` : '›')}
      ${ME.support ? row('tg', '✈️', '@' + ME.support, t('acc_tg_sub')) : ''}
    </div>
    <div class="section-title">${t('acc_settings')}</div>
    <div class="acc-list">
      ${row('lang', '🌐', t('lang'), langName)}
      ${curs.length > 1 ? row('cur', '💱', t('currency'), `${CUR} · ${curName(CUR)}`) : ''}
    </div>
    <div class="section-title">${t('acc_info')}</div>
    <div class="acc-list">
      ${row('terms', '📄', t('acc_terms'))}${row('privacy', '🛡', t('acc_privacy'))}
      ${row('refund', '💳', t('acc_refund'))}${row('contacts', '🏢', t('acc_contacts'))}
    </div>
    <div class="acc-foot">@${esc(ME.bot || 'booking_esim_bot')}</div>`;
  loadRef().then(r => renderRef(r, $('#acc-ref')));
  $$('#v-account [data-acc]').forEach(b => b.onclick = () => {
    haptic('sel');
    const k = b.dataset.acc;
    if (k === 'support') return openSupport();
    if (k === 'tg') return IN_TG ? tg.openTelegramLink('https://t.me/' + ME.support) : open('https://t.me/' + ME.support);
    if (k === 'lang') return pickLangSheet(renderAccount);
    if (k === 'cur') return pickCurSheet(renderAccount);
    openDoc(k);
  });
}
function openDoc(k) {
  const el = $('#v-doc');
  const body = String(t('doc_' + k, {bot: ME.bot || 'booking_esim_bot'}));
  el.innerHTML = `<div class="chat-head"><button class="back" id="doc-back">‹</button><div class="grow"><b>${esc(t('acc_' + k))}</b></div></div>
    <div class="card doc">${body.split(/\n\n+/).map(p => `<p>${esc(p).replace(/\n/g, '<br>')}</p>`).join('')}</div>`;
  show('doc');
  $('#doc-back').onclick = () => { show('account'); renderAccount(); };
}

// ---------------- yordam chati (mijoz <-> admin) ----------------
let CHAT = null;   // joriy ochiq chat: {admin, back(), ...}
function setSupUnread(n) {
  $('#help-dot').textContent = n || ''; $('#help-dot').classList.toggle('hidden', !n);
  $('#sup-cnt').textContent = n || ''; $('#sup-cnt').classList.toggle('hidden', !n);
}
function openSupport() {
  if (!IN_TG) return alert_(t('open_in_tg'));
  setSupUnread(0);
  openChat({admin: false, title: t('chat_title'), sub: t('chat_sub'), empty: t('chat_empty'),
    url: '/api/support', back: () => { show('account'); renderAccount(); }});
}
window.openChat = openChat;
function openChat(o) {
  const el = $('#v-chat');
  const my = {...o, last: 0, alive: true, imgs: {}};
  if (CHAT) CHAT.alive = false;
  CHAT = my;
  el.innerHTML = `
    <div class="chat-head"><button class="back" id="ch-back">‹</button>
      <div class="grow"><b>${esc(o.title)}</b><small id="ch-sub">${esc(o.sub || '')}</small></div>${o.headRight || ''}</div>
    <div id="ch-info"></div>
    <div class="chat-list" id="ch-list"><div class="skeleton"></div></div>
    <div class="chat-bar">
      <div class="ch-prev hidden" id="ch-prev"></div>
      <div class="ch-row"><label class="ch-att" title="Photo">📎<input type="file" id="ch-file" accept="image/*" hidden></label>
        <textarea id="ch-in" rows="1" maxlength="2000" placeholder="${esc(t('chat_ph'))}"></textarea>
        <button class="ch-send" id="ch-send" disabled>➤</button></div>
    </div>`;
  show('chat');
  $('#ch-back').onclick = () => { my.alive = false; my.back(); };
  my.back = (b => () => { my.alive = false; b(); })(o.back);
  const list = $('#ch-list'), inp = $('#ch-in'), sendBtn = $('#ch-send');
  const mainEl = document.querySelector('main');
  const nearBottom = () => mainEl.scrollHeight - mainEl.scrollTop - mainEl.clientHeight < 140;
  const toBottom = () => requestAnimationFrame(() => { mainEl.scrollTop = mainEl.scrollHeight; });
  const fmtTime = at => { const d = new Date(String(at).replace(' ', 'T') + 'Z'); return isNaN(d) ? '' : d.toLocaleTimeString(LANG, {hour: '2-digit', minute: '2-digit'}); };
  const dayOf = at => { const d = new Date(String(at).replace(' ', 'T') + 'Z'); return isNaN(d) ? '' : d.toDateString(); };
  const dayLbl = at => { const d = new Date(String(at).replace(' ', 'T') + 'Z');
    return d.toDateString() === new Date().toDateString() ? t('today') : d.toLocaleDateString(LANG, {day: 'numeric', month: 'long'}); };
  let lastDay = '';
  const bubble = m => {
    const mine = o.admin ? m.admin : !m.admin;
    let h = '';
    const dd = dayOf(m.at);
    if (dd !== lastDay) { lastDay = dd; h += `<div class="ch-day"><span>${esc(dayLbl(m.at))}</span></div>`; }
    return h + `<div class="ch-msg ${mine ? 'me' : 'them'}">${m.photo ? `<div class="ch-img" data-mid="${m.id}"><div class="skeleton"></div></div>` : ''}
      ${m.text ? `<div class="ch-txt">${esc(m.text).replace(/\n/g, '<br>')}</div>` : ''}<span class="ch-time">${fmtTime(m.at)}</span></div>`;
  };
  const loadImgs = () => $$('#ch-list .ch-img[data-mid]').forEach(async box => {
    const mid = box.dataset.mid; box.removeAttribute('data-mid');
    try {
      const url = my.imgs[mid] || URL.createObjectURL(await (await api('/api/support/file/' + mid, {raw: true})).blob());
      my.imgs[mid] = url;
      box.innerHTML = `<img src="${url}" alt="">`;
      box.onclick = () => { const w = document.createElement('div'); w.className = 'ch-zoom'; w.innerHTML = `<img src="${url}" alt="">`; w.onclick = () => w.remove(); document.body.append(w); };
      if (nearBottom()) toBottom();
    } catch (e) { box.innerHTML = '⚠️'; }
  });
  const append = (msgs, first) => {
    if (first) { list.innerHTML = msgs.length ? '' : `<div class="ch-empty"><span class="big">💬</span>${esc(o.empty || '')}</div>`; lastDay = ''; }
    if (!msgs.length) return;
    list.querySelector('.ch-empty')?.remove();
    const stick = first || nearBottom();
    list.insertAdjacentHTML('beforeend', msgs.filter(m => m.id > my.last).map(bubble).join(''));
    my.last = Math.max(my.last, ...msgs.map(m => m.id));
    loadImgs();
    if (stick) toBottom();
  };
  const poll = async first => {
    if (!my.alive) return;
    try {
      const r = await api(o.url + (first ? '' : '?after=' + my.last));
      if (!my.alive) return;
      if (first && o.onInfo) o.onInfo(r.user, $('#ch-info'));
      append(r.msgs, first);
    } catch (e) { if (first) list.innerHTML = `<div class="ch-empty">${esc(e.message)}</div>`; }
    if (my.alive) setTimeout(() => poll(false), document.hidden ? 15000 : 4000);
  };
  poll(true);
  // yozish
  let file = null;
  const upd = () => { sendBtn.disabled = !inp.value.trim() && !file; inp.style.height = 'auto'; inp.style.height = Math.min(120, inp.scrollHeight) + 'px'; };
  inp.oninput = upd;
  inp.onkeydown = e => { if (e.key === 'Enter' && !e.shiftKey && !('ontouchstart' in window)) { e.preventDefault(); sendBtn.click(); } };
  $('#ch-file').onchange = e => {
    file = e.target.files[0] || null; e.target.value = '';
    if (file && file.size > 10 * 1024 * 1024) { file = null; alert_(t('pay_file_big')); }
    const pv = $('#ch-prev');
    pv.classList.toggle('hidden', !file);
    pv.innerHTML = file ? `<img src="${URL.createObjectURL(file)}" alt=""><span>${esc(file.name || 'photo')}</span><button id="ch-unfile">✕</button>` : '';
    $('#ch-unfile')?.addEventListener('click', () => { file = null; pv.classList.add('hidden'); pv.innerHTML = ''; upd(); });
    upd(); if (file) haptic('sel');
  };
  sendBtn.onclick = async () => {
    const text = inp.value.trim();
    if (!text && !file) return;
    sendBtn.disabled = true;
    const fd = new FormData(); fd.append('text', text); if (file) fd.append('photo', file, file.name || 'photo.jpg');
    try {
      const m = await api(o.url, {method: 'POST', body: fd});
      inp.value = ''; file = null; $('#ch-prev').classList.add('hidden'); $('#ch-prev').innerHTML = '';
      append([m], false); toBottom(); haptic('success');
      if (m.delivered === false) toast('⚠️ Mijoz botni bloklagan — javob faqat Mini App\'da ko\'rinadi');
    } catch (e) { haptic('error'); toast('⚠️ ' + (e.message || t('chat_fail'))); }
    upd();
  };
}

// ---------------- to'lov usullari (mijoz qayerdaligiga qarab) ----------------
const PAY = {
  UZ: [['Click', '#0098DA'], ['Payme', '#1FB5AC'], ['Uzcard', '#1B4F9C'], ['Humo', '#F28C00']],
  RU: [['МИР', '#0F754E'], ['СБП', '#5B2C83'], ['SberPay', '#21A038'], ['T-Pay', '#333333']],
  INTL: [['VISA', '#1A1F71'], ['Mastercard', '#EB5B25'], ['UnionPay', '#D7272F']],
};
const SHOW_RU_PAY = false;  // Rossiya to'lovlari (МИР/СБП/SberPay) hali qabul qilinmaydi — yoqish uchun true qiling
const RU_TZ = /^(Europe\/(Moscow|Kaliningrad|Samara|Volgograd|Saratov|Ulyanovsk|Astrakhan|Kirov|Simferopol)|Asia\/(Yekaterinburg|Omsk|Novosibirsk|Barnaul|Tomsk|Novokuznetsk|Krasnoyarsk|Irkutsk|Chita|Yakutsk|Khandyga|Vladivostok|Ust-Nera|Magadan|Sakhalin|Srednekolymsk|Kamchatka|Anadyr))$/;
let PAY_COUNTRY = '';
function payRegion() {
  const c = PAY_COUNTRY;  // serverdan (IP bo'yicha) kelgan mamlakat
  if (c === 'UZ' || c === 'RU') return c;
  if (c && c !== 'XX' && c !== 'T1') return 'INTL';
  let tz = ''; try { tz = Intl.DateTimeFormat().resolvedOptions().timeZone || ''; } catch (e) {}
  if (/^Asia\/(Tashkent|Samarkand)$/.test(tz)) return 'UZ';
  if (RU_TZ.test(tz)) return 'RU';
  return tz ? 'INTL' : 'UZ';
}
function renderPay() {
  const el = $('#pay-row'); if (!el) return;
  const reg = payRegion();
  el.classList.toggle('hidden', reg === 'RU' && !SHOW_RU_PAY);
  if (reg === 'RU' && !SHOW_RU_PAY) { el.innerHTML = ''; return; }
  el.innerHTML = `<span class="pay-lbl">💳 ${esc(t('pay_accept'))}</span>` +
    PAY[payRegion()].map(([n, c]) => `<span class="pay-tag" style="color:${c}">${esc(n)}</span>`).join('');
}

function renderCurPicker() {
  const sel = $('#cur-sel'); if (!sel) return;
  const avail = CURRENCIES.filter(([c]) => RATES[c]);
  $('#cur-pick').classList.toggle('hidden', avail.length < 2);
  sel.innerHTML = avail.map(([c, s]) => `<option value="${c}" ${c === CUR ? 'selected' : ''}>${s}  ${c}</option>`).join('');
  $('#cur-cur').textContent = CUR;
}
function rerenderPrices() {
  renderCurPicker(); renderCatalog();
  if (current && !$('#v-country').classList.contains('hidden')) openCountry(current.country, true);
}
function setCur(c) {
  CUR = c; CUR_SAVED = CUR; try { localStorage.setItem('cur', CUR); } catch (_) {}
  if (IN_TG) api('/api/lang', {method: 'POST', body: JSON.stringify({currency: CUR})}).catch(() => {});
  haptic('sel'); rerenderPrices();
}
$('#cur-sel')?.addEventListener('change', e => setCur(e.target.value));

// ---------------- zamonaviy tanlash oynasi (bottom sheet) — til va valyuta uchun ----------------
function openSheet({title, items, value, onPick}) {
  $('.sheet-wrap')?.remove();
  const w = document.createElement('div');
  w.className = 'sheet-wrap';
  w.innerHTML = `<div class="sheet" role="dialog" aria-modal="true"><div class="sheet-grab"></div>
    <div class="sheet-h"><b>${esc(title)}</b><button class="sheet-x" aria-label="close">✕</button></div>
    <div class="sheet-list">${items.map(it => `<button class="sheet-it ${it.value === value ? 'on' : ''}" data-v="${esc(it.value)}">
      <span class="sheet-ic">${it.icon || ''}</span><span class="sheet-t"><b>${esc(it.label)}</b>${it.sub ? `<small>${esc(it.sub)}</small>` : ''}</span>
      <span class="sheet-ok">${it.value === value ? '✓' : ''}</span></button>`).join('')}</div></div>`;
  document.body.append(w);
  requestAnimationFrame(() => w.classList.add('open'));
  const close = () => { w.classList.remove('open'); setTimeout(() => w.remove(), 220); document.removeEventListener('keydown', esc_); };
  const esc_ = e => { if (e.key === 'Escape') close(); };
  document.addEventListener('keydown', esc_);
  w.onclick = e => { if (e.target === w) close(); };
  w.querySelector('.sheet-x').onclick = close;
  w.querySelectorAll('.sheet-it').forEach(b => b.onclick = () => {
    haptic('sel'); close();
    if (b.dataset.v !== value) onPick(b.dataset.v);
  });
  w.querySelector('.sheet-it.on')?.scrollIntoView({block: 'center'});
}
const CUR_NAMES = {};
const CUR_UZ = {USD: "AQSh dollari", EUR: 'Yevro', RUB: 'Rossiya rubli', CNY: 'Xitoy yuani', UZS: "O'zbek so'mi"};
const curName = c => { if (LANG === 'uz') return CUR_UZ[c] || c; try { CUR_NAMES[LANG + c] ??= new Intl.DisplayNames([LANG === 'uz' ? 'uz' : LANG], {type: 'currency'}).of(c); } catch (e) {} return CUR_NAMES[LANG + c] || c; };
function pickLangSheet(after) {
  openSheet({title: t('lang'), value: LANG,
    items: I18N_LANGS.map(([c, n, f]) => ({value: c, label: n, icon: flagHtml(f), sub: c.toUpperCase()})),
    onPick: async v => { await switchLang(v, true); after?.(); }});
}
function pickCurSheet(after) {
  const avail = CURRENCIES.filter(([c]) => RATES[c]);
  openSheet({title: t('currency'), value: CUR,
    items: avail.map(([c, sym]) => ({value: c, label: `${c} · ${curName(c)}`, icon: `<span class="cur-sym ${sym.length > 2 ? 'sm' : ''}">${esc(sym)}</span>`,
      sub: c === 'UZS' ? '' : `1 ${c} = ${Math.round(RATES[c]).toLocaleString('ru-RU').replace(/,/g, ' ')} ${t('cur')}`})),
    onPick: v => { setCur(v); after?.(); }});
}
// tepadagi tugmalar: brauzer ro'yxati o'rniga zamonaviy oyna
$('#lang-sel')?.closest('label')?.addEventListener('click', e => { e.preventDefault(); haptic('sel'); pickLangSheet(); });
$('#cur-sel')?.closest('label')?.addEventListener('click', e => { e.preventDefault(); haptic('sel'); pickCurSheet(); });
api('/api/rates').then(r => {
  RATES = r && r.UZS ? r : {UZS: 1};
  // birinchi marta: O'zbekistonda so'm, Rossiyada rubl, boshqa joyda dollar
  // birinchi kirishda doim dollar; mijoz o'zgartirsa, tanlovi saqlanadi
  if (!CUR_SAVED || !RATES[CUR]) CUR = RATES.USD ? 'USD' : 'UZS';
  rerenderPrices();
}).catch(() => { CUR = 'UZS'; renderCurPicker(); });

// eslatmadagi "To'lovni yakunlash" tugmasi (?pay=ID) — to'g'ridan-to'g'ri to'lov sahifasini ochadi
const PAY_ID = new URLSearchParams(location.search).get('pay');
if (PAY_ID && IN_TG) api(`/api/orders/${PAY_ID}/pay`).then(p => { if (p.status === 'new' || p.status === 'checking') openPay(p); }).catch(() => {});

// ---------------- start ----------------
applyLang(); renderHelp(); renderPay();
const BUY_ID = +new URLSearchParams(location.search).get('buy') || 0;
// katalog: telefonda saqlangan nusxa DARHOL ko'rsatiladi, orqada serverdan tekshiriladi (o'zgarmagan bo'lsa 304 — bir necha bayt)
function hydrate(d) {   // ixcham [id, GB, kun, narx, kunlik] -> obyekt
  d.countries.forEach(c => { c.packages = c.packages.map(p => Array.isArray(p) ? {id: p[0], data_gb: p[1], days: p[2], price: p[3], daily: p[4], old: p[5] || 0} : p); });
  return d;
}
let CAT_ETAG = '', catShown = false;
function setCatalog(d) {
  DATA = hydrate(d); d.countries.forEach(c => FLAG_OF[c.country] = c.flag);
  renderCatalog(); renderBanners();
  if (current && !$('#v-country').classList.contains('hidden')) openCountry(current.country, true);
  if (BUY_ID && !catShown) openPackage(BUY_ID);
  catShown = true;
}
window.setCatalog = setCatalog;

// ---- katalog tepasidagi banner rasmlar (admin yuklaydi); yo'q bo'lsa oddiy banner ----
let bnTimer = null, bnKey = '';
function renderBanners() {
  const list = DATA.banners || [], box = $('#banners'), track = $('#bn-track'), hero = $('.hero');
  const key = JSON.stringify(list);
  if (key === bnKey) return;
  bnKey = key; clearInterval(bnTimer);
  const pay = $('#pay-row');
  if (!list.length) {   // rasm yo'q — oddiy banner o'z joyida
    box.classList.add('hidden');
    if (hero.parentElement !== box.parentElement) box.after(hero);
    hero.classList.remove('hidden', 'bn-hero');
    if (pay.parentElement !== hero) hero.append(pay);
    return;
  }
  box.classList.remove('hidden');
  track.style.aspectRatio = `${list[0].w} / ${list[0].h}`;
  // yangi rasmlar oldinda, oddiy (ko'k) banner — oxirgi slayd bo'lib qoladi
  track.innerHTML = list.map((b, i) => `<div class="bn" data-i="${i}">
      <img src="${esc(b.img)}" alt="" ${i ? 'loading="lazy"' : 'fetchpriority="high"'} decoding="async"></div>`).join('')
    + '<div class="bn bn-last" data-i="-1"></div>';
  box.append(pay);
  hero.classList.remove('hidden'); hero.classList.add('bn-hero');
  track.querySelector('.bn-last').append(hero);
  const n = list.length + 1;
  $('#bn-dots').innerHTML = Array.from({length: n}, (_, i) => `<i class="${i ? '' : 'on'}"></i>`).join('');
  const dots = [...$$('#bn-dots i')];
  let cur = 0;
  const go = i => { cur = (i + n) % n; track.scrollTo({left: cur * track.clientWidth, behavior: 'smooth'}); };
  track.onscroll = () => {
    const i = Math.round(track.scrollLeft / Math.max(1, track.clientWidth));
    if (i !== cur) { cur = i; dots.forEach((d, k) => d.classList.toggle('on', k === i)); }
  };
  const auto = () => { clearInterval(bnTimer); bnTimer = setInterval(() => { if (!document.hidden && !$('#v-catalog').classList.contains('hidden')) go(cur + 1); }, 5000); };
  track.onpointerdown = () => clearInterval(bnTimer);
  track.onpointerup = track.onpointercancel = auto;
  auto();
  $$('#bn-track .bn[data-i]').forEach(el => el.onclick = () => {
    const i = +el.dataset.i; if (i < 0) return;
    const l = list[i].link || {};
    if (l.type === 'country') {
      const c = DATA.countries.find(c => c.country === l.value);
      if (c) openCountry(c.country);
    } else if (l.type === 'countries' && Array.isArray(l.value)) {
      haptic('sel'); setPick(l.value);
    } else if (l.type === 'url' && l.value) {
      haptic('sel');
      if (/^https:\/\/t\.me\//.test(l.value) && IN_TG) tg.openTelegramLink(l.value);
      else if (IN_TG) tg.openLink(l.value); else window.open(l.value, '_blank');
    }
  });
}
// banner bir nechta davlatni ko'rsatsa — katalog shu davlatlar bilan filtrlanadi
let PICK = null;
function setPick(names) {
  PICK = names && names.length ? names : null;
  $('#q').value = ''; region = '';
  $$('#regions .pill').forEach(p => p.classList.toggle('on', !p.dataset.r));
  renderCountries();
  if (PICK) $('#pick-bar')?.scrollIntoView({behavior: 'smooth', block: 'start'});
}
try {
  const c = JSON.parse(localStorage.getItem('cat2') || 'null');
  if (c && c.d && c.d.countries) { CAT_ETAG = c.e || ''; setCatalog(c.d); }
} catch (e) {}
async function fetchCatalog() {
  try {
    const r = await fetch('/api/catalog', {headers: {'X-Init-Data': tg?.initData || '', ...(CAT_ETAG ? {'If-None-Match': CAT_ETAG} : {})}, cache: 'no-cache'});
    if (r.status === 304) return;
    if (!r.ok) throw new Error(r.status);
    const text = await r.text(), d = JSON.parse(text);
    CAT_ETAG = r.headers.get('ETag') || '';
    try { localStorage.setItem('cat2', JSON.stringify({e: CAT_ETAG, d: JSON.parse(text)})); } catch (e) {}
    setCatalog(d);
  } catch (e) {
    if (!catShown) $('#countries').innerHTML = `<div class="empty">${t('load_fail')}</div>`;
  }
}
fetchCatalog();
document.addEventListener('visibilitychange', () => { if (!document.hidden && catShown) fetchCatalog(); });

// admin paneli fayli faqat admin uchun yuklanadi (mijozga 45 KB kam)
function loadAdmin() {
  return window.Admin ? Promise.resolve() : new Promise((ok, no) => {
    const s = document.createElement('script'); s.src = '/static/admin.js?v=' + ADMIN_VER; s.onload = ok; s.onerror = no; document.head.append(s);
  });
}
if (IN_TG) api('/api/me').then(r => {
  const qs = new URLSearchParams(location.search);
  if (r.is_admin) loadAdmin().then(() => {
    $('#nav-admin').classList.remove('hidden'); window.Admin?.init();
    if (qs.get('chat') && !qs.get('support')) window.Admin?.openChat(+qs.get('chat'));
  }).catch(() => {});
  setSupUnread(r.support_unread || 0);
  ME = r;
  if (qs.get('support')) openSupport();
  loadRef();
  // til: botda/Mini App'da oxirgi tanlangani (bazada) asosiy — eski havoladagi ?lang= uni qaytarib yubormaydi
  if (r.lang) switchLang(r.lang, false); else saveLang();
  // valyuta: boshqa qurilmada yoki oldin tanlangan bo'lsa — o'sha
  if (r.currency && r.currency !== CUR) {
    CUR_SAVED = r.currency;
    try { localStorage.setItem('cur', r.currency); } catch (_) {}
    if (RATES[r.currency]) { CUR = r.currency; rerenderPrices(); } else CUR = r.currency;
  } else if (!r.currency && CUR_SAVED && IN_TG) api('/api/lang', {method: 'POST', body: JSON.stringify({currency: CUR_SAVED})}).catch(() => {});
  if (r.country) { PAY_COUNTRY = r.country; renderPay(); }
}).catch(() => {});


// ---- gorizontal tugmalar qatori (.pills): kompyuterda sichqoncha g'ildiragi va sudrash bilan aylantirish ----
(() => {
  const strip = e => e.target.closest?.('.pills');
  document.addEventListener('wheel', e => {
    const el = strip(e);
    if (!el || el.scrollWidth <= el.clientWidth || Math.abs(e.deltaX) > Math.abs(e.deltaY)) return;
    const max = el.scrollWidth - el.clientWidth;
    if ((e.deltaY > 0 && el.scrollLeft >= max - 1) || (e.deltaY < 0 && el.scrollLeft <= 0)) return;
    el.scrollLeft += e.deltaY;
    e.preventDefault();
  }, {passive: false});
  let drag = null;
  document.addEventListener('pointerdown', e => {
    if (e.pointerType !== 'mouse') return;  // telefonda barmoq bilan o'zi ishlaydi
    const el = strip(e);
    if (el && el.scrollWidth > el.clientWidth) drag = {el, x: e.clientX, left: el.scrollLeft, moved: false};
  });
  document.addEventListener('pointermove', e => {
    if (!drag) return;
    const dx = e.clientX - drag.x;
    if (Math.abs(dx) > 4) drag.moved = true;
    if (drag.moved) drag.el.scrollLeft = drag.left - dx;
  });
  let dragEnd = 0;
  document.addEventListener('pointerup', () => { if (drag?.moved) dragEnd = Date.now(); drag = null; });
  // sudrab bo'lgach tugma bosilib ketmasin
  document.addEventListener('click', e => { if (Date.now() - dragEnd < 80 && strip(e)) { e.stopPropagation(); e.preventDefault(); } }, true);
})();
