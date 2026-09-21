"""
Step 4. Run the three way match and the rest of the controls.

Reads what the extraction step captured, compares it against the purchase
orders and goods received notes, and writes every finding into the exceptions
table with a rand value attached.

    python src/step4_run_controls.py
"""

from __future__ import annotations

import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg
from src.controls import rules


def load(conn) -> dict:
    q = lambda sql: [dict(r) for r in conn.execute(sql)]
    return {
        "invoices": q("SELECT * FROM invoices"),
        "invoice_lines": q("SELECT * FROM invoice_lines ORDER BY invoice_id, line_no"),
        "suppliers": q("SELECT * FROM suppliers"),
        "purchase_orders": q("SELECT * FROM purchase_orders"),
        "po_lines": q("SELECT * FROM po_lines"),
        "grns": q("SELECT * FROM goods_received_notes"),
        "grn_lines": q("SELECT * FROM grn_lines"),
    }


def main() -> None:
    if not cfg.DB_PATH.exists():
        raise SystemExit("No database. Run the earlier steps first.")

    conn = sqlite3.connect(cfg.DB_PATH)
    conn.row_factory = sqlite3.Row
    data = load(conn)

    if not data["invoices"]:
        raise SystemExit("No invoices captured. Run step3_extract_invoices.py first.")

    suppliers = {s["supplier_id"]: s for s in data["suppliers"]}
    pos = {p["po_number"]: p for p in data["purchase_orders"]}

    po_lines = defaultdict(list)
    for l in data["po_lines"]:
        po_lines[l["po_number"]].append(l)

    grn_by_po = {g["po_number"]: g for g in data["grns"]}
    grn_qty = defaultdict(dict)
    for l in data["grn_lines"]:
        grn_qty[l["po_number"]][l["line_no"]] = l["qty_received"]

    inv_lines = defaultdict(list)
    for l in data["invoice_lines"]:
        inv_lines[l["invoice_id"]].append(l)

    # Checks that need to see the whole population at once
    cross_invoice = defaultdict(list)
    for invoice_id, items in rules.find_duplicates(data["invoices"]).items():
        cross_invoice[invoice_id].extend(items)
    for invoice_id, items in rules.find_threshold_splitting(data["invoices"]).items():
        cross_invoice[invoice_id].extend(items)

    rows = []
    statuses = {}
    unreadable = 0

    for inv in data["invoices"]:
        invoice_id = inv["invoice_id"]

        if not rules.is_readable(inv):
            unreadable += 1
            statuses[invoice_id] = "manual_capture"
            continue

        po = pos.get((inv.get("po_number") or "").strip() or None)
        grn = grn_by_po.get(po["po_number"]) if po else None
        supplier = suppliers.get(inv.get("supplier_id"))
        lines = inv_lines.get(invoice_id, [])
        order_lines = po_lines.get(po["po_number"], []) if po else []
        received = grn_qty.get(po["po_number"], {}) if po else {}

        findings = []
        findings += rules.check_purchase_order(inv, po)
        findings += rules.check_supplier_approved(inv, supplier)
        findings += rules.check_goods_received(inv, po, grn)
        findings += rules.check_price(inv, lines, order_lines)
        findings += rules.check_quantity(inv, lines, order_lines, received)
        findings += rules.check_vat(inv)
        findings += rules.check_arithmetic(inv, lines)
        findings += rules.check_bank(inv, supplier)
        findings += rules.check_dates(inv, po, grn)
        findings += rules.check_tax_invoice_validity(inv)
        findings += cross_invoice.get(invoice_id, [])

        statuses[invoice_id] = "exception" if findings else "clean"
        for f in findings:
            rows.append((invoice_id, f["code"], f["control"], f["severity"],
                         f["line_no"], f["detail"], f["value_at_risk"],
                         f["recommendation"]))

    conn.execute("DELETE FROM exceptions")
    conn.executemany(
        "INSERT INTO exceptions (invoice_id, code, control, severity, line_no, "
        "detail, value_at_risk, recommendation) VALUES (?,?,?,?,?,?,?,?)", rows)
    conn.executemany("UPDATE invoices SET processing_status = ? WHERE invoice_id = ?",
                     [(v, k) for k, v in statuses.items()])
    conn.commit()

    # ---- reporting ---------------------------------------------------------
    total_invoices = len(data["invoices"])
    checked = total_invoices - unreadable
    with_exceptions = sum(1 for v in statuses.values() if v == "exception")
    clean = sum(1 for v in statuses.values() if v == "clean")

    print(f"Invoices captured            {total_invoices:>6}")
    print(f"  checked by the controls    {checked:>6}")
    print(f"  sent for manual capture    {unreadable:>6}")
    print(f"  passed every control       {clean:>6}")
    print(f"  raised at least one flag   {with_exceptions:>6}")
    print()

    print(f"{'Code':<26}{'Found':>7}{'Value at risk':>18}")
    by_code = conn.execute(
        "SELECT code, COUNT(*) n, SUM(value_at_risk) v FROM exceptions "
        "GROUP BY code ORDER BY v DESC").fetchall()
    for r in by_code:
        print(f"{r['code']:<26}{r['n']:>7}{'R' + format(r['v'], ',.2f'):>18}")

    gross = conn.execute("SELECT COALESCE(SUM(value_at_risk),0) FROM exceptions").fetchone()[0]

    # One invoice can trip several controls. Counting each finding separately
    # would overstate the exposure, so the whole invoice codes are taken once
    # at their largest value and the overcharge codes are added on top.
    net = 0.0
    per_invoice = defaultdict(list)
    for r in conn.execute("SELECT invoice_id, code, value_at_risk FROM exceptions"):
        per_invoice[r["invoice_id"]].append((r["code"], r["value_at_risk"]))
    for items in per_invoice.values():
        whole = [v for c, v in items if c in rules.WHOLE_INVOICE_CODES]
        parts = [v for c, v in items if c not in rules.WHOLE_INVOICE_CODES]
        net += max(whole) if whole else sum(parts)

    invoiced = conn.execute(
        "SELECT COALESCE(SUM(total_incl_vat),0) FROM invoices "
        "WHERE processing_status != 'manual_capture'").fetchone()[0]

    print()
    print(f"Total invoiced value checked      R{invoiced:,.2f}")
    print(f"Sum of every finding              R{gross:,.2f}")
    print(f"Exposure after removing overlap   R{net:,.2f}")
    if invoiced:
        print(f"Exposure as a share of spend      {net / invoiced * 100:.1f} percent")

    conn.close()


if __name__ == "__main__":
    main()
