"""Brand-new retail prices for listings, kept in data/retail_prices.json.

    python3 -m scraper.retail missing   # listings that still need a retail price looked up
    python3 -m scraper.retail apply     # put the prices in the file onto data/listings.json

A retail price is only used when it is a Canadian-dollar price for the exact model, from a
Canadian retailer or the manufacturer, and higher than the asking price. A listing without
one shows no "% off": the site never estimates a saving.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FILE = ROOT / "data" / "retail_prices.json"
RETRY_AFTER_DAYS = 30


def load(path: Path = FILE) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def lookup(retail: dict, listing_id: str, price: float | None) -> dict | None:
    """The usable retail entry for a listing, or None."""
    entry = retail.get(str(listing_id)) or {}
    value = entry.get("retail_price")
    if not isinstance(value, (int, float)) or isinstance(value, bool) or not entry.get("source"):
        return None
    if price is None or value <= price:
        return None  # a "retail price" at or below the asking price is not a saving
    return entry


def fields(entry: dict | None) -> dict:
    if not entry:
        return {"retail_source": None, "retail_url": None, "retail_basis": None, "retail_checked": None}
    return {"retail_source": entry["source"], "retail_url": entry.get("url"),
            "retail_basis": entry.get("basis", "regular"), "retail_checked": entry.get("checked")}


def missing(listings: list[dict], retail: dict, today: date | None = None) -> list[dict]:
    """Listings with no retail price that are due for a (re)search."""
    today = today or date.today()
    due = []
    for l in listings:
        if l.get("msrp") or l.get("status") == "sold":
            continue
        entry = retail.get(l["id"]) or {}
        checked = entry.get("checked")
        if entry.get("status") == "not_found" and checked and \
                date.fromisoformat(checked) > today - timedelta(days=RETRY_AFTER_DAYS):
            continue
        due.append(l)
    return due


def apply(snapshot: dict, retail: dict, overrides: dict | None = None) -> int:
    """Recompute retail price and % off on every listing. Returns how many have one."""
    from .ingest import detect_msrp, pct_off, to_amount
    overrides = overrides or {}
    count = 0
    for l in snapshot["listings"]:
        entry = lookup(retail, l["id"], l["price"])
        manual = to_amount((overrides.get(l["id"]) or {}).get("msrp"))
        l["msrp"] = manual or (entry["retail_price"] if entry else None) or detect_msrp(l["description"], l["price"])
        l["discount_pct"] = pct_off(l["price"], l["msrp"])
        l.update(fields(entry if entry and not manual else None))
        count += bool(l["discount_pct"])
    return count


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    path = ROOT / "data" / "listings.json"
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    retail = load()
    if args == ["missing"]:
        due = missing(snapshot["listings"], retail)
        print(f"{len(due)} listing(s) need a retail price:")
        for l in due:
            print(f"- {l['id']}: {l['title']} (asking ${l['price']:g})\n    Facebook title: {l['facebook_title'].splitlines()[0]}")
        return 0
    if args == ["apply"]:
        try:
            overrides = json.loads((ROOT / "data" / "overrides.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            overrides = {}
        n = apply(snapshot, retail, overrides)
        path.write_text(json.dumps(snapshot, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"{n} of {len(snapshot['listings'])} listings now show a retail price and % off.")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main())
