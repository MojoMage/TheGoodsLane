"""Turn a Facebook Marketplace title into a clean page title.

Sellers write titles for the Marketplace feed: emojis, ALL CAPS, a second line that
Facebook cuts off mid-word. The wording stays the seller's; only the decoration goes.
The original title is kept in the data as `facebook_title`.
"""
from __future__ import annotations

import re
import unicodedata

KEEP_UPPER = {"XL", "LED", "TV", "UHD", "HD", "USB", "AI", "AC", "DC", "UV", "HEPA", "OLED", "QLED", "TEO", "LCD", "BBQ"}
SMALL = {"and", "or", "of", "in", "with", "if", "for", "the", "at", "a", "an", "to", "by", "on"}
SYMBOL_WORDS = {"\U0001F4AF": "100"}  # the "100" emoji carries meaning in "100% brand new"
BRAND_SPELLING = [
    (r"de\W?longhi", "De'Longhi"), (r"ecovacs", "Ecovacs"), (r"deebot", "Deebot"), (r"nespresso", "Nespresso"),
    (r"kitchenaid", "KitchenAid"), (r"irobot", "iRobot"), (r"citiz", "CitiZ"), (r"cleanslate", "CleanSlate"),
]


def strip_symbols(text: str) -> str:
    out = []
    for ch in text:
        cp = ord(ch)
        if ch in SYMBOL_WORDS:
            out.append(SYMBOL_WORDS[ch])
        elif cp in (0xFE0F, 0x200D, 0x20E3) or 0x1F000 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF \
                or unicodedata.category(ch) in ("So", "Sk", "Cs", "Co", "Cn"):
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def _cap(part: str, first: bool, was_shouty: bool) -> str:
    if not part.isalpha():
        return part                      # N30, 20V, 10,000Pa, T10+ stay as written
    if part.upper() in KEEP_UPPER and part.isupper():
        return part
    if part.isupper() and len(part) > 1 or (was_shouty and part.islower()):
        low = part.lower()
        return low if (low in SMALL and not first) else low.capitalize()
    return part


def clean_title(raw: str) -> str:
    text = (raw or "").split("\n")[0]
    text = strip_symbols(text).replace("’", "'").replace("‘", "'")
    text = re.sub(r"!+", " ", text)
    text = re.sub(r"\s+", " ", text).strip(" -–|,.")
    text = re.sub(r"\s+%", "%", text)
    text = re.sub(r"(?<=\w)- (?=\w)", " \u2013 ", text)  # "Machine- New" -> "Machine \u2013 New"
    letters = [c for c in text if c.isalpha()]
    shouty = bool(letters) and sum(c.isupper() for c in letters) / len(letters) > 0.6
    words = []
    for i, word in enumerate(text.split(" ")):
        pieces = re.split(r"([-/])", word)
        words.append("".join(_cap(p, i == 0 and j == 0, shouty) for j, p in enumerate(pieces)))
    text = " ".join(words)
    for pattern, spelling in BRAND_SPELLING:
        text = re.sub(rf"(?<![A-Za-z]){pattern}(?![A-Za-z])", spelling, text, flags=re.I)
    return text.strip()


# The seller signs listings "The Goods Lane by <company>"; the site shows the shop name only.
_COMPANY = r"abb?ott?[\s.\-]*com"
_COMPANY_TAG = re.compile(rf"[ \t]*\bby[ \t]+{_COMPANY}\b|\b{_COMPANY}\b", re.I)


def drop_company_name(text: str) -> str:
    return _COMPANY_TAG.sub("", text or "")


def plain_text(text: str, limit: int | None = None) -> str:
    """Description as one clean line (for meta descriptions and feeds)."""
    text = re.sub(r"\s+", " ", strip_symbols(text or "")).strip()
    text = re.sub(r"\s+([,.;:%])", r"\1", text)
    if limit and len(text) > limit:
        text = text[: limit - 1].rsplit(" ", 1)[0].rstrip(",.;:") + "…"
    return text
