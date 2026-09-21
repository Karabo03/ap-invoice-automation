"""
Step 1. Create the source data for Kalahari Components.

Writes the supplier master file, purchase orders, goods received notes and a
folder of invoice PDFs, together with a ground truth file recording exactly
which errors were planted in which invoice.

    python src/step1_generate_data.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config as cfg
from src.generate import build_records, render_pdfs


def main() -> None:
    print("Building records")
    invoices = build_records.main()

    print("Rendering invoice PDFs")
    payload = []
    for inv in invoices:
        payload.append(
            {
                "invoice_id": inv.invoice_id,
                "invoice_number": inv.invoice_number,
                "supplier_name": inv.supplier_name,
                "supplier_vat_number": inv.supplier_vat_number,
                "supplier_address": inv.supplier_address,
                "supplier_email": inv.supplier_email,
                "bank_name": inv.bank_name,
                "branch_code": inv.branch_code,
                "account_number": inv.account_number,
                "po_number": inv.po_number,
                "invoice_date": inv.invoice_date,
                "due_date": inv.due_date,
                "lines": inv.lines,
                "subtotal_ex_vat": inv.subtotal_ex_vat,
                "vat_amount": inv.vat_amount,
                "total_incl_vat": inv.total_incl_vat,
                "layout": inv.layout,
                "is_scan": inv.is_scan,
                "omit_particulars": inv.omit_particulars,
            }
        )
    render_pdfs.render_all(payload)

    pdfs = sorted(cfg.INVOICE_PDF_DIR.glob("*.pdf"))
    truth = pd.read_csv(cfg.GROUND_TRUTH_DIR / "invoice_truth.csv")

    print()
    print(f"PDFs written to {cfg.INVOICE_PDF_DIR}")
    print(f"  files            {len(pdfs)}")
    print(f"  scanned images   {int(truth['is_scan'].sum())}")
    print("  layouts          " + ", ".join(
        f"{k} {v}" for k, v in truth["layout"].value_counts().sort_index().items()))
    print()
    print("Planted exceptions")
    counts: dict[str, int] = {}
    for s in truth["seeded_exceptions"].fillna(""):
        for code in [c for c in str(s).split("|") if c]:
            counts[code] = counts.get(code, 0) + 1
    for code in sorted(counts):
        print(f"  {code:<26} {counts[code]:>4}")
    print(f"  {'invoices affected':<26} {int((truth['seeded_exceptions'].fillna('') != '').sum()):>4}")
    print(f"  {'invoices total':<26} {len(truth):>4}")


if __name__ == "__main__":
    main()
