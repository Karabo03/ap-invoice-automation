"""
Run the whole pipeline from an empty folder to a finished dashboard.

    python run_all.py                 use the Claude API if a key is present
    python run_all.py --fallback      force the pattern matching parser
    python run_all.py --skip-generate keep the invoices already generated

Each step can also be run on its own, which is usually what you want while
working on one part of it. See the README.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

STEPS = [
    ("step1_generate_data.py", "Generate the invoices and the source records"),
    ("step2_build_database.py", "Build the database"),
    ("step3_extract_invoices.py", "Read the invoices"),
    ("step4_run_controls.py", "Run the controls"),
    ("step5_measure_accuracy.py", "Measure what it got right"),
    ("step6_build_reports.py", "Write the reports"),
    ("step7_build_dashboard.py", "Build the dashboard"),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fallback", action="store_true")
    ap.add_argument("--skip-generate", action="store_true")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    started = time.time()
    for n, (script, label) in enumerate(STEPS, start=1):
        if args.skip_generate and script.startswith("step1"):
            print(f"[{n}/{len(STEPS)}] {label} .. skipped")
            continue

        print()
        print("=" * 72)
        print(f"[{n}/{len(STEPS)}] {label}")
        print("=" * 72)

        cmd = [sys.executable, str(ROOT / "src" / script)]
        if script.startswith("step3"):
            if args.fallback:
                cmd.append("--fallback")
            if args.limit:
                cmd += ["--limit", str(args.limit)]

        result = subprocess.run(cmd, cwd=ROOT)
        if result.returncode != 0:
            print(f"\nStopped at {script}.")
            sys.exit(result.returncode)

    print()
    print("=" * 72)
    print(f"Finished in {time.time() - started:.0f} seconds.")
    print(f"Open {ROOT / 'outputs' / 'dashboard.html'} in a browser.")


if __name__ == "__main__":
    main()
