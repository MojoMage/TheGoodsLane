"""Turn a pull file from the browser into the data the site is built from.

    python -m scraper.ingest ~/Desktop/TheGoodsLane/goods-lane-pull-2026-11-15-0907.json
    python -m scraper.ingest <file> --force     # accept a large drop in inventory

Input: the single JSON file written by scraper/browser/export_pull.js (text plus photos).
Output: data/listings.json and data/photos/<listing id>/<n>.jpg.

Ingest is strict on purpose. A signed-out browser or a Facebook layout change shows up as
"no listings" or "most of the inventory vanished"; publishing that would wipe the public
site. Such pulls are rejected and the previous data stays live.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import re
import shutil
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

from PIL import Image

from . import retail as retail_prices
from .titles import clean_title, drop_company_name

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
MAX_SHRINK = 0.6  # largest share of yesterday's inventory that may vanish in one day


class PullRejected(Exception):
    """The pull looks broken; do not publish it."""


CATEGORIES = [
    # (slug, name, pattern) - first match on the title wins, then the description
    ("coffee", "Coffee machines", r"coffee|espresso|nespresso|keurig|barista|grinder|latte|cappuccino"),
    ("floor-care", "Robot vacuums and floor care",
     r"vacuum|robot|deebot|roomba|roborock|dreame|\bmop\b|spot cleaner|carpet|upholstery|steam cleaner"),
    ("garden", "Garden and outdoor", r"leaf blower|blower|lawn|mower|hedge|trimmer|pressure washer|garden|patio|snow"),
    ("kids", "Baby and kids", r"car seat|booster|stroller|crib|high chair|toddler|\bkids\b|\bbaby\b"),
    ("bedroom", "Mattresses and furniture", r"mattress|bed frame|\bbed\b|sofa|couch|dresser|desk|\bchair\b|\btable\b"),
    ("kitchen", "Kitchen",
     r"kitchen|air ?fryer|blender|mixer|toaster|oven|microwave|kettle|juicer|instant pot|cooker|food processor|"
     r"compost|waffle|griddle|grill|dishwasher|fridge|freezer|cookware"),
    ("heating-air", "Heating and air", r"heater|purifier|humidifier|dehumidifier|\bfan\b|air conditioner|thermostat"),
    ("tech", "TVs, audio and tech",
     r"\btv\b|television|monitor|speaker|soundbar|headphone|earbud|airpods|laptop|tablet|ipad|iphone|phone|camera|"
     r"console|playstation|xbox|nintendo|router|printer|projector|smart ?watch|drone"),
    ("personal-care", "Personal care", r"hair|dryer|straightener|shaver|toothbrush|massager"),
]
DEFAULT_CATEGORY = ("home", "Home")

BRANDS = [
    "De'Longhi", "Ecovacs", "Dyson", "Ninja", "Breville", "Shark", "iRobot", "Roborock", "Dreame", "Eufy", "Samsung",
    "LG", "Sony", "Apple", "Bose", "JBL", "KitchenAid", "Nespresso", "Philips", "Keurig", "Cuisinart", "Vitamix",
    "Tineco", "Bissell", "Instant Pot", "Jura", "Miele", "Bosch", "Panasonic", "Hamilton Beach", "Google", "Amazon",
    "HP", "Dell", "Lenovo", "Levoit", "Honeywell", "Sonos", "Anker", "Hoover", "Emma", "Cosco", "Litheli", "Steelite",
    "Compost Genie", "Graco", "Greenworks", "Ryobi", "DeWalt", "Makita", "Sealy", "Endy", "Casper", "Yeedi", "Narwal",
]
BRAND_ALIASES = {"de longhi": "De'Longhi", "delonghi": "De'Longhi", "deebot": "Ecovacs", "roomba": "iRobot"}
MSRP_RE = re.compile(
    r"(?:msrp|retail(?:s|ing)?(?:\s+(?:price|value|for|at))?|reg(?:ular)?\.?(?:\s+price)?|sells?\s+for|"
    r"new\s+(?:price|for|at)|list\s+price|store\s+price)\s*(?:is|was|of|:|-|–|=|at|for)?\s*(?:cad|ca|c)?\s*\$\s*"
    r"([\d][\d,]*(?:\.\d{1,2})?)", re.I)


def _key(text: str) -> str:
    text = (text or "").lower().replace("'", "").replace("’", "")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", text).split())


_BRAND_KEYS = sorted(list({_key(b): b for b in BRANDS}.items()) + list(BRAND_ALIASES.items()), key=lambda kv: -len(kv[0]))


def slugify(text: str, max_len: int = 60) -> str:
    text = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", re.sub(r"['’`]", "", text.lower())).strip("-")
    if len(text) > max_len:
        text = text[:max_len].rsplit("-", 1)[0]
    return text or "item"


def to_amount(value) -> float | None:
    """250, "250.00", "$1,250", "CA$280" -> float; anything else -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value) if value >= 0 else None
    s = str(value).strip()
    if s.lower() == "free":
        return 0.0
    m = re.fullmatch(r"(?:CA|C|US)?\s*\$?\s*([\d][\d,]*(?:\.\d{1,2})?)", s, re.I)
    return float(m.group(1).replace(",", "")) if m else None


