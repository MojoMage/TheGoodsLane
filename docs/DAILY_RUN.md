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

7. **Test.** `python3 -m pytest -q` must pass.

8. **Commit the data.** `git add data && git commit -m "Inventory update <date>"`, push `main`.

9. **Publish.** `scripts/publish.sh` runs the tests, builds the site and pushes it to `gh-pages`.

10. **Check the publish.** GitHub Pages redeploys within a minute or two. Confirm with
    `curl -s https://api.github.com/repos/MojoMage/TheGoodsLane/deployments?per_page=1`
    (newest deployment is for the commit just pushed) and its `statuses_url` (state
    `success`). If a browser or web fetch can open
    `https://mojomage.github.io/TheGoodsLane/inventory.json`, also check `count` and
    `updated_at` there.

11. **Report** in a few lines: listings and photos pulled, what was added or sold since
    yesterday, and anything that failed. Pull files accumulate in the Desktop folder
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
