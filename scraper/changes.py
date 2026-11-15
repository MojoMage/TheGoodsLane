"""Say what changed in data/listings.json since the last commit: new, gone and repriced listings.

    python3 -m scraper.changes        # run after ingest, before committing
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def diff(old: list[dict], new: list[dict]) -> list[str]:
    a, b = {l["id"]: l for l in old}, {l["id"]: l for l in new}
    lines = [f"New: {b[i]['title']} (${b[i]['price']:g})" for i in b if i not in a]
    lines += [f"Gone: {a[i]['title']} (${a[i]['price']:g})" for i in a if i not in b]
    for i in b:
        if i in a and a[i]["price"] != b[i]["price"]:
            lines.append(f"Repriced: {b[i]['title']} ${a[i]['price']:g} -> ${b[i]['price']:g}")
        if i in a and a[i]["status"] != b[i]["status"]:
            lines.append(f"Status: {b[i]['title']} {a[i]['status']} -> {b[i]['status']}")
    return lines


def main() -> int:
    new = json.loads((ROOT / "data" / "listings.json").read_text(encoding="utf-8"))["listings"]
    shown = subprocess.run(["git", "show", "HEAD:data/listings.json"], cwd=ROOT, capture_output=True, text=True)
    old = json.loads(shown.stdout)["listings"] if shown.returncode == 0 else []
    lines = diff(old, new)
    print(f"{len(new)} listings now, {len(old)} at the last commit.")
    print("\n".join(lines) if lines else "No listings added, removed or repriced.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
