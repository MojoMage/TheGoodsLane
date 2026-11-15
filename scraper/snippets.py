"""Print a browser script in the exact form to paste into the browser's JavaScript tool.

    python3 -m scraper.snippets collect     # step 1, on the seller profile page
    python3 -m scraper.snippets install     # step 2a, once, on the same page
    python3 -m scraper.snippets store       # step 2b, on every listing page (short form)
    python3 -m scraper.snippets store-full  # step 2b fallback if the short form is refused
    python3 -m scraper.snippets export      # step 3, once at the end

The scripts in scraper/browser/ are commented for people. Here the comments and
indentation are stripped (nothing else changes) and `await` is put in front, which is what
the JavaScript tool needs. `install` parks the listing script in the tab's sessionStorage so
that each listing page needs only a one-line call instead of the whole script again.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BROWSER = Path(__file__).resolve().parent / "browser"
FILES = {"collect": "collect_ids.js", "store-full": "store_listing.js", "export": "export_pull.js"}
STORE_SHORT = "await eval(sessionStorage.getItem('gl_store'))"


def stripped(name: str) -> str:
    """The script without comment lines and indentation. Statements are untouched."""
    lines = []
    for line in (BROWSER / FILES[name]).read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if s and not s.startswith("//"):
            lines.append(s)
    return "\n".join(lines)


def snippet(name: str) -> str:
    if name == "store":
        return STORE_SHORT
    if name == "install":
        src = stripped("store-full")
        return ("await (async () => { const src = " + json.dumps(src) + "; sessionStorage.setItem('gl_store', src); "
                "let eval_works = false; try { eval_works = await eval('(async () => true)()'); } catch (e) {} "
                "return { ok: sessionStorage.getItem('gl_store') === src, chars: src.length, eval_works }; })()")
    return "await " + stripped(name)


def main(argv=None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1 or args[0] not in (*FILES, "store", "install"):
        print(__doc__)
        return 1
    print(snippet(args[0]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
