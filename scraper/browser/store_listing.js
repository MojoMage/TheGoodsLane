(async () => {
  // STEP 2 of 3. Run on each listing page (https://www.facebook.com/marketplace/item/<id>/),
  // opened by a real navigation: a background fetch of the page comes back without the data.
  // Reads the listing from the data Facebook embeds in the page, downloads its photos inside
  // the page, and keeps both in a temporary store (IndexedDB) until export_pull.js runs.
  // Nothing but a short status is returned, so no text or link passes through the assistant.
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const id = (location.pathname.match(/\/marketplace\/item\/(\d+)/) || [])[1];
  if (!id) return { ok: false, reason: 'not-a-listing-page' };
  let L = null, P = null;
  const walk = (n, d) => {
    if (!n || typeof n !== 'object' || d > 60) return;
    if (Array.isArray(n)) { for (const x of n) walk(x, d + 1); return; }
    if (String(n.id) === id) {
      // text and price live in one object, photos in another object with the same id
      if (typeof n.marketplace_listing_title === 'string' && n.redacted_description && !L) L = n;
      if (Array.isArray(n.listing_photos) && !P) P = n;
    }
    for (const k in n) walk(n[k], d + 1);
  };
  for (let attempt = 0; attempt < 5 && !L; attempt++) {
    await sleep(attempt ? 1500 : 2000);
    document.querySelectorAll('script[type="application/json"]').forEach(s => {
      const t = s.textContent;
      if (t.includes(id) && (t.includes('redacted_description') || t.includes('listing_photos'))) {
        try { walk(JSON.parse(t), 0); } catch (e) { /* not JSON we can use */ }
      }
    });
  }
  if (!L) return { id, ok: false, reason: document.querySelector('input[name="pass"]') ? 'login-required' : 'listing-data-not-found' };

  const photos = [];
  for (const p of (P ? P.listing_photos : [])) {
    const r = await fetch(p.image.uri);
    if (!r.ok) return { id, ok: false, reason: 'photo-http-' + r.status };
    photos.push(await r.blob());
  }
  const seller = L.marketplace_listing_seller || {};
  const rec = {
    id, seq: Date.now(), title: L.marketplace_listing_title,
    price: L.listing_price ? L.listing_price.amount : null,
    currency: L.listing_price ? L.listing_price.currency : 'CAD',
    was: L.strikethrough_price ? (L.strikethrough_price.formattedAmountWithoutDecimals || L.strikethrough_price.amount || null) : null,
    condition: (L.attribute_data || []).filter(a => /condition/i.test(a.attribute_name)).map(a => a.label || a.value).join(', '),
    location: L.location_text ? L.location_text.text : '',
    sold: !!L.is_sold, pending: !!L.is_pending, created: L.creation_time || null,
    seller_id: seller.id || null, description: L.redacted_description.text || '', photos
  };
  const db = await new Promise((res, rej) => {
    const q = indexedDB.open('goods_lane_pull', 1);
    q.onupgradeneeded = () => q.result.createObjectStore('l', { keyPath: 'id' });
    q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error);
  });
  await new Promise((res, rej) => { const t = db.transaction('l', 'readwrite'); t.objectStore('l').put(rec); t.oncomplete = res; t.onerror = () => rej(t.error); });
  const stored = await new Promise(res => { const q = db.transaction('l').objectStore('l').count(); q.onsuccess = () => res(q.result); });
  db.close();
  return { id, ok: true, ph: photos.length, stored };
})()
