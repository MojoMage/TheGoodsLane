"""Generate The Goods Lane brand assets (run once; the outputs are committed).

    python build/make_brand_assets.py

The logo is the artwork supplied by the business (build/brand/logo-source.jpg): a stacked
wordmark over a rule. It is used as supplied; this script only cuts it out of its
background (so it sits on any page colour) and sizes it for the header, the browser and
phone icons and the social share card.
Fonts are Latin subsets of Inter (SIL Open Font License), self-hosted so the site
makes no third-party requests.
"""
from pathlib import Path

import numpy as np
from fontTools import subset
from PIL import Image

HERE = Path(__file__).resolve().parent
STATIC = HERE / "static"
SOURCE = HERE / "brand" / "logo-source.jpg"
FONTS = Path("/usr/share/fonts/opentype/inter")


def cut_out_logo():
    """(the wordmark on a transparent background, cropped to the artwork; the artwork's own background colour)"""
    rgb = Image.open(SOURCE).convert("RGB")
    grey = np.asarray(rgb.convert("L")).astype(float)
    background = tuple(int(v) for v in np.median(np.asarray(rgb)[:24, :24].reshape(-1, 3), axis=0))
    paper = float(np.median(grey[:24, :24]))
    ys, xs = np.where(grey < 128)
    alpha = np.clip((paper - grey) / paper, 0, 1)
    alpha[alpha < 0.08] = 0  # JPEG speckle in the background
    rgba = np.zeros(grey.shape + (4,), np.uint8)
    rgba[..., 3] = (alpha * 255).round()
    pad = 2
    logo = Image.fromarray(rgba, "RGBA").crop((xs.min() - pad, ys.min() - pad, xs.max() + 1 + pad, ys.max() + 1 + pad))
    return logo, background


def on_tile(logo, background, width, height, fill):
    """The logo centred on an opaque tile; `fill` is the share of the shorter side it takes up."""
    scale = min(width, height) * fill / max(logo.size)
    art = logo.resize((max(1, round(logo.width * scale)), max(1, round(logo.height * scale))), Image.LANCZOS)
    tile = Image.new("RGBA", (width, height), background + (255,))
    tile.alpha_composite(art, ((width - art.width) // 2, (height - art.height) // 2))
    return tile.convert("RGB")


def make_font(src, out, family, weight_name):
    opts = subset.Options(flavor="woff", layout_features=["kern", "liga", "tnum", "calt"], name_IDs=[1, 2, 3, 4, 6],
                          notdef_outline=True)
    font = subset.load_font(str(FONTS / src), opts)
    sub = subset.Subsetter(opts)
    sub.populate(unicodes=list(range(0x20, 0x7F)) + [0xA0, 0xA9, 0xAE, 0xB0, 0xB7, 0xC9, 0xE9, 0xD7, 0x2013, 0x2014,
                                                     0x2018, 0x2019, 0x201C, 0x201D, 0x2022, 0x2026, 0x2122])
    sub.subset(font)
    subset.save_font(font, str(STATIC / "fonts" / out), opts)


def main():
    (STATIC / "fonts").mkdir(parents=True, exist_ok=True)
    logo, background = cut_out_logo()
    logo.save(STATIC / "logo.png", optimize=True)
    for name, size, fill in [("favicon-32.png", 32, 0.92), ("favicon-48.png", 48, 0.9), ("apple-touch-icon.png", 180, 0.74),
                             ("icon-192.png", 192, 0.74), ("icon-512.png", 512, 0.74)]:
        on_tile(logo, background, size, size, fill).save(STATIC / name, optimize=True)
    on_tile(logo, background, 1200, 630, 0.68).save(STATIC / "og-default.png", optimize=True)

    make_font("Inter-Regular.otf", "inter-regular.woff", "Inter", "Regular")
    make_font("Inter-SemiBold.otf", "inter-semibold.woff", "Inter", "SemiBold")
    make_font("InterDisplay-Medium.otf", "inter-display-medium.woff", "Inter Display", "Medium")
    (STATIC / "fonts" / "LICENSE.txt").write_text(
        "The .woff files here are Latin subsets of Inter by Rasmus Andersson (https://rsms.me/inter/),\n"
        "licensed under the SIL Open Font License 1.1 (https://openfontlicense.org).\n")
    print("brand assets written to", STATIC)


if __name__ == "__main__":
    main()
