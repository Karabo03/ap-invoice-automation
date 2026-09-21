"""
Renders each invoice as a PDF in one of four house styles.

The layouts deliberately disagree with each other. One calls the reference
"Invoice No.", another "Document No", a third "INVOICE #". Totals sit in
different places, the number formatting differs, and roughly one in six is
turned into a scanned image with no text layer at all. This is what makes the
extraction step worth doing with a language model rather than a regular
expression.
"""

from __future__ import annotations

import io
import random
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from PIL import Image, ImageFilter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas as rl_canvas

import config as cfg

rng = random.Random(cfg.RANDOM_SEED + 1)

W, H = A4


# ---------------------------------------------------------------------------
# Number formatting, one per layout
# ---------------------------------------------------------------------------

def fmt(amount: float, style: str) -> str:
    a = f"{amount:,.2f}"
    if style == "A":
        return "R " + a.replace(",", " ")
    if style == "B":
        return "R" + a
    if style == "C":
        return a.replace(",", "")
    return "R " + a.replace(",", " ")


def nice_date(iso: str, style: str) -> str:
    d = date.fromisoformat(iso)
    if style == "A":
        return d.strftime("%d %B %Y")
    if style == "B":
        return d.strftime("%d/%m/%Y")
    if style == "C":
        return d.strftime("%Y-%m-%d")
    return d.strftime("%d %b %Y")


def wrap(text: str, limit: int) -> list[str]:
    words, out, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 <= limit:
            cur = f"{cur} {w}".strip()
        else:
            out.append(cur)
            cur = w
    if cur:
        out.append(cur)
    return out or [""]


# ---------------------------------------------------------------------------
# Layout A: traditional, boxed table, totals bottom right
# ---------------------------------------------------------------------------

def layout_a(c, inv, omit):
    y = H - 22 * mm
    c.setFont("Helvetica-Bold", 20)
    if "tax_invoice_wording" not in omit:
        c.drawString(20 * mm, y, "TAX INVOICE")
    else:
        c.drawString(20 * mm, y, "STATEMENT OF ACCOUNT")

    c.setFont("Helvetica-Bold", 11)
    c.drawString(20 * mm, y - 11 * mm, inv["supplier_name"])
    c.setFont("Helvetica", 8.5)
    yy = y - 16 * mm
    for line in wrap(inv["supplier_address"], 46):
        c.drawString(20 * mm, yy, line)
        yy -= 4.2 * mm
    if "supplier_vat_number" not in omit:
        c.drawString(20 * mm, yy, f"VAT Reg No: {inv['supplier_vat_number']}")
        yy -= 4.2 * mm
    c.drawString(20 * mm, yy, f"Email: {inv['supplier_email']}")

    bx = 120 * mm
    c.setFont("Helvetica", 9)
    rows = [("Invoice No.", inv["invoice_number"])]
    if "invoice_date" not in omit:
        rows.append(("Date", nice_date(inv["invoice_date"], "A")))
    rows += [("Order No.", inv["po_number"] or "-"),
             ("Due Date", nice_date(inv["due_date"], "A")),
             ("Terms", "Strictly net")]
    ry = y - 11 * mm
    for k, v in rows:
        c.setFont("Helvetica", 8.5)
        c.drawString(bx, ry, k)
        c.setFont("Helvetica-Bold", 8.5)
        c.drawString(bx + 30 * mm, ry, str(v))
        ry -= 5 * mm

    c.setFont("Helvetica-Bold", 9)
    c.drawString(20 * mm, ry - 6 * mm, "INVOICE TO")
    c.setFont("Helvetica", 8.5)
    if "recipient_name" not in omit:
        c.drawString(20 * mm, ry - 11 * mm, cfg.COMPANY["name"])
    c.drawString(20 * mm, ry - 15 * mm, cfg.COMPANY["address"])
    c.drawString(20 * mm, ry - 19 * mm, f"VAT Reg No: {cfg.COMPANY['vat_number']}")

    ty = ry - 30 * mm
    c.setFillColor(colors.HexColor("#e8e8e8"))
    c.rect(20 * mm, ty - 2 * mm, 170 * mm, 7 * mm, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 8)
    for label, x in [("CODE", 22), ("DESCRIPTION", 46), ("QTY", 118),
                     ("UNIT PRICE", 134), ("AMOUNT", 168)]:
        c.drawString(x * mm, ty, label)

    c.setFont("Helvetica", 8)
    ly = ty - 7 * mm
    for l in inv["lines"]:
        c.drawString(22 * mm, ly, l["item_code"])
        for k, seg in enumerate(wrap(l["description"], 42)):
            c.drawString(46 * mm, ly - k * 3.6 * mm, seg)
        c.drawRightString(126 * mm, ly, str(l["quantity"]))
        c.drawRightString(158 * mm, ly, fmt(l["unit_price"], "A"))
        c.drawRightString(188 * mm, ly, fmt(l["line_total"], "A"))
        ly -= max(6 * mm, len(wrap(l["description"], 42)) * 3.8 * mm + 2.5 * mm)

    c.setStrokeColor(colors.HexColor("#999999"))
    c.line(20 * mm, ly + 1 * mm, 190 * mm, ly + 1 * mm)
    c.setFont("Helvetica", 9)
    ly -= 7 * mm
    c.drawRightString(158 * mm, ly, "Subtotal excluding VAT")
    c.drawRightString(188 * mm, ly, fmt(inv["subtotal_ex_vat"], "A"))
    ly -= 5.5 * mm
    c.drawRightString(158 * mm, ly, "VAT @ 15%")
    c.drawRightString(188 * mm, ly, fmt(inv["vat_amount"], "A"))
    ly -= 7 * mm
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(158 * mm, ly, "TOTAL DUE")
    c.drawRightString(188 * mm, ly, fmt(inv["total_incl_vat"], "A"))

    c.setFont("Helvetica-Bold", 8.5)
    c.drawString(20 * mm, 34 * mm, "BANKING DETAILS")
    c.setFont("Helvetica", 8)
    c.drawString(20 * mm, 29 * mm, f"Bank: {inv['bank_name']}")
    c.drawString(20 * mm, 25 * mm, f"Account Number: {inv['account_number']}")
    c.drawString(20 * mm, 21 * mm, f"Branch Code: {inv['branch_code']}")
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(20 * mm, 14 * mm,
                 "Goods remain the property of the supplier until paid in full. E&OE.")


