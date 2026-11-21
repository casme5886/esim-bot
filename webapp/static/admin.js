/* Booking eSIM Mini App — admin paneli (faqat ADMIN_IDS uchun; server ham har so'rovni tekshiradi) */
(() => {
  const som = n => Number(n || 0).toLocaleString('ru-RU').replace(/[\s,]/g, ' ') + " so'm";
  const gbS = (g, daily) => g ? `${+g} GB${daily ? '/kun' : ''}` : 'Cheksiz';
  const REG = Object.fromEntries(REGIONS.map(r => [r.id, r.uz]));
  const ST = {checking: ['🔎 Chek tekshirilsin', 's-checking'], paid: ["⏳ To'langan — QR yuboring", 's-paid'],
              delivered: ['✅ Yetkazilgan', 's-delivered'], cancelled: ['❌ Bekor', 's-cancelled'], new: ["To'lov kutilmoqda", 's-new']};
  let tab = 'stats', group = 'pending', editing = null, pkgCache = [];

  // ---------- umumiy ----------
  function setTab(t) {
    tab = t;
    $$('#admin-seg button').forEach(b => b.classList.toggle('on', b.dataset.a === t));
    ['stats', 'orders', 'chat', 'pkgs', 'promo', 'card'].forEach(x => $('#a-' + x).classList.toggle('hidden', x !== t));
    ({stats: loadStats, orders: loadOrders, chat: loadChats, pkgs: loadPkgs, promo: loadPromo, card: loadCard})[t]();
  }
  $$('#admin-seg button').forEach(b => b.onclick = () => { haptic('sel'); setTab(b.dataset.a); });

  let chatUnread = 0;
  async function refreshBadge() {
    try { const c = await api('/api/admin/chats'); chatUnread = c.unread; setDot('#a-chat-dot', chatUnread); } catch (e) {}
    try {
      const list = await api('/api/admin/orders?group=pending');
      const n = list.length;
      setDot('#a-dot', n); setDot('#nav-dot', n + chatUnread);
      return list;
    } catch (e) { return null; }
  }
  const setDot = (s, n) => { const el = $(s); if (el) { el.textContent = n || ''; el.classList.toggle('hidden', !n); } };

  // ---------- yordam chati ----------
  async function loadChats() {
    const box = $('#a-chat');
    box.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
    let r; try { r = await api('/api/admin/chats'); } catch (e) { box.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
    chatUnread = r.unread; setDot('#a-chat-dot', chatUnread);
    const when = at => { const d = new Date(String(at).replace(' ', 'T') + 'Z');
      return d.toDateString() === new Date().toDateString() ? d.toLocaleTimeString('ru', {hour: '2-digit', minute: '2-digit'}) : d.toLocaleDateString('ru', {day: '2-digit', month: '2-digit'}); };
    box.innerHTML = r.chats.length ? '<div class="list">' + r.chats.map(c => `
      <div class="row chat-row ${c.unread ? 'unread' : ''}" data-uid="${c.user_id}">
        <div class="ch-ava">${esc(((c.full_name || c.username || '?').trim()[0] || '?').toUpperCase())}</div>
        <div class="grow"><div class="name">${esc(c.full_name || c.username || c.user_id)}${c.username ? ` <small>@${esc(c.username)}</small>` : ''}</div>
          <div class="sub">${c.last_admin ? '↩️ ' : ''}${c.last_photo && !c.last_text ? '📷 Surat' : esc((c.last_text || '').slice(0, 70))}</div></div>
        <div class="ch-meta"><small>${when(c.last_at)}</small>${c.unread ? `<b class="cnt">${c.unread}</b>` : ''}</div></div>`).join('') + '</div>'
      : `<div class="list"><div class="empty"><span class="big">💬</span>Hali hech kim yozmagan.<br>Mijozlar Mini App'dagi «Yordam» bo'limidan yoki botning o'ziga yozsa, shu yerda chiqadi.</div></div>`;
    $$('#a-chat [data-uid]').forEach(r => r.onclick = () => { haptic('sel'); openChat(+r.dataset.uid, r.querySelector('.name').firstChild.textContent); });
  }

  function openChat(uid, name) {
    window.openChat({admin: true, title: name || ('#' + uid), sub: 'ID ' + uid, empty: 'Xabarlar yo\'q. Birinchi bo\'lib yozishingiz mumkin.',
      url: '/api/admin/chats/' + uid,
      back: () => { show('admin'); setTab('chat'); },
      onInfo: (u, box) => {
        if (!u) return;
        if (!name) { const h = $('#v-chat .chat-head b'); if (h) h.textContent = u.full_name || u.username || ('#' + uid); }
        $('#ch-sub').innerHTML = `${u.username ? `<a data-user="${esc(u.username)}">@${esc(u.username)}</a> · ` : ''}ID ${uid}${u.lang ? ' · ' + esc(u.lang.toUpperCase()) : ''}`;
        $('#ch-sub [data-user]')?.addEventListener('click', e => tg?.openTelegramLink?.('https://t.me/' + e.target.dataset.user));
        box.innerHTML = `<div class="ch-user"><span>🧾 ${u.orders} ta buyurtma · ${som(u.spent)} · 💰 bonus ${som(u.balance || 0)}</span>
          ${(u.last_orders || []).map(o => `<span class="ch-o">#${o.id} ${flagHtml(o.flag)} ${esc(o.country)} · ${gbS(o.data_gb, o.daily)}/${o.days}k · ${(ST[o.status] || [o.status])[0]}</span>`).join('')}</div>`;
      }});
    setTimeout(refreshBadge, 1500);
  }

  // ---------- statistika ----------
  let statDays = 30;
  const PMN = {card: 'Karta', humo: 'Humo', uzcard: 'Uzcard', click: 'Click', payme: 'Payme', telegram: 'Telegram', online: 'Click/Payme',
               click_link: 'Click havola', payme_link: 'Payme havola', uzum_link: 'Uzum havola'};
  const short = n => { n = +n || 0; const a = Math.abs(n);
    return a >= 1e9 ? (n / 1e9).toFixed(1).replace('.0', '') + ' mlrd' : a >= 1e6 ? (n / 1e6).toFixed(1).replace('.0', '') + ' mln'
      : a >= 1e3 ? Math.round(n / 1e3) + ' ming' : String(Math.round(n)); };
  async function loadStats() {
    const box = $('#a-stats');
    const periods = [[1, 'Bugun'], [7, '7 kun'], [30, '30 kun'], [90, '90 kun'], [0, 'Hammasi']];
    box.innerHTML = `<div class="pills">${periods.map(([d, l]) => `<button class="pill ${d === statDays ? 'on' : ''}" data-d="${d}">${l}</button>`).join('')}</div>
      <div id="st-body"><div class="skeleton"></div><div class="skeleton"></div></div>`;
    $$('#a-stats .pill').forEach(p => p.onclick = () => { haptic('sel'); statDays = +p.dataset.d; loadStats(); });
    let s;
    try { s = await api('/api/admin/stats?days=' + statDays); }
    catch (e) { $('#st-body').innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
    const delta = (cur, prev) => {
      if (!s.prev || !prev) return '';
      const d = Math.round((cur - prev) / Math.abs(prev) * 100);
      return `<span class="st-d ${d >= 0 ? 'up' : 'down'}">${d >= 0 ? '▲' : '▼'} ${Math.abs(d)}%</span>`;
    };
    const margin = s.revenue ? Math.round(s.profit / s.revenue * 100) : 0;
    // kunlik grafik (bo'sh kunlar ham ko'rinsin)
    const span = statDays || 30, map = Object.fromEntries(s.daily.map(d => [d.d, d]));
    const now = new Date(Date.now() + 5 * 3600e3), days = [];
    for (let i = span - 1; i >= 0; i--) { const d = new Date(now - i * 864e5).toISOString().slice(0, 10); days.push(map[d] || {d, sold: 0, revenue: 0, profit: 0}); }
    const mx = Math.max(1, ...days.map(d => d.revenue));
    const chart = span > 1 ? `<div class="card st-chart"><div class="st-ch-h"><b>Kunlik tushum</b><small><i class="lg rev"></i>tushum <i class="lg pro"></i>foyda</small></div>
      <div class="st-bars">${days.map(d => `<div class="st-bar" title="${d.d}: ${som(d.revenue)} · foyda ${som(d.profit)} · ${d.sold} ta">
        <i style="height:${d.revenue / mx * 100}%"></i><em style="height:${Math.max(0, d.profit) / mx * 100}%"></em></div>`).join('')}</div>
      <div class="st-ax"><span>${days[0].d.slice(5).split('-').reverse().join('.')}</span><span>${days[days.length - 1].d.slice(5).split('-').reverse().join('.')}</span></div></div>` : '';
    const top = s.top.length ? s.top.map(c => `<div class="row" style="cursor:default"><div class="flag">${flagHtml(c.flag)}</div>
        <div class="grow"><div class="name">${esc(c.country)}</div><div class="sub">${som(c.revenue)} · foyda <b style="color:#16A34A">${som(c.profit)}</b></div></div><b>${c.n} ta</b></div>`).join('')
      : '<div class="empty">Bu davrda sotuv yo\'q</div>';
    const meth = s.methods.length ? `<div class="section-title">💳 To'lov usullari</div><div class="card st-meth">${s.methods.map(m => `
        <div class="st-mrow"><span>${esc(PMN[m.m] || m.m)}</span><div class="st-mbar"><i style="width:${m.n / s.sold * 100}%"></i></div><b>${m.n}</b></div>`).join('')}</div>` : '';
    const pr = s.promos.length ? `<div class="section-title">🎟 Promo-kodlar</div><div class="card">${s.promos.map(p => `
        <div class="st-mrow"><span><b>${esc(p.promo === 'REF' ? "Do'st taklifi" : p.promo)}</b></span><span>${p.n} ta</span><b>−${som(p.discount)}</b></div>`).join('')}</div>` : '';
    $('#st-body').innerHTML = `
      <div class="stats">
        <div class="stat"><div class="v">${short(s.revenue)}</div><div class="l">Tushum, so'm ${delta(s.revenue, s.prev?.revenue)}</div></div>
        <div class="stat"><div class="v" style="color:${s.profit >= 0 ? '#16A34A' : 'var(--danger)'}">${short(s.profit)}</div><div class="l">Sof foyda · ${margin}% ${delta(s.profit, s.prev?.profit)}</div></div>
        <div class="stat"><div class="v">${s.sold}</div><div class="l">Sotilgan eSIM ${delta(s.sold, s.prev?.sold)}</div></div>
        <div class="stat"><div class="v">${short(s.avg)}</div><div class="l">O'rtacha chek</div></div>
        <div class="stat"><div class="v">${s.buyers}</div><div class="l">Xaridorlar · qayta: ${s.repeat_buyers}</div></div>
        <div class="stat"><div class="v">${s.new_users}</div><div class="l">Yangi foydalanuvchi (jami ${s.users})</div></div>
        ${statDays !== 1 ? `<div class="stat"><div class="v">${short(s.today.revenue)}</div><div class="l">Bugun: ${s.today.sold} ta · foyda ${short(s.today.profit)}</div></div>` : ''}
        <div class="stat"><div class="v" style="color:${s.pending ? 'var(--danger)' : 'inherit'}">${s.pending}</div><div class="l">Kutilayotgan · to'lanmagan ${s.unpaid}</div></div>
        <div class="stat wide"><div class="v">${som(s.cost)}</div><div class="l">Trip.com tannarxi · chegirmalar ${som(s.discount)} · bekor ${s.cancelled}</div></div>
        ${s.ref_invited || s.cashback_total ? `<div class="stat wide"><div class="v">${s.ref_invited}</div><div class="l">Do'st taklifi bilan kelgan · referal bonusi ${som(s.ref_bonus)} · keshbek ${som(s.cashback_total)} · mijozlar balansida ${som(s.balance_total)}</div></div>` : ''}
      </div>
      ${s.pending ? `<button class="btn" id="go-pending">🧾 ${s.pending} ta buyurtmani ko'rish</button>` : ''}
      ${chart}
      <div class="section-title">🏆 Eng ko'p sotilgan davlatlar</div>
      <div class="list">${top}</div>${meth}${pr}
      <p class="st-note">Foyda = sotuv narxi − Trip.com tannarxi (buyurtma paytidagi kurs bo'yicha). Karta/Click komissiyasi hisobga olinmagan.</p>`;
    $('#go-pending')?.addEventListener('click', () => { group = 'pending'; setTab('orders'); });
  }

  // ---------- buyurtmalar ----------
  async function loadOrders() {
    const box = $('#a-orders');
    const groups = [['pending', '⏳ Kutilmoqda'], ['delivered', '✅ Yetkazilgan'], ['cancelled', '❌ Bekor'], ['all', 'Hammasi']];
    box.innerHTML = `<div class="pills">${groups.map(([g, l]) => `<button class="pill ${g === group ? 'on' : ''}" data-g="${g}">${l}</button>`).join('')}</div>
      <div id="a-olist"><div class="skeleton"></div><div class="skeleton"></div></div>`;
    $$('#a-orders .pill').forEach(p => p.onclick = () => { haptic('sel'); group = p.dataset.g; loadOrders(); });
    try {
      const list = group === 'pending' ? await refreshBadge() : await api('/api/admin/orders?group=' + group);
      if (!list) throw new Error("Yuklab bo'lmadi");
      $('#a-olist').innerHTML = list.length ? list.map(orderHtml).join('')
        : `<div class="list"><div class="empty"><span class="big">${group === 'pending' ? '✨' : '📭'}</span>${group === 'pending' ? "Kutilayotgan buyurtma yo'q" : "Buyurtma yo'q"}</div></div>`;
      list.forEach(bindOrder);
    } catch (e) { $('#a-olist').innerHTML = `<div class="card">${esc(e.message)}</div>`; }
  }

  function orderHtml(o) {
    const [label, cls] = ST[o.status] || [o.status, ''];
    const who = o.username ? `<a data-user="${esc(o.username)}">@${esc(o.username)}</a>` : esc(o.full_name || o.user_id);
    let body = '';
    if (o.status === 'checking') {
      body = `${o.has_receipt ? `<button class="btn soft" data-act="receipt">🧾 Chekni ko'rish</button><div class="receipt hidden"></div>` : ''}
        <div class="btns"><button class="btn" data-act="approve">✅ To'lov keldi</button><button class="btn danger" data-act="reject">❌ Rad etish</button></div>`;
    } else if (o.status === 'paid') {
      const TS = {preparing: "🤖 Trip.com ochilmoqda…", confirm: "🤖 Telegram'da «Sotib ol»ni tasdiqlang", paying: "🤖 To'lanmoqda…",
                  bought: `🤖 Sotib olindi${o.trip_order_no ? ' (' + esc(o.trip_order_no) + ')' : ''} — QR kutilmoqda`,
                  failed: "⚠️ Avto-xarid to'xtadi (Telegram'dagi xabarni ko'ring)", login: "⚠️ Trip.com'ga kirish kerak: /trip_login",
                  skipped: "✋ Qo'lda qilinadi"};
      const busy = ['preparing', 'confirm', 'paying', 'bought'].includes(o.trip_status);
      const tripLine = o.trip_status ? `<div class="hint-box" style="margin-top:10px">${TS[o.trip_status] || esc(o.trip_status)}${o.trip_price ? ` · $${esc(o.trip_price)}` : ''}</div>` : '';
      const autoBtn = o.has_trip && !busy && !['done'].includes(o.trip_status)
        ? `<button class="btn soft" data-act="autobuy">🤖 Trip.com'dan avto-sotib olish</button>` : '';
      body = `${tripLine}${autoBtn}<div class="hint-box">🛒 Trip.com'dan oling: <b>${esc(o.country)} · ${gbS(o.data_gb, o.daily)} · ${o.days} kun</b>${o.cost_usd ? ` (~$${+o.cost_usd})` : ''}
          <button class="btn sm soft" data-act="copy" style="margin-top:8px">📋 Nusxa olish</button></div>
        <label class="upload"><input type="file" accept="image/*,.pdf" hidden data-file>
          <span class="pv">📷</span><span class="ut">Trip.com PDF vaucheri, QR rasm yoki skrinshotni tanlang</span></label>
        <label class="field" style="margin:10px 0 0"><input data-lpa placeholder="yoki LPA:1$... kod (ixtiyoriy)" autocomplete="off"></label>
        <label class="field" style="margin:10px 0 0"><input data-note placeholder="Mijozga izoh (ixtiyoriy)" autocomplete="off"></label>
        <div class="btns"><button class="btn" data-act="deliver">📤 Mijozga yuborish</button><button class="btn danger" data-act="cancel" style="flex:.5">↩️ Bekor</button></div>`;
    }
    return `<div class="order" id="o-${o.id}">
      <div class="top"><b>#${o.id} · ${flagHtml(o.flag)} ${esc(o.country)}</b><span class="badge ${cls}">${label}</span></div>
      <div class="meta">${gbS(o.data_gb, o.daily)} / ${o.days} kun · <b style="color:var(--text)">${som(o.price)}</b> · ${o.payment_method === 'telegram' ? 'Click/Payme' : 'Karta'}<br>
        👤 ${who} · ${esc((o.created_at || '').slice(5, 16))}</div>
      ${body}</div>`;
  }

  function bindOrder(o) {
    const el = $('#o-' + o.id); if (!el) return;
    const act = (name, fn) => el.querySelector(`[data-act="${name}"]`)?.addEventListener('click', fn);
    el.querySelector('[data-user]')?.addEventListener('click', e => tg?.openTelegramLink('https://t.me/' + e.target.dataset.user));

    act('receipt', async e => {
      const box = el.querySelector('.receipt');
      if (!box.classList.contains('hidden')) { box.classList.add('hidden'); return; }
      e.target.disabled = true;
      try {
        const r = await api(`/api/admin/orders/${o.id}/receipt`, {raw: true});
        const blob = await r.blob(); const url = URL.createObjectURL(blob);
        box.innerHTML = blob.type.startsWith('image/') ? `<img src="${url}">` : `<a class="btn soft" href="${url}" target="_blank">📄 Faylni ochish</a>`;
        box.classList.remove('hidden');
      } catch (err) { alert_(err.message); }
      e.target.disabled = false;
    });
    const simple = (name, question, okMsg) => act(name, async e => {
      if (question && !(await confirm_(question))) return;
      e.target.disabled = true;
      try { await api(`/api/admin/orders/${o.id}/${name}`, {method: 'POST'}); haptic('success'); toast(okMsg); loadOrders(); }
      catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
    });
    simple('approve', `#${o.id}: ${som(o.price)} kartangizga tushganini tasdiqlaysizmi?`, "To'lov tasdiqlandi");
    simple('reject', `#${o.id} to'lovini rad etasizmi? Mijozga xabar boradi.`, 'Rad etildi');
    simple('autobuy', `#${o.id}: Trip.com sahifasi ochilib, narx Telegram'da tasdiqlashga yuboriladi. Boshlaymi?`, "🤖 Boshlandi — Telegram'ni kuting");
    simple('cancel', `#${o.id} bekor qilinsinmi? Pulni mijozga qaytarishingiz kerak bo'ladi.`, 'Bekor qilindi');

    act('copy', () => {
      const txt = `${o.country} ${o.daily ? 'Daily ' + (+o.data_gb) + 'GB' : 'Total ' + (+o.data_gb) + 'GB'} ${o.days} days`;
      navigator.clipboard?.writeText(txt).then(() => toast('Nusxa olindi'), () => alert_(txt));
    });
    const fileInp = el.querySelector('[data-file]');
    fileInp?.addEventListener('change', () => {
      const f = fileInp.files[0]; if (!f) return;
      el.querySelector('.ut').textContent = f.name;
      el.querySelector('.pv').innerHTML = f.type.startsWith('image/') ? `<img src="${URL.createObjectURL(f)}">` : '📄';
    });
    act('deliver', async e => {
      const f = fileInp.files[0], lpa = el.querySelector('[data-lpa]').value.trim(), note = el.querySelector('[data-note]').value.trim();
      if (!f && !lpa) return alert_('QR kod rasmini tanlang yoki LPA kodni yozing.');
      if (!(await confirm_(`#${o.id} uchun eSIM mijozga yuborilsinmi?`))) return;
      const fd = new FormData();
      if (f) fd.append('file', f, f.name);
      if (lpa) fd.append('lpa', lpa);
      if (note) fd.append('note', note);
      e.target.disabled = true; e.target.textContent = 'Yuborilmoqda…';
      try {
        const r = await api(`/api/admin/orders/${o.id}/deliver`, {method: 'POST', body: fd}); haptic('success');
        if (r.lpa_found) toast('✅ Yuborildi · kod avtomatik ajratildi'); else alert_("✅ Yuborildi, lekin fayldan kod o'qilmadi — faylning o'zi ketdi.");
        loadOrders();
      }
      catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; e.target.textContent = '📤 Mijozga yuborish'; }
    });
  }

  // ---------- paketlar ----------
  async function loadPkgs() {
    const box = $('#a-pkgs');
    box.innerHTML = `<div class="card pr-card" id="price-card"></div><div class="card" id="auto-card"></div><div class="card" id="imp-card"></div>
      <button class="btn" id="p-new">➕ Yangi paket</button><div id="p-form"></div>
      <div class="section-title" style="margin-top:14px"><span>Paketlar</span><span id="p-count"></span></div>
      <div class="search" style="position:static"><input id="p-q" type="search" placeholder="Davlatni qidiring…" autocomplete="off"></div>
      <button class="btn soft" id="p-flt-tg" style="margin:8px 0;width:100%;display:flex;justify-content:space-between;align-items:center"><span id="p-flt-lbl">🔍 Filtr</span><span id="p-flt-ar">▼</span></button>
      <div id="p-flt-box" style="display:none">
      <div class="pr-chips" id="p-flt" style="margin:0 0 8px"></div>
      <div style="display:flex;gap:8px;margin-bottom:10px">
        <label class="field" style="flex:1;margin:0"><span>Mintaqa</span><select id="p-reg"><option value="">Hammasi</option>${REGIONS.map(r => `<option value="${r.id}">${esc(r.uz)}</option>`).join('')}<option value="-">Tanlanmagan</option></select></label>
        <label class="field" style="flex:1;margin:0"><span>Saralash</span><select id="p-sort"><option value="name">Nomi (A–Z)</option><option value="cnt">Faol paketlar soni</option><option value="cheap">Eng arzon narx</option><option value="exp">Eng qimmat narx</option></select></label>
      </div></div>
      <div id="p-list"><div class="skeleton"></div></div>`;
    $('#p-q').oninput = () => renderPkgList();
    $('#p-reg').onchange = () => renderPkgList();
    $('#p-sort').onchange = () => renderPkgList();
    let fltOpen = false; try { fltOpen = localStorage.getItem('pkgFltOpen') === '1'; } catch (_) {}
    const applyFlt = () => { $('#p-flt-box').style.display = fltOpen ? '' : 'none'; $('#p-flt-ar').textContent = fltOpen ? '▲' : '▼'; };
    $('#p-flt-tg').onclick = () => { fltOpen = !fltOpen; try { localStorage.setItem('pkgFltOpen', fltOpen ? '1' : '0'); } catch (_) {} haptic('sel'); applyFlt(); };
    applyFlt();
    $('#p-new').onclick = () => { editing = null; renderForm(); };
    renderPricing(); renderAuto(); renderImport();
    try { pkgCache = await api('/api/admin/packages'); renderPkgList(); }
    catch (e) { $('#p-list').innerHTML = `<div class="card">${esc(e.message)}</div>`; }
  }

  const opened = new Set();
  let pkgFilter = 'all';
  // Davlatlar bo'yicha filtrlar: nima ekanini bilish uchun (Top, yashirin, avto-xarid va h.k.)
  const PKG_FILTERS = [
    ['all', 'Hammasi', () => true],
    ['top', '⭐ Top', ps => ps.some(p => p.popular)],
    ['notop', 'Top emas', ps => !ps.some(p => p.popular)],
    ['active', '✅ Faol', ps => ps.some(p => p.active)],
    ['hidden', '🚫 Yashirin', ps => !ps.some(p => p.active)],
    ['partial', '◐ Qisman yashirin', ps => ps.some(p => p.active) && ps.some(p => !p.active)],
    ['auto', '🤖 Avto-xarid', ps => ps.some(p => p.trip_url)],
    ['manual', '✋ Avtosiz', ps => ps.some(p => p.active && !p.trip_url)],
    ['nocost', '💲 Tannarxsiz', ps => ps.some(p => !+p.cost_usd)],
    ['noreg', '🗺 Mintaqasiz', ps => !ps[0].region],
  ];
  function renderPkgList() {
    const groups = {};
    pkgCache.forEach(p => (groups[p.country] ||= []).push(p));
    const q = ($('#p-q')?.value || '').trim().toLowerCase();
    const reg = $('#p-reg')?.value || '', sort = $('#p-sort')?.value || 'name';
    const flt = PKG_FILTERS.find(f => f[0] === pkgFilter) || PKG_FILTERS[0];
    const base = Object.keys(groups).filter(n => (!q || n.toLowerCase().includes(q))
      && (!reg || (reg === '-' ? !groups[n][0].region : groups[n][0].region === reg)));
    const box = $('#p-flt');
    if (box) {
      box.innerHTML = PKG_FILTERS.map(([id, label, fn]) => {
        const n = base.filter(c => fn(groups[c])).length;
        return `<button data-pf="${id}" class="${id === pkgFilter ? 'on' : ''}">${label} · ${n}</button>`;
      }).join('');
      $$('[data-pf]').forEach(b => b.onclick = () => { pkgFilter = b.dataset.pf; haptic('sel'); renderPkgList(); });
    }
    const minP = c => Math.min(...groups[c].filter(p => p.active).map(p => p.price).concat(groups[c].map(p => p.price)));
    const act = c => groups[c].filter(p => p.active).length;
    const names = base.filter(c => flt[2](groups[c])).sort((a, b) =>
      sort === 'cnt' ? act(b) - act(a) || a.localeCompare(b)
      : sort === 'cheap' ? minP(a) - minP(b)
      : sort === 'exp' ? minP(b) - minP(a)
      : a.localeCompare(b));
    const lbl = $('#p-flt-lbl'); if (lbl) {
      const parts = [];
      if (pkgFilter !== 'all') parts.push(flt[1]);
      if (reg) parts.push(reg === '-' ? 'Mintaqasiz' : (REG[reg] || reg));
      if (sort !== 'name') parts.push($('#p-sort').selectedOptions[0].textContent);
      lbl.textContent = '🔍 Filtr' + (parts.length ? ': ' + parts.join(' · ') : '');
    }
    $('#p-count').textContent = `${names.length} / ${Object.keys(groups).length} davlat · ${pkgCache.filter(p => p.active).length} faol paket`;
    $('#p-list').innerHTML = names.length ? names.map(c => {
      const ps = groups[c].sort((a, b) => (a.daily - b.daily) || (a.data_gb - b.data_gb) || (a.days - b.days)), f = ps[0];
      const pop = ps.some(p => p.popular);
      return `<div class="pkg-group"><div class="head"><div class="flag">${flagHtml(f.flag)}</div>
          <div class="grow"><div class="name">${esc(c)}</div><div class="sub">${esc(REG[f.region || ''] && f.region ? REG[f.region] : 'Mintaqa tanlanmagan')}</div></div>
          <button class="star ${pop ? 'on' : ''}" data-star="${esc(c)}" data-id="${f.id}" title="Mashhur">⭐</button>
          <button class="icon-btn" data-addto="${esc(c)}" title="Shu davlatga paket qo'shish">➕</button>
          <button class="icon-btn" data-open="${esc(c)}">${opened.has(c) ? '▲' : '▼'}</button></div>
        <div class="sub" style="padding:6px 14px 10px">${ps.filter(p => p.active).length} faol${ps.some(p => !p.active) ? ` · ${ps.filter(p => !p.active).length} yashirin` : ''} paket · ${som(Math.min(...ps.map(p => p.price)))} dan${ps.some(p => p.trip_url) ? ' · 🤖' : ''}${pop ? ' · ⭐ Top' : ''}</div>
        ${!opened.has(c) ? '' : ps.map(p => `<div class="pkg-row ${p.active ? '' : 'off'}">
          <div class="grow"><b>${gbS(p.data_gb, p.daily)} · ${p.days} kun</b><div class="sub">${som(p.price)}${p.cost_usd ? ` · tannarx $${+p.cost_usd}` : ''} · ID ${p.id}${p.trip_url ? ' · 🤖 avto' : ''}</div></div>
          <label class="switch"><input type="checkbox" data-toggle="${p.id}" ${p.active ? 'checked' : ''}><span></span></label>
          <button class="icon-btn" data-edit="${p.id}">✏️</button><button class="icon-btn" data-del="${p.id}">🗑</button></div>`).join('')}
      </div>`;
    }).join('') : `<div class="list"><div class="empty"><span class="big">📦</span>Hali paket yo'q.<br>«➕ Yangi paket» bilan birinchisini qo'shing.</div></div>`;

    $$('[data-open]').forEach(b => b.onclick = () => { const c = b.dataset.open; opened.has(c) ? opened.delete(c) : opened.add(c); renderPkgList(); });
    $$('[data-toggle]').forEach(i => i.onchange = async () => {
      try { await api('/api/admin/packages/' + i.dataset.toggle, {method: 'PUT', body: JSON.stringify({active: i.checked})});
        haptic('sel'); toast(i.checked ? "Yoqildi — mijozlarga ko'rinadi" : 'Yashirildi');
        pkgCache.find(p => p.id == i.dataset.toggle).active = i.checked ? 1 : 0; renderPkgList(); }
      catch (e) { alert_(e.message); i.checked = !i.checked; }
    });
    $$('[data-star]').forEach(b => b.onclick = async () => {
      const on = !b.classList.contains('on');
      try { await api('/api/admin/packages/' + b.dataset.id, {method: 'PUT', body: JSON.stringify({popular: on})});
        haptic('sel'); pkgCache.filter(p => p.country === b.dataset.star).forEach(p => p.popular = on ? 1 : 0);
        toast(on ? "⭐ «Mashhur» bo'limiga qo'shildi" : "Mashhur'dan olindi"); renderPkgList(); }
      catch (e) { alert_(e.message); }
    });
    $$('[data-edit]').forEach(b => b.onclick = () => { editing = pkgCache.find(p => p.id == b.dataset.edit); renderForm(); });
    $$('[data-addto]').forEach(b => b.onclick = () => {
      const f = pkgCache.find(p => p.country === b.dataset.addto);
      editing = null; renderForm({country: f.country, flag: f.flag, region: f.region, popular: f.popular});
    });
    $$('[data-del]').forEach(b => b.onclick = async () => {
      const p = pkgCache.find(x => x.id == b.dataset.del);
      if (!(await confirm_(`${p.country} ${gbS(p.data_gb, p.daily)}/${p.days} kun paketini o'chirasizmi?`))) return;
      try { const r = await api('/api/admin/packages/' + p.id, {method: 'DELETE'});
        toast(r.result === 'hidden' ? "Buyurtmasi bor — o'chirilmadi, yashirildi" : "O'chirildi"); loadPkgs(); }
      catch (e) { alert_(e.message); }
    });
  }

  function renderForm(prefill = {}) {
    const p = editing || {country: '', flag: '', region: '', data_gb: '', days: '', price: '', cost_usd: '', popular: 0, ...prefill};
    $('#p-form').innerHTML = `<div class="card" style="margin-top:10px">
      <h3>${editing ? `✏️ Paketni tahrirlash (ID ${editing.id})` : '➕ Yangi paket'}</h3>
      <label class="field"><span>Davlat (ro'yxatdan tanlang yoki o'zingiz yozing)</span>
        <input id="f-country" list="f-presets" value="${esc(p.country)}" placeholder="Masalan: Turkiya" autocomplete="off"></label>
      <datalist id="f-presets">${COUNTRY_PRESETS.map(c => `<option value="${esc(c.uz)}">${esc(c.flag)}</option>`).join('')}</datalist>
      <div class="grid2">
        <label class="field"><span>Bayroq</span><input id="f-flag" value="${esc(p.flag)}" placeholder="🇹🇷" maxlength="8"></label>
        <label class="field"><span>Mintaqa</span><select id="f-region">
          ${REGIONS.map(r => `<option value="${r.id}" ${r.id === (p.region || '') ? 'selected' : ''}>${r.id ? r.uz : '— tanlang —'}</option>`).join('')}</select></label>
      </div>
      <div class="grid3">
        <label class="field"><span>Internet, GB</span><input id="f-gb" inputmode="decimal" value="${p.data_gb === 0 ? '' : esc(p.data_gb)}" placeholder="10"></label>
        <label class="field"><span>Muddat, kun</span><input id="f-days" inputmode="numeric" value="${esc(p.days)}" placeholder="30"></label>
        <label class="field"><span>Tannarx, $</span><input id="f-cost" inputmode="decimal" value="${p.cost_usd ? esc(p.cost_usd) : ''}" placeholder="12.5"></label>
      </div>
      <label class="check"><input type="checkbox" id="f-unl" ${editing && !editing.data_gb ? 'checked' : ''}> Cheksiz internet</label>
      <label class="check"><input type="checkbox" id="f-daily" ${p.daily ? 'checked' : ''}> Kunlik limit (GB har kuni yangilanadi)</label>
      <label class="field"><span>Sotuv narxi, so'm</span><input id="f-price" inputmode="numeric" value="${p.price ? som(p.price).replace(" so'm", '') : ''}" placeholder="150 000"></label>
      <div id="f-margin" class="sub" style="margin:-6px 4px 10px"></div>
      <label class="field"><span>Dollar kursi (foydani hisoblash uchun, saqlanmaydi)</span><input id="f-rate" inputmode="numeric" placeholder="12 800"></label>
      <label class="field"><span>🤖 Trip.com havola (avto-xarid uchun, ixtiyoriy)</span>
        <input id="f-trip" value="${esc(p.trip_url || '')}" placeholder="https://www.trip.com/xthings-to-do/booking-activity?actid=…&optid=…" autocomplete="off"></label>
      <div class="sub" style="margin:-6px 4px 12px">Trip.com'da shu paketni (kun + GB) tanlab «Book now» bosing va ochilgan sahifa havolasini shu yerga qo'ying.</div>
      <label class="check"><input type="checkbox" id="f-pop" ${p.popular ? 'checked' : ''}> ⭐ «Mashhur» bo'limida ko'rsatish</label>
      <div class="btns"><button class="btn" id="f-save">💾 Saqlash</button><button class="btn soft" id="f-close" style="flex:.5">Yopish</button></div>
    </div>`;
    const num = v => +String(v).replace(/[^\d.,]/g, '').replace(',', '.') || 0;
    let rate = 0; try { rate = +localStorage.getItem('usd_rate') || 0; } catch (e) {}
    if (rate) $('#f-rate').value = rate;
    const margin = () => {
      const price = num($('#f-price').value), cost = num($('#f-cost').value), r = num($('#f-rate').value);
      $('#f-margin').innerHTML = price && cost && r
        ? `Tannarx ≈ ${som(Math.round(cost * r))} → foyda <b style="color:${price - cost * r > 0 ? '#20a35a' : 'var(--danger)'}">${som(Math.round(price - cost * r))}</b> (${Math.round((price - cost * r) / price * 100)}%)` : '';
    };
    $('#f-price').oninput = e => { const d = e.target.value.replace(/\D/g, ''); e.target.value = d ? som(d).replace(" so'm", '') : ''; margin(); };
    $('#f-cost').oninput = margin;
    $('#f-rate').oninput = () => { try { localStorage.setItem('usd_rate', num($('#f-rate').value)); } catch (e) {} margin(); };
    margin();
    const syncUnl = () => { $('#f-gb').disabled = $('#f-unl').checked; if ($('#f-unl').checked) $('#f-gb').value = ''; };
    $('#f-unl').onchange = syncUnl; syncUnl();
    $('#f-country').oninput = () => {
      const c = COUNTRY_PRESETS.find(x => x.uz.toLowerCase() === $('#f-country').value.trim().toLowerCase());
      const ex = pkgCache.find(x => x.country.toLowerCase() === $('#f-country').value.trim().toLowerCase());
      const src = ex || c;
      if (src) { $('#f-flag').value = src.flag; $('#f-region').value = src.region || ''; }
    };
    $('#f-close').onclick = () => { editing = null; $('#p-form').innerHTML = ''; };
    $('#f-save').onclick = async e => {
      const body = {
        country: $('#f-country').value.trim(), flag: $('#f-flag').value.trim() || '🌍', region: $('#f-region').value,
        data_gb: $('#f-unl').checked ? 0 : num($('#f-gb').value), days: num($('#f-days').value),
        price: num($('#f-price').value), cost_usd: num($('#f-cost').value), popular: $('#f-pop').checked,
        trip_url: $('#f-trip').value.trim(), daily: $('#f-daily').checked,
      };
      if (!body.country) return alert_('Davlat nomini yozing');
      if (!$('#f-unl').checked && !body.data_gb) return alert_("GB miqdorini yozing yoki «Cheksiz»ni belgilang");
      if (!body.days) return alert_('Muddatni (kun) yozing');
      if (!body.price) return alert_('Sotuv narxini yozing');
      e.target.disabled = true;
      try {
        await api(editing ? '/api/admin/packages/' + editing.id : '/api/admin/packages',
                  {method: editing ? 'PUT' : 'POST', body: JSON.stringify(body)});
        haptic('success'); toast(editing ? '✅ Saqlandi' : "✅ Paket qo'shildi");
        editing = null; loadPkgs(); refreshCatalog();
      } catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
    };
    $('#p-form').scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // ---------- Trip.com'dan import ----------
  let impTimer = null;
  async function renderImport() {
    const card = $('#imp-card'); if (!card) return;
    let s; try { s = await api('/api/admin/import'); } catch (e) { card.innerHTML = esc(e.message); return; }
    if (s.running) {
      const pct = s.total ? Math.round(s.done / s.total * 100) : 0;
      card.innerHTML = `<h3>📥 Trip.com'dan import ketmoqda…</h3>
        <p>${s.done} / ${s.total} davlat · hozir: <b style="color:var(--text)">${esc(s.current || '…')}</b></p>
        <div style="height:8px;background:var(--bg2);border-radius:99px;overflow:hidden;margin:8px 0">
          <div style="height:100%;width:${pct}%;background:var(--accent);transition:width .4s"></div></div>
        <p>➕ ${s.added} yangi · 🔄 ${s.updated} yangilandi · ⚠️ ${s.failed.length} topilmadi</p>
        <p style="font-size:12.5px">Kompyuter va bot yoqiq tursin. Tugaganda Telegram'ga hisobot keladi.</p>`;
      clearTimeout(impTimer); impTimer = setTimeout(() => { if (tab === 'pkgs') { renderImport(); } }, 4000);
      return;
    }
    card.innerHTML = `<h3>📥 Trip.com'dan import</h3>
      <p>Bot Trip.com'dan <b style="color:var(--text)">${s.countries_total} ta davlat</b> uchun eSIM paketlarini (1–30 kun, barcha GB)
        qo'shadi va tannarxini yangilaydi. Taxminan ${Math.ceil(s.countries_total * 25 / 60)} daqiqa.</p>
      <p style="font-size:12.5px">Sotuv narxi yuqoridagi <b>Narx sozlamalari</b> bo'yicha hisoblanadi.</p>
      ${s.failed && s.failed.length && s.total ? `<p style="font-size:12.5px">Oxirgi importda topilmagan: ${s.failed.length} ta</p>` : ''}
      <button class="btn soft" id="imp-go">📥 Barcha davlatlarni yangilash</button>`;
    $('#imp-go').onclick = async e => {
      if (!(await confirm_(`Barcha ${s.countries_total} ta davlat Trip.com'dan qayta tekshirilsinmi? Taxminan ${Math.ceil(s.countries_total * 25 / 60)} daqiqa ketadi, bu vaqtda kompyuter yoqiq tursin.`))) return;
      e.target.disabled = true;
      try { await api('/api/admin/import', {method: 'POST', body: '{}'}); haptic('success'); renderImport(); }
      catch (err) { alert_(err.message); e.target.disabled = false; }
    };
  }

  // ---------- narx sozlamalari (ustama) ----------
  async function renderPricing() {
    const card = $('#price-card'); if (!card) return;
    let p; try { p = await api('/api/admin/pricing'); } catch (e) { card.innerHTML = esc(e.message); return; }
    const sum = n => Math.round(n).toLocaleString('ru-RU').replace(/,/g, ' ') + " so'm";
    const price = (cost, mk, rt) => Math.max(1000, Math.ceil(cost * mk * rt / 1000) * 1000);
    const chips = [1.3, 1.5, 1.8, 2, 2.5, 3];
    card.innerHTML = `<h3>💰 Narx sozlamalari</h3>
      <p>Sotuv narxi = Trip.com narxi × <b>ustama</b> × dollar kursi (1 000 so'mgacha yaxlitlanadi). Saqlaganda <b>${p.packages}</b> ta paket narxi darhol yangilanadi.</p>
      <div class="pr-mk"><span>Ustama</span><b id="pr-mk-v"></b><small id="pr-pct"></small></div>
      <input type="range" id="pr-mk" min="1" max="4" step="0.05" value="${p.markup}">
      <div class="pr-chips">${chips.map(c => `<button data-v="${c}">×${c}</button>`).join('')}</div>
      <label class="field" style="margin-top:12px"><span>Dollar kursi (so'm)</span><input id="pr-rate" inputmode="numeric" value="${p.rate}"></label>
      <div class="pr-prev" id="pr-prev"></div>
      <button class="btn" id="pr-save">💾 Saqlash va narxlarni yangilash</button>`;
    const upd = () => {
      const mk = +$('#pr-mk').value, rt = +String($('#pr-rate').value).replace(/\s/g, '') || 0;
      $('#pr-mk-v').textContent = '×' + mk.toFixed(2).replace(/\.?0+$/, '');
      $('#pr-pct').textContent = `+${Math.round((mk - 1) * 100)}% foyda`;
      $$('#price-card .pr-chips button').forEach(b => b.classList.toggle('on', Math.abs(+b.dataset.v - mk) < 0.001));
      const ex = [0.5, 3, 15];
      $('#pr-prev').innerHTML = `<div class="pr-prev-h">Misol</div>` + ex.map(c => {
        const s = price(c, mk, rt), cost = c * rt;
        return `<div class="pr-row"><span>Trip.com $${c}</span><span>→ <b>${sum(s)}</b></span><span class="pr-gain">+${sum(s - cost)}</span></div>`;
      }).join('') + (mk < 1.15 ? `<div class="pr-warn">⚠️ Ustama juda past — karta komissiyasi va kurs farqini qoplamasligi mumkin.</div>` : '');
    };
    $('#pr-mk').oninput = upd; $('#pr-rate').oninput = upd;
    $$('#price-card .pr-chips button').forEach(b => b.onclick = () => { haptic('sel'); $('#pr-mk').value = b.dataset.v; upd(); });
    upd();
    $('#pr-save').onclick = async e => {
      const body = {markup: $('#pr-mk').value, rate: $('#pr-rate').value, min_price: 0, apply: true};
      if (!(await confirm_(`Ustama ×${(+body.markup).toFixed(2).replace(/\.?0+$/, '')}, kurs ${body.rate}. ${p.packages} ta paket narxi yangilansinmi?`))) return;
      e.target.disabled = true;
      try {
        const r = await api('/api/admin/pricing', {method: 'POST', body: JSON.stringify(body)});
        haptic('success'); toast(`✅ Saqlandi · ${r.changed} ta paket narxi o'zgardi`);
        refreshCatalog(); renderPricing();
        try { pkgCache = await api('/api/admin/packages'); renderPkgList(); } catch (_) {}
      } catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
    };
  }

  function refreshCatalog() { api('/api/catalog').then(d => window.setCatalog(d)).catch(() => {}); }

  // ---------- karta ----------
  const fmtCard = v => String(v || '').replace(/\D/g, '').slice(0, 16).replace(/(\d{4})(?=\d)/g, '$1 ');
  async function loadCard() {
    const TYPE = n => { n = String(n || '').replace(/\D/g, '');
      return n.startsWith('9860') ? 'Humo' : /^(8600|5614|6262)/.test(n) ? 'Uzcard' : n.startsWith('4') ? 'Visa' : /^[52]/.test(n) ? 'Mastercard' : 'Karta'; };
    let cards = [], online = [], links = {};
    try { const r = await api('/api/admin/card'); cards = (r.cards || []).map(c => ({number: c.number, holder: c.holder})); online = r.online || []; links = r.links || {}; }
    catch (e) { alert_(e.message); }
    if (!cards.length) cards = [{number: '', holder: ''}];
    const render = () => {
      $('#a-card').innerHTML = `
        <div class="card"><h3>💳 Kartalar (Humo, Uzcard…)</h3>
          <p>Mijoz to'lov sahifasida qaysi kartaga o'tkazishini tanlaydi. 3 tagacha karta qo'shish mumkin.</p></div>
        ${cards.map((c, i) => `
          <div class="bank-card"><div class="top">${i + 1}-karta · <b id="ty-${i}">${TYPE(c.number)}</b></div>
            <div class="num" id="pv-num-${i}">${fmtCard(c.number) || '•••• •••• •••• ••••'}</div><div class="hold" id="pv-hold-${i}">${esc((c.holder || 'ISM FAMILIYA').toUpperCase())}</div></div>
          <div class="card">
            <label class="field"><span>Karta raqami</span><input data-i="${i}" data-f="number" inputmode="numeric" autocomplete="off" placeholder="9860 1234 5678 9012" maxlength="19" value="${fmtCard(c.number)}"></label>
            <label class="field"><span>Karta egasi</span><input data-i="${i}" data-f="holder" autocomplete="off" placeholder="SARDOR ..." maxlength="60" value="${esc(c.holder || '')}"></label>
            ${cards.length > 1 ? `<button class="btn soft danger" data-del="${i}">🗑 Kartani olib tashlash</button>` : ''}
          </div>`).join('')}
        ${cards.length < 3 ? '<button class="btn soft" id="c-add">➕ Yana karta qo\'shish</button>' : ''}
        <button class="btn" id="c-save">💾 Saqlash</button>
        <div class="card" style="margin-top:12px"><h3>🔗 To'lov havolalari (Click, Payme, Uzum)</h3>
          <p>Hamyoningiz yoki to'lov sahifangiz havolasini qo'ying. Mijoz tugmani bosib to'laydi, keyin chek yuklaydi, siz tasdiqlaysiz.
          Havolaga <code>{amount}</code> yozsangiz, o'rniga buyurtma summasi qo'yiladi. Bo'sh qoldirilgani mijozga ko'rinmaydi.</p>
          ${[['click', 'Click', 'https://my.click.uz/...'], ['payme', 'Payme', 'https://payme.uz/...'], ['uzum', 'Uzum', 'https://...uzum...']].map(([k, n, ph]) => `
          <label class="field"><span>${n} havolasi ${links[k] ? '✅' : ''}</span><input data-l="${k}" type="url" inputmode="url" autocomplete="off" placeholder="${ph}" value="${esc(links[k] || '')}"></label>`).join('')}
          <button class="btn" id="l-save">💾 Havolalarni saqlash</button></div>
        <div class="card" style="margin-top:12px"><h3>⚡ Click / Payme (darhol to'lov)</h3>
          <p>${online.length ? '✅ Ulangan: <b>' + online.map(x => x === 'online' ? 'Click / Payme' : x[0].toUpperCase() + x.slice(1)).join(', ') + '</b>'
            : "Ulanmagan. @BotFather → Payments bo'limidan Click va Payme tokenlarini oling va .env fayliga <code>CLICK_PROVIDER_TOKEN</code> / <code>PAYME_PROVIDER_TOKEN</code> qilib yozing."}</p></div>`;
      $$('#a-card input[data-i]').forEach(inp => inp.oninput = e => {
        const i = +e.target.dataset.i, f = e.target.dataset.f;
        if (f === 'number') { e.target.value = fmtCard(e.target.value); cards[i].number = e.target.value;
          $('#pv-num-' + i).textContent = e.target.value || '•••• •••• •••• ••••'; $('#ty-' + i).textContent = TYPE(e.target.value); }
        else { cards[i].holder = e.target.value; $('#pv-hold-' + i).textContent = (e.target.value || 'ISM FAMILIYA').toUpperCase(); }
      });
      $$('#a-card input[data-l]').forEach(inp => inp.oninput = e => { links[e.target.dataset.l] = e.target.value.trim(); });
      $('#l-save').onclick = async e => {
        e.target.disabled = true;
        try { const r = await api('/api/admin/paylinks', {method: 'POST', body: JSON.stringify(links)});
          links = r.links || {}; render(); haptic('success'); toast('✅ Havolalar saqlandi'); refreshCatalog(); }
        catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
      };
      $$('#a-card [data-del]').forEach(b => b.onclick = () => { cards.splice(+b.dataset.del, 1); render(); });
      $('#c-add')?.addEventListener('click', () => { cards.push({number: '', holder: ''}); render(); });
      $('#c-save').onclick = async e => {
        e.target.disabled = true;
        try { const r = await api('/api/admin/card', {method: 'POST', body: JSON.stringify({cards})});
          cards = r.cards.map(c => ({number: c.number, holder: c.holder})); render(); haptic('success'); toast('✅ Kartalar saqlandi'); }
        catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
      };
    };
    render();
  }

  // ---------- promo-kodlar va referal ----------
  async function loadPromo() {
    const box = $('#a-promo');
    box.innerHTML = '<div class="skeleton"></div><div class="skeleton"></div>';
    let d; try { d = await api('/api/admin/promos'); } catch (e) { box.innerHTML = `<div class="card">${esc(e.message)}</div>`; return; }
    const r = d.ref, today = new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10);
    const st = p => !p.active ? ['⚪️ O\'chirilgan', 'off'] : p.expires && p.expires < today ? ['⌛ Muddati o\'tgan', 'off']
      : p.max_uses && p.used >= p.max_uses ? ['✔️ Tugagan', 'off'] : ['🟢 Faol', 'on'];
    box.innerHTML = `<div class="card" id="sale-card"></div><div class="card" id="bn-card"></div><div class="card" id="bal-card"></div>
      <div class="card"><h3>🎁 Referal va keshbek</h3>
        <p>Har bir mijozning shaxsiy havolasi bor (Buyurtmalarim sahifasida). Do'sti shu havola orqali kelib birinchi marta xarid qilsa:
          do'stiga chegirma, taklif qilganga bonus balans beriladi. Balans keyingi xaridda chegirma sifatida ishlatiladi.</p>
        <label class="tgl"><input type="checkbox" id="rf-on" ${r.enabled ? 'checked' : ''}><span>Yoqilgan</span></label>
        <div class="two"><label class="field"><span>Do'stga chegirma, %</span><input id="rf-new" inputmode="numeric" value="${r.new_pct}"></label>
          <label class="field"><span>Taklif qilganga bonus, %</span><input id="rf-bonus" inputmode="numeric" value="${r.bonus_pct}"></label></div>
        <label class="field"><span>💰 Har bir xariddan keshbek, % (0 = o'chiq)</span><input id="rf-cb" inputmode="decimal" value="${r.cashback_pct ?? ''}" placeholder="1"></label>
        <p style="font-size:12.5px">Keshbek eSIM mijozga yetkazilgach to'lagan summasidan hisoblanadi va bonus balansiga tushadi; mijozga bot xabar yuboradi.
          Balans keyingi xaridda chegirma sifatida ishlatiladi.</p>
        <button class="btn soft" id="rf-save">💾 Saqlash</button></div>
      <div class="card"><h3>🎟 Yangi promo-kod</h3>
        <label class="field"><span>Kod (lotin harf/raqam)</span><input id="pc-code" placeholder="SALE10" maxlength="20" autocapitalize="characters" autocomplete="off"></label>
        <div class="seg" id="pc-kind"><button class="on" data-k="percent">Foiz, %</button><button data-k="fixed">Summa, so'm</button></div>
        <div class="two"><label class="field"><span id="pc-vl">Chegirma, %</span><input id="pc-val" inputmode="numeric" placeholder="10"></label>
          <label class="field"><span>Limit (0 = cheksiz)</span><input id="pc-max" inputmode="numeric" value="0"></label></div>
        <label class="field"><span>Amal qilish muddati (ixtiyoriy)</span><input id="pc-exp" type="date" min="${today}"></label>
        <button class="btn" id="pc-save">➕ Promo-kod yaratish</button>
        <p style="font-size:12.5px">Har bir mijoz bitta kodni bir marta ishlata oladi. Chegirma hech qachon Trip.com tannarxidan pastga tushirmaydi.</p></div>
      <div class="section-title"><span>Promo-kodlar</span><span>${d.promos.length}</span></div>
      <div class="list">${d.promos.length ? d.promos.map(p => { const [sl, sc] = st(p); return `
        <div class="row promo-item ${sc}" style="cursor:default"><div class="grow">
          <div class="name"><code>${esc(p.code)}</code> · ${p.kind === 'percent' ? '−' + p.value + '%' : '−' + som(p.value)}</div>
          <div class="sub">${sl} · ishlatildi ${p.used}${p.max_uses ? ' / ' + p.max_uses : ''}${p.expires ? ' · ' + p.expires + ' gacha' : ''}</div></div>
          <button class="icon-btn" data-pa="${p.active ? 'off' : 'on'}" data-code="${esc(p.code)}" title="${p.active ? "O'chirish" : 'Yoqish'}">${p.active ? '⏸' : '▶️'}</button>
          <button class="icon-btn" data-pa="delete" data-code="${esc(p.code)}" title="O'chirib tashlash">🗑</button></div>`; }).join('')
        : '<div class="empty">Hali promo-kod yo\'q</div>'}</div>`;
    renderSales(); renderBannerAdmin(); renderBalances();
    let kind = 'percent';
    $$('#pc-kind button').forEach(b => b.onclick = () => { kind = b.dataset.k; haptic('sel');
      $$('#pc-kind button').forEach(x => x.classList.toggle('on', x === b));
      $('#pc-vl').textContent = kind === 'percent' ? 'Chegirma, %' : "Chegirma, so'm"; $('#pc-val').placeholder = kind === 'percent' ? '10' : '20000'; });
    $('#pc-code').oninput = e => { e.target.value = e.target.value.toUpperCase().replace(/[^A-Z0-9_-]/g, ''); };
    $('#rf-save').onclick = async e => {
      e.target.disabled = true;
      try { await api('/api/admin/referral', {method: 'POST', body: JSON.stringify({enabled: $('#rf-on').checked,
              new_pct: +$('#rf-new').value || 0, bonus_pct: +$('#rf-bonus').value || 0,
              cashback_pct: +String($('#rf-cb').value).replace(',', '.') || 0})}); haptic('success'); toast('✅ Saqlandi'); window.resetRef?.(); }
      catch (err) { alert_(err.message); }
      e.target.disabled = false;
    };
    $('#pc-save').onclick = async e => {
      const body = {code: $('#pc-code').value, kind, value: +String($('#pc-val').value).replace(/\s/g, '') || 0,
                    max_uses: +$('#pc-max').value || 0, expires: $('#pc-exp').value};
      if (!body.code) return alert_('Kodni yozing');
      if (!body.value) return alert_('Chegirma miqdorini yozing');
      e.target.disabled = true;
      try { await api('/api/admin/promos', {method: 'POST', body: JSON.stringify(body)}); haptic('success'); toast('✅ ' + body.code + ' yaratildi'); loadPromo(); }
      catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
    };
    $$('#a-promo [data-pa]').forEach(b => b.onclick = async () => {
      if (b.dataset.pa === 'delete' && !(await confirm_(`${b.dataset.code} o'chirib tashlansinmi?`))) return;
      try { await api(`/api/admin/promos/${encodeURIComponent(b.dataset.code)}/${b.dataset.pa}`, {method: 'POST'}); haptic('sel'); loadPromo(); }
      catch (err) { alert_(err.message); }
    });
  }

  // ---------- davlatlarga chegirma (aksiya) ----------
  async function renderSales(list) {
    const card = $('#sale-card'); if (!card) return;
    if (!list) { try { list = await api('/api/admin/sales'); } catch (e) { card.innerHTML = esc(e.message); return; } }
    const today = new Date(Date.now() + 5 * 3600e3).toISOString().slice(0, 10);
    const countries = (DATA.countries || []).map(c => c.country).sort((a, b) => a.localeCompare(b));
    const who = x => x.countries[0] === '*' ? '🌍 Barcha davlatlar' : x.countries.length <= 3 ? x.countries.map(esc).join(', ')
      : `${x.countries.slice(0, 3).map(esc).join(', ')} va yana ${x.countries.length - 3} ta`;
    card.innerHTML = `<h3>🏷 Davlatlarga chegirma</h3>
      <p>Tanlangan davlatlarning barcha paketlari arzonlashadi. Mijoz katalogda <b style="color:#E5484D">−20%</b> belgisini va eski narxni chizilgan holda ko'radi,
        «🏷 Chegirmalar» bo'limi paydo bo'ladi. Narx hech qachon Trip.com tannarxidan pastga tushmaydi.</p>
      ${list.length ? '<div class="list" style="margin-bottom:10px">' + list.map(x => { const off = x.until && x.until < today; return `
        <div class="row" style="cursor:default;${off ? 'opacity:.5' : ''}"><div class="sale-pct">−${x.pct}%</div>
          <div class="grow"><div class="name">${who(x)}</div><div class="sub">${off ? '⌛ Tugagan' : x.until ? x.until + ' gacha' : 'Muddatsiz'}</div></div>
          <button class="icon-btn" data-sdel="${x.id}">🗑</button></div>`; }).join('') + '</div>' : ''}
      <div class="two"><label class="field"><span>Chegirma, %</span><input id="sl-p" inputmode="numeric" placeholder="20"></label>
        <label class="field"><span>Qachongacha (ixtiyoriy)</span><input id="sl-u" type="date" min="${today}"></label></div>
      <label class="tgl"><input type="checkbox" id="sl-all"><span>🌍 Barcha davlatlar</span></label>
      <div class="field" id="sl-cf"><span>Davlatlar <b id="sl-n"></b></span>
        <div class="search" style="position:static;padding:0 0 6px"><input id="sl-q" type="search" placeholder="Qidirish…" autocomplete="off"></div>
        <div class="bn-cl" id="sl-cl">${countries.map(c => `<label><input type="checkbox" value="${esc(c)}"><span>${flagHtml(FLAG_OF[c])} ${esc(c)}</span></label>`).join('')}</div></div>
      <button class="btn" id="sl-add">🏷 Chegirmani yoqish</button>`;
    const picked = () => $$('#sl-cl input:checked').map(x => x.value);
    const updN = () => { $('#sl-n').textContent = picked().length ? `· ${picked().length} ta tanlandi` : ''; };
    $$('#sl-cl input').forEach(x => x.onchange = updN);
    $('#sl-q').oninput = e => { const q = e.target.value.trim().toLowerCase();
      $$('#sl-cl label').forEach(l => l.classList.toggle('hidden', !!q && !l.textContent.toLowerCase().includes(q))); };
    $('#sl-all').onchange = e => $('#sl-cf').classList.toggle('hidden', e.target.checked);
    $('#sl-add').onclick = async e => {
      const pct = +$('#sl-p').value, all = $('#sl-all').checked, cs = picked();
      if (!(pct >= 1 && pct <= 90)) return alert_('Chegirma 1–90% oralig\'ida bo\'lsin');
      if (!all && !cs.length) return alert_('Davlatlarni belgilang yoki «Barcha davlatlar»ni tanlang');
      if (!(await confirm_(`${all ? 'Barcha davlatlar' : cs.length + ' ta davlat'} uchun −${pct}% chegirma yoqilsinmi?`))) return;
      e.target.disabled = true;
      try { const l = await api('/api/admin/sales', {method: 'POST', body: JSON.stringify({pct, all, countries: cs, until: $('#sl-u').value})});
        haptic('success'); toast('✅ Chegirma yoqildi'); renderSales(l); refreshCatalog(); }
      catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
    };
    $$('#sale-card [data-sdel]').forEach(b => b.onclick = async () => {
      if (!(await confirm_('Chegirma o\'chirilsinmi? Narxlar odatdagiga qaytadi.'))) return;
      try { const l = await api(`/api/admin/sales/${b.dataset.sdel}/delete`, {method: 'POST'}); haptic('sel'); renderSales(l); refreshCatalog(); }
      catch (err) { alert_(err.message); }
    });
  }

  // ---------- mijozlar bonus balansi ----------
  let balQ = '', balTimer = null;
  async function renderBalances() {
    const card = $('#bal-card'); if (!card) return;
    card.innerHTML = `<h3>💰 Mijozlar bonus balansi</h3>
      <p>Mijozni toping (ID, @username yoki ism) va bonusini qo'shing / ayiring. Bo'sh qidiruvda — balansi borlar.</p>
      <div class="search" style="position:static"><input id="bal-q" type="search" placeholder="ID, @username yoki ism…" autocomplete="off" value="${esc(balQ)}"></div>
      <div id="bal-list"><div class="skeleton"></div></div><div id="bal-edit"></div>`;
    $('#bal-q').oninput = e => { balQ = e.target.value; clearTimeout(balTimer); balTimer = setTimeout(loadBalList, 250); };
    loadBalList();
  }
  async function loadBalList() {
    const box = $('#bal-list'); if (!box) return;
    let list; try { list = await api('/api/admin/balances?q=' + encodeURIComponent(balQ)); } catch (e) { box.innerHTML = esc(e.message); return; }
    box.innerHTML = list.length ? '<div class="list">' + list.map(u => `
      <div class="row" data-bu="${u.id}"><div class="ch-ava">${esc(((u.full_name || u.username || '?').trim()[0] || '?').toUpperCase())}</div>
        <div class="grow"><div class="name">${esc(u.full_name || u.username || u.id)}${u.username ? ` <small style="color:var(--hint)">@${esc(u.username)}</small>` : ''}</div>
          <div class="sub">ID ${u.id} · ${u.orders} ta xarid</div></div><b>${som(u.balance)}</b></div>`).join('') + '</div>'
      : `<div class="empty">${balQ ? 'Topilmadi' : "Hozircha hech kimda bonus yo'q"}</div>`;
    $$('#bal-list [data-bu]').forEach(r => r.onclick = () => { haptic('sel'); editBalance(+r.dataset.bu); });
  }
  async function editBalance(uid) {
    const box = $('#bal-edit');
    let u; try { u = await api('/api/admin/balances/' + uid); } catch (e) { return alert_(e.message); }
    const fmt = at => { const d = new Date(String(at).replace(' ', 'T') + 'Z'); return isNaN(d) ? '' : d.toLocaleDateString('ru', {day: '2-digit', month: '2-digit'}); };
    const draw = () => {
      box.innerHTML = `<div class="bal-ed">
        <div class="bal-h"><div><b>${esc(u.full_name || u.username || uid)}</b><small>ID ${uid}${u.username ? ' · @' + esc(u.username) : ''}</small></div>
          <div class="bal-now"><small>Hozirgi balans</small><b>${som(u.balance)}</b></div></div>
        <div class="pr-chips">${[5000, 10000, 20000, 50000].map(v => `<button data-add="${v}">+${(v / 1000)} ming</button>`).join('')}</div>
        <div class="two"><label class="field"><span>Qo'shish / ayirish (−)</span><input id="bal-d" inputmode="numeric" placeholder="masalan 10000 yoki -5000"></label>
          <label class="field"><span>Yoki aniq qiymat</span><input id="bal-set" inputmode="numeric" placeholder="masalan 0"></label></div>
        <label class="field"><span>Sabab (mijozga ham ko'rinadi)</span><input id="bal-r" maxlength="200" placeholder="masalan: kechikish uchun uzr sifatida"></label>
        <label class="tgl"><input type="checkbox" id="bal-n" checked><span>Bonus qo'shilsa, mijozga bot orqali xabar yuborish</span></label>
        <div class="btns"><button class="btn" id="bal-save">💾 Saqlash</button><button class="btn soft" id="bal-close">Yopish</button></div>
        ${u.log && u.log.length ? `<div class="bal-log"><small>Oxirgi o'zgarishlar</small>${u.log.map(l => `<div><span>${fmt(l.created_at)}</span>
          <b style="color:${l.delta >= 0 ? '#16A34A' : 'var(--danger)'}">${l.delta >= 0 ? '+' : ''}${som(l.delta)}</b><span>${esc(l.reason || '')}</span></div>`).join('')}</div>` : ''}
      </div>`;
      $$('#bal-edit [data-add]').forEach(b => b.onclick = () => { $('#bal-d').value = b.dataset.add; $('#bal-set').value = ''; haptic('sel'); });
      $('#bal-close').onclick = () => { box.innerHTML = ''; };
      $('#bal-save').onclick = async e => {
        const d = String($('#bal-d').value).replace(/[\s,]/g, ''), st = String($('#bal-set').value).replace(/[\s,]/g, '');
        if (!d && !st) return alert_('Summani yozing');
        const body = {reason: $('#bal-r').value, notify: $('#bal-n').checked};
        if (st) body.set = +st; else body.delta = +d;
        const next = st ? +st : Math.max(0, u.balance + (+d));
        if (!(await confirm_(`${u.full_name || uid}: ${som(u.balance)} → ${som(next)}. Saqlansinmi?`))) return;
        e.target.disabled = true;
        try { const r = await api('/api/admin/balances/' + uid, {method: 'POST', body: JSON.stringify(body)});
          u.balance = r.balance; u.log = r.log; haptic('success'); toast('✅ Balans: ' + som(r.balance)); draw(); loadBalList(); }
        catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; }
      };
    };
    draw();
    box.scrollIntoView({behavior: 'smooth', block: 'start'});
  }

  // ---------- katalog bannerlari ----------
  async function renderBannerAdmin(list) {
    const card = $('#bn-card'); if (!card) return;
    if (!list) { try { list = await api('/api/admin/banners'); } catch (e) { card.innerHTML = esc(e.message); return; } }
    const countries = (DATA.countries || []).map(c => c.country).sort((a, b) => a.localeCompare(b));
    const linkTxt = l => !l || !l.type ? 'Bosilganda hech narsa' : l.type === 'country' ? '→ ' + esc(l.value)
      : l.type === 'countries' ? `→ ${l.value.length} ta davlat: ${esc(l.value.slice(0, 3).join(', '))}${l.value.length > 3 ? '…' : ''}` : '🔗 ' + esc(l.value);
    card.innerHTML = `<h3>🖼 Katalog bannerlari</h3>
      <p>Katalog tepasidagi banner o'rnida rasm chiqadi. Bir nechtasi bo'lsa — 5 soniyada almashadi, mijoz surib ham ko'radi.
        Rasm yo'q bo'lsa — oddiy ko'k banner. <b style="color:var(--text)">Tavsiya: 1200×500 px</b> (barcha bannerlar bir xil o'lchamda bo'lsin).</p>
      ${list.map((b, i) => `<div class="bn-adm">
        <img src="${esc(b.img)}" alt="">
        <div class="bn-adm-r"><small>${i + 1}-banner · ${b.w}×${b.h}</small><span>${linkTxt(b.link)}</span>
          <div class="bn-adm-b">
            <button class="icon-btn" data-bn="up" data-id="${b.id}" ${i ? '' : 'disabled'}>↑</button>
            <button class="icon-btn" data-bn="down" data-id="${b.id}" ${i < list.length - 1 ? '' : 'disabled'}>↓</button>
            <button class="icon-btn" data-bn="delete" data-id="${b.id}">🗑</button></div></div></div>`).join('')}
      ${list.length < 6 ? `<div class="bn-new">
        <label class="pay-drop" id="bn-drop"><input type="file" id="bn-file" accept="image/*" hidden>
          <div id="bn-prev"><span class="big">🖼</span><span>Rasm tanlash</span></div></label>
        <label class="field"><span>Bosilganda</span><select id="bn-lt"><option value="">Hech narsa</option>
          <option value="country">Davlat(lar)ni ko'rsatish</option><option value="url">Havolani ochish</option></select></label>
        <div class="field hidden" id="bn-c-f"><span>Davlatlar — bir yoki bir nechtasini belgilang <b id="bn-c-n"></b></span>
          <div class="search" style="position:static;padding:0 0 6px"><input id="bn-cq" type="search" placeholder="Qidirish…" autocomplete="off"></div>
          <div class="bn-cl" id="bn-cl">${countries.map(c => `<label><input type="checkbox" value="${esc(c)}"><span>${flagHtml(FLAG_OF[c])} ${esc(c)}</span></label>`).join('')}</div></div>
        <label class="field hidden" id="bn-u-f"><span>Havola</span><input id="bn-u" placeholder="https://t.me/kanalingiz"></label>
        <button class="btn" id="bn-add" disabled>➕ Bannerni qo'shish</button></div>` : '<p>Ko\'pi bilan 6 ta banner.</p>'}`;
    let file = null;
    const picked = () => $$('#bn-cl input:checked').map(x => x.value);
    const updN = () => { const n = picked().length; $('#bn-c-n') && ($('#bn-c-n').textContent = n ? `· ${n} ta tanlandi` : ''); };
    $$('#bn-cl input').forEach(x => x.onchange = updN);
    $('#bn-cq')?.addEventListener('input', e => {
      const q = e.target.value.trim().toLowerCase();
      $$('#bn-cl label').forEach(l => l.classList.toggle('hidden', !!q && !l.textContent.toLowerCase().includes(q)));
    });
    $('#bn-lt')?.addEventListener('change', e => {
      $('#bn-c-f').classList.toggle('hidden', e.target.value !== 'country');
      $('#bn-u-f').classList.toggle('hidden', e.target.value !== 'url');
    });
    $('#bn-file')?.addEventListener('change', e => {
      file = e.target.files[0] || null;
      if (file && file.size > 10 * 1024 * 1024) { file = null; return alert_('Rasm 10 MB dan kichik bo\'lsin'); }
      $('#bn-prev').innerHTML = file ? `<img src="${URL.createObjectURL(file)}" alt="">` : '<span class="big">🖼</span><span>Rasm tanlash</span>';
      $('#bn-add').disabled = !file;
    });
    $('#bn-add')?.addEventListener('click', async e => {
      if (!file) return;
      const lt = $('#bn-lt').value;
      const fd = new FormData();
      fd.append('image', file, file.name || 'banner.jpg'); fd.append('link_type', lt);
      if (lt === 'country' && !picked().length) { e.target.disabled = false; return alert_('Kamida bitta davlatni belgilang'); }
      fd.set('link_type', lt === 'country' ? 'countries' : lt);
      fd.append('link_value', lt === 'country' ? JSON.stringify(picked()) : lt === 'url' ? $('#bn-u').value : '');
      e.target.disabled = true; e.target.textContent = '…';
      try { const l = await api('/api/admin/banners', {method: 'POST', body: fd}); haptic('success'); toast('✅ Banner qo\'shildi'); renderBannerAdmin(l); refreshCatalog(); }
      catch (err) { haptic('error'); alert_(err.message); e.target.disabled = false; e.target.textContent = '➕ Bannerni qo\'shish'; }
    });
    $$('#bn-card [data-bn]').forEach(b => b.onclick = async () => {
      if (b.dataset.bn === 'delete' && !(await confirm_('Banner o\'chirilsinmi?'))) return;
      try { const l = await api(`/api/admin/banners/${b.dataset.id}/${b.dataset.bn}`, {method: 'POST'}); haptic('sel'); renderBannerAdmin(l); refreshCatalog(); }
      catch (err) { alert_(err.message); }
    });
  }

  // ---------- narxlarni avto-yangilash ----------
  async function renderAuto() {
    const card = $('#auto-card'); if (!card) return;
    let a; try { a = await api('/api/admin/autoupdate'); } catch (e) { card.innerHTML = esc(e.message); return; }
    const hours = Array.from({length: 24}, (_, h) => h);
    const L = a.last;
    card.innerHTML = `<h3>🔄 Narxlarni avtomatik yangilash</h3>
      <p>Har kecha Trip.com narxlari o'zi tekshiriladi. Tannarx o'zgargan paketning narxi ustama bo'yicha qayta hisoblanadi —
        qimmatlagan paket zarar bilan sotilmaydi. Tugagach Telegram'ga qisqa hisobot keladi.</p>
      <label class="tgl"><input type="checkbox" id="au-on" ${a.enabled ? 'checked' : ''}><span>Har kuni yangilash</span></label>
      <label class="field"><span>Soat (Toshkent vaqti)</span><select id="au-h">${hours.map(h => `<option value="${h}" ${h === a.hour ? 'selected' : ''}>${String(h).padStart(2, '0')}:00</option>`).join('')}</select></label>
      ${L ? `<p style="font-size:12.5px">Oxirgisi: <b style="color:var(--text)">${esc(L.at)}</b> · ${L.ok}/${L.total} davlat · 📈 ${L.up} · 📉 ${L.down} · ➕ ${L.added}</p>` : '<p style="font-size:12.5px">Hali ishga tushmagan.</p>'}
      <button class="btn soft" id="au-save">💾 Saqlash</button>`;
    $('#au-save').onclick = async e => {
      e.target.disabled = true;
      try { await api('/api/admin/autoupdate', {method: 'POST', body: JSON.stringify({enabled: $('#au-on').checked, hour: +$('#au-h').value})});
        haptic('success'); toast('✅ Saqlandi'); }
      catch (err) { alert_(err.message); }
      e.target.disabled = false;
    };
  }

  window.Admin = {
    openChat(uid) { show('admin'); setTab('chat'); openChat(uid); },
    init() { refreshBadge(); setInterval(refreshBadge, 30000); },
    open() { setTab(tab); },
  };
})();
