"""The generated site: every listing published, search and agent metadata right, contact links right."""
import json
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup
from PIL import Image

from build import build as site_build
from scraper import ingest
from tests import fakefb

BASE = "https://example.github.io/TheGoodsLane"


def soup(path):
    return BeautifulSoup(path.read_text(encoding="utf-8"), "html.parser")


def jsonld(doc):
    return [json.loads(s.string) for s in doc.find_all("script", type="application/ld+json")]


def item_pages(built):
    return sorted((built["out"] / "item").glob("*/index.html"))


def test_one_page_per_listing(built):
    assert len(item_pages(built)) == 4 == built["stats"]["listings"] and built["stats"]["photos"] == 6


def test_home_shows_every_item_in_facebook_order(built):
    doc = soup(built["out"] / "index.html")
    cards = doc.select("ul.grid article.card")
    assert [c.h3.get_text(strip=True) for c in cards] == [l["title"] for l in built["snapshot"]["listings"]]
    for card in cards:
        assert re.fullmatch(r"\$[\d,]+(\.\d\d)?", card.select_one(".price").get_text(strip=True))
        img = card.select_one("img")
        assert img["alt"] and img["width"] == "480" and img["height"] == "600"  # sized: no layout shift
        assert card.a["href"].startswith("/TheGoodsLane/item/")
    assert "was$280" in cards[1].select_one(".money").get_text(strip=True).replace(" ", "")
    assert not cards[0].select_one(".was"), "no 'was' price unless Facebook shows one"


def test_page_text_has_no_emoji_or_shouting_in_titles(built):
    for page in [built["out"] / "index.html", *item_pages(built)]:
        doc = soup(page)
        for el in doc.select("h1, h3, title"):
            text = el.get_text()
            assert not re.search("[\U0001F000-\U0001FAFF☀-➿]", text), text
            assert not re.search(r"\b[A-Z]{5,}\b", text.replace("CAD", "")), text


def test_home_is_mobile_first_local_and_says_new_not_used(built):
    doc = soup(built["out"] / "index.html")
    assert "width=device-width" in doc.find("meta", attrs={"name": "viewport"})["content"]
    assert doc.html["lang"] == "en-CA" and len(doc.find_all("h1")) == 1
    title, desc = doc.title.string, doc.find("meta", attrs={"name": "description"})["content"]
    assert "Mississauga" in title and "GTA" in title and len(title) <= 70
    assert "Mississauga" in desc and 80 <= len(desc) <= 165
    assert doc.find("link", rel="canonical")["href"] == BASE + "/"
    assert doc.find("meta", attrs={"name": "geo.placename"})["content"] == "Mississauga"
    text = doc.get_text(" ").lower()
    assert "open-box" in text and "pre-owned" not in text and "like new" not in text and "used" not in text


def test_local_business_structured_data(built):
    blocks = jsonld(soup(built["out"] / "index.html"))
    store = next(b for b in blocks if b["@type"] == "Store")
    assert store["name"] == "The Goods Lane" and store["telephone"] == "+16477706652"
    assert store["address"] == {"@type": "PostalAddress", "addressLocality": "Mississauga", "addressRegion": "ON",
                                "addressCountry": "CA"}
    assert {"Mississauga", "Toronto", "Brampton", "Greater Toronto Area"} <= {a["name"] for a in store["areaServed"]}
    assert "https://www.facebook.com/marketplace/profile/61577549634421/" in store["sameAs"]
    items = next(b for b in blocks if b["@type"] == "ItemList")
    assert items["numberOfItems"] == 4 and all(e["url"].startswith(BASE + "/item/") for e in items["itemListElement"])
    assert len(next(b for b in blocks if b["@type"] == "FAQPage")["mainEntity"]) >= 5


def test_product_structured_data_matches_the_listing(built):
    by_id = {l["id"]: l for l in built["snapshot"]["listings"]}
    for page in item_pages(built):
        doc = soup(page)
        product = next(b for b in jsonld(doc) if b["@type"] == "Product")
        src = by_id[product["sku"]]
        assert product["name"] == src["title"] == doc.h1.get_text(strip=True)
        offer = product["offers"]
        assert float(offer["price"]) == src["price"] and offer["priceCurrency"] == "CAD"
        assert offer["itemCondition"] == product["itemCondition"] == "https://schema.org/NewCondition"
        assert offer["availability"] == "https://schema.org/InStock"
        assert offer["url"] == doc.find("link", rel="canonical")["href"] == f"{BASE}/item/{src['slug']}/"
        assert len(product["image"]) == len(src["photos"]) and all(u.startswith("https://example.github.io/TheGoodsLane/img/") for u in product["image"])
        assert "priceSpecification" not in offer and not doc.select_one(".off"), "no retail price or % off is invented"
        facts = doc.select_one(".facts").get_text(" ", strip=True)
        assert "Condition New" in facts
        crumbs = next(b for b in jsonld(doc) if b["@type"] == "BreadcrumbList")
        assert [c["position"] for c in crumbs["itemListElement"]] == [1, 2, 3]


def test_item_page_keeps_the_sellers_description_whole(built):
    page = next(p for p in item_pages(built) if "984841858011538" in p.parent.name)
    desc = soup(page).select_one(".desc").get_text()
    assert desc == fakefb.ITEMS[1]["description"].strip() and len(desc) > 3000