# ---------------------------------------------------------------------------
# Layout B: modern, coloured band, totals in a shaded box
# ---------------------------------------------------------------------------

def layout_b(c, inv, omit):
    band = colors.HexColor("#1f3b57")
    c.setFillColor(band)
    c.rect(0, H - 34 * mm, W, 34 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 16)
    c.drawString(18 * mm, H - 16 * mm, inv["supplier_name"])
    c.setFont("Helvetica", 8.5)
    c.drawString(18 * mm, H - 22 * mm, inv["supplier_address"])
    if "supplier_vat_number" not in omit:
        c.drawString(18 * mm, H - 27 * mm,
                     f"VAT Registration {inv['supplier_vat_number']}   |   {inv['supplier_email']}")
    else:
        c.drawString(18 * mm, H - 27 * mm, inv["supplier_email"])

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 13)
    label = "TAX INVOICE" if "tax_invoice_wording" not in omit else "ACCOUNT"
    c.drawRightString(W - 18 * mm, H - 16 * mm, label)

    c.setFillColor(colors.black)
    y = H - 46 * mm
    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, y, "BILL TO")
    c.setFont("Helvetica", 9)
    if "recipient_name" not in omit:
        c.drawString(18 * mm, y - 5 * mm, cfg.COMPANY["name"])
    c.drawString(18 * mm, y - 9.5 * mm, cfg.COMPANY["address"])
    c.drawString(18 * mm, y - 14 * mm, f"VAT {cfg.COMPANY['vat_number']}")

    right = [("Tax Invoice Number", inv["invoice_number"])]
    if "invoice_date" not in omit:
        right.append(("Invoice Date", nice_date(inv["invoice_date"], "B")))
    right += [("Your Order", inv["po_number"] or "Not supplied"),
              ("Payment Due", nice_date(inv["due_date"], "B"))]
    ry = y
    for k, v in right:
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.HexColor("#666666"))
        c.drawRightString(W - 52 * mm, ry, k)
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(W - 18 * mm, ry, str(v))
        ry -= 5.5 * mm

    ty = y - 26 * mm
    c.setFont("Helvetica-Bold", 7.5)
    c.setFillColor(colors.HexColor("#1f3b57"))
    for label, x in [("ITEM", 18), ("DESCRIPTION", 44), ("QTY", 116),
                     ("RATE", 132), ("LINE TOTAL", 164)]:
        c.drawString(x * mm, ty, label)
    c.setStrokeColor(colors.HexColor("#1f3b57"))
    c.setLineWidth(0.8)
    c.line(18 * mm, ty - 2 * mm, W - 18 * mm, ty - 2 * mm)

    ly = ty - 8 * mm
    c.setFillColor(colors.black)
    for i, l in enumerate(inv["lines"]):
        rows = wrap(l["description"], 40)
        hgt = max(6 * mm, len(rows) * 3.8 * mm + 2.5 * mm)
        if i % 2 == 1:
            c.setFillColor(colors.HexColor("#f4f6f8"))
            c.rect(18 * mm, ly - hgt + 4.5 * mm, W - 36 * mm, hgt, fill=1, stroke=0)
            c.setFillColor(colors.black)
        c.setFont("Helvetica", 8)
        c.drawString(18 * mm, ly, l["item_code"])
        for k, seg in enumerate(rows):
            c.drawString(44 * mm, ly - k * 3.6 * mm, seg)
        c.drawRightString(124 * mm, ly, str(l["quantity"]))
        c.drawRightString(156 * mm, ly, fmt(l["unit_price"], "B"))
        c.drawRightString(W - 18 * mm, ly, fmt(l["line_total"], "B"))
        ly -= hgt

    bh = 26 * mm
    c.setFillColor(colors.HexColor("#f4f6f8"))
    c.rect(110 * mm, ly - bh + 2 * mm, W - 128 * mm, bh, fill=1, stroke=0)
    c.setFillColor(colors.black)
    c.setFont("Helvetica", 8.5)
    c.drawString(114 * mm, ly - 3 * mm, "Total excluding VAT")
    c.drawRightString(W - 22 * mm, ly - 3 * mm, fmt(inv["subtotal_ex_vat"], "B"))
    c.drawString(114 * mm, ly - 9 * mm, "Value Added Tax 15%")
    c.drawRightString(W - 22 * mm, ly - 9 * mm, fmt(inv["vat_amount"], "B"))
    c.setFont("Helvetica-Bold", 11)
    c.drawString(114 * mm, ly - 18 * mm, "Amount Payable")
    c.drawRightString(W - 22 * mm, ly - 18 * mm, fmt(inv["total_incl_vat"], "B"))

    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, 30 * mm, "Payment to")
    c.setFont("Helvetica", 8)
    c.drawString(18 * mm, 25 * mm,
                 f"{inv['bank_name']}  |  Acc {inv['account_number']}  |  Branch {inv['branch_code']}")
    c.setFont("Helvetica-Oblique", 7)
    c.drawString(18 * mm, 18 * mm,
                 "Please quote the tax invoice number on your remittance advice.")


