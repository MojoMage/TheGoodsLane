(async () => {
  // STEP 1 of 3. Run on the seller's Marketplace profile page, in a tab signed in to Facebook.
  // Returns the ids of the seller's listings, in the order Facebook shows them, and empties
  // the temporary store used by store_listing.js.
  //
  // The profile opens as a pop-up over the general Marketplace feed. Only links inside the
  // pop-up belong to the seller; the feed behind it is other people's listings and is ignored.
  const SELLER = 'Ali Abbas';
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  const ids = root => [...new Set([...root.querySelectorAll('a[href*="/marketplace/item/"]')]
    .map(a => (a.getAttribute('href').match(/\/marketplace\/item\/(\d+)/) || [])[1]).filter(Boolean))];
  const popup = () => [...document.querySelectorAll('div[role="dialog"]')]
    .filter(d => d.textContent.includes(SELLER)).sort((a, b) => ids(b).length - ids(a).length)[0];

  if (document.querySelector('form[action*="/login"], input[name="pass"], #login_form') ||
      /^\/(login|checkpoint)/.test(location.pathname)) return { ok: false, reason: 'login-required' };
  let dialog = null;
  for (let i = 0; i < 10 && !(dialog && ids(dialog).length); i++) { await sleep(1000); dialog = popup(); }
  if (!dialog) return { ok: false, reason: 'seller-popup-not-found', page_title: document.title };

  // Scroll the pop-up until no new listings load.
  const scroller = [dialog, ...dialog.querySelectorAll('*')].find(e => {
    const s = getComputedStyle(e);
    return /(auto|scroll)/.test(s.overflowY) && e.scrollHeight > e.clientHeight + 20;
  });
  let last = -1, stable = 0, rounds = 0;
  while (stable < 3 && rounds < 60) {
    const n = ids(dialog).length;
    stable = n === last ? stable + 1 : 0; last = n; rounds++;
    if (scroller) scroller.scrollTop = scroller.scrollHeight;
    const links = dialog.querySelectorAll('a[href*="/marketplace/item/"]');
    if (links.length) links[links.length - 1].scrollIntoView({ block: 'end' });
    await sleep(1300);
  }
  await new Promise(res => { const q = indexedDB.deleteDatabase('goods_lane_pull'); q.onsuccess = q.onerror = q.onblocked = () => res(); });
  const found = ids(dialog);
  return { ok: found.length > 0, reason: found.length ? null : 'no-listings-in-popup', count: found.length,
           ids: found.join(' '), feed_links_ignored: ids(document).length - found.length, rounds };
})()
