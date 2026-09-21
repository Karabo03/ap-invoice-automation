"""
The rules based fallback.

This runs when no API key is present, so that anyone who clones the repository
gets a working pipeline instead of a crash. It is a genuine attempt, not a straw
man: it knows every label the four layouts use and handles all three number
formats.

It also has an obvious ceiling. A scanned invoice has no text at all, so there
is nothing for a regular expression to match, and a layout nobody anticipated
needs a new pattern written by hand. Comparing this against the model is the
honest way to show what the language model is actually buying.
"""

from __future__ import annotations

import re
from datetime import datetime

MONTHS = {m.lower(): i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July",
     "August", "September", "October", "November", "December"], start=1)}
MONTHS.update({m[:3].lower(): i for m, i in list(MONTHS.items())})

# Amounts on these invoices always carry cents. Insisting on the decimal part
# is what stops a VAT registration number such as 4180267913, which sits right
# next to the word VAT, being read as four billion rand.
AMOUNT = r"R?\s*(-?\d[\d  ,]*\d|\d)[.,](\d{2})(?!\d)"

# Words that mean the number after the label is a reference, not money.
REFERENCE_WORDS = r"(?:reg(?:istration)?|no\.?|number|#)"


def to_number(whole: str, cents: str | None) -> float | None:
    if whole is None:
        return None
    cleaned = re.sub(r"[  ,]", "", whole)
    if not cleaned or not re.fullmatch(r"-?\d+", cleaned):
        return None
    value = float(cleaned)
    if cents:
        value += float(f"0.{cents}") * (1 if value >= 0 else -1)
    return round(value, 2)


def find_amount(text: str, labels: list[str]) -> float | None:
    for label in labels:
        pattern = (re.escape(label) + r"(?!\s*" + REFERENCE_WORDS + r")"
                   + r"[^0-9\-\n]{0,24}" + AMOUNT)
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            return to_number(m.group(1), m.group(2))
    return None


def find_after(text: str, labels: list[str], pattern: str) -> str | None:
    for label in labels:
        m = re.search(re.escape(label) + r"[^\S\n]*[:#]?[^\S\n]*(" + pattern + ")",
                      text, re.IGNORECASE)
        if m:
            return m.group(1).strip()
    return None


def parse_date(raw: str | None) -> str | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date().isoformat()
        except ValueError:
            pass
    m = re.match(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", raw)
    if m and m.group(2).lower() in MONTHS:
        return f"{int(m.group(3)):04d}-{MONTHS[m.group(2).lower()]:02d}-{int(m.group(1)):02d}"
    return None


DATE_PATTERN = r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Za-z]{3,9}\s+\d{4}"

LINE_PATTERNS = [
    # layout A, B and D: code, description, qty, unit price, line total
    re.compile(
        r"^(?P<code>[A-Z]{3}-[A-Z0-9]+)\s+(?P<desc>.+?)\s+(?P<qty>\d+)\s+"
        r"R?\s*(?P<unit>[\d  ,]+\.\d{2})\s+R?\s*(?P<total>[\d  ,]+\.\d{2})\s*$"
    ),
    # layout C: qty first
    re.compile(
        r"^\s*(?P<qty>\d+)\s+(?P<code>[A-Z]{3}-[A-Z0-9]+)\s+(?P<desc>.+?)\s+"
        r"(?P<unit>[\d,]+\.\d{2})\s+(?P<total>[\d,]+\.\d{2})\s*$"
    ),
]


def parse_lines(text: str) -> list[dict]:
    out = []
    for raw in text.splitlines():
        for pattern in LINE_PATTERNS:
            m = pattern.match(raw.strip())
            if not m:
                continue
            out.append(
                {
                    "item_code": m.group("code"),
                    "description": m.group("desc").strip(),
                    "quantity": float(m.group("qty")),
                    "unit_price": to_number(*split_money(m.group("unit"))),
                    "line_total": to_number(*split_money(m.group("total"))),
                }
            )
            break
    return out


def split_money(raw: str) -> tuple[str, str | None]:
    raw = raw.strip()
    if "." in raw:
        whole, cents = raw.rsplit(".", 1)
        return whole, cents
    return raw, None


