"""Build The Goods Lane static site from data/listings.json and data/photos/.

    python -m build.build                      # -> ./_site, URLs from site.config.json
    python -m build.build --base-url ""        # local preview with root-relative links

Output is plain static HTML: every listing is a real page with its own URL, structured
data and photos, so search engines and AI agents can read the inventory without
running JavaScript.
"""
from __future__ import annotations

import argparse
import html
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from PIL import Image, ImageOps

from scraper.titles import plain_text

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
TORONTO = ZoneInfo("America/Toronto")
MAX_PHOTOS = 10
AI_CRAWLERS = ["GPTBot", "OAI-SearchBot", "ChatGPT-User", "ClaudeBot", "Claude-SearchBot", "Claude-User",
               "PerplexityBot", "Perplexity-User", "Google-Extended", "Applebot-Extended", "Bingbot", "CCBot",
               "Amazonbot", "meta-externalagent", "DuckAssistBot"]


def money(amount: float | None) -> str:
    if amount is None:
        return "Ask for price"
    if amount == 0:
        return "Free"
    return f"${amount:,.0f}" if float(amount).is_integer() else f"${amount:,.2f}"


def one_line(text: str, limit: int = 155) -> str:
    return plain_text(text, limit)


def schema_condition(condition: str) -> str:
    c = (condition or "").lower()
    if "refurb" in c:
        return "https://schema.org/RefurbishedCondition"
    if "used" in c:
        return "https://schema.org/UsedCondition"
    return "https://schema.org/NewCondition"


def origin(base: str) -> str:
    u = urlparse(base)
    return f"{u.scheme}://{u.netloc}" if u.scheme else ""


def make_images(listing: dict, data_dir: Path, out: Path, p: str) -> list[dict]:
    """Resize each photo: a 4:5 card crop in two sizes and a full image for the item page."""
    images = []
    for n, photo in enumerate(listing["photos"][:MAX_PHOTOS], 1):
        src = data_dir / photo["file"]
        try:
            img = ImageOps.exif_transpose(Image.open(src)).convert("RGB")
        except Exception as exc:
            print(f"  ! photo skipped for {listing['id']}: {exc}", file=sys.stderr)
            continue
        dest = out / "img" / listing["id"]
        dest.mkdir(parents=True, exist_ok=True)
        full = img.copy()
        full.thumbnail((1200, 1200), Image.LANCZOS)
        full.save(dest / f"{n}.jpg", "JPEG", quality=84, optimize=True, progressive=True)
        ImageOps.fit(img, (480, 600), Image.LANCZOS).save(dest / f"{n}-480.webp", "WEBP", quality=78, method=6)
        ImageOps.fit(img, (800, 1000), Image.LANCZOS).save(dest / f"{n}-800.webp", "WEBP", quality=76, method=6)
        rel = f"{p}/img/{listing['id']}/{n}"
        images.append({"full": f"{rel}.jpg", "thumb": f"{rel}-480.webp", "thumb2x": f"{rel}-800.webp",
                       "w": full.width, "h": full.height})
    return images


# ----------------------------------------------------------- structured data
def business_jsonld(site: dict, base: str) -> dict:
    return {
        "@context": "https://schema.org", "@type": "Store", "@id": f"{base}/#business",
        "name": site["name"], "alternateName": site["legal_line"], "description": site["description"],
        "url": f"{base}/", "logo": f"{base}/assets/icon-512.png", "image": f"{base}/assets/og-default.png",
        "telephone": site["phone_e164"], "priceRange": "$", "currenciesAccepted": site["currency"],
        "founder": {"@type": "Person", "name": site["owner"]},
        "address": {"@type": "PostalAddress", "addressLocality": site["city"], "addressRegion": site["region"],
                    "addressCountry": site["country"]},
        "areaServed": [{"@type": "City", "name": a} for a in site["areas_served"]]
                      + [{"@type": "AdministrativeArea", "name": "Greater Toronto Area"}],
        "sameAs": [site["marketplace_profile_url"]],
        "contactPoint": [
            {"@type": "ContactPoint", "contactType": "sales", "name": "Facebook Messenger", "url": site["messenger_url"],
             "availableLanguage": "English"},
            {"@type": "ContactPoint", "contactType": "sales", "name": "WhatsApp", "telephone": site["phone_e164"],
             "url": f"https://wa.me/{site['whatsapp_number']}"},
        ],
    }


