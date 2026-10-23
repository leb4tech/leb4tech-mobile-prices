(() => {
  'use strict';
  const root = document.querySelector('#leb4tech-index');
  if (!root) return;
  const $ = selector => root.querySelector(selector);
  const status = $('.notice'), grid = $('.grid'), summary = $('.summary');
  const input = $('#phone-input'), brand = $('#brand-filter'), maxPrice = $('#price-filter');
  const SIX_HOURS = 6 * 60 * 60 * 1000;
  const conditions = {new:'جديد',used:'مستعمل',refurbished:'مجدّد'};
  let data = null, cached = false;
  const endpoint = root.dataset.url;
  const cacheKey = 'leb4tech-prices-v1:' + endpoint;
  const validDate = value => typeof value === 'string' && /(?:Z|[+-]\d{2}:\d{2})$/.test(value) && Number.isFinite(Date.parse(value)) && Date.parse(value) <= Date.now();
  function https(value) {
    try { const u = new URL(value); return u.protocol === 'https:' && !u.username && !u.password; } catch { return false; }
  }
  function validate(value) {
    if (!value || value.schema_version !== 1 || !Array.isArray(value.phones) || value.phones.length > 10000) throw Error('schema');
    if (value.updated_at !== null && !validDate(value.updated_at)) throw Error('date');
    const ids = new Set(), variants = new Set();
    value.phones.forEach(p => {
      if (!p || typeof p.id !== 'string' || !/^[a-f0-9]{24}$/.test(p.id) || ids.has(p.id)) throw Error('id');
      ids.add(p.id);
      const variant = JSON.stringify([p.brand,p.model,p.storage_gb,p.ram_gb,p.sim,p.warranty,p.condition]);
      if (variants.has(variant)) throw Error('duplicate'); variants.add(variant);
      if (![p.brand,p.model].every(v => typeof v === 'string' && /^[A-Za-z0-9][A-Za-z0-9 .+()/-]*$/.test(v))) throw Error('name');
      if (!Number.isInteger(p.storage_gb) || p.storage_gb <= 0 || !(p.ram_gb === null || Number.isInteger(p.ram_gb) && p.ram_gb > 0)) throw Error('storage');
      if (![p.sim,p.warranty].every(v => typeof v === 'string' && v.trim()) || !conditions[p.condition]) throw Error('variant');
      if (!Array.isArray(p.specs) || p.specs.length > 12 || !p.specs.every(s => typeof s === 'string' && s.trim())) throw Error('specs');
      if (p.image !== null && (!p.image || !https(p.image.url) || !https(p.image.permission_url))) throw Error('image');
      if (!validDate(p.updated_at) || !Array.isArray(p.offers) || !p.offers.length) throw Error('offers');
      const owners = new Set(), stores = new Set(), hosts = new Set();
      p.offers.forEach(o => {
        if (!o || ![o.owner,o.store].every(v => typeof v === 'string' && v.trim()) || !https(o.url) || o.currency !== 'USD' || o.available !== true || o.condition !== p.condition || !Number.isFinite(o.price_usd) || o.price_usd <= 0 || o.observed_at !== p.updated_at) throw Error('offer');
        const owner = o.owner.trim().toLowerCase(), store = o.store.trim().toLowerCase(), host = new URL(o.url).hostname;
        if (owners.has(owner) || stores.has(store) || hosts.has(host)) throw Error('independence');
        owners.add(owner); stores.add(store); hosts.add(host);
      });
      if (p.offers.length >= 2) {
        const mean = p.offers.reduce((s,o) => s + o.price_usd, 0) / p.offers.length;
        if (p.status !== 'verified' || !Number.isFinite(p.average_usd) || p.average_usd <= 0 || Math.abs(p.average_usd - mean) > 0.005001) throw Error('average');
      } else if (p.status !== 'insufficient_data' || p.average_usd !== null) throw Error('quorum');
    });
    const newest = value.phones.length ? Math.max(...value.phones.map(p => Date.parse(p.updated_at))) : null;
    if ((value.updated_at === null ? null : Date.parse(value.updated_at)) !== newest) throw Error('update');
    return value;
  }
  function element(tag, text, className) {
    const el = document.createElement(tag);
    if (text !== undefined) el.textContent = text;
    if (className) el.className = className;
    return el;
  }
  function date(value) { return new Intl.DateTimeFormat('ar-LB',{dateStyle:'medium',timeStyle:'short',timeZone:'Asia/Beirut'}).format(new Date(value)); }
  function message(text) { status.textContent = text; }
  function render() {
    if (!data) return;
    grid.replaceChildren();
    const query = input.value.trim().toLowerCase();
    const ceiling = maxPrice.value === '' ? Infinity : Number(maxPrice.value);
    const phones = data.phones.filter(p => (p.brand + ' ' + p.model).toLowerCase().includes(query) && (!brand.value || p.brand === brand.value) && (ceiling === Infinity || p.average_usd !== null && p.average_usd <= ceiling));
    summary.textContent = 'عدد النتائج: ' + phones.length;
    if (!data.phones.length) message((cached ? 'تعذّر تحميل البيانات الحديثة؛ نعرض آخر نسخة محفوظة. ' : '') + 'لا تتوفر أسعار موثّقة حالياً. لن نعرض أسعاراً أو مواصفات تقديرية.');
    else {
      const stale = data.phones.some(p => Date.now() - Date.parse(p.updated_at) >= SIX_HOURS);
      message((cached ? 'تعذّر تحميل البيانات الحديثة؛ نعرض آخر نسخة محفوظة. ' : '') + (stale ? 'تنبيه: تتضمن القائمة أسعاراً قديمة؛ تحقّق من المتجر قبل الشراء. ' : '') + 'آخر تحديث ناجح: ' + date(data.updated_at));
    }
    if (!phones.length) grid.append(element('p','لا توجد هواتف مطابقة للفلاتر الحالية.'));
    phones.forEach(p => {
      const card = element('article');
      const heading = element('h2',p.brand + ' ' + p.model,'en'); heading.dir = 'ltr'; card.append(heading);
      if (p.image) {
        const image = element('img'); image.src = p.image.url; image.alt = p.brand + ' ' + p.model; image.loading = 'lazy'; image.referrerPolicy = 'no-referrer';
        image.addEventListener('error',() => image.remove()); card.append(image);
      }
      card.append(element('div',`${p.storage_gb} GB · RAM: ${p.ram_gb === null ? 'غير موثّقة' : p.ram_gb + ' GB'}`));
      card.append(element('div','النسخة: ' + p.sim + ' · الحالة: ' + conditions[p.condition]));
      card.append(element('div','الضمان: ' + p.warranty,'muted'));
      const old = Date.now() - Date.parse(p.updated_at) >= SIX_HOURS;
      card.append(element('span',old ? 'سعر قديم' : p.status === 'verified' ? 'متوسط موثّق' : 'مصادر غير كافية','badge'));
      card.append(element('p',p.average_usd === null ? 'لا يتوفر متوسط موثوق' : new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(p.average_usd),'price'));
      card.append(element('p',p.average_usd === null ? 'يلزم متجران مستقلان للنسخة نفسها.' : 'متوسط حسابي من ' + p.offers.length + ' متاجر مستقلة.','muted'));
      if (p.specs.length) { const ul = element('ul'); p.specs.forEach(s => ul.append(element('li',s))); card.append(ul); }
      const time = element('time','آخر تحقق: ' + date(p.updated_at)); time.dateTime = p.updated_at; card.append(time);
      const details = element('details'); details.append(element('summary','المصادر والأسعار'));
      p.offers.forEach(o => {
        const row = element('p'); const a = element('a',o.store); a.href = o.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
        row.append(a,document.createTextNode(' — ' + new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(o.price_usd))); details.append(row);
      }); card.append(details); grid.append(card);
    });
  }
  async function getJSON(url) {
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(),12000);
    try {
      const response = await fetch(url,{mode:'cors',credentials:'omit',cache:'no-cache',signal:controller.signal});
      if (!response.ok) throw Error('http');
      const text = await response.text(); if (text.length > 4_000_000) throw Error('size');
      return JSON.parse(text);
    } finally { clearTimeout(timer); }
  }
  async function load() {
    $('.reload').disabled = true;
    try {
      if (!endpoint) throw Error('config');
      data = validate(await getJSON(endpoint)); cached = false;
      try { localStorage.setItem(cacheKey,JSON.stringify(data)); } catch { /* Storage may be disabled. */ }
    } catch {
      if (!data) { try { const value = localStorage.getItem(cacheKey); if (value) data = validate(JSON.parse(value)); } catch { /* Reject invalid cache. */ } }
      cached = true;
      if (!data) message('تعذّر تحميل ملف الأسعار. تحقّق من الرابط العام ودعم CORS ثم أعد المحاولة.');
    } finally { $('.reload').disabled = false; }
    if (data) {
      const selected = brand.value; brand.replaceChildren(element('option','كل الشركات')); brand.firstChild.value = '';
      [...new Set(data.phones.map(p => p.brand))].sort().forEach(name => { const opt = element('option',name); opt.value = name; brand.append(opt); }); brand.value = selected;
      render();
    }
    try {
      const report = await getJSON(new URL('status.json',new URL(endpoint,location.href)).href);
      $('.source-status').textContent = Array.isArray(report.failures) && report.failures.length ? 'تعذّر تحديث بعض المصادر؛ قد تبقى الأسعار السابقة مع تاريخها الأصلي.' : report.state === 'not_configured' ? 'مصادر الأسعار قيد المراجعة ولم تُفعّل بعد.' : '';
    } catch { $('.source-status').textContent = 'تقرير حالة المصادر غير متاح.'; }
  }
  input.addEventListener('input',render); brand.addEventListener('change',render); maxPrice.addEventListener('input',render);
  $('#search-btn').addEventListener('click',render); $('.reload').addEventListener('click',load);
  setInterval(render,60000);
  load();
})();
