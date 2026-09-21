"""
Step 6. Turn the database into reports.

Writes:
    outputs/exceptions.csv            every finding, one row each
    outputs/invoice_register.csv      one row per invoice with its status
    outputs/supplier_risk.csv         value at risk by supplier
    outputs/monthly_summary.csv       spend and exposure by month
    outputs/control_performance.csv   how each control did against the truth
    outputs/ap_exception_report.xlsx  the four tables in one workbook
    outputs/dashboard_data.json       the figures the dashboard reads

The CSV files are deliberately flat so they can be dropped straight into
Power BI without reshaping.

    python src/step6_build_reports.py
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
from src.controls.rules import WHOLE_INVOICE_CODES


def net_exposure(rows: list[tuple]) -> float:
    """One invoice tripping several controls must not be counted several times."""
    whole = [v for c, v in rows if c in WHOLE_INVOICE_CODES]
    parts = [v for c, v in rows if c not in WHOLE_INVOICE_CODES]
    return max(whole) if whole else sum(parts)


def main() -> None:
    conn = sqlite3.connect(cfg.DB_PATH)
    conn.row_factory = sqlite3.Row

    exceptions = pd.read_sql_query(
        """
        SELECT e.exception_id, e.invoice_id, i.invoice_number, i.supplier_id,
               COALESCE(s.supplier_name, i.supplier_name_raw) AS supplier_name,
               i.invoice_date, i.po_number, i.total_incl_vat,
               e.code, e.control, e.severity, e.line_no,
               e.value_at_risk, e.detail, e.recommendation,
               i.extraction_method, i.extraction_confidence
        FROM exceptions e
        JOIN invoices i ON i.invoice_id = e.invoice_id
        LEFT JOIN suppliers s ON s.supplier_id = i.supplier_id
        ORDER BY e.value_at_risk DESC
        """, conn)

    register = pd.read_sql_query(
        """
        SELECT i.invoice_id, i.pdf_file, i.invoice_number,
               COALESCE(s.supplier_name, i.supplier_name_raw) AS supplier_name,
               i.supplier_id, i.po_number, i.invoice_date, i.due_date,
               i.subtotal_ex_vat, i.vat_amount, i.total_incl_vat,
               i.processing_status, i.extraction_method, i.extraction_confidence,
               COUNT(e.exception_id) AS exceptions_raised,
               COALESCE(SUM(e.value_at_risk), 0) AS value_at_risk
        FROM invoices i
        LEFT JOIN suppliers s ON s.supplier_id = i.supplier_id
        LEFT JOIN exceptions e ON e.invoice_id = i.invoice_id
        GROUP BY i.invoice_id
        ORDER BY value_at_risk DESC
        """, conn)

    # ---- net exposure per invoice -----------------------------------------
    per_invoice = defaultdict(list)
    for r in conn.execute("SELECT invoice_id, code, value_at_risk FROM exceptions"):
        per_invoice[r["invoice_id"]].append((r["code"], r["value_at_risk"]))
    net = {k: round(net_exposure(v), 2) for k, v in per_invoice.items()}
    register["net_exposure"] = register["invoice_id"].map(net).fillna(0.0)

    # ---- by supplier ------------------------------------------------------
    checked = register[register["processing_status"] != "manual_capture"]
    supplier_risk = (
        checked.groupby(["supplier_id", "supplier_name"], dropna=False)
        .agg(invoices=("invoice_id", "count"),
             invoiced=("total_incl_vat", "sum"),
             exceptions_raised=("exceptions_raised", "sum"),
             net_exposure=("net_exposure", "sum"))
        .reset_index()
        .sort_values("net_exposure", ascending=False)
    )
    supplier_risk["exposure_pct_of_spend"] = (
        supplier_risk["net_exposure"] / supplier_risk["invoiced"].replace(0, pd.NA) * 100
    ).round(1)

    # ---- by month ---------------------------------------------------------
    checked = checked.copy()
    checked["month"] = checked["invoice_date"].astype(str).str.slice(0, 7)
    monthly = (
        checked[checked["month"].str.match(r"\d{4}-\d{2}", na=False)]
        .groupby("month")
        .agg(invoices=("invoice_id", "count"),
             invoiced=("total_incl_vat", "sum"),
             exceptions_raised=("exceptions_raised", "sum"),
             net_exposure=("net_exposure", "sum"))
        .reset_index()
        .sort_values("month")
    )

    # ---- by control -------------------------------------------------------
    by_code = (
        exceptions.groupby("code")
        .agg(findings=("exception_id", "count"),
             invoices=("invoice_id", "nunique"),
             value_at_risk=("value_at_risk", "sum"))
        .reset_index()
    )
    by_code["name"] = by_code["code"].map(lambda c: cfg.EXCEPTION_CATALOGUE[c]["name"])
    by_code["severity"] = by_code["code"].map(lambda c: cfg.EXCEPTION_CATALOGUE[c]["severity"])
    by_code["control"] = by_code["code"].map(lambda c: cfg.EXCEPTION_CATALOGUE[c]["control"])
    by_code = by_code.sort_values("value_at_risk", ascending=False)

    # ---- how the controls did against the planted truth -------------------
    accuracy_path = cfg.OUTPUTS / "accuracy_report.json"
    accuracy = json.loads(accuracy_path.read_text()) if accuracy_path.exists() else {}
    performance = pd.DataFrame(accuracy.get("controls", []))
    if not performance.empty:
        performance["name"] = performance["code"].map(
            lambda c: cfg.EXCEPTION_CATALOGUE[c]["name"])

    # ---- write ------------------------------------------------------------
    exceptions.to_csv(cfg.OUTPUTS / "exceptions.csv", index=False)
    register.to_csv(cfg.OUTPUTS / "invoice_register.csv", index=False)
    supplier_risk.to_csv(cfg.OUTPUTS / "supplier_risk.csv", index=False)
    monthly.to_csv(cfg.OUTPUTS / "monthly_summary.csv", index=False)
    if not performance.empty:
        performance.to_csv(cfg.OUTPUTS / "control_performance.csv", index=False)

    with pd.ExcelWriter(cfg.OUTPUTS / "ap_exception_report.xlsx", engine="openpyxl") as xl:
        exceptions.to_excel(xl, sheet_name="Exceptions", index=False)
        register.to_excel(xl, sheet_name="Invoice register", index=False)
        supplier_risk.to_excel(xl, sheet_name="Supplier risk", index=False)
        monthly.to_excel(xl, sheet_name="Monthly", index=False)
        by_code.to_excel(xl, sheet_name="By control", index=False)
        if not performance.empty:
            performance.to_excel(xl, sheet_name="Control performance", index=False)

    # ---- headline figures --------------------------------------------------
    total_invoices = len(register)
    manual = int((register["processing_status"] == "manual_capture").sum())
    flagged = int((register["processing_status"] == "exception").sum())
    clean = int((register["processing_status"] == "clean").sum())
    invoiced = float(checked["total_incl_vat"].sum())
    exposure = float(register["net_exposure"].sum())

    method = conn.execute(
        "SELECT extraction_method, COUNT(*) c FROM invoices "
        "GROUP BY 1 ORDER BY c DESC LIMIT 1").fetchone()
    seconds = conn.execute(
        "SELECT COALESCE(SUM(seconds), 0) FROM extraction_log").fetchone()[0]

    top_exceptions = exceptions.head(12)[
        ["invoice_id", "supplier_name", "invoice_date", "code", "severity",
         "value_at_risk", "detail", "recommendation"]
    ].fillna("")

    payload = {
        "generated": pd.Timestamp.today().strftime("%d %B %Y"),
        "company": cfg.COMPANY["name"],
        "period": "October 2025 to September 2026",
        "extraction_method": method["extraction_method"] if method else "unknown",
        "extraction_seconds": round(float(seconds), 1),
        "stats": {
            "invoices": total_invoices,
            "checked": total_invoices - manual,
            "clean": clean,
            "flagged": flagged,
            "manual_capture": manual,
            "invoiced": round(invoiced, 2),
            "exposure": round(exposure, 2),
            "exposure_pct": round(exposure / invoiced * 100, 1) if invoiced else 0,
            "findings": int(len(exceptions)),
        },
        "by_control": by_code[["code", "name", "severity", "findings",
                               "value_at_risk"]].to_dict("records"),
        "by_month": monthly.to_dict("records"),
        "by_supplier": supplier_risk.head(10)[
            ["supplier_name", "invoices", "invoiced", "net_exposure"]
        ].fillna("Unmatched").to_dict("records"),
        "performance": performance.to_dict("records") if not performance.empty else [],
        "accuracy": accuracy.get("overall", {}),
        "field_accuracy": accuracy.get("field_accuracy", {}),
        "accuracy_by_group": accuracy.get("accuracy_by_group", {}),
        "top_exceptions": top_exceptions.to_dict("records"),
    }

    (cfg.OUTPUTS / "dashboard_data.json").write_text(json.dumps(payload, indent=2))

    print(f"Invoices                {total_invoices:>8}")
    print(f"  clean                 {clean:>8}")
    print(f"  flagged               {flagged:>8}")
    print(f"  manual capture        {manual:>8}")
    print(f"Findings                {len(exceptions):>8}")
    print(f"Invoiced value checked  R{invoiced:>15,.2f}")
    print(f"Exposure                R{exposure:>15,.2f}")
    print()
    for name in ["exceptions.csv", "invoice_register.csv", "supplier_risk.csv",
                 "monthly_summary.csv", "control_performance.csv",
                 "ap_exception_report.xlsx", "dashboard_data.json"]:
        path = cfg.OUTPUTS / name
        if path.exists():
            print(f"  {name:<28} {path.stat().st_size / 1024:>8.0f} KB")

    conn.close()


if __name__ == "__main__":
    main()