def product_jsonld(l: dict, site: dict, base: str) -> dict:
    offer = {
        "@type": "Offer", "url": l["page_url"], "priceCurrency": l["currency"],
        "price": f"{l['price']:.2f}" if l["price"] is not None else None,
        "availability": "https://schema.org/InStock" if l["status"] == "available"
                        else "https://schema.org/LimitedAvailability",
        "itemCondition": schema_condition(l["condition"]),
        "seller": {"@id": f"{base}/#business"},
        "availableAtOrFrom": {"@type": "Place", "address": {
            "@type": "PostalAddress", "addressLocality": site["city"], "addressRegion": site["region"],
            "addressCountry": site["country"]}},
        "areaServed": {"@type": "AdministrativeArea", "name": "Greater Toronto Area"},
    }
    if l["msrp"]:
        offer["priceSpecification"] = [
            {"@type": "UnitPriceSpecification", "price": f"{l['price']:.2f}", "priceCurrency": l["currency"]},
            {"@type": "UnitPriceSpecification", "priceType": "https://schema.org/MSRP", "price": f"{l['msrp']:.2f}",
             "priceCurrency": l["currency"]},
        ]
    data = {
        "@context": "https://schema.org", "@type": "Product", "@id": f"{l['page_url']}#product", "name": l["title"],
        "sku": l["id"], "url": l["page_url"], "category": l["category_name"],
        "description": plain_text(l["description"]) or l["title"],
        "image": [origin(base) + im["full"] for im in l["images"]],
        "itemCondition": schema_condition(l["condition"]),
        "offers": {k: v for k, v in offer.items() if v is not None},
    }
    if l["brand"]:
        data["brand"] = {"@type": "Brand", "name": l["brand"]}
    return data


def breadcrumb_jsonld(trail: list[tuple[str, str]]) -> dict:
    return {"@context": "https://schema.org", "@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": url} for i, (name, url) in enumerate(trail, 1)]}


def itemlist_jsonld(name: str, listings: list[dict]) -> dict:
    return {"@context": "https://schema.org", "@type": "ItemList", "name": name, "numberOfItems": len(listings),
            "itemListElement": [{"@type": "ListItem", "position": i, "name": l["title"], "url": l["page_url"]}
                                for i, l in enumerate(listings, 1)]}


def faq_for(site: dict) -> list[dict]:
    areas = ", ".join(site["areas_served"][1:7])
    first = site["owner_first_name"]
    return [
        {"q": f"Where is {site['name']}?",
         "a": f"In {site['city']}, {site['region_name']}. Pickup is around {site['pickup_area']}. Buyers come from "
              f"across the Greater Toronto Area, including {areas}."},
        {"q": "Are the items new?",
         "a": "Most are new or new open-box, bought as liquidation stock. Every listing states its own condition, so "
              "check the item you are interested in."},
        {"q": "Is there a warranty?",
         "a": f"Several items come with a 15-day replacement warranty if faulty; the listing says so when it applies. "
              f"Ask {first} if you are unsure about a particular item."},
        {"q": "Do you deliver?",
         "a": f"Yes. Delivery is available at a reasonable charge on many items. Message {first} with your location "
              "for a quote, or pick up in person."},
        {"q": "How do I buy something?",
         "a": f"Open the item and tap the Messenger button to chat with {site['owner']}. If Messenger doesn't open, "
              f"message or text him on WhatsApp at {site['phone_display']}."},
        {"q": "How current is this page?",
         "a": f"Stock is checked against {site['owner']}'s Facebook Marketplace listings every day. Sold items are "
              "removed and new ones added at each check."},
    ]


def faq_jsonld(faq: list[dict]) -> dict:
    return {"@context": "https://schema.org", "@type": "FAQPage", "mainEntity": [
        {"@type": "Question", "name": q["q"], "acceptedAnswer": {"@type": "Answer", "text": q["a"]}} for q in faq]}


