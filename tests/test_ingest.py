"""Pull file -> data/listings.json + photos: normalising, and never publishing a broken pull."""
import copy
import json
from datetime import datetime, timezone

import pytest

from scraper import ingest
from scraper.ingest import PullRejected
from tests import fakefb

NOW = datetime(2026, 11, 15, 14, 7, tzinfo=timezone.utc)
SELLER = fakefb.SELLER_ID


def run(pull, **kw):
    return ingest.ingest(pull, now=kw.pop("now", NOW), expected_seller=SELLER, **kw)


def test_every_listing_comes_through_in_facebook_order(pull):
    snap, photos = run(pull)
    assert snap["count"] == 4 and [l["id"] for l in snap["listings"]] == [i["id"] for i in fakefb.ITEMS]
    assert {k: len(v) for k, v in photos.items()} == {i["id"]: i["photos"] for i in fakefb.ITEMS}


def test_listing_shape(pull):
    l = run(pull)[0]["listings"][1]
    assert l["title"] == "Ecovacs N30 Omni Robot Vacuum & Mop | 10,000Pa Suction | 15 Days replacement warranty if faulty"
    assert l["facebook_title"].startswith("\U0001F525ECOVACS")
    assert l["slug"] == "ecovacs-n30-omni-robot-vacuum-mop-10-000pa-suction-15-days-984841858011538"
    assert l["price"] == 250.0 and l["previous_price"] == 280.0 and l["currency"] == "CAD"
    assert l["condition"] == "New" and l["brand"] == "Ecovacs" and l["category"] == "floor-care"
    assert l["photos"] == [{"file": "photos/984841858011538/1.jpg", "width": 720, "height": 960},
                           {"file": "photos/984841858011538/2.jpg", "width": 720, "height": 960}]
    assert l["msrp"] is None and l["discount_pct"] is None, "no retail price is invented"


@pytest.mark.parametrize("title,slug", [
    ("De'Longhi Magnifica Evo – Automatic Espresso & Coffee Machine", "coffee"),
    ("Nespresso CitiZ Platinum Espresso Machine", "coffee"),
    ("Ecovacs Deebot T30S Floor Cleaning Robot", "floor-care"),
    ("Hoover CleanSlate Pet+ Carpet & Upholstery Spot Cleaner", "floor-care"),
    ("Hoover Cordless Stick Vacuum", "floor-care"),
    ("Steelite Cordless Leaf Blower – 20V", "garden"),
    ("Cosco Kids Finale 2-in-1 Booster Car Seat", "kids"),
    ("Emma Hybrid 22 Lite King Mattress", "bedroom"),
    ("Ninja Deluxe Kitchen System", "kitchen"),
    ("Compost Genie 14L Compost Dust Bin", "kitchen"),
    ("De'Longhi Ceramic Tower Heater-New Open Box", "heating-air"),
    ("Sony WH-1000XM5 headphones", "tech"),
    ("Brass floor lamp", "home"),
])
def test_category(title, slug):
    assert ingest.detect_category(title)[0] == slug


@pytest.mark.parametrize("title,brand", [
    ("De'Longhi Magnifica Evo", "De'Longhi"), ("DeLonghi Ceramic Tower Heater", "De'Longhi"),
    ("Ecovacs Deebot X2 Omni", "Ecovacs"), ("Deebot N10", "Ecovacs"), ("Emma Hybrid Comfort", "Emma"),
    ("Litheli U20 Brushless Leaf Blower", "Litheli"), ("Brass floor lamp", None),
])
def test_brand(title, brand):
    assert ingest.detect_brand(title) == brand


@pytest.mark.parametrize("value,amount", [(250, 250.0), ("250.00", 250.0), ("CA$280", 280.0), ("$1,250", 1250.0),
                                          ("Free", 0.0), (None, None), ("call me", None), (True, None)])
def test_to_amount(value, amount):
    assert ingest.to_amount(value) == amount


@pytest.mark.parametrize("text,price,expected", [
    ("Retails for $999.99 at Best Buy", 450, 999.99), ("MSRP: $549.99", 300, 549.99),
    ("Regular price $249.", 120, 249.0), ("Call 647-770-6652, $20 delivery", 100, None),
    ("Get premium comfort without paying premium retail prices!", 250, None),
])
def test_retail_price_is_only_taken_when_the_seller_states_one(text, price, expected):
    assert ingest.detect_msrp(text, price) == expected


