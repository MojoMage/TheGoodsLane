import os
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def pytest_configure(config):
    config.addinivalue_line("markers", "browser: needs a local Chrome/Chromium (skipped if none)")


@pytest.fixture(scope="session")
def pull():
    from tests.fakefb import make_pull
    return make_pull()


@pytest.fixture()
def built(tmp_path, pull):
    """Ingest the sample pull and build the site into a temp folder."""
    from build import build as site_build
    from scraper import ingest
    snapshot, photos = ingest.ingest(pull, expected_seller="61577549634421")
    ingest.write(snapshot, photos, tmp_path / "data")
    stats = site_build.build(tmp_path / "out", "https://example.github.io/TheGoodsLane", tmp_path / "data")
    return {"out": tmp_path / "out", "data": tmp_path / "data", "stats": stats, "snapshot": snapshot}


@pytest.fixture(scope="session")
def browser():
    """A headless Chromium for running extract.js and the built pages for real."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        pytest.skip("playwright is not installed")
    pw = sync_playwright().start()
    exe = os.environ.get("CHROME_PATH") or shutil.which("google-chrome") or shutil.which("chromium")
    try:
        b = pw.chromium.launch(executable_path=exe, args=["--no-sandbox"]) if exe else pw.chromium.launch()
    except Exception as exc:  # no browser on this machine
        pw.stop()
        pytest.skip(f"no browser available: {exc}")
    yield b
    b.close()
    pw.stop()


@pytest.fixture()
def page(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    yield pg
    ctx.close()
