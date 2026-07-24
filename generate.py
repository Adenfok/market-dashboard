"""
generate.py
-----------
Builds the static website into ./docs so it can be hosted for free on GitHub
Pages (or any static host). Run locally, or on a schedule via GitHub Actions.

It does two things:
  1. Fetches live data + scores it (market_data.build_report) -> docs/data.json
  2. Turns the single-source dashboard.html into docs/index.html, swapping the
     live "/api/data" endpoint for the static "data.json" file.

So dashboard.html stays the ONE source of truth for the UI; the deployed copy
is always regenerated from it.
"""

import json
import os

import market_data

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")


def main():
    os.makedirs(DOCS, exist_ok=True)

    report = market_data.build_report()
    with open(os.path.join(DOCS, "data.json"), "w", encoding="utf-8") as f:
        json.dump(report, f)
    print(f"wrote docs/data.json  (composite={report.get('composite')}, "
          f"{report.get('available')}/5 indicators)")

    with open(os.path.join(HERE, "dashboard.html"), encoding="utf-8") as f:
        html = f.read()
    # Point the static page at the generated JSON file instead of the local API.
    html = html.replace(
        'fetch("/api/data"+(refresh?"?refresh=1":""))',
        'fetch("data.json?t="+Date.now())')
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(html)
    print("wrote docs/index.html")


if __name__ == "__main__":
    main()
