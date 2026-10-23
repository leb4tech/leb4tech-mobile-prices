(() => {
  'use strict';
  const root = document.querySelector('#leb4tech-index');
  const panel = root?.querySelector('.image-prices');
  if (!panel) return;
  const $ = s => panel.querySelector(s);
  const search = $('#image-search'), brand = $('#image-brand'), max = $('#image-price');
  const notice = $('.image-notice'), reload = $('.image-reload');
  const endpoint = new URL('image-prices.json',new URL(root.dataset.url,location.href)).href;
  const cacheKey = 'leb4tech-image-list-v1:' + endpoint;
  const today = () => new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Beirut'}).format(new Date());
  let data = null, cached = false, loading = false;
  function el(tag,text) { const n = document.createElement(tag); if (text !== undefined) n.textContent = text; return n; }
  function validate(v) {
    if (!v || v.format !== 'image_price_list_v1' || v.currency !== 'USD' || v.currency_basis !== 'user_confirmed' || v.method !== 'manual_transcription_from_user_image' || v.retailer_verified !== false) throw Error('basis');
    if (typeof v.list_date !== 'string' || !/^\d{4}-\d{2}-\d{2}$/.test(v.list_date) || !Number.isFinite(Date.parse(v.list_date)) || new Date(v.list_date).toISOString().slice(0,10) !== v.list_date || v.list_date > today()) throw Error('date');
    const url = new URL(v.source_url);
    if (url.protocol !== 'https:' || url.username || url.password || !(v.source_name === null || typeof v.source_name === 'string' && v.source_name.trim())) throw Error('source');
    if (!Array.isArray(v.listings) || !v.listings.length || v.listings.length > 1000 || typeof v.source_warranty_text !== 'string' || !v.source_warranty_text.trim()) throw Error('list');
    const ids = new Set();
    for (const r of v.listings) {
      if (!r || ![r.source_section,r.listing_text].every(x => typeof x === 'string' && x.trim() && x.length <= 500) || !Number.isFinite(r.price_usd) || r.price_usd <= 0 || r.price_usd > 1000000 || r.availability !== null || r.condition !== null || r.model_identity_verified !== false) throw Error('row');
      const id = JSON.stringify([r.source_section.toLowerCase(),r.listing_text.toLowerCase()]);
      if (ids.has(id)) throw Error('duplicate'); ids.add(id);
    }
    return v;
  }
  function render() {
    if (!data) return;
    const old = data.list_date < today();
    notice.textContent = (cached ? 'تعذر تحميل القائمة الحديثة؛ نعرض آخر قائمة محفوظة. ' : '') + (old ? 'تنبيه: القائمة مؤرخة بيوم سابق وقد تكون الأسعار تغيرت. ' : '') + 'العملة USD بتأكيد رافع الصورة. التوفر وحالة الأجهزة وهوية الموديلات غير متحقق منها؛ ليست متوسط سوق.';
    const meta = $('.image-meta');
    meta.replaceChildren(document.createTextNode('تاريخ القائمة: ' + data.list_date + ' — '));
    const link = el('a',data.source_name || 'رابط الصورة المصدر'); link.href = data.source_url; link.target = '_blank'; link.rel = 'noopener noreferrer'; meta.append(link);
    const warranty = el('span',' — عبارة الضمان في الصورة: '); const raw = el('bdi',data.source_warranty_text); raw.dir = 'ltr'; warranty.append(raw); meta.append(warranty);
    const query = search.value.trim().toLowerCase(), ceiling = max.value === '' ? Infinity : Number(max.value);
    const rows = data.listings.filter(r => r.listing_text.toLowerCase().includes(query) && (!brand.value || r.source_section === brand.value) && r.price_usd <= ceiling);
    const body = $('tbody'); body.replaceChildren();
    for (const row of rows) {
      const tr = el('tr'); const section = el('td',row.source_section), name = el('td',row.listing_text), price = el('td',new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(row.price_usd));
      section.dir = name.dir = price.dir = 'ltr'; tr.append(section,name,price); body.append(tr);
    }
    $('.image-count').textContent = 'عدد النتائج: ' + rows.length + ' من ' + data.listings.length;
    $('.image-empty').hidden = rows.length !== 0;
  }
  async function load() {
    if (loading) return; loading = true; reload.disabled = true;
    const controller = new AbortController(), timer = setTimeout(() => controller.abort(),12000);
    try {
      const response = await fetch(endpoint,{mode:'cors',credentials:'omit',cache:'no-cache',signal:controller.signal});
      if (!response.ok) throw Error('http');
      const text = await response.text(); if (text.length > 1000000) throw Error('size');
      data = validate(JSON.parse(text)); cached = false;
      try { localStorage.setItem(cacheKey,JSON.stringify(data)); } catch { /* Optional cache. */ }
    } catch {
      if (!data) { try { const text = localStorage.getItem(cacheKey); if (text) data = validate(JSON.parse(text)); } catch { /* Reject invalid cache. */ } }
      cached = true;
      if (!data) notice.textContent = 'تعذر تحميل القائمة المصورة. يمكنك إعادة المحاولة؛ أسعار المتاجر في القسم الآخر مستقلة عنها.';
    } finally { clearTimeout(timer); loading = false; reload.disabled = false; }
    if (data) {
      const selected = brand.value; brand.replaceChildren(el('option','كل الأقسام')); brand.firstChild.value = '';
      [...new Set(data.listings.map(r => r.source_section))].sort().forEach(s => {const o = el('option',s); o.value = s; brand.append(o);});
      brand.value = selected; render();
    }
  }
  search.addEventListener('input',render); brand.addEventListener('change',render); max.addEventListener('input',render);
  reload.addEventListener('click',load); setInterval(render,60000); load();
})();
