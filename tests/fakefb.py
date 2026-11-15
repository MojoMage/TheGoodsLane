"""Stand-ins for Facebook, modelled on what the real pages looked like on 2026-11-14:

- the seller profile is a pop-up (div[role=dialog]) over the general Marketplace feed,
  so the page holds other sellers' item links outside the pop-up;
- a listing page embeds its data as JSON: one object with title, price, description,
  condition and status, and a separate object with the same id holding the photos;
- the same page embeds other listings ("related items") that must not be mixed in.
"""
import base64
import hashlib
import io
import json

from PIL import Image

SELLER_ID = "61577549634421"
ITEMS = [
    {"id": "1647194386782124", "title": "☕ De’LONGHI MAGNIFICA EVO – AUTOMATIC ESPRESSO & COFFEE MACHINE\n\n✨ NEW OPEN BOX – FULLY TESTED & REA",
     "price": "400.00", "was": None, "photos": 1,
     "description": "Bring the café experience home.\n\n☕ AMAZING FEATURES:\n\n* One-touch coffee\n\n\U0001F4CD Location: Mississauga (near Square One)\n\n\U0001F697 Delivery available at reasonable charges."},
    {"id": "984841858011538", "title": "\U0001F525ECOVACS N30 OMNI ROBOT VACUUM & MOP | 10,000Pa SUCTION | 15 Days replacement warranty if faulty \U0001F525",
     "price": "250.00", "was": "CA$280", "photos": 2, "description": "SMARTER CLEANING. " + "Long text. " * 300 + "\n\n15 DAYS REPLACEMENT WARRANTY."},
    {"id": "1792027652123038", "title": "Cosco Kids Finale 2-in-1 Booster Car Seat", "price": "90.00", "was": None, "photos": 1,
     "description": "New Cosco Kids Finale 2-in-1 booster car seat."},
    {"id": "1636915607777200", "title": "\U0001F525 EMMA HYBRID 22 LITE KING MATTRESS – PREMIUM COMFORT! \U0001F525", "price": "250.00", "was": "CA$400",
     "photos": 2, "description": "Upgrade your sleep.\n\nPickup: Matheson Blvd E & Hurontario, Mississauga"},
]
STRANGER_IDS = ["900000000000001", "900000000000002", "900000000000003"]


def jpeg(seed: int, size=(720, 960)) -> bytes:
    img = Image.new("RGB", size, ((seed * 53) % 200 + 30, (seed * 97) % 200 + 30, (seed * 31) % 200 + 30))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=70)
    return buf.getvalue()


def photo_url(item_id: str, n: int) -> str:
    return f"https://scontent.fyyz1-1.fna.fbcdn.net/v/t45.5328-4/{item_id}_{n}_n.jpg?stp=dst-jpg&_nc_cat=1&oh=00_TEST&oe=6F000000"


def profile_html(items=ITEMS, seller="Ali Abbas", with_popup=True) -> str:
    def card(i, title):
        return (f'<div><a href="/marketplace/item/{i}/?ref=marketplace_profile" role="link"><img alt="{title[:20]}" '
                f'src="{photo_url(i, 1).replace("&", "&amp;")}"><span>CA$1</span><span>{title[:30]}</span></a></div>')
    feed = "".join(card(i, "Someone else's item") for i in STRANGER_IDS)
    popup = ""
    if with_popup:
        popup = (f'<div role="dialog" aria-label="Seller details"><div style="height:300px;overflow-y:auto">'
                 f'<h2><span>{seller}</span></h2><span>Joined Facebook in 2025</span><span>20+ active listings</span>'
                 + "".join(card(it["id"], it["title"].split("\n")[0]) for it in items)
                 + f'<a href="/marketplace/item/{items[0]["id"]}/">duplicate link</a></div></div>' if items else
                 f'<div role="dialog"><h2>{seller}</h2><span>No listings</span></div>')
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>(14) Facebook</title></head><body>'
            f'<div role="main"><h1>Marketplace</h1>{feed}</div>{popup}</body></html>')


def item_html(item: dict, seller_id: str = SELLER_ID) -> str:
    listing = {
        "__typename": "GroupCommerceProductItem", "id": item["id"], "marketplace_listing_title": item["title"],
        "redacted_description": {"text": item["description"]},
        "listing_price": {"amount": item["price"], "currency": "CAD"},
        "strikethrough_price": {"formattedAmountWithoutDecimals": item["was"]} if item["was"] else None,
        "attribute_data": [{"attribute_name": "Condition", "value": "new", "label": "New"}],
        "location_text": {"text": "Mississauga, ON"}, "is_sold": False, "is_pending": False, "is_live": True,
        "creation_time": 1794700000, "marketplace_listing_seller": {"id": seller_id, "name": "Ali Abbas"},
    }
    photos = {"__typename": "GroupCommerceProductItem", "id": item["id"], "is_hidden": False, "pre_recorded_videos": [],
              "listing_photos": [{"id": str(n), "image": {"uri": photo_url(item["id"], n), "width": 720, "height": 960}}
                                 for n in range(1, item["photos"] + 1)]}
    related = {"id": STRANGER_IDS[0], "marketplace_listing_title": "Someone else's sofa",
               "redacted_description": {"text": "not ours"}, "listing_price": {"amount": "5.00", "currency": "CAD"},
               "listing_photos": [{"image": {"uri": photo_url(STRANGER_IDS[0], 1)}}]}

    def script(obj):
        body = json.dumps({"require": [["ScheduledServerJS", "handle", None, [{"__bbox": {"result": {"data": obj}}}]]]})
        return f'<script type="application/json" data-sjs>{body.replace("</", "<\\/")}</script>'
    return (f'<!DOCTYPE html><html><head><meta charset="utf-8"><title>Marketplace | Facebook</title></head><body>'
            f'{script({"viewer": {"related": [related]}})}{script({"viewer": {"marketplace_product_details_page": {"target": listing}}})}'
            f'{script({"node": photos})}<script type="application/json">not json {item["id"]} redacted_description</script>'
            f'<h1>{item["title"].splitlines()[0]}</h1></body></html>')


LOGGED_OUT = ('<!DOCTYPE html><html><head><title>Log into Facebook</title></head><body><form id="login_form" '
              'action="/login/device-based/regular/login/"><input name="email"><input name="pass" type="password"></form></body></html>')


def make_pull(items=ITEMS, pulled_at="2026-11-15T14:07:00.000Z") -> dict:
    """A pull file exactly as scraper/browser/export_pull.js writes it."""
    listings = []
    for k, it in enumerate(items):
        photos = []
        for n in range(1, it["photos"] + 1):
            data = jpeg(k * 10 + n)
            photos.append({"name": f"{it['id']}_{n}.jpg", "type": "image/jpeg", "bytes": len(data),
                           "sha256": hashlib.sha256(data).hexdigest(), "base64": base64.b64encode(data).decode()})
        listings.append({
            "id": it["id"], "url": f"https://www.facebook.com/marketplace/item/{it['id']}/", "title": it["title"],
            "price": it["price"], "currency": "CAD", "previous_price": it["was"], "condition": "New",
            "location": "Mississauga, ON", "status": "available", "seller_id": SELLER_ID,
            "listed_at": "2026-11-14T12:00:00.000Z", "description": it["description"],
            "description_sha256": hashlib.sha256(it["description"].encode("utf-8")).hexdigest(), "photos": photos})
    return {"source": "facebook-marketplace", "format": 1,
            "profile_url": f"https://www.facebook.com/marketplace/profile/{SELLER_ID}/", "pulled_at": pulled_at,
            "count": len(listings), "listings": listings}
