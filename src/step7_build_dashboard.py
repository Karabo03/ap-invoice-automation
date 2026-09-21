"""
Step 7. Build the dashboard.

Takes the figures written by step 6 and drops them into a single self contained
HTML file. No server, no internet, no build tools. Open it in a browser.

    python src/step7_build_dashboard.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg

TEMPLATE = Path(__file__).resolve().parent / "templates" / "dashboard.html"


def main() -> None:
    data_path = cfg.OUTPUTS / "dashboard_data.json"
    if not data_path.exists():
        raise SystemExit("No dashboard data. Run step6_build_reports.py first.")

    payload = json.loads(data_path.read_text())
    # Keep it inert inside the script tag.
    blob = json.dumps(payload).replace("</", "<\\/")

    html = TEMPLATE.read_text().replace("__DATA__", blob)
    out = cfg.OUTPUTS / "dashboard.html"
    out.write_text(html, encoding="utf-8")

    print(f"Dashboard written to {out}")
    print(f"  {out.stat().st_size / 1024:.0f} KB, opens in any browser")

    # A second copy with the document wrapper stripped, for hosting the page
    # somewhere that supplies its own skeleton.
    body = html
    for tag in ("<!DOCTYPE html>", "<html lang=\"en\">", "<head>", "</head>",
                "<body>", "</body>", "</html>",
                "<meta charset=\"utf-8\">",
                "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">"):
        body = body.replace(tag, "")
    embed = cfg.OUTPUTS / "dashboard_embed.html"
    embed.write_text(body.strip() + "\n", encoding="utf-8")
    print(f"Embeddable copy written to {embed}")


if __name__ == "__main__":
    main()