# ---------------------------------------------------------------------------
# Layout C: plain, typewriter style, no rules at all
# ---------------------------------------------------------------------------

def layout_c(c, inv, omit):
    c.setFont("Courier-Bold", 11)
    y = H - 20 * mm
    if "tax_invoice_wording" not in omit:
        c.drawString(18 * mm, y, "TAX INVOICE")
    else:
        c.drawString(18 * mm, y, "DELIVERY NOTE / CHARGE")
    y -= 7 * mm
    c.setFont("Courier", 9)
    c.drawString(18 * mm, y, inv["supplier_name"].upper())
    y -= 4.5 * mm
    c.drawString(18 * mm, y, inv["supplier_address"])
    y -= 4.5 * mm
    if "supplier_vat_number" not in omit:
        c.drawString(18 * mm, y, f"VAT NO {inv['supplier_vat_number']}")
        y -= 4.5 * mm
    c.drawString(18 * mm, y, inv["supplier_email"])
    y -= 8 * mm

    c.drawString(18 * mm, y, f"INVOICE #  {inv['invoice_number']}")
    y -= 4.5 * mm
    if "invoice_date" not in omit:
        c.drawString(18 * mm, y, f"DATE       {nice_date(inv['invoice_date'], 'C')}")
        y -= 4.5 * mm
    c.drawString(18 * mm, y, f"P/O        {inv['po_number'] or 'NONE'}")
    y -= 4.5 * mm
    c.drawString(18 * mm, y, f"DUE        {nice_date(inv['due_date'], 'C')}")
    y -= 8 * mm

    c.drawString(18 * mm, y, "SOLD TO:")
    y -= 4.5 * mm
    if "recipient_name" not in omit:
        c.drawString(18 * mm, y, cfg.COMPANY["name"].upper())
        y -= 4.5 * mm
    c.drawString(18 * mm, y, cfg.COMPANY["address"])
    y -= 4.5 * mm
    c.drawString(18 * mm, y, f"VAT NO {cfg.COMPANY['vat_number']}")
    y -= 9 * mm

    c.setFont("Courier", 8)
    c.drawString(18 * mm, y, "QTY  CODE          DESCRIPTION                          UNIT       TOTAL")
    y -= 5 * mm
    for l in inv["lines"]:
        desc = l["description"][:36].ljust(36)
        row = (f"{str(l['quantity']):>3}  {l['item_code'][:12]:<12}  {desc}  "
               f"{fmt(l['unit_price'], 'C'):>9}  {fmt(l['line_total'], 'C'):>10}")
        c.drawString(18 * mm, y, row)
        y -= 4.6 * mm

    y -= 4 * mm
    c.drawString(18 * mm, y, f"{'SUBTOTAL':>58}  {fmt(inv['subtotal_ex_vat'], 'C'):>10}")
    y -= 4.6 * mm
    c.drawString(18 * mm, y, f"{'VAT':>58}  {fmt(inv['vat_amount'], 'C'):>10}")
    y -= 4.6 * mm
    c.setFont("Courier-Bold", 9)
    c.drawString(18 * mm, y, f"{'TOTAL':>56}  {fmt(inv['total_incl_vat'], 'C'):>10}")

    c.setFont("Courier", 8)
    c.drawString(18 * mm, 28 * mm, f"BANK {inv['bank_name']}")
    c.drawString(18 * mm, 23.5 * mm, f"ACC  {inv['account_number']}   BRANCH {inv['branch_code']}")
    c.drawString(18 * mm, 17 * mm, "E&OE")


