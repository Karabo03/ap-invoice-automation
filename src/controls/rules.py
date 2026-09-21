"""
The twelve control checks.

No language model is involved anywhere in this file, and that is the point. A
control has to give the same answer every time it sees the same facts, has to be
explainable to an auditor line by line, and has to be arguable in front of a
supplier. A model that is right most of the time is the wrong tool for that.

The model's job was to read the document. This file decides whether the document
is acceptable.

Each check returns a list of findings. A finding carries the rand amount that
would have been lost or mis-stated had the invoice been paid as it arrived,
which is what turns a control report into something a finance manager will act
on.
"""

from __future__ import annotations

import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import config as cfg

# Codes where the whole invoice is at stake rather than an overcharge on part
# of it. Used later so that one invoice carrying three of these is not counted
# three times over.
WHOLE_INVOICE_CODES = {
    "E03_DUPLICATE", "E04_NO_PO", "E07_UNAPPROVED_SUPPLIER",
    "E12_GOODS_NOT_RECEIVED", "E10_THRESHOLD_SPLIT",
}


def finding(code: str, detail: str, value: float = 0.0,
            line_no: int | None = None, recommendation: str = "") -> dict:
    meta = cfg.EXCEPTION_CATALOGUE[code]
    return {
        "code": code,
        "control": meta["control"],
        "severity": meta["severity"],
        "line_no": line_no,
        "detail": detail,
        "value_at_risk": round(max(0.0, value), 2),
        "recommendation": recommendation,
    }


def rands(x: float | None) -> str:
    if x is None:
        return "no amount"
    return f"R{x:,.2f}"


def as_date(value) -> date | None:
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Readability gate
# ---------------------------------------------------------------------------

def is_readable(inv: dict) -> bool:
    """
    A control can only speak about a document it can actually see.

    If the total or the invoice number never came off the page, running the
    other eleven checks would produce a pile of findings that say nothing about
    the supplier and everything about the reader. Those documents go to a person
    to key in by hand, which is what a real system does.
    """
    return inv.get("total_incl_vat") is not None and bool(inv.get("invoice_number"))


# ---------------------------------------------------------------------------
# E01 and E02, the three way match on price and quantity
# ---------------------------------------------------------------------------

def match_lines(inv_lines: list[dict], po_lines: list[dict]) -> list[tuple]:
    """Pair invoice lines to order lines on the stock code."""
    by_code: dict[str, list[dict]] = defaultdict(list)
    for pl in po_lines:
        by_code[(pl["item_code"] or "").upper()].append(pl)

    pairs = []
    for il in inv_lines:
        code = (il.get("item_code") or "").upper()
        candidates = by_code.get(code)
        pairs.append((il, candidates[0] if candidates else None))
    return pairs


def check_price(inv, inv_lines, po_lines) -> list[dict]:
    out = []
    for il, pl in match_lines(inv_lines, po_lines):
        if pl is None or il.get("unit_price") is None:
            continue
        agreed = pl["unit_price_ex_vat"]
        charged = il["unit_price"]
        if charged <= agreed:
            continue
        gap = charged - agreed
        tolerance = max(agreed * cfg.PRICE_TOLERANCE_PCT, 0.0)
        qty = il.get("quantity") or 0
        overcharge = gap * qty
        if gap <= tolerance or overcharge <= cfg.PRICE_TOLERANCE_ABS:
            continue
        out.append(finding(
            "E01_PRICE_VARIANCE",
            f"{il.get('item_code')} charged at {rands(charged)} against "
            f"{rands(agreed)} on {inv['po_number']}, a difference of "
            f"{gap / agreed * 100:.1f} percent over {qty:g} units.",
            overcharge,
            il.get("line_no"),
            "Hold the line and ask the supplier for a credit note, or a written "
            "price increase agreed before the order was placed.",
        ))
    return out


def check_quantity(inv, inv_lines, po_lines, grn_qty) -> list[dict]:
    out = []
    for il, pl in match_lines(inv_lines, po_lines):
        if pl is None or il.get("quantity") is None:
            continue
        received = grn_qty.get(pl["line_no"])
        if received is None:
            continue
        billed = il["quantity"]
        if billed <= received:
            continue
        over = billed - received
        unit = il.get("unit_price") or pl["unit_price_ex_vat"]
        out.append(finding(
            "E02_QTY_OVER_BILLED",
            f"{il.get('item_code')} billed for {billed:g} units but the "
            f"warehouse booked in {received:g}. {over:g} units were never "
            f"received.",
            over * unit,
            il.get("line_no"),
            "Pay the received quantity only. Ask the warehouse to confirm "
            "nothing is sitting unbooked before the balance is released.",
        ))
    return out