# ---------------------------------------------------------------- the build
def build(out: Path, base_url: str | None = None, data_dir: Path | None = None, config_file: Path | None = None) -> dict:
    site = json.loads((config_file or ROOT / "site.config.json").read_text(encoding="utf-8"))
    data_dir = data_dir or ROOT / "data"
    base = (site.get("base_url", "") if base_url is None else base_url).rstrip("/")
    p = urlparse(base).path.rstrip("/") if base else ""
    snapshot = json.loads((data_dir / "listings.json").read_text(encoding="utf-8"))
    updated = datetime.fromisoformat(snapshot["updated_at"]).astimezone(TORONTO)

    if out.exists():
        shutil.rmtree(out)
    (out / "assets").mkdir(parents=True)
    shutil.copytree(HERE / "static", out / "assets", dirs_exist_ok=True)
    (out / ".nojekyll").write_text("")

    wa_base = f"https://wa.me/{site['whatsapp_number']}?text="
    first = site["owner_first_name"]
    msg_general = f"Hi {first}, I found {site['name']} online. What do you have available right now?"

    listings = [dict(l) for l in snapshot["listings"] if not l.get("hidden") and l.get("status") != "sold"]
    for l in listings:
        l["page_url"] = f"{base}/item/{l['slug']}/"
        l["price_text"] = money(l["price"])
        l["msrp_text"] = money(l["msrp"]) if l.get("msrp") else ""
        l["previous_price_text"] = money(l["previous_price"]) if l.get("previous_price") else ""
        l["images"] = make_images(l, data_dir, out, p)
        # the gallery frame follows the first photo's shape, kept between 3:4 portrait and 4:3 landscape
        first_photo = l["images"][0] if l["images"] else {"w": 4, "h": 5}
        l["ar"] = round(min(max(first_photo["w"] / first_photo["h"], 0.75), 1.3334), 4)
        price_bit = f" listed for {l['price_text']}" if l["price"] is not None else ""
        l["message"] = f"Hi {first}, is the {l['title']}{price_bit} still available? {l['page_url']}".strip()
        l["whatsapp_url"] = wa_base + quote(l["message"], safe="")

    categories = []
    for l in listings:
        cat = next((c for c in categories if c["slug"] == l["category"]), None)
        if not cat:
            cat = {"slug": l["category"], "name": l["category_name"], "count": 0}
            categories.append(cat)
        cat["count"] += 1
    categories.sort(key=lambda c: (-c["count"], c["name"]))

    env = Environment(loader=FileSystemLoader(HERE / "templates"), autoescape=select_autoescape(["html", "svg"]),
                      trim_blocks=True, lstrip_blocks=True)
    common = {
        "site": site, "base": base, "p": p, "categories": categories, "total": len(listings),
        "wa_general": wa_base + quote(msg_general, safe=""), "msg_general": msg_general,
        "updated_iso": updated.isoformat(), "updated_human": f"{updated.day} {updated:%B %Y}",
        "updated_short": f"{updated:%b} {updated.day}",
    }
    business, faq, n = business_jsonld(site, base), faq_for(site), len(listings)

    def write(rel: str, template: str, **ctx):
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(env.get_template(template).render(**common, **ctx), encoding="utf-8")

    write("index.html", "home.html", listings=listings, category=None, faq=faq, page={
        "title": f"{site['name']}: new and open-box deals in {site['city']} and GTA",
        "description": one_line(f"{n} new and open-box electronics, appliances and home goods at liquidation prices, "
                                f"typically {site['discount_range']} below retail. Pickup in {site['city']}; delivery "
                                "across the GTA."),
        "canonical": f"{base}/" if base else "",
        "jsonld": [business,
                   {"@context": "https://schema.org", "@type": "WebSite", "@id": f"{base}/#website", "url": f"{base}/",
                    "name": site["name"], "inLanguage": "en-CA", "publisher": {"@id": f"{base}/#business"}},
                   itemlist_jsonld(f"{site['name']} items in stock", listings), faq_jsonld(faq)],
    })

    for cat in categories:
        subset = [l for l in listings if l["category"] == cat["slug"]]
        url = f"{base}/shop/{cat['slug']}/"
        write(f"shop/{cat['slug']}/index.html", "home.html", listings=subset, category=cat, faq=faq, page={
            "title": f"{cat['name']} in {site['city']} and the GTA | {site['name']}",
            "description": one_line(f"{len(subset)} new and open-box {cat['name'].lower()} at liquidation prices from "
                                    f"{site['name']}. Pickup in {site['city']}, {site['region_name']}; delivery "
                                    "available across the GTA."),
            "canonical": url if base else "",
            "jsonld": [breadcrumb_jsonld([("Everything", f"{base}/"), (cat["name"], url)]),
                       itemlist_jsonld(f"{cat['name']} at {site['name']}", subset)],
        })

    for l in listings:
        related = [r for r in listings if r["id"] != l["id"] and r["category"] == l["category"]]
        related += [r for r in listings if r["id"] != l["id"] and r not in related]
        cond = f"{l['condition']}. " if l["condition"] else ""
        desc = (f"{l['title']} for {l['price_text']}. {cond}Pickup in {site['city']}, {site['region']}; delivery "
                f"available. Message {site['owner']} on Messenger or WhatsApp.")
        write(f"item/{l['slug']}/index.html", "item.html", l=l, related=related[:4], page={
            "title": one_line(f"{l['title']} for {l['price_text']} in {site['city']} | {site['name']}", 110),
            "og_title": f"{l['title']} for {l['price_text']}",
            "description": one_line(desc, 200), "canonical": l["page_url"] if base else "", "og_type": "product",
            "price": f"{l['price']:.2f}" if l["price"] is not None else "",
            "image": origin(base) + l["images"][0]["full"] if l["images"] else "", "has_bar": True,
            "jsonld": [product_jsonld(l, site, base),
                       breadcrumb_jsonld([("Everything", f"{base}/"),
                                          (l["category_name"], f"{base}/shop/{l['category']}/"),
                                          (l["title"], l["page_url"])])],
        })

    write("404.html", "404.html", page={"title": f"Not found | {site['name']}", "noindex": True, "jsonld": [],
                                        "description": "That item has sold or the link is out of date."})

    # ------------------------------------------------ machine-readable outputs
    lastmod = updated.date().isoformat()
    urls = [f"{base}/"] + [f"{base}/shop/{c['slug']}/" for c in categories] + [l["page_url"] for l in listings]
    (out / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{html.escape(u)}</loc><lastmod>{lastmod}</lastmod></url>\n" for u in urls)
        + "</urlset>\n", encoding="utf-8")
    robots = "User-agent: *\nAllow: /\n\n# AI search and assistant crawlers are welcome here.\n"
    robots += "".join(f"User-agent: {bot}\nAllow: /\n\n" for bot in AI_CRAWLERS) + f"Sitemap: {base}/sitemap.xml\n"
    (out / "robots.txt").write_text(robots, encoding="utf-8")

    public = [{
        "id": l["id"], "title": l["title"], "url": l["page_url"], "price": l["price"], "currency": l["currency"],
        "previous_price": l.get("previous_price"), "retail_price": l.get("msrp"), "condition": l["condition"],
        "brand": l["brand"], "category": l["category_name"], "status": l["status"],
        "pickup_location": l["location"] or f"{site['city']}, {site['region']}", "description": l["description"],
        "images": [origin(base) + im["full"] for im in l["images"]], "facebook_title": l.get("facebook_title"),
        "facebook_marketplace_url": l["url"], "listed_at": l.get("listed_at"),
        "contact_messenger": site["messenger_url"], "contact_whatsapp": l["whatsapp_url"],
    } for l in listings]
    (out / "inventory.json").write_text(json.dumps({
        "business": site["name"], "seller": site["owner"], "location": f"{site['city']}, {site['region']}, Canada",
        "pickup_area": site["pickup_area"], "areas_served": site["areas_served"], "updated_at": updated.isoformat(),
        "count": len(public),
        "contact": {"messenger": site["messenger_url"], "whatsapp": f"https://wa.me/{site['whatsapp_number']}",
                    "phone": site["phone_e164"]},
        "listings": public}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def md_line(l):
        was = f" (was {l['previous_price_text']})" if l.get("previous_price") else ""
        cond = f" Condition: {l['condition']}." if l["condition"] else ""
        return f"- [{l['title']}]({l['page_url']}): {l['price_text']} {l['currency']}{was}.{cond}"

    head = (f"# {site['name']}\n\n> {site['description']}\n\n"
            f"- Seller: {site['owner']} ({site['legal_line']})\n"
            f"- Location: {site['city']}, {site['region_name']}, Canada. Pickup around {site['pickup_area']}.\n"
            f"- Delivery: available across the Greater Toronto Area at a reasonable charge; ask for a quote.\n"
            f"- Serves: {', '.join(site['areas_served'])} and the rest of the Greater Toronto Area\n"
            f"- Contact: Facebook Messenger {site['messenger_url']} or WhatsApp/text {site['phone_e164']} "
            f"(https://wa.me/{site['whatsapp_number']})\n"
            f"- Stock last checked: {lastmod} (checked daily; items are limited stock and sell quickly)\n"
            f"- Prices are in Canadian dollars.\n\n")
    (out / "llms.txt").write_text(
        head + f"## In stock ({len(listings)} items)\n\n" + "\n".join(md_line(l) for l in listings)
        + f"\n\n## Data\n\n- [Full inventory as JSON]({base}/inventory.json)\n- [Full inventory with descriptions]"
          f"({base}/llms-full.txt)\n- [Sitemap]({base}/sitemap.xml)\n", encoding="utf-8")
    (out / "llms-full.txt").write_text(head + "## In stock\n\n" + "\n\n".join(
        f"### {l['title']}\n\n- Price: {l['price_text']} {l['currency']}\n"
        + (f"- Previous price: {l['previous_price_text']}\n" if l.get("previous_price") else "")
        + (f"- Condition: {l['condition']}\n" if l["condition"] else "")
        + (f"- Brand: {l['brand']}\n" if l["brand"] else "")
        + f"- Category: {l['category_name']}\n- Page: {l['page_url']}\n- Facebook Marketplace: {l['url']}\n\n"
        + l["description"] for l in listings) + "\n", encoding="utf-8")

    entries = "".join(
        f"<entry><id>{html.escape(l['page_url'])}</id><title>{html.escape(l['title'])} for {l['price_text']}</title>"
        f"<link href=\"{html.escape(l['page_url'])}\"/><updated>{l.get('listed_at') or updated.isoformat()}</updated>"
        f"<summary>{html.escape(one_line(l['description'] or l['title'], 300))}</summary></entry>\n"
        for l in sorted(listings, key=lambda x: x.get("listed_at") or "", reverse=True))
    (out / "feed.xml").write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n<feed xmlns="http://www.w3.org/2005/Atom"><title>{site["name"]} new '
        f'listings</title><id>{base}/</id><link href="{base}/"/><link rel="self" href="{base}/feed.xml"/>'
        f"<updated>{updated.isoformat()}</updated><author><name>{site['owner']}</name></author>\n{entries}</feed>\n",
        encoding="utf-8")
    (out / "site.webmanifest").write_text(json.dumps({
        "name": site["name"], "short_name": "Goods Lane", "start_url": f"{p}/", "display": "browser",
        "background_color": "#F7F6F3", "theme_color": "#F7F6F3",
        "icons": [{"src": f"{p}/assets/icon-512.png", "sizes": "512x512", "type": "image/png"}]}, indent=2),
        encoding="utf-8")
    return {"pages": len(urls), "listings": len(listings), "categories": len(categories),
            "photos": sum(len(l["images"]) for l in listings), "base": base, "out": str(out)}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", default=str(ROOT / "_site"))
    ap.add_argument("--base-url", default=None, help="public URL; default is base_url in site.config.json")
    args = ap.parse_args(argv)
    stats = build(Path(args.out), args.base_url)
    print(f"Built {stats['listings']} listings, {stats['photos']} photos, {stats['pages']} pages -> {stats['out']} "
          f"(base: {stats['base'] or 'root-relative'})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
