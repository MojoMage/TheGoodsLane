# Daily update runbook

This is what the scheduled Claude task does once a day. It needs three things, all on
Ali Moiz's Mac: Chrome open with the Claude extension connected and signed in to
Facebook, the folder `/Users/alistonks/Desktop/TheGoodsLane` connected (Chrome's
download location is set to it), and push access to `MojoMage/TheGoodsLane`.

## Rules

- If Facebook is signed out, blocked, or the seller pop-up is missing: stop and report.
  Do not publish and do not look for another way in.
- The browser scripts return only short status objects. Never make them return listing
  text or photo links; the Chrome extension blocks links with query strings on purpose.
- A pull that ingest rejects is never published. Yesterday's site stays up.

## Steps

1. **Get the code.** Clone `https://github.com/MojoMage/TheGoodsLane` (push access).

2. **Read the seller's listing ids.** In Claude in Chrome, open a new tab at
   `https://www.facebook.com/marketplace/profile/61577549634421/`. Print the script with
   `python3 -m scraper.snippets collect` and run that exact text with the JavaScript tool.
   Expect `{ok: true, count, ids}`. `ids` is space-separated, in the order to keep.
   `ok: false` means stop (see Rules).

3. **Store each listing.**
   - Once, still on the profile page: run the text from `python3 -m scraper.snippets install`.
     Expect `{ok: true, chars, eval_works: true}`. It parks the listing script in the tab so
     each listing needs only a one-line call.
   - Then for every id, in order: navigate the tab to
     `https://www.facebook.com/marketplace/item/<id>/` and run
     `await eval(sessionStorage.getItem('gl_store'))`. Expect `{id, ok: true, ph, stored}`
     with `stored` counting up. All listings fit in one `browser_batch` call.
   - If `eval_works` was false, run the text from `python3 -m scraper.snippets store-full`
     on each listing page instead.
   - Retry a listing that returns `ok: false` once; if it still fails, carry on and report it.

4. **Save the file.** Run the text from `python3 -m scraper.snippets export` once. Expect
   `{ok: true, count, photos, fileBytes, fileName}`. Chrome saves `fileName` into the
   Desktop folder. Close the tab.

5. **Bring the file in.** List `/Users/alistonks/Desktop/TheGoodsLane`, confirm `fileName`
   is there with size `fileBytes`, and stage it into the workspace.

6. **Ingest.** `python3 -m scraper.ingest <staged file>`. Exit code 2 means the pull was
   rejected: stop, report the reason, publish nothing.

7. **Retail prices for new listings.** Every listing shows the brand-new retail price struck
   out and a "% off" badge; this is the point of the site. Run `python3 -m scraper.retail missing`.
   For each listing it names (new ones, and ones not found more than 30 days ago), search the
   web for what the exact model costs brand new in Canada and add an entry to
   `data/retail_prices.json` keyed by the listing id:
   `{"retail_price": 999.99, "product": "<brand, model, model number>", "source": "Canadian Tire", "url": "https://...", "basis": "regular", "checked": "<today>"}`.
   Rules: Canadian dollars only, from a Canadian retailer or the manufacturer's Canadian
   site or Canadian press release; never a US price, never a converted price, never an
   estimate. Use the regular (non-sale, "was") price; for a model no longer sold new, the
   Canadian launch price with `"basis": "launch"`. Match the exact model: check the listing
   photos when the text is vague (the box usually names it). Only record a link that came
   back from a search or fetch. If nothing qualifies after a couple of searches, record
   `{"status": "not_found", "note": "<why>", "checked": "<today>"}` and move on: that listing
   shows its price with no badge. Spend at most a few minutes on this step. Then run
   `python3 -m scraper.retail apply`.

8. **Test and note the changes.** `python3 -m pytest -q` must pass. Then run
   `python3 -m scraper.changes` and keep its output for the report.

9. **Commit the data.** `git add data && git commit -m "Inventory update <date>"`, push `main`.

10. **Publish.** `scripts/publish.sh` runs the tests, builds the site and pushes it to `gh-pages`.

11. **Check the publish.** GitHub Pages redeploys within a minute or two. Confirm with
    `curl -s https://api.github.com/repos/MojoMage/TheGoodsLane/deployments?per_page=1`
    (newest deployment is for the commit just pushed) and its `statuses_url` (state
    `success`). If a browser or web fetch can open
    `https://mojomage.github.io/TheGoodsLane/inventory.json`, also check `count` and
    `updated_at` there.

12. **Report** in a few lines: listings and photos pulled, what was added or sold since
    yesterday, retail prices added and which listings still have none, and anything that failed. Pull files accumulate in the Desktop folder
    (about 6 MB a day); mention it when there are more than about 30.

## When something fails

| Symptom | Meaning | What to do |
|---|---|---|
| `login-required` | Chrome is signed out of Facebook | Report; Ali Moiz signs in again |
| `seller-popup-not-found` | Facebook changed the profile page | Report; the script needs updating |
| `listing-data-not-found` on every listing | Facebook changed the listing page | Report; the script needs updating |
| Site blocked in the browser | Site permissions changed | Report; do not work around it |
| File not in the Desktop folder | Chrome's download location changed | Report; it must point at the folder |
| Ingest "Inventory dropped from X to Y" | Real clear-out, or a broken pull | Report both counts; re-run with `--force` only if Ali confirms |

## Proven runs

- 2026-11-14: three pulls, identical results (22 listings, 46 photos).
- 2026-11-15: full run with the scripts exactly as in this repo, short form. 22 listings,
  46 photos, 6.0 MB file. It picked up a real overnight price drop ($380 to $340).