# ---------------------------------------------------------------------------
# E05 and E08, the arithmetic on the face of the document
# ---------------------------------------------------------------------------

def check_vat(inv) -> list[dict]:
    subtotal, vat = inv.get("subtotal_ex_vat"), inv.get("vat_amount")
    if subtotal is None or vat is None:
        return []
    expected = round(subtotal * cfg.VAT_RATE, 2)
    gap = round(vat - expected, 2)
    if abs(gap) <= cfg.VAT_ROUNDING_TOLERANCE:
        return []
    direction = "more" if gap > 0 else "less"
    return [finding(
        "E05_VAT_ERROR",
        f"VAT shown as {rands(vat)} on a net amount of {rands(subtotal)}. "
        f"At 15 percent it should be {rands(expected)}, which is "
        f"{rands(abs(gap))} {direction} than charged.",
        abs(gap),
        None,
        "Ask for a corrected tax invoice. Claiming input VAT off a document "
        "that states the wrong amount exposes the company on assessment.",
    )]


def check_arithmetic(inv, inv_lines) -> list[dict]:
    out = []
    subtotal = inv.get("subtotal_ex_vat")
    vat = inv.get("vat_amount")
    total = inv.get("total_incl_vat")

    if inv_lines and subtotal is not None:
        line_sum = round(sum(l.get("line_total") or 0 for l in inv_lines), 2)
        gap = round(subtotal - line_sum, 2)
        if abs(gap) > 0.05 and all(l.get("line_total") is not None for l in inv_lines):
            out.append(finding(
                "E08_ARITHMETIC",
                f"The {len(inv_lines)} line items add up to {rands(line_sum)} "
                f"but the invoice states a subtotal of {rands(subtotal)}, a "
                f"difference of {rands(abs(gap))}.",
                abs(gap),
                None,
                "Send it back. A document that does not add up cannot be "
                "approved for payment whatever the cause.",
            ))

    if subtotal is not None and vat is not None and total is not None:
        gap = round(total - (subtotal + vat), 2)
        if abs(gap) > 0.05:
            out.append(finding(
                "E08_ARITHMETIC",
                f"Subtotal {rands(subtotal)} plus VAT {rands(vat)} comes to "
                f"{rands(subtotal + vat)}, but the total demanded is "
                f"{rands(total)}.",
                abs(gap),
                None,
                "Send it back for a corrected invoice before it reaches the "
                "payment run.",
            ))
    return out


# ---------------------------------------------------------------------------
# E04, E07, E12, whether the purchase was authorised at all
# ---------------------------------------------------------------------------

def check_purchase_order(inv, po) -> list[dict]:
    quoted = (inv.get("po_number") or "").strip()
    total = inv.get("total_incl_vat") or 0
    if po is not None:
        return []
    if not quoted:
        return [finding(
            "E04_NO_PO",
            f"No order number appears on the invoice. {rands(total)} is being "
            f"claimed for goods nobody raised an order for.",
            total, None,
            "Find out who ordered this and under what authority. Maverick "
            "spend is bought at whatever price the supplier felt like.",
        )]
    return [finding(
        "E04_NO_PO",
        f"The invoice quotes {quoted}, which does not exist on the purchasing "
        f"system.",
        total, None,
        "Query the number with the supplier. A wrong reference is usually a "
        "typing error, but it can also be an invoice aimed at the wrong company.",
    )]


def check_supplier_approved(inv, supplier) -> list[dict]:
    total = inv.get("total_incl_vat") or 0
    if supplier is None:
        return [finding(
            "E07_UNAPPROVED_SUPPLIER",
            f"The name on the invoice could not be matched to any supplier on "
            f"the master file. {rands(total)} is being claimed by a party the "
            f"company has no record of.",
            total, None,
            "Do not pay until the supplier is identified and loaded properly. "
            "An unknown payee is how invoice fraud gets through.",
        )]
    if supplier["approved"] != "Y":
        return [finding(
            "E07_UNAPPROVED_SUPPLIER",
            f"{supplier['supplier_name']} is on the system but was never "
            f"approved by procurement.",
            total, None,
            "Route to procurement for vendor onboarding, including tax "
            "clearance and bank verification, before any payment is released.",
        )]
    return []


def check_goods_received(inv, po, grn) -> list[dict]:
    if po is None or grn is not None:
        return []
    total = inv.get("total_incl_vat") or 0
    return [finding(
        "E12_GOODS_NOT_RECEIVED",
        f"Order {po['po_number']} exists and the supplier has invoiced "
        f"{rands(total)}, but the warehouse has never booked anything in "
        f"against it.",
        total, None,
        "Confirm with the warehouse before paying. Either the delivery never "
        "arrived or it arrived and was not recorded, and both need fixing.",
    )]