def detect_category(title: str, description: str = "") -> tuple[str, str]:
    for hay in (title or "", description or ""):
        for slug, name, pattern in CATEGORIES:
            if re.search(pattern, hay, re.I):
                return slug, name
    return DEFAULT_CATEGORY


def detect_brand(title: str) -> str | None:
    hay = f" {_key(title)} "
    hits = [(hay.find(f" {key} "), brand) for key, brand in _BRAND_KEYS if f" {key} " in hay]
    return min(hits)[1] if hits else None  # the brand named first


def detect_msrp(description: str, price: float | None) -> float | None:
    best = None
    for m in MSRP_RE.finditer(description or ""):
        value = float(m.group(1).replace(",", ""))
        if price is not None and value <= price:
            continue
        best = value if best is None else max(best, value)
    return best


def pct_off(price: float | None, reference: float | None) -> int | None:
    if not price or not reference or reference <= price:
        return None
    return round((1 - price / reference) * 100)


def decode_photos(item: dict) -> list[tuple[bytes, int, int]]:
    """Check every photo against its checksum and make sure it really is an image."""
    out = []
    for p in item.get("photos") or []:
        data = base64.b64decode(p["base64"])
        if hashlib.sha256(data).hexdigest() != p.get("sha256") or len(data) != p.get("bytes"):
            raise PullRejected(f"photo {p.get('name')} of listing {item.get('id')} is damaged (checksum mismatch)")
        try:
            with Image.open(io.BytesIO(data)) as im:
                im.load()
                out.append((data, im.width, im.height))
        except Exception as exc:
            raise PullRejected(f"photo {p.get('name')} of listing {item.get('id')} is not a readable image: {exc}")
    return out


def normalize(item: dict, override: dict, old: dict, now: datetime, photos: list[tuple[bytes, int, int]],
              retail: dict | None = None) -> dict:
    listing_id = str(item.get("id") or "").strip()
    if not listing_id.isdigit():
        raise ValueError(f"listing has no numeric id: {str(item)[:80]}")
    facebook_title = drop_company_name(str(item.get("title") or "")).strip()
    title = " ".join(str(override.get("title") or clean_title(facebook_title)).split())
    if not title:
        raise ValueError(f"listing {listing_id} has no title")
    description = drop_company_name(str(item.get("description") or "").replace("\r\n", "\n")).strip()
    if "description_sha256" in item and hashlib.sha256(
            str(item.get("description") or "").encode("utf-8")).hexdigest() != item["description_sha256"]:
        raise PullRejected(f"description of listing {listing_id} is damaged (checksum mismatch)")
    price = to_amount(item.get("price"))
    previous = to_amount(item.get("previous_price"))
    manual = to_amount(override.get("msrp"))
    entry = None if manual else retail_prices.lookup(retail or {}, listing_id, price)
    msrp = manual or (entry["retail_price"] if entry else None) or detect_msrp(description, price)
    if override.get("category"):
        slug = slugify(override["category"])
        cat = (slug, next((n for s, n, _ in CATEGORIES if s == slug), override["category"]))
    else:
        cat = detect_category(title, description)
    status = str(item.get("status") or "available").lower()
    return {
        "id": listing_id,
        "slug": old.get("slug") or f"{slugify(title)}-{listing_id}",  # keep the first URL even if the title changes
        "url": f"https://www.facebook.com/marketplace/item/{listing_id}/",
        "title": title,
        "facebook_title": facebook_title,
        "description": description,
        "price": price,
        "currency": item.get("currency") or "CAD",
        "previous_price": previous if previous and price is not None and previous > price else None,
        "msrp": msrp,
        "discount_pct": pct_off(price, msrp),
        **retail_prices.fields(entry),
        "condition": " ".join(str(item.get("condition") or "").split()),
        "location": " ".join(str(item.get("location") or "").split()),
        "brand": override.get("brand") or detect_brand(title),
        "category": cat[0],
        "category_name": cat[1],
        "status": status if status in ("available", "pending", "sold") else "available",
        "hidden": bool(override.get("hidden", False)),
        "listed_at": item.get("listed_at"),
        "first_seen": old.get("first_seen") or now.isoformat(timespec="seconds"),
        "last_seen": now.isoformat(timespec="seconds"),
        "photos": [{"file": f"photos/{listing_id}/{i}.jpg", "width": w, "height": h}
                   for i, (_, w, h) in enumerate(photos, 1)],
    }