def test_a_page_url_never_changes_when_the_seller_edits_the_title(pull):
    day1, _ = run(pull)
    edited = copy.deepcopy(pull)
    edited["listings"][2]["title"] = "COSCO BOOSTER SEAT - PRICE DROP"
    day2, _ = run(edited, previous=day1, now=datetime(2026, 11, 16, 14, 7, tzinfo=timezone.utc))
    assert day2["listings"][2]["title"] == "Cosco Booster Seat - Price Drop"
    assert day2["listings"][2]["slug"] == day1["listings"][2]["slug"]
    assert day2["listings"][2]["first_seen"].startswith("2026-11-15") and day2["listings"][2]["last_seen"].startswith("2026-11-16")


def test_overrides(pull):
    snap, _ = run(pull, overrides={"1792027652123038": {"msrp": 180, "hidden": True}, "1636915607777200": {"category": "tech"}})
    by = {l["id"]: l for l in snap["listings"]}
    assert by["1792027652123038"]["msrp"] == 180 and by["1792027652123038"]["discount_pct"] == 50
    assert by["1792027652123038"]["hidden"] is True and by["1636915607777200"]["category"] == "tech"


def test_write_puts_photos_on_disk_and_drops_sold_items_photos(tmp_path, pull):
    snap, photos = run(pull)
    ingest.write(snap, photos, tmp_path)
    assert (tmp_path / "photos" / "984841858011538" / "2.jpg").read_bytes() == fakefb.jpeg(12)
    fewer = copy.deepcopy(pull)
    fewer["listings"] = fewer["listings"][1:]
    snap2, photos2 = run(fewer, previous=snap)
    ingest.write(snap2, photos2, tmp_path)
    assert not (tmp_path / "photos" / "1647194386782124").exists()
    assert json.loads((tmp_path / "listings.json").read_text())["count"] == 3


# ---- a broken pull must never wipe the public site
def test_rejects_empty_pull(pull):
    with pytest.raises(PullRejected, match="no listings"):
        run({**pull, "listings": []})


def test_rejects_a_file_that_is_not_a_pull():
    with pytest.raises(PullRejected, match="not a Goods Lane pull"):
        run({"hello": "world", "listings": [fakefb.make_pull()["listings"][0]]})


def test_rejects_sudden_collapse_of_inventory_unless_forced():
    big = fakefb.make_pull([{**fakefb.ITEMS[0], "id": str(1000 + i)} for i in range(10)])
    day1, _ = run(big)
    small = {**big, "listings": big["listings"][:3]}
    with pytest.raises(PullRejected, match="dropped from 10 to 3"):
        run(small, previous=day1)
    assert run(small, previous=day1, force=True)[0]["count"] == 3


def test_rejects_listings_from_another_seller(pull):
    bad = copy.deepcopy(pull)
    bad["listings"][0]["seller_id"] = "999"
    with pytest.raises(PullRejected, match="another seller"):
        run(bad)


def test_rejects_a_damaged_photo(pull):
    bad = copy.deepcopy(pull)
    bad["listings"][0]["photos"][0]["base64"] = bad["listings"][0]["photos"][0]["base64"][:-8] + "AAAAAAA="
    with pytest.raises(PullRejected, match="damaged"):
        run(bad)


def test_rejects_a_damaged_description(pull):
    bad = copy.deepcopy(pull)
    bad["listings"][0]["description"] += " tampered"
    with pytest.raises(PullRejected, match="description of listing"):
        run(bad)


def test_rejects_layout_change_that_loses_prices(pull):
    bad = copy.deepcopy(pull)
    for l in bad["listings"]:
        l["price"] = None
    with pytest.raises(PullRejected, match="no price"):
        run(bad)


def test_one_malformed_listing_is_skipped_not_fatal(pull):
    odd = copy.deepcopy(pull)
    odd["listings"].append({"id": "abc", "title": "x", "photos": []})
    snap, _ = run(odd)
    assert snap["count"] == 4 and len(snap["skipped"]) == 1


def test_cli_leaves_existing_data_alone_when_rejected(tmp_path, pull):
    good, bad = tmp_path / "good.json", tmp_path / "bad.json"
    good.write_text(json.dumps(pull))
    bad.write_text(json.dumps({**pull, "listings": []}))
    data = tmp_path / "data"
    assert ingest.main([str(good), "--data-dir", str(data)]) == 0
    before = (data / "listings.json").read_text()
    assert ingest.main([str(bad), "--data-dir", str(data)]) == 2
    assert (data / "listings.json").read_text() == before and (data / "photos" / "984841858011538" / "1.jpg").exists()