# ---------------------------------------------------------------------------
# E06, the bank account
# ---------------------------------------------------------------------------

def check_bank(inv, supplier) -> list[dict]:
    if supplier is None:
        return []
    on_invoice = (inv.get("account_number") or "").strip()
    on_file = (supplier.get("account_number") or "").strip()
    if not on_invoice or not on_file or on_invoice == on_file:
        return []
    total = inv.get("total_incl_vat") or 0
    return [finding(
        "E06_BANK_CHANGE",
        f"The invoice asks for payment into {inv.get('bank_name')} account "
        f"{on_invoice}. The master file holds {supplier['bank_name']} account "
        f"{on_file} for {supplier['supplier_name']}.",
        total, None,
        "Do not change the banking details off the back of a document. Phone "
        "the supplier on the number already held on file, never one printed on "
        "the invoice, and confirm before anything is paid.",
    )]


# ---------------------------------------------------------------------------
# E09, the dates
# ---------------------------------------------------------------------------

def check_dates(inv, po, grn) -> list[dict]:
    inv_date = as_date(inv.get("invoice_date"))
    if inv_date is None:
        return []
    out = []
    if po is not None:
        po_date = as_date(po["po_date"])
        if po_date and inv_date < po_date:
            out.append(finding(
                "E09_DATE_ANOMALY",
                f"The invoice is dated {inv_date.isoformat()} but the order was "
                f"only raised on {po_date.isoformat()}, {(po_date - inv_date).days} "
                f"days later.",
                0, None,
                "Goods cannot be billed before they were ordered. Establish "
                "whether the order was raised after the fact to cover a "
                "purchase already made.",
            ))
            return out
    if grn is not None:
        receipt = as_date(grn["receipt_date"])
        if receipt and inv_date < receipt:
            out.append(finding(
                "E09_DATE_ANOMALY",
                f"The invoice is dated {inv_date.isoformat()}, "
                f"{(receipt - inv_date).days} days before the goods were "
                f"received on {receipt.isoformat()}.",
                0, None,
                "Check the cut off. Billing ahead of delivery moves cost into "
                "the wrong period.",
            ))
    return out


# ---------------------------------------------------------------------------
# E11, whether the document is a valid tax invoice
# ---------------------------------------------------------------------------

def check_tax_invoice_validity(inv) -> list[dict]:
    total = inv.get("total_incl_vat")
    if total is None or total <= cfg.FULL_TAX_INVOICE_THRESHOLD:
        return []

    missing = []
    if not inv.get("has_tax_invoice_words"):
        missing.append("the words Tax Invoice")
    if not (inv.get("supplier_vat_number") or "").strip():
        missing.append("the supplier VAT registration number")
    if not inv.get("invoice_date"):
        missing.append("the date of issue")
    if not (inv.get("recipient_name") or "").strip():
        missing.append("the name of the recipient")
    if not missing:
        return []

    vat = inv.get("vat_amount") or 0
    return [finding(
        "E11_INVALID_TAX_INVOICE",
        f"The supply is {rands(total)}, above the R5 000 full tax invoice "
        f"threshold, but the document is missing " + ", ".join(missing) + ". "
        f"The {rands(vat)} of input VAT cannot be claimed as it stands.",
        vat, None,
        "Request a compliant tax invoice before the VAT return is filed. The "
        "goods can still be paid for, the input tax cannot be claimed.",
    )]


# ---------------------------------------------------------------------------
# E03 and E10, patterns that only appear across several invoices
# ---------------------------------------------------------------------------

def normalise_invoice_number(value: str | None) -> str:
    if not value:
        return ""
    return "".join(ch for ch in str(value).upper() if ch.isalnum())


