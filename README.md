# The Goods Lane

Website for The Goods Lane (Ali Abbas, Mississauga): new and open-box electronics and
home goods at liquidation prices. The site mirrors his Facebook Marketplace listings and
is refreshed once a day.

Live site: https://mojomage.github.io/TheGoodsLane/

## How it works

```
Facebook Marketplace seller profile        (needs a signed-in Chrome)
   |  scraper/browser/*.js   read the seller pop-up, open each listing,
   |                         save ONE file with text and photos
   v
goods-lane-pull-<date>.json                (in Desktop/TheGoodsLane)
   |  python -m scraper.ingest             checks checksums, refuses broken pulls
   v
data/listings.json + data/photos/          (committed to main)
   |  scripts/publish.sh                   tests, build, push
   v
gh-pages branch -> GitHub Pages            (plain static HTML)
```

- **Why a browser:** Facebook shows a seller's listings only to signed-in visitors, and
  listing details only on a real page load. The scripts were written against the real
  pages on 2026-11-14; `docs/DAILY_RUN.md` is the step-by-step runbook.
- **Why one file:** descriptions and photos never pass through the assistant, so they
  arrive byte for byte. Every photo and description carries a checksum that ingest verifies.
- **Wording follows the listing:** condition, price and description are Ali Abbas' own.
  Titles are cleaned for display (emoji and ALL CAPS removed); the original is kept as
  `facebook_title`.

## Day to day

| I want to... | Do this |
|---|---|
| Update now | Follow `docs/DAILY_RUN.md` |
| Set or correct a retail price ("% off" badge) | Edit the listing's entry in `data/retail_prices.json`, then `python3 -m scraper.retail apply` |
| See which listings have no retail price yet | `python3 -m scraper.retail missing` |
| Hide a listing | `"<listing id>": {"hidden": true}` in `data/overrides.json` |
| Fix a title, category or brand | `"<listing id>": {"title": "...", "category": "kitchen", "brand": "Ninja"}` |
| Accept a big drop in stock | `python3 -m scraper.ingest <file> --force` |
| Preview locally | `python3 -m build.build --base-url "" --out _site && python3 -m http.server -d _site` |
| Change phone, pickup area, areas served | `site.config.json` |
| Use a custom domain | set it in GitHub Pages settings and in `base_url` in `site.config.json` |

## Tests

`python3 -m pytest` runs everything offline (a local Chrome is used for the browser tests):

- `test_browser_scripts.py`: the three browser scripts end to end against stand-in Facebook
  pages modelled on the real ones (seller pop-up over the feed, data embedded in the page)
- `test_ingest.py`: categories, brands, prices, and every "refuse a broken pull" rule
- `test_titles.py`: title cleaning, using the real listing titles
- `test_build.py`: every listing published, structured data matches, sitemap, robots, llms.txt
- `test_site_browser.py`: phone layout, fonts and photos load, Messenger and WhatsApp buttons side by side
- `test_published_data.py`: the committed inventory and photo files are consistent, and every "% off" has a named source

## Search and AI visibility

Each listing has its own page with `Product` and `Offer` structured data (price in CAD,
condition, availability). The home page carries `Store` data for Mississauga with the GTA
cities as `areaServed`, an `ItemList` and an `FAQPage`. The site also serves `sitemap.xml`,
`robots.txt` (search and AI crawlers allowed), `llms.txt`, `llms-full.txt`,
`inventory.json` and an Atom `feed.xml`.

Two things only the owner can do, and they matter most for local search: a Google Business
Profile for The Goods Lane with this site as its website, and adding the site to Google
Search Console with `sitemap.xml` submitted.