def validate(listings: list[dict], previous: list[dict], pull: dict, expected_seller: str | None, force: bool) -> None:
    if pull.get("source") != "facebook-marketplace" or not isinstance(pull.get("listings"), list):
        raise PullRejected("This is not a Goods Lane pull file.")
    if not listings:
        raise PullRejected("The pull has no listings (signed out of Facebook, or the page layout changed).")
    strangers = [i["id"] for i in pull["listings"] if expected_seller and i.get("seller_id")
                 and str(i["seller_id"]) != str(expected_seller)]
    if strangers:
        raise PullRejected(f"{len(strangers)} listing(s) belong to another seller: {', '.join(strangers[:5])}")
    no_price = [l["id"] for l in listings if l["price"] is None]
    if len(no_price) > len(listings) / 2:
        raise PullRejected(f"{len(no_price)} of {len(listings)} listings have no price - layout change?")
    no_photo = [l["id"] for l in listings if not l["photos"]]
    if len(no_photo) > len(listings) / 2:
        raise PullRejected(f"{len(no_photo)} of {len(listings)} listings have no photo - layout change?")
    before = len([l for l in previous if l.get("status") != "sold"])
    if not force and before >= 4 and len(listings) < before * (1 - MAX_SHRINK):
        raise PullRejected(f"Inventory dropped from {before} to {len(listings)} listings in one run. "
                           "If that is real, run again with --force.")


def ingest(pull: dict, previous: dict | None = None, overrides: dict | None = None, now: datetime | None = None,
           force: bool = False, expected_seller: str | None = None, retail: dict | None = None) -> tuple[dict, dict[str, list[bytes]]]:
    """Pure function: pull + previous snapshot -> (new snapshot, photo bytes by listing id)."""
    now = now or datetime.now(timezone.utc)
    previous, overrides = previous or {}, overrides or {}
    old_by_id = {l["id"]: l for l in previous.get("listings", [])}
    listings, photo_bytes, skipped = [], {}, []
    for item in pull.get("listings") or []:
        try:
            photos = decode_photos(item)
            listing = normalize(item, overrides.get(str(item.get("id")), {}), old_by_id.get(str(item.get("id")), {}),
                                now, photos, retail)
        except ValueError as exc:
            skipped.append(str(exc))
            continue
        listings.append(listing)
        photo_bytes[listing["id"]] = [data for data, _, _ in photos]
    validate(listings, previous.get("listings", []), pull, expected_seller, force)
    snapshot = {
        "updated_at": now.isoformat(timespec="seconds"),
        "pulled_at": pull.get("pulled_at") or now.isoformat(timespec="seconds"),
        "profile_url": pull.get("profile_url"),
        "count": len(listings),
        "skipped": skipped,
        "listings": listings,  # kept in the order Facebook shows them: newest first
    }
    return snapshot, photo_bytes


def write(snapshot: dict, photo_bytes: dict[str, list[bytes]], data_dir: Path) -> None:
    photos_dir = data_dir / "photos"
    if photos_dir.exists():
        shutil.rmtree(photos_dir)  # photos of sold items go; current ones are rewritten below
    for listing_id, blobs in photo_bytes.items():
        folder = photos_dir / listing_id
        folder.mkdir(parents=True, exist_ok=True)
        for i, data in enumerate(blobs, 1):
            (folder / f"{i}.jpg").write_bytes(data)
    (data_dir / "listings.json").write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("pull", help="pull file written by the browser")
    ap.add_argument("--data-dir", default=str(DATA_DIR))
    ap.add_argument("--force", action="store_true", help="accept a large drop in inventory")
    args = ap.parse_args(argv)
    data_dir = Path(args.data_dir)
    previous = load_json(data_dir / "listings.json", {})
    config = load_json(ROOT / "site.config.json", {})
    try:
        pull = json.loads(Path(args.pull).read_text(encoding="utf-8"))
        snapshot, photos = ingest(pull, previous, load_json(data_dir / "overrides.json", {}), force=args.force,
                                  expected_seller=config.get("facebook_profile_id"), retail=retail_prices.load())
    except (PullRejected, json.JSONDecodeError, KeyError) as exc:
        print(f"REJECTED: {exc}\nKept the existing data unchanged.", file=sys.stderr)
        return 2
    write(snapshot, photos, data_dir)
    new_ids, old_ids = {l["id"] for l in snapshot["listings"]}, {l["id"] for l in previous.get("listings", [])}
    print(f"OK: {snapshot['count']} listings, {sum(len(p) for p in photos.values())} photos "
          f"(+{len(new_ids - old_ids)} new, -{len(old_ids - new_ids)} gone, {len(snapshot['skipped'])} skipped)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