def find_duplicates(invoices: list[dict]) -> dict[str, list[dict]]:
    """Returns findings keyed by the invoice id of the later submission."""
    found: dict[str, list[dict]] = defaultdict(list)

    by_number: dict[tuple, list[dict]] = defaultdict(list)
    for inv in invoices:
        if not is_readable(inv):
            continue
        key = (inv.get("supplier_id"), normalise_invoice_number(inv.get("invoice_number")))
        if key[0] and key[1]:
            by_number[key].append(inv)

    flagged: set[str] = set()
    for (supplier_id, number), group in by_number.items():
        if len(group) < 2:
            continue
        group.sort(key=lambda i: (str(i.get("invoice_date") or ""), i["invoice_id"]))
        first = group[0]
        for later in group[1:]:
            flagged.add(later["invoice_id"])
            found[later["invoice_id"]].append(finding(
                "E03_DUPLICATE",
                f"Invoice number {later.get('invoice_number')} has already been "
                f"captured as {first['invoice_id']} dated "
                f"{first.get('invoice_date')} for "
                f"{rands(first.get('total_incl_vat'))}.",
                later.get("total_incl_vat") or 0, None,
                "Block the payment and mark it a duplicate. Confirm the "
                "original has not already gone out in an earlier run.",
            ))

    # Same supplier, same amount, a few days apart, different reference. This
    # is how a resubmitted invoice usually looks once a clerk has retyped it.
    by_supplier: dict[str, list[dict]] = defaultdict(list)
    for inv in invoices:
        if is_readable(inv) and inv.get("supplier_id"):
            by_supplier[inv["supplier_id"]].append(inv)

    for group in by_supplier.values():
        group.sort(key=lambda i: str(i.get("invoice_date") or ""))
        for a_idx, a in enumerate(group):
            for b in group[a_idx + 1:]:
                if b["invoice_id"] in flagged or a["invoice_id"] == b["invoice_id"]:
                    continue
                if normalise_invoice_number(a.get("invoice_number")) == \
                        normalise_invoice_number(b.get("invoice_number")):
                    continue
                if a.get("total_incl_vat") is None or b.get("total_incl_vat") is None:
                    continue
                if abs(a["total_incl_vat"] - b["total_incl_vat"]) > 0.05:
                    continue
                da, db = as_date(a.get("invoice_date")), as_date(b.get("invoice_date"))
                if not da or not db or abs((db - da).days) > cfg.DUPLICATE_WINDOW_DAYS:
                    continue
                flagged.add(b["invoice_id"])
                found[b["invoice_id"]].append(finding(
                    "E03_DUPLICATE",
                    f"{rands(b['total_incl_vat'])} from the same supplier was "
                    f"already invoiced on {a.get('invoice_date')} under "
                    f"{a.get('invoice_number')}. This one is dated "
                    f"{b.get('invoice_date')} under {b.get('invoice_number')}.",
                    b["total_incl_vat"], None,
                    "Two identical amounts days apart from one supplier is "
                    "rarely a coincidence. Confirm with the supplier's "
                    "statement before either is paid.",
                ))
    return found


def find_threshold_splitting(invoices: list[dict]) -> dict[str, list[dict]]:
    """
    Several invoices from one supplier, each sitting just under a sign off
    limit, inside a short window. Individually each one is approvable by a
    junior. Together they are not.
    """
    found: dict[str, list[dict]] = defaultdict(list)
    by_supplier: dict[str, list[dict]] = defaultdict(list)
    for inv in invoices:
        if is_readable(inv) and inv.get("supplier_id"):
            by_supplier[inv["supplier_id"]].append(inv)

    for supplier_id, group in by_supplier.items():
        group = [i for i in group if i.get("total_incl_vat")]
        group.sort(key=lambda i: str(i.get("invoice_date") or ""))

        for threshold in cfg.APPROVAL_THRESHOLDS:
            floor = threshold * (1 - cfg.SPLIT_PROXIMITY)
            near = [i for i in group if floor <= i["total_incl_vat"] < threshold]
            if len(near) < 3:
                continue
            for start in range(len(near)):
                window = [near[start]]
                d0 = as_date(near[start].get("invoice_date"))
                if d0 is None:
                    continue
                for other in near[start + 1:]:
                    d1 = as_date(other.get("invoice_date"))
                    if d1 and 0 <= (d1 - d0).days <= cfg.SPLIT_WINDOW_DAYS:
                        window.append(other)
                if len(window) < 3:
                    continue
                combined = sum(i["total_incl_vat"] for i in window)
                level = next(w for lo, hi, w in cfg.APPROVAL_BANDS
                             if lo <= combined < hi)
                for inv in window:
                    if any(f["code"] == "E10_THRESHOLD_SPLIT"
                           for f in found[inv["invoice_id"]]):
                        continue
                    found[inv["invoice_id"]].append(finding(
                        "E10_THRESHOLD_SPLIT",
                        f"{len(window)} invoices from this supplier between "
                        f"{window[0].get('invoice_date')} and "
                        f"{window[-1].get('invoice_date')} each sit just under "
                        f"the R{threshold:,.0f} approval limit and total "
                        f"{rands(combined)}, which needs {level} sign off.",
                        inv["total_incl_vat"] / len(window) * 0 + inv["total_incl_vat"],
                        None,
                        "Treat the run as one commitment and route it to the "
                        "level the combined value requires. Ask the requester "
                        "why it was placed in pieces.",
                    ))
                break
    return found
