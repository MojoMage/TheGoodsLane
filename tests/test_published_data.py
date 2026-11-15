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
