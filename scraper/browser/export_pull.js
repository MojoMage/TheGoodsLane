(async () => {
  // STEP 3 of 3. Run once, on any facebook.com page, after every listing has been stored.
  // Writes everything to ONE file that Chrome saves to its download folder, then empties
  // the temporary store. The file holds text and the photos themselves (base64), no links.
  const db = await new Promise((res, rej) => { const q = indexedDB.open('goods_lane_pull', 1); q.onupgradeneeded = () => q.result.createObjectStore('l', { keyPath: 'id' }); q.onsuccess = () => res(q.result); q.onerror = () => rej(q.error); });
  const recs = await new Promise(res => { const q = db.transaction('l').objectStore('l').getAll(); q.onsuccess = () => res(q.result); });
  db.close();
  if (!recs.length) return { ok: false, reason: 'nothing-stored' };
  recs.sort((a, b) => a.seq - b.seq);
  const hex = async buf => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', buf))).map(b => b.toString(16).padStart(2, '0')).join('');
  const b64 = u => { let s = ''; for (let i = 0; i < u.length; i += 32768) s += String.fromCharCode.apply(null, u.subarray(i, i + 32768)); return btoa(s); };
  const out = { source: 'facebook-marketplace', format: 1, profile_url: 'https://www.facebook.com/marketplace/profile/61577549634421/',
                pulled_at: new Date().toISOString(), count: recs.length, listings: [] };
  let nph = 0;
  for (const r of recs) {
    const photos = []; let i = 0;
    for (const b of r.photos) {
      const u = new Uint8Array(await b.arrayBuffer());
      photos.push({ name: r.id + '_' + (++i) + '.jpg', type: b.type, bytes: u.length, sha256: await hex(u), base64: b64(u) });
      nph++;
    }
    out.listings.push({
      id: r.id, url: 'https://www.facebook.com/marketplace/item/' + r.id + '/', title: r.title, price: r.price,
      currency: r.currency, previous_price: r.was, condition: r.condition, location: r.location,
      status: r.sold ? 'sold' : r.pending ? 'pending' : 'available', seller_id: r.seller_id || null,
      listed_at: r.created ? new Date(r.created * 1000).toISOString() : null, description: r.description,
      description_sha256: await hex(new TextEncoder().encode(r.description)), photos
    });
  }
  const now = new Date(), two = n => String(n).padStart(2, '0');
  const fileName = 'goods-lane-pull-' + now.getFullYear() + '-' + two(now.getMonth() + 1) + '-' + two(now.getDate()) + '-' + two(now.getHours()) + two(now.getMinutes()) + '.json';
  const blob = new Blob([JSON.stringify(out)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = fileName;
  document.body.appendChild(a); a.click(); a.remove();
  await new Promise(r => setTimeout(r, 2000));
  await new Promise(res => { const q = indexedDB.deleteDatabase('goods_lane_pull'); q.onsuccess = q.onerror = q.onblocked = () => res(); });
  sessionStorage.removeItem('gl_store');
  return { ok: true, count: recs.length, photos: nph, fileBytes: blob.size, fileName };
})()