def test_messenger_first_whatsapp_failsafe_on_every_item(built):
    for page in item_pages(built):
        doc = soup(page)
        title = doc.h1.get_text(strip=True)
        messenger = doc.select('main a[data-contact="messenger"]')
        assert len(messenger) == 2, "inline button + sticky phone bar"
        for a in messenger:
            assert a["href"] == "https://m.me/61577549634421"
            wa = urlparse(a["data-whatsapp"])
            assert wa.netloc == "wa.me" and wa.path == "/16477706652"
            text = parse_qs(wa.query)["text"][0]
            assert title in text and BASE + "/item/" in text and a["data-message"] == text
        assert doc.select_one('main a[href^="https://wa.me/16477706652"]'), "plain WhatsApp link works without JavaScript"
        assert doc.select_one('main a[href^="https://www.facebook.com/marketplace/item/"]')
        assert doc.select_one("dialog#contact-sheet #sheet-whatsapp")


def test_sold_and_hidden_items_are_not_published_and_pending_is_labelled(tmp_path, pull):
    snap, photos = ingest.ingest(pull, overrides={fakefb.ITEMS[3]["id"]: {"hidden": True}}, expected_seller=fakefb.SELLER_ID)
    snap["listings"][0]["status"] = "sold"
    snap["listings"][1]["status"] = "pending"
    ingest.write(snap, photos, tmp_path / "data")
    stats = site_build.build(tmp_path / "out", BASE, tmp_path / "data")
    assert stats["listings"] == 2
    home = (tmp_path / "out" / "index.html").read_text()
    assert "Sale pending" in home and "Magnifica" not in home and "Emma" not in home
    assert not list((tmp_path / "out" / "item").glob("*1647194386782124"))


def test_empty_stock_still_builds_a_useful_page(tmp_path):
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "listings.json").write_text(json.dumps({"updated_at": "2026-11-15T14:00:00+00:00", "listings": []}))
    site_build.build(tmp_path / "out", BASE, tmp_path / "data")
    doc = soup(tmp_path / "out" / "index.html")
    assert "Everything has sold for now" in doc.get_text() and doc.select_one('main a[data-contact="messenger"]')


def test_sitemap_lists_every_page_and_every_url_is_a_real_file(built):
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    locs = [e.text for e in ET.parse(built["out"] / "sitemap.xml").getroot().findall("s:url/s:loc", ns)]
    assert BASE + "/" in locs and len(locs) == 1 + built["stats"]["categories"] + 4 and len(set(locs)) == len(locs)
    for loc in locs:
        assert (built["out"] / loc[len(BASE) + 1:] / "index.html").exists(), loc


def test_robots_welcomes_search_and_ai_crawlers(built):
    robots = (built["out"] / "robots.txt").read_text()
    assert "Disallow" not in robots and f"Sitemap: {BASE}/sitemap.xml" in robots
    for bot in ("GPTBot", "ClaudeBot", "PerplexityBot", "Google-Extended", "OAI-SearchBot"):
        assert f"User-agent: {bot}\nAllow: /" in robots


def test_agent_readable_inventory(built):
    llms = (built["out"] / "llms.txt").read_text()
    assert llms.startswith("# The Goods Lane") and "Mississauga" in llms and "+16477706652" in llms
    assert llms.count(f"]({BASE}/item/") == 4 and "(was $280)" in llms and "Condition: New" in llms
    assert "Long text. Long text." in (built["out"] / "llms-full.txt").read_text()
    inv = json.loads((built["out"] / "inventory.json").read_text())
    assert inv["count"] == 4 and inv["contact"]["whatsapp"] == "https://wa.me/16477706652"
    for l in inv["listings"]:
        assert l["title"] and l["price"] is not None and l["url"].startswith(BASE) and l["images"] and l["condition"] == "New"
        assert l["facebook_marketplace_url"].startswith("https://www.facebook.com/marketplace/item/")
    ET.parse(built["out"] / "feed.xml")  # well-formed Atom


def test_photos_are_resized_for_phones(built):
    folder = built["out"] / "img" / "984841858011538"
    assert sorted(p.name for p in folder.iterdir()) == ["1-480.webp", "1-800.webp", "1.jpg", "2-480.webp", "2-800.webp", "2.jpg"]
    assert Image.open(folder / "1-480.webp").size == (480, 600) and max(Image.open(folder / "1.jpg").size) <= 1200
    assert (folder / "1-480.webp").stat().st_size < 60_000


def test_no_internal_link_is_broken(built):
    pages = [built["out"] / "index.html", *item_pages(built), *(built["out"] / "shop").glob("*/index.html")]
    for page in pages:
        doc = soup(page)
        for el in doc.select('[href^="/TheGoodsLane/"], [src^="/TheGoodsLane/"]'):
            ref = (el.get("href") or el.get("src"))[len("/TheGoodsLane/"):].split("#")[0]
            target = built["out"] / ref
            assert (target / "index.html").exists() or target.is_file(), f"{ref} on {page}"


def test_listing_text_cannot_inject_markup(tmp_path, pull):
    raw = json.loads(json.dumps(pull))
    evil = raw["listings"][2]
    evil["title"] = 'Kettle <script>alert(1)</script> "deal"'
    evil["description"] = "</script><img src=x onerror=alert(1)>"
    import hashlib
    evil["description_sha256"] = hashlib.sha256(evil["description"].encode()).hexdigest()
    snap, photos = ingest.ingest(raw, expected_seller=fakefb.SELLER_ID)
    ingest.write(snap, photos, tmp_path / "data")
    site_build.build(tmp_path / "out", BASE, tmp_path / "data")
    doc = soup(next((tmp_path / "out" / "item").glob("kettle*/index.html")))
    assert not doc.select("img[onerror]") and len(doc.find_all("script")) == 3  # 2 JSON-LD + site.js
    assert json.loads(doc.find("script", type="application/ld+json").string)["name"].startswith("Kettle <script>")