# ---------------------------------------------------------------------------
# Layout D: right aligned masthead, supplier block at the foot
# ---------------------------------------------------------------------------

def layout_d(c, inv, omit):
    c.setFont("Helvetica-Bold", 22)
    c.setFillColor(colors.HexColor("#2d4a2b"))
    c.drawRightString(W - 18 * mm, H - 24 * mm,
                      "TAX INVOICE" if "tax_invoice_wording" not in omit else "CHARGE ADVICE")
    c.setFillColor(colors.black)

    c.setFont("Helvetica-Bold", 12)
    c.drawString(18 * mm, H - 24 * mm, inv["supplier_name"])

    y = H - 36 * mm
    c.setFont("Helvetica", 8.5)
    pairs = [("Document No", inv["invoice_number"])]
    if "invoice_date" not in omit:
        pairs.append(("Issued", nice_date(inv["invoice_date"], "D")))
    pairs += [("Customer Order Ref", inv["po_number"] or "n/a"),
              ("Settlement Date", nice_date(inv["due_date"], "D"))]
    for k, v in pairs:
        c.setFillColor(colors.HexColor("#555555"))
        c.drawRightString(W - 52 * mm, y, k + "  ")
        c.setFillColor(colors.black)
        c.setFont("Helvetica-Bold", 9)
        c.drawRightString(W - 18 * mm, y, str(v))
        c.setFont("Helvetica", 8.5)
        y -= 5.4 * mm

    c.setFont("Helvetica-Bold", 8)
    c.drawString(18 * mm, H - 36 * mm, "CHARGED TO")
    c.setFont("Helvetica", 9)
    if "recipient_name" not in omit:
        c.drawString(18 * mm, H - 41 * mm, cfg.COMPANY["name"])
    c.drawString(18 * mm, H - 45.5 * mm, cfg.COMPANY["address"])
    c.drawString(18 * mm, H - 50 * mm, f"VAT {cfg.COMPANY['vat_number']}")

    ty = min(y, H - 60 * mm) - 6 * mm
    c.setStrokeColor(colors.HexColor("#2d4a2b"))
    c.setLineWidth(1.2)
    c.line(18 * mm, ty + 4 * mm, W - 18 * mm, ty + 4 * mm)
    c.setFont("Helvetica-Bold", 7.5)
    for label, x in [("STOCK CODE", 18), ("GOODS SUPPLIED", 52), ("UNITS", 116),
                     ("PRICE EACH", 132), ("VALUE", 166)]:
        c.drawString(x * mm, ty - 2 * mm, label)
    c.setLineWidth(0.4)
    c.setStrokeColor(colors.HexColor("#bbbbbb"))
    c.line(18 * mm, ty - 5 * mm, W - 18 * mm, ty - 5 * mm)

    ly = ty - 11 * mm
    c.setFont("Helvetica", 8)
    for l in inv["lines"]:
        rows = wrap(l["description"], 38)
        c.drawString(18 * mm, ly, l["item_code"])
        for k, seg in enumerate(rows):
            c.drawString(52 * mm, ly - k * 3.6 * mm, seg)
        c.drawRightString(126 * mm, ly, f"{l['quantity']}")
        c.drawRightString(158 * mm, ly, fmt(l["unit_price"], "D"))
        c.drawRightString(W - 18 * mm, ly, fmt(l["line_total"], "D"))
        hgt = max(6 * mm, len(rows) * 3.8 * mm + 2.5 * mm)
        c.line(18 * mm, ly - hgt + 4 * mm, W - 18 * mm, ly - hgt + 4 * mm)
        ly -= hgt

    ly -= 4 * mm
    c.setFont("Helvetica", 9)
    c.drawRightString(158 * mm, ly, "Net value of supply")
    c.drawRightString(W - 18 * mm, ly, fmt(inv["subtotal_ex_vat"], "D"))
    ly -= 5.5 * mm
    c.drawRightString(158 * mm, ly, "Tax 15%")
    c.drawRightString(W - 18 * mm, ly, fmt(inv["vat_amount"], "D"))
    ly -= 8 * mm
    c.setFillColor(colors.HexColor("#2d4a2b"))
    c.rect(110 * mm, ly - 3 * mm, W - 128 * mm, 10 * mm, fill=1, stroke=0)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 11)
    c.drawString(114 * mm, ly, "BALANCE DUE")
    c.drawRightString(W - 22 * mm, ly, fmt(inv["total_incl_vat"], "D"))
    c.setFillColor(colors.black)

    c.setFont("Helvetica", 7.5)
    c.drawString(18 * mm, 36 * mm, inv["supplier_address"])
    if "supplier_vat_number" not in omit:
        c.drawString(18 * mm, 32 * mm, f"VAT Registration Number {inv['supplier_vat_number']}")
    c.drawString(18 * mm, 28 * mm, inv["supplier_email"])
    c.setFont("Helvetica-Bold", 7.5)
    c.drawString(18 * mm, 21 * mm,
                 f"Banking  {inv['bank_name']}   Account {inv['account_number']}   Branch {inv['branch_code']}")


