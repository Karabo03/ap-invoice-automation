"""
The instruction given to Claude when it reads an invoice.

The single most important rule in this file is the one telling the model to
transcribe and not to correct. A helpful model will quietly recalculate VAT that
looks wrong, or make the line totals add up to the printed total. If it does
that, every downstream control goes quiet and the system finds nothing. The
model's job is to read the document. Deciding whether the document is right is
the control engine's job, and that is deliberate.
"""

SYSTEM_PROMPT = """You read supplier invoices for the accounts payable team at \
Kalahari Components (Pty) Ltd, a South African company.

Your only job is to transcribe what is printed on the document into JSON. You \
are not checking the document and you are not fixing it.

Rules you must follow:

1. Copy the numbers exactly as printed. If the VAT shown does not equal 15 \
percent of the amount excluding VAT, report the figure that is printed. If the \
line items do not add up to the printed subtotal, report both as printed. \
Errors on the invoice are the reason this system exists, so never silently \
correct one.

2. Never calculate a value that is not printed. If the invoice shows no \
subtotal, return null for it rather than working it out from the lines.

3. Use null for anything that is genuinely absent from the page. Do not guess, \
and do not carry a value over from a similar field.

4. Dates go into YYYY-MM-DD form. South African invoices normally write day \
before month, so 03/08/2026 is 3 August 2026.

5. Amounts are plain numbers with a full stop as the decimal point and no \
currency symbol, thousands separator or spaces. R12 450,00 and R12,450.00 both \
become 12450.00.

6. The reference to the buyer's own order may be labelled Order No, Your Order, \
Customer Order Ref, P/O or something similar. It usually looks like \
PO-2025-01234. If there is none, return null.

7. has_tax_invoice_words is true only when the words Tax Invoice, VAT Invoice \
or Invoice appear as the heading of the document. A document headed Statement \
of Account, Delivery Note or Charge Advice is false.

8. confidence is your own honest reading of how clear the document was. Use 1.0 \
for a crisp page where every field was unambiguous, lower it for a poor scan, \
a cramped layout or a field you had to infer from position rather than a label.

Reply with the JSON object and nothing else. No explanation, no markdown fence."""


JSON_SHAPE = """{
  "invoice_number": string or null,
  "supplier_name": string or null,
  "supplier_vat_number": string or null,
  "recipient_name": string or null,
  "po_number": string or null,
  "invoice_date": "YYYY-MM-DD" or null,
  "due_date": "YYYY-MM-DD" or null,
  "bank_name": string or null,
  "branch_code": string or null,
  "account_number": string or null,
  "subtotal_ex_vat": number or null,
  "vat_amount": number or null,
  "total_incl_vat": number or null,
  "currency": string,
  "has_tax_invoice_words": true or false,
  "document_type": string,
  "lines": [
    {
      "item_code": string or null,
      "description": string or null,
      "quantity": number or null,
      "unit_price": number or null,
      "line_total": number or null
    }
  ],
  "confidence": number between 0 and 1,
  "notes": string or null
}"""


def text_user_message(page_text: str) -> str:
    return (
        "Below is the text layer of a supplier invoice, taken straight out of "
        "the PDF. Spacing and column alignment may have been lost.\n\n"
        "<invoice_text>\n"
        f"{page_text.strip()}\n"
        "</invoice_text>\n\n"
        "Return this exact JSON shape:\n\n"
        f"{JSON_SHAPE}"
    )


def vision_user_message() -> str:
    return (
        "The image is a scanned supplier invoice. It has no text layer, so read "
        "it from the page itself. It may be slightly crooked or faint.\n\n"
        "Return this exact JSON shape:\n\n"
        f"{JSON_SHAPE}"
    )
