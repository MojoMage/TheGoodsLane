"""The three browser scripts, run in a real browser engine against stand-in Facebook pages.

This is the whole pull, end to end: read the seller pop-up, open each listing, keep text
and photos in the page, save one file, and feed that file to ingest.
"""
import hashlib
import json
import re
from pathlib import Path

import pytest

from scraper import ingest
from tests import fakefb

pytestmark = pytest.mark.browser
SCRIPTS = Path(__file__).resolve().parent.parent / "scraper" / "browser"
COLLECT, STORE, EXPORT = [(SCRIPTS / n).read_text() for n in ("collect_ids.js", "store_listing.js", "export_pull.js")]
PROFILE = f"https://www.facebook.com/marketplace/profile/{fakefb.SELLER_ID}/"


def fake_facebook(page, items=fakefb.ITEMS, logged_out=False, with_popup=True, photo_status=200, seller_id=fakefb.SELLER_ID):
    by_id = {it["id"]: it for it in items}
    seen = []

    def facebook(route):
        url = route.request.url
        seen.append((route.request.resource_type, url))
        m = re.search(r"/marketplace/item/(\d+)", url)
        if logged_out:
            return route.fulfill(content_type="text/html", body=fakefb.LOGGED_OUT)
        if "/marketplace/profile/" in url:
            return route.fulfill(content_type="text/html", body=fakefb.profile_html(items, with_popup=with_popup))
        if m and m.group(1) in by_id:
            return route.fulfill(content_type="text/html", body=fakefb.item_html(by_id[m.group(1)], seller_id))
        return route.fulfill(status=404, body="")

    def cdn(route):
        if photo_status != 200:
            return route.fulfill(status=photo_status, body="")
        n = int(re.search(r"_(\d+)_n\.jpg", route.request.url).group(1))
        route.fulfill(content_type="image/jpeg", headers={"access-control-allow-origin": "*"}, body=fakefb.jpeg(n))

    page.context.route("https://www.facebook.com/**", facebook)
    page.context.route("https://scontent.fyyz1-1.fna.fbcdn.net/**", cdn)
    return seen


def run_pull(page, tmp_path):
    page.goto(PROFILE)
    found = page.evaluate(COLLECT)
    stored = []
    for listing_id in found["ids"].split():
        page.goto(f"https://www.facebook.com/marketplace/item/{listing_id}/")
        stored.append(page.evaluate(STORE))
    with page.expect_download() as download:
        exported = page.evaluate(EXPORT)
    target = tmp_path / download.value.suggested_filename
    download.value.save_as(target)
    return found, stored, exported, target


def test_profile_returns_only_the_sellers_listings(page):
    fake_facebook(page)
    page.goto(PROFILE)
    found = page.evaluate(COLLECT)
    assert found["ok"] and found["count"] == 4
    assert found["ids"].split() == [it["id"] for it in fakefb.ITEMS], "pop-up order kept, duplicate link collapsed"
    assert found["feed_links_ignored"] == 3
    assert not set(found["ids"].split()) & set(fakefb.STRANGER_IDS), "feed behind the pop-up is not the seller's"


def test_profile_without_the_popup_reports_it_and_returns_no_ids(page):
    fake_facebook(page, with_popup=False)
    page.goto(PROFILE)
    found = page.evaluate(COLLECT)
    assert found["ok"] is False and found["reason"] == "seller-popup-not-found" and "ids" not in found


def test_signed_out_is_reported_not_treated_as_empty_stock(page):
    fake_facebook(page, logged_out=True)
    page.goto(PROFILE)
    assert page.evaluate(COLLECT) == {"ok": False, "reason": "login-required"}


def test_full_pull_writes_one_file_with_text_and_photos(page, tmp_path):
    fake_facebook(page)
    found, stored, exported, target = run_pull(page, tmp_path)
    assert [s["ok"] for s in stored] == [True] * 4 and [s["stored"] for s in stored] == [1, 2, 3, 4]
    assert [s["ph"] for s in stored] == [1, 2, 1, 2]
    assert exported["ok"] and exported["count"] == 4 and exported["photos"] == 6
    assert re.fullmatch(r"goods-lane-pull-\d{4}-\d\d-\d\d-\d{4}\.json", target.name)
    assert target.stat().st_size == exported["fileBytes"]

    pull = json.loads(target.read_text(encoding="utf-8"))
    assert [l["id"] for l in pull["listings"]] == found["ids"].split(), "file keeps the profile order"
    for got, want in zip(pull["listings"], fakefb.ITEMS):
        assert got["title"] == want["title"] and got["description"] == want["description"]
        assert got["price"] == want["price"] and got["previous_price"] == want["was"]
        assert got["condition"] == "New" and got["status"] == "available" and got["location"] == "Mississauga, ON"
        assert got["seller_id"] == fakefb.SELLER_ID and got["listed_at"].startswith("2026-")
        assert hashlib.sha256(got["description"].encode()).hexdigest() == got["description_sha256"]
        assert len(got["photos"]) == want["photos"]
    long_one = pull["listings"][1]["description"]
    assert len(long_one) > 3000, "long descriptions arrive whole, not cut at 1,000 characters"
    text_only = json.dumps([{k: v for k, v in l.items() if k != "photos"} for l in pull["listings"]])
    assert "fbcdn" not in text_only and "oh=" not in text_only, "no photo links leave the browser"


def test_pull_file_passes_ingest_and_photos_survive_byte_for_byte(page, tmp_path):
    fake_facebook(page)
    _, _, _, target = run_pull(page, tmp_path)
    snapshot, photos = ingest.ingest(json.loads(target.read_text(encoding="utf-8")), expected_seller=fakefb.SELLER_ID)
    assert snapshot["count"] == 4
    assert photos["984841858011538"] == [fakefb.jpeg(1), fakefb.jpeg(2)]


def test_related_listings_on_a_page_are_not_mixed_in(page, tmp_path):
    fake_facebook(page)
    _, _, _, target = run_pull(page, tmp_path)
    text = target.read_text(encoding="utf-8")
    assert "Someone else" not in text and fakefb.STRANGER_IDS[0] not in text


def test_store_refuses_a_listing_whose_photo_fails(page):
    fake_facebook(page, photo_status=403)
    page.goto(f"https://www.facebook.com/marketplace/item/{fakefb.ITEMS[0]['id']}/")
    assert page.evaluate(STORE) == {"id": fakefb.ITEMS[0]["id"], "ok": False, "reason": "photo-http-403"}


def test_export_with_nothing_stored_downloads_nothing(page):
    fake_facebook(page)
    page.goto(PROFILE)
    page.evaluate(COLLECT)  # empties the store
    assert page.evaluate(EXPORT) == {"ok": False, "reason": "nothing-stored"}


def test_a_new_pull_starts_clean(page, tmp_path):
    fake_facebook(page)
    run_pull(page, tmp_path)
    page.goto(f"https://www.facebook.com/marketplace/item/{fakefb.ITEMS[0]['id']}/")
    assert page.evaluate(STORE)["stored"] == 1, "export emptied the store"
    page.goto(PROFILE)
    page.evaluate(COLLECT)
    assert page.evaluate(EXPORT)["ok"] is False, "collect empties a half-finished earlier run"
