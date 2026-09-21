"""
Step 5. Measure how well it actually worked.

Two questions, answered against the file written when the data was generated,
which records exactly what each invoice said and exactly which errors were
planted in it.

    Did the extraction read the document correctly, field by field?
    Did the controls catch what was planted, and how much did they invent?

Anything claimed in the write up comes from here. Nothing is estimated.

    python src/step5_measure_accuracy.py
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd

import config as cfg

# Fields compared, with how strictly. Money is compared to the cent, text is
# compared after stripping case and spacing, because a supplier name read as
# "ABC (PTY) LTD" is not a mistake worth counting.
FIELDS = {
    "invoice_number": "text",
    "supplier_name": "name",
    "supplier_vat_number": "text",
    "po_number": "text",
    "invoice_date": "text",
    "bank_name": "name",
    "account_number": "text",
    "subtotal_ex_vat": "money",
    "vat_amount": "money",
    "total_incl_vat": "money",
}

TRUTH_COLUMN = {
    "supplier_name": "supplier_name",
    "bank_name": "bank_name",
}


def norm_text(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return "".join(str(v).split()).upper()


def norm_name(v) -> str:
    s = norm_text(v)
    for junk in ("(PTY)LTD", "(PTY)LTD.", "PTYLTD"):
        s = s.replace(junk, "")
    return s


def same(kind: str, got, want) -> bool:
    if kind == "money":
        if got is None or want is None or (isinstance(want, float) and pd.isna(want)):
            return got is None and (want is None or pd.isna(want))
        return abs(float(got) - float(want)) <= 0.01
    if kind == "name":
        return norm_name(got) == norm_name(want)
    return norm_text(got) == norm_text(want)


def main() -> None:
    conn = sqlite3.connect(cfg.DB_PATH)
    conn.row_factory = sqlite3.Row

    truth = pd.read_csv(cfg.GROUND_TRUTH_DIR / "invoice_truth.csv").set_index("invoice_id")
    captured = {r["invoice_id"]: dict(r) for r in conn.execute("SELECT * FROM invoices")}
    if not captured:
        raise SystemExit("Nothing captured. Run step3_extract_invoices.py first.")

    method_of = {k: v["extraction_method"] for k, v in captured.items()}
    report: dict = {"invoices": len(captured)}

    # ---- extraction accuracy ----------------------------------------------
    correct = defaultdict(int)
    by_group = defaultdict(lambda: {"fields": 0, "right": 0, "invoices": 0})

    for invoice_id, row in captured.items():
        if invoice_id not in truth.index:
            continue
        t = truth.loc[invoice_id]
        group = "scanned" if int(t["is_scan"]) == 1 else "text layer"
        by_group[group]["invoices"] += 1
        by_group[method_of[invoice_id]]["invoices"] += 1

        for field, kind in FIELDS.items():
            col = TRUTH_COLUMN.get(field, field)
            want = t[col] if col in t.index else None
            if isinstance(want, float) and pd.isna(want):
                want = None
            if field == "po_number" and (want is None or str(want) == "nan"):
                want = None
            got = row.get("supplier_name_raw" if field == "supplier_name" else field)
            hit = same(kind, got, want)
            correct[field] += int(hit)
            for g in (group, method_of[invoice_id]):
                by_group[g]["fields"] += 1
                by_group[g]["right"] += int(hit)

    n = len(captured)
    print("Field accuracy across all", n, "invoices")
    print(f"{'field':<22}{'correct':>9}{'accuracy':>11}")
    for field in FIELDS:
        pct = correct[field] / n * 100
        print(f"{field:<22}{correct[field]:>9}{pct:>10.1f}%")
    overall = sum(correct.values()) / (n * len(FIELDS)) * 100
    print(f"{'all fields':<22}{sum(correct.values()):>9}{overall:>10.1f}%")
    report["field_accuracy"] = {f: round(correct[f] / n * 100, 1) for f in FIELDS}
    report["field_accuracy_overall"] = round(overall, 1)

    print()
    print("Accuracy by document type and by route taken")
    print(f"{'group':<18}{'invoices':>10}{'accuracy':>11}")
    report["accuracy_by_group"] = {}
    for group, g in sorted(by_group.items()):
        if not g["fields"]:
            continue
        pct = g["right"] / g["fields"] * 100
        print(f"{group:<18}{g['invoices']:>10}{pct:>10.1f}%")
        report["accuracy_by_group"][group] = {
            "invoices": g["invoices"], "accuracy": round(pct, 1)}

    # ---- did the controls catch what was planted --------------------------
    planted = defaultdict(set)
    for invoice_id, row in truth.iterrows():
        raw = row["seeded_exceptions"]
        if raw is None or (isinstance(raw, float) and pd.isna(raw)):
            continue
        for code in [c for c in str(raw).split("|") if c in cfg.EXCEPTION_CATALOGUE]:
            planted[code].add(invoice_id)

    flagged = defaultdict(set)
    for r in conn.execute("SELECT DISTINCT invoice_id, code FROM exceptions"):
        flagged[r["code"]].add(r["invoice_id"])

    unreadable = {k for k, v in captured.items()
                  if v["processing_status"] == "manual_capture"}

    print()
    print("Control performance against the planted errors")
    print(f"{'code':<26}{'planted':>8}{'found':>7}{'hit':>5}{'miss':>6}"
          f"{'extra':>7}{'recall':>9}{'prec':>8}")

    rows = []
    for code in sorted(cfg.EXCEPTION_CATALOGUE):
        want, got = planted.get(code, set()), flagged.get(code, set())
        if not want and not got:
            continue
        tp = len(want & got)
        fn = len(want - got)
        fp = len(got - want)
        recall = tp / len(want) * 100 if want else float("nan")
        precision = tp / len(got) * 100 if got else float("nan")
        rows.append({"code": code, "planted": len(want), "found": len(got),
                     "hit": tp, "missed": fn, "extra": fp,
                     "recall": None if want == set() else round(recall, 1),
                     "precision": None if got == set() else round(precision, 1)})
        rec = f"{recall:.1f}%" if want else "  n/a"
        pre = f"{precision:.1f}%" if got else "  n/a"
        print(f"{code:<26}{len(want):>8}{len(got):>7}{tp:>5}{fn:>6}{fp:>7}"
              f"{rec:>9}{pre:>8}")

    all_planted = {(c, i) for c, s in planted.items() for i in s}
    all_flagged = {(c, i) for c, s in flagged.items() for i in s}
    tp = len(all_planted & all_flagged)
    fn = len(all_planted - all_flagged)
    fp = len(all_flagged - all_planted)
    fn_unreadable = len({p for p in all_planted - all_flagged if p[1] in unreadable})

    print()
    print(f"Planted errors            {len(all_planted):>5}")
    print(f"  caught                  {tp:>5}")
    print(f"  missed                  {fn:>5}")
    print(f"    of which the document could not be read  {fn_unreadable}")
    print(f"  raised but not planted  {fp:>5}")
    print(f"Recall                    {tp / len(all_planted) * 100:>5.1f}%")
    print(f"Precision                 {tp / (tp + fp) * 100:>5.1f}%")

    report["controls"] = rows
    report["overall"] = {
        "planted": len(all_planted), "caught": tp, "missed": fn,
        "missed_unreadable": fn_unreadable, "false_positives": fp,
        "recall": round(tp / len(all_planted) * 100, 1),
        "precision": round(tp / (tp + fp) * 100, 1),
        "manual_capture": len(unreadable),
        "extraction_method": max(
            set(method_of.values()), key=list(method_of.values()).count),
    }

    out = cfg.OUTPUTS / "accuracy_report.json"
    out.write_text(json.dumps(report, indent=2))
    print()
    print(f"Written to {out}")
    conn.close()


if __name__ == "__main__":
    main()
