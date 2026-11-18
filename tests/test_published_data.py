"""Checks on the real data committed in data/ - the last gate before a daily publish."""
import json
from pathlib import Path

from PIL import Image

DATA = Path(__file__).resolve().parent.parent / "data"


def snapshot():
    return json.loads((DATA / "listings.json").read_text(encoding="utf-8"))


def test_every_listing_has_what_a_page_needs():
    listings = snapshot()["listings"]
    assert listings, "the committed inventory is empty"
    assert len({l["id"] for l in listings}) == len(listings) and len({l["slug"] for l in listings}) == len(listings)
    for l in listings:
        assert l["id"].isdigit() and l["title"] and l["facebook_title"] and l["url"].endswith(f"/{l['id']}/")
        assert l["status"] in ("available", "pending", "sold") and l["currency"] == "CAD"
        assert l["previous_price"] is None or l["previous_price"] > l["price"]


def test_most_listings_have_a_price_description_and_photo():
    listings = snapshot()["listings"]
    for field in ("price", "description", "photos", "condition"):
        missing = [l["id"] for l in listings if l[field] in (None, "", [])]
        assert len(missing) <= len(listings) * 0.2, f"{len(missing)} listings have no {field}: {missing[:5]}"


def test_every_photo_file_exists_and_matches_its_recorded_size():
    for l in snapshot()["listings"]:
        for photo in l["photos"]:
            with Image.open(DATA / photo["file"]) as im:
                assert im.size == (photo["width"], photo["height"]), photo["file"]


def test_no_stray_photo_folders():
    ids = {l["id"] for l in snapshot()["listings"]}
    on_disk = {p.name for p in (DATA / "photos").iterdir()} if (DATA / "photos").exists() else set()
    assert on_disk == {i for i in ids if any(l["photos"] for l in snapshot()["listings"] if l["id"] == i)}


def test_every_percent_off_is_backed_by_a_named_canadian_source():
    from scraper import retail
    from scraper.ingest import pct_off
    prices = retail.load()
    listings = snapshot()["listings"]
    for l in listings:
        if l["discount_pct"] is None:
            assert l["msrp"] is None
            continue
        assert l["msrp"] > l["price"] and l["discount_pct"] == pct_off(l["price"], l["msrp"]) and 1 <= l["discount_pct"] <= 95
        entry = prices[l["id"]]
        assert entry["retail_price"] == l["msrp"] and entry["source"] == l["retail_source"] and entry["product"]
        assert entry["url"].startswith("https://") and entry["basis"] in ("regular", "launch") and entry["checked"]
    for key, entry in prices.items():
        assert key.isdigit() and ("retail_price" in entry or entry.get("status") == "not_found"), key


def test_company_name_is_nowhere_in_the_project():
    import subprocess
    root = Path(__file__).resolve().parent.parent
    files = subprocess.run(["git", "ls-files"], cwd=root, capture_output=True, text=True, check=True).stdout.split()
    hits = []
    for name in files:
        if name.startswith("tests/") or name == "scraper/titles.py":
            continue  # the filter itself and its tests have to name what they remove
        try:
            text = (root / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if "abbott" in text.lower():
            hits.append(name)
    assert hits == []


def test_no_phone_number_in_the_published_listing_text_or_config():
    import re
    root = Path(__file__).resolve().parent.parent
    for l in snapshot()["listings"]:
        for key in ("title", "facebook_title", "description"):
            assert not re.search(r"\d{3}[\s.\-]\d{3}[\s.\-]\d{4}", l[key]), (l["id"], key)
    config = json.loads((root / "site.config.json").read_text(encoding="utf-8"))
    assert "phone_display" not in config and "phone_e164" not in config