def test_change_report_names_new_gone_and_repriced_listings(pull):
    from scraper import changes
    day1, _ = run(pull)
    later = copy.deepcopy(pull)
    later["listings"][0]["price"] = "340.00"
    later["listings"] = later["listings"][:3] + [{**copy.deepcopy(later["listings"][2]), "id": "555", "title": "Shark Navigator vacuum"}]
    day2, _ = run(later, previous=day1)
    lines = changes.diff(day1["listings"], day2["listings"])
    assert lines == ["New: Shark Navigator vacuum ($90)", "Gone: Emma Hybrid 22 Lite King Mattress – Premium Comfort ($250)",
                     "Repriced: De'Longhi Magnifica Evo – Automatic Espresso & Coffee Machine $400 -> $340"]
    assert changes.diff(day1["listings"], day1["listings"]) == []


RETAIL = {"984841858011538": {"retail_price": 499.99, "source": "Ecovacs Canada", "url": "https://www.ecovacs.com/ca/", "basis": "regular", "checked": "2026-11-15"}}


def test_retail_price_from_the_retail_file_gives_the_percent_off(pull):
    l = run(pull, retail=RETAIL)[0]["listings"][1]
    assert l["price"] == 250.0 and l["msrp"] == 499.99 and l["discount_pct"] == 50
    assert l["retail_source"] == "Ecovacs Canada" and l["retail_url"] == "https://www.ecovacs.com/ca/"
    assert l["retail_basis"] == "regular" and l["retail_checked"] == "2026-11-15"


@pytest.mark.parametrize("entry", [
    {"retail_price": 250, "source": "Shop"},            # same as the asking price: no saving to show
    {"retail_price": 199.99, "source": "Shop"},         # below the asking price
    {"retail_price": 499.99},                           # no source named
    {"retail_price": "499.99", "source": "Shop"},       # not a number
    {"status": "not_found", "note": "US price only"},
])
def test_a_retail_price_that_is_not_a_real_saving_is_never_shown(pull, entry):
    l = run(pull, retail={"984841858011538": entry})[0]["listings"][1]
    assert l["msrp"] is None and l["discount_pct"] is None and l["retail_source"] is None


def test_a_manual_override_beats_the_retail_file(pull):
    l = run(pull, retail=RETAIL, overrides={"984841858011538": {"msrp": 600}})[0]["listings"][1]
    assert l["msrp"] == 600 and l["discount_pct"] == 58 and l["retail_source"] is None


def test_missing_lists_what_still_needs_a_retail_price(pull):
    from datetime import date
    from scraper import retail
    snap = run(pull, retail=RETAIL)[0]
    other = [l["id"] for l in snap["listings"] if l["id"] != "984841858011538"]
    assert [l["id"] for l in retail.missing(snap["listings"], RETAIL, date(2026, 11, 16))] == other
    tried = {**RETAIL, other[0]: {"status": "not_found", "checked": "2026-11-15"}}
    assert [l["id"] for l in retail.missing(snap["listings"], tried, date(2026, 11, 16))] == other[1:], "not retried the next day"
    assert [l["id"] for l in retail.missing(snap["listings"], tried, date(2026, 12, 20))] == other, "retried after a month"


def test_apply_puts_new_retail_prices_on_an_existing_snapshot(pull):
    from scraper import retail
    snap = run(pull)[0]
    assert retail.apply(snap, RETAIL) == 1
    l = snap["listings"][1]
    assert l["msrp"] == 499.99 and l["discount_pct"] == 50 and l["retail_source"] == "Ecovacs Canada"
    assert retail.apply(snap, {}) == 0 and l["msrp"] is None and l["retail_source"] is None, "a removed price disappears"


def test_company_name_never_reaches_the_site_data(pull):
    import hashlib
    item = pull["listings"][0]
    item["description"] += "\n\nThe Goods Lane by Abbottcom\nQuality products at great prices!"
    item["description_sha256"] = hashlib.sha256(item["description"].encode("utf-8")).hexdigest()
    item["title"] += " – The Goods Lane by Abbottcom"
    l = run(pull)[0]["listings"][0]
    blob = json.dumps(l).lower()
    assert "abbott" not in blob and "The Goods Lane\nQuality products at great prices!" in l["description"]