def parse(text: str) -> dict:
    """Best effort structured read of an invoice's text layer."""
    if not text or len(text.strip()) < 40:
        return {
            "invoice_number": None, "supplier_name": None,
            "supplier_vat_number": None, "recipient_name": None,
            "po_number": None, "invoice_date": None, "due_date": None,
            "bank_name": None, "branch_code": None, "account_number": None,
            "subtotal_ex_vat": None, "vat_amount": None, "total_incl_vat": None,
            "currency": "ZAR", "has_tax_invoice_words": False,
            "document_type": "unreadable", "lines": [], "confidence": 0.0,
            "notes": "No text layer. A rules based parser cannot read a scanned page.",
        }

    lines_of_text = [l.rstrip() for l in text.splitlines() if l.strip()]
    head = "\n".join(lines_of_text[:6])

    supplier = None
    for l in lines_of_text[:8]:
        if "(Pty) Ltd" in l or "(PTY) LTD" in l:
            supplier = l.strip()
            break

    vat_numbers = re.findall(r"VAT(?:\s+Reg(?:istration)?)?(?:\s+No)?\.?\s*:?\s*(4\d{9})",
                             text, re.IGNORECASE)
    supplier_vat = next((v for v in vat_numbers if v != "4180267913"), None)

    recipient = None
    if re.search(r"Kalahari Components", text, re.IGNORECASE):
        recipient = "Kalahari Components (Pty) Ltd"

    invoice_number = find_after(
        text,
        ["Invoice No.", "Tax Invoice Number", "INVOICE #", "Document No", "Invoice No"],
        r"[A-Z0-9][A-Z0-9/\-]{3,20}",
    )

    po_number = find_after(
        text,
        ["Order No.", "Your Order", "Customer Order Ref", "P/O", "Order No"],
        r"PO-\d{4}-\d{4,6}",
    )

    invoice_date = parse_date(find_after(
        text, ["Date", "Invoice Date", "Issued", "DATE"], DATE_PATTERN))
    due_date = parse_date(find_after(
        text, ["Due Date", "Payment Due", "Settlement Date", "DUE"], DATE_PATTERN))

    subtotal = find_amount(text, [
        "Subtotal excluding VAT", "Total excluding VAT", "Net value of supply",
        "SUBTOTAL", "Subtotal"])
    vat_amount = find_amount(text, [
        "VAT @ 15%", "Value Added Tax 15%", "Tax 15%", "VAT", "Tax"])
    total = find_amount(text, [
        "TOTAL DUE", "Amount Payable", "BALANCE DUE", "TOTAL", "Total"])

    bank_name = find_after(text, ["Bank:", "BANK", "Payment to", "Banking"],
                           r"[A-Za-z][A-Za-z ]{3,28}")
    account = find_after(text, ["Account Number:", "ACC", "Acc", "Account"], r"\d{9,11}")
    branch = find_after(text, ["Branch Code:", "BRANCH", "Branch"], r"\d{6}")

    has_words = bool(re.search(r"\b(TAX INVOICE|VAT INVOICE)\b", head, re.IGNORECASE))
    doc_type = "tax_invoice" if has_words else "other"

    parsed_lines = parse_lines(text)

    filled = sum(1 for v in [invoice_number, supplier, invoice_date, total,
                             subtotal, vat_amount] if v is not None)
    confidence = round(min(0.85, 0.10 * filled + (0.12 if parsed_lines else 0)), 2)

    return {
        "invoice_number": invoice_number,
        "supplier_name": supplier,
        "supplier_vat_number": supplier_vat,
        "recipient_name": recipient,
        "po_number": po_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "bank_name": bank_name.strip() if bank_name else None,
        "branch_code": branch,
        "account_number": account,
        "subtotal_ex_vat": subtotal,
        "vat_amount": vat_amount,
        "total_incl_vat": total,
        "currency": "ZAR",
        "has_tax_invoice_words": has_words,
        "document_type": doc_type,
        "lines": parsed_lines,
        "confidence": confidence,
        "notes": "Read by pattern matching, no language model involved.",
    }
