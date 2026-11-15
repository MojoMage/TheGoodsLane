"""Generate The Goods Lane brand assets (run once; the outputs are committed).

    python build/make_brand_assets.py

The wordmark is converted to outlines so the logo never depends on installed fonts.
Fonts are Latin subsets of Inter (SIL Open Font License), self-hosted so the site
makes no third-party requests.
"""
import subprocess
from pathlib import Path

from fontTools import subset
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

STATIC = Path(__file__).resolve().parent / "static"
FONTS = Path("/usr/share/fonts/opentype/inter")
INK, PAPER, SAGE, MIST, BLUSH, OAT = "#1F2328", "#F7F6F3", "#DCE5DA", "#D9E3EA", "#EFDDD8", "#ECE6DA"

# The mark: a lane running to the horizon, drawn with three strokes on a soft sage tile.
MARK = f'''<rect width="64" height="64" rx="18" fill="{SAGE}"/>
<path d="M19 48 28 16M45 48 36 16" fill="none" stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>
<path d="M32 20v5M32 31v6M32 43v6" fill="none" stroke="{INK}" stroke-width="2.6" stroke-linecap="round"/>'''


def outline(text, size, x, baseline, font_file="InterDisplay-Medium.otf", tracking=0.0):
    font = TTFont(FONTS / font_file)
    glyphs, cmap, hmtx = font.getGlyphSet(), font.getBestCmap(), font["hmtx"]
    scale = size / font["head"].unitsPerEm
    paths, cursor = [], x
    for ch in text:
        name = cmap[ord(ch)]
        pen = SVGPathPen(glyphs)
        glyphs[name].draw(TransformPen(pen, (scale, 0, 0, -scale, cursor, baseline)))
        if pen.getCommands():
            paths.append(pen.getCommands())
        cursor += hmtx[name][0] * scale + tracking
    return " ".join(paths), cursor


def svg(w, h, body, title="The Goods Lane"):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" '
            f'role="img" aria-label="{title}"><title>{title}</title>{body}</svg>\n')


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
    (STATIC / "mark.svg").write_text(svg(64, 64, MARK))
    (STATIC / "favicon.svg").write_text(svg(64, 64, MARK))

    d, end = outline("The Goods Lane", 34, 80, 44, tracking=-0.5)
    (STATIC / "logo.svg").write_text(svg(round(end + 4), 64, MARK + f'<path d="{d}" fill="{INK}"/>'))

    # Social share card, 1200x630: quiet paper background, wordmark, one line, four pastel tiles.
    h1, _ = outline("The Goods Lane", 104, 90, 250, tracking=-2.5)
    l1, _ = outline("New and open-box electronics and home goods", 44, 92, 334, "Inter-Regular.otf", -0.4)
    l2, _ = outline("Mississauga and the Greater Toronto Area", 44, 92, 392, "Inter-Regular.otf", -0.4)
    tiles = "".join(f'<rect x="{90 + i * 150}" y="470" width="126" height="70" rx="20" fill="{c}"/>'
                    for i, c in enumerate([SAGE, MIST, BLUSH, OAT]))
    og = (f'<rect width="1200" height="630" fill="{PAPER}"/><path d="{h1}" fill="{INK}"/>'
          f'<path d="{l1} {l2}" fill="#5F656C"/>{tiles}')
    (STATIC / "og-default.svg").write_text(svg(1200, 630, og))
    for src, out, size in [("mark.svg", "favicon-32.png", 32), ("mark.svg", "apple-touch-icon.png", 180),
                           ("mark.svg", "icon-512.png", 512), ("og-default.svg", "og-default.png", 1200)]:
        subprocess.run(["rsvg-convert", "-w", str(size), str(STATIC / src), "-o", str(STATIC / out)], check=True)
    (STATIC / "og-default.svg").unlink()

    make_font("Inter-Regular.otf", "inter-regular.woff", "Inter", "Regular")
    make_font("Inter-SemiBold.otf", "inter-semibold.woff", "Inter", "SemiBold")
    make_font("InterDisplay-Medium.otf", "inter-display-medium.woff", "Inter Display", "Medium")
    (STATIC / "fonts" / "LICENSE.txt").write_text(
        "The .woff files here are Latin subsets of Inter by Rasmus Andersson (https://rsms.me/inter/),\n"
        "licensed under the SIL Open Font License 1.1 (https://openfontlicense.org).\n")
    print("brand assets written to", STATIC)


if __name__ == "__main__":
    main()
