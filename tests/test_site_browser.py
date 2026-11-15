"""The built pages opened in a phone-sized browser: layout and the Messenger -> WhatsApp failsafe."""
import functools
import http.server
import threading

import pytest

from build import build as site_build
from scraper import ingest
from tests import fakefb

pytestmark = pytest.mark.browser


@pytest.fixture(scope="module")
def served(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("served")
    snap, photos = ingest.ingest(fakefb.make_pull(), expected_seller=fakefb.SELLER_ID)
    ingest.write(snap, photos, tmp / "data")
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp / "out"))
    handler.log_message = lambda *a, **k: None
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    base = f"http://127.0.0.1:{server.server_address[1]}"
    site_build.build(tmp / "out", base, tmp / "data")
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield {"base": base, "item": f"/item/{snap['listings'][1]['slug']}/"}
    server.shutdown()


@pytest.mark.parametrize("path", ["/", "ITEM", "/shop/floor-care/", "/404.html"])
def test_no_sideways_scroll_on_a_phone(page, served, path):
    page.goto(served["base"] + (served["item"] if path == "ITEM" else path))
    assert page.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth")


def test_fonts_and_photos_load(page, served):
    failed = []
    page.on("response", lambda r: failed.append(r.url) if r.status >= 400 else None)
    page.goto(served["base"] + served["item"], wait_until="networkidle")
    assert failed == []
    assert page.evaluate("document.fonts.check('500 20px \"Inter Display\"') && document.fonts.check('16px Inter')")
    assert page.evaluate("[...document.querySelectorAll('.gallery img')].every(i => i.complete && i.naturalWidth > 0)")


def test_tap_targets_are_thumb_sized(page, served):
    page.goto(served["base"] + served["item"])
    for box in page.eval_on_selector_all(".bar .btn, header .chan", "els => els.map(e => e.getBoundingClientRect().toJSON())"):
        assert box["height"] >= 40 and box["width"] >= 44


def test_home_card_opens_the_item_page(page, served):
    page.goto(served["base"] + "/")
    page.locator("ul.grid article.card a").first.click()
    assert "/item/" in page.url and page.locator("h1").inner_text()


def test_both_message_buttons_sit_side_by_side_and_open_their_chats(page, served):
    page.context.route("https://m.me/**", lambda r: r.fulfill(body="ok"))
    page.context.route("https://wa.me/**", lambda r: r.fulfill(body="ok"))
    page.goto(served["base"] + served["item"])
    for place in ("header .talk", ".bar"):
        m, w = page.locator(f"{place} .chan-m"), page.locator(f"{place} .chan-w")
        assert m.is_visible() and w.is_visible()
        mb, wb = m.bounding_box(), w.bounding_box()
        assert abs(mb["y"] - wb["y"]) < 1 and abs(mb["height"] - wb["height"]) < 1, f"{place}: same row, same height"
        assert abs(mb["width"] - wb["width"]) < 24 and mb["x"] < wb["x"], f"{place}: equal weight, Messenger first"
        assert m.locator("svg").is_visible() and w.locator("svg").is_visible()
    for sel, start in ((".bar .chan-m", "https://m.me/61577549634421"), (".bar .chan-w", "https://wa.me/16477706652?text=")):
        with page.context.expect_page() as popup:
            page.locator(sel).click()
        assert popup.value.url.startswith(start)
        popup.value.close()
        page.bring_to_front()
    assert "Ecovacs%20N30%20Omni" in page.locator(".bar .chan-w").get_attribute("href")
    assert page.locator("dialog").count() == 0 and page.locator("script:not([type])").count() == 0


def test_page_works_without_javascript(browser, served):
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    pg.goto(served["base"] + served["item"])
    assert pg.locator("h1").inner_text().startswith("Ecovacs N30 Omni")
    assert pg.locator(".bar a[href^='https://m.me/']").count() == 1 and pg.locator(".bar a[href^='https://wa.me/']").count() == 1
    ctx.close()
