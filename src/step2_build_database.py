"""
Step 2. Create the SQLite database and load the company's own records.

The supplier master file, the purchase orders and the goods received notes are
what the business already knows. Nothing from the supplier's invoice goes in
here, because that side is not trusted until it has been matched.

    python src/step2_build_database.py
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config as cfg

LOADS = [
    ("suppliers.csv", "suppliers"),
    ("purchase_orders.csv", "purchase_orders"),
    ("po_lines.csv", "po_lines"),
    ("goods_received_notes.csv", "goods_received_notes"),
    ("grn_lines.csv", "grn_lines"),
]


def main() -> None:
    if cfg.DB_PATH.exists():
        cfg.DB_PATH.unlink()

    conn = sqlite3.connect(cfg.DB_PATH)
    conn.executescript((cfg.SQL_DIR / "schema.sql").read_text())

    for filename, table in LOADS:
        path = cfg.DATA / filename
        if not path.exists():
            raise SystemExit(f"Missing {path}. Run step1_generate_data.py first.")
        df = pd.read_csv(path)
        df.to_sql(table, conn, if_exists="append", index=False)
        print(f"{table:<22} {len(df):>6} rows")

    conn.execute("PRAGMA foreign_keys = ON")
    conn.commit()

    print()
    print("Sanity checks")
    checks = {
        "orders without a supplier on file":
            "SELECT COUNT(*) FROM purchase_orders p "
            "LEFT JOIN suppliers s ON s.supplier_id = p.supplier_id "
            "WHERE s.supplier_id IS NULL",
        "orders never received":
            "SELECT COUNT(*) FROM purchase_orders p "
            "LEFT JOIN goods_received_notes g ON g.po_number = p.po_number "
            "WHERE g.po_number IS NULL",
        "suppliers not approved":
            "SELECT COUNT(*) FROM suppliers WHERE approved = 'N'",
        "short deliveries":
            "SELECT COUNT(*) FROM grn_lines g "
            "JOIN po_lines l ON l.po_number = g.po_number AND l.line_no = g.line_no "
            "WHERE g.qty_received < l.qty_ordered",
    }
    for label, sql in checks.items():
        print(f"  {label:<36} {conn.execute(sql).fetchone()[0]:>5}")

    total = conn.execute("SELECT SUM(total_ex_vat) FROM purchase_orders").fetchone()[0]
    print(f"  {'committed spend on open orders':<36} R{total:,.2f}")

    conn.close()
    print()
    print(f"Database written to {cfg.DB_PATH}")


if __name__ == "__main__":
    main()