LAYOUTS = {"A": layout_a, "B": layout_b, "C": layout_c, "D": layout_d}


# ---------------------------------------------------------------------------
# Scanning simulation
# ---------------------------------------------------------------------------

def to_scan(pdf_bytes: bytes) -> bytes:
    """Turn a clean PDF into a slightly crooked, noisy image with no text layer."""
    import pymupdf

    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    page = doc[0]
    pix = page.get_pixmap(dpi=155)
    img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)
    doc.close()

    img = img.convert("L")
    img = img.rotate(rng.uniform(-0.9, 0.9), resample=Image.BICUBIC,
                     expand=False, fillcolor=238)
    img = img.point(lambda p: min(255, int(p * rng.uniform(0.93, 1.0) + rng.uniform(6, 16))))
    img = img.filter(ImageFilter.GaussianBlur(rng.uniform(0.25, 0.6)))

    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=62)
    buf.seek(0)

    out = pymupdf.open()
    newpage = out.new_page(width=W, height=H)
    newpage.insert_image(pymupdf.Rect(0, 0, W, H), stream=buf.read())
    data = out.tobytes()
    out.close()
    return data


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def render_all(invoices: list[dict]) -> None:
    for inv in invoices:
        buf = io.BytesIO()
        c = rl_canvas.Canvas(buf, pagesize=A4)
        c.setTitle(f"Invoice {inv['invoice_number']}")
        LAYOUTS[inv["layout"]](c, inv, set(inv.get("omit_particulars", [])))
        c.showPage()
        c.save()
        data = buf.getvalue()

        if inv.get("is_scan"):
            data = to_scan(data)

        (cfg.INVOICE_PDF_DIR / f"{inv['invoice_id']}.pdf").write_bytes(data)
