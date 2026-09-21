"""
Central configuration for the accounts payable automation project.

Everything that a finance department would set as policy lives here, so the
control rules stay readable and nothing is hard coded halfway down a script.
"""

from pathlib import Path

# ----------------------------------------------------------------------------
# Paths
# ----------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
INVOICE_PDF_DIR = DATA / "invoices_pdf"
GROUND_TRUTH_DIR = DATA / "ground_truth"
EXTRACTED_DIR = DATA / "extracted"
OUTPUTS = ROOT / "outputs"
SQL_DIR = ROOT / "sql"
DOCS = ROOT / "docs"
DB_PATH = DATA / "ap_automation.db"

for _p in (DATA, INVOICE_PDF_DIR, GROUND_TRUTH_DIR, EXTRACTED_DIR, OUTPUTS, DOCS):
    _p.mkdir(parents=True, exist_ok=True)

# ----------------------------------------------------------------------------
# The fictional company
# ----------------------------------------------------------------------------
COMPANY = {
    "name": "Kalahari Components (Pty) Ltd",
    "reg_number": "2011/034782/07",
    "vat_number": "4180267913",
    "address": "17 Bosman Road, Wynberg, Sandton, 2090",
    "city": "Johannesburg",
    "email": "creditors@kalaharicomponents.co.za",
}

# ----------------------------------------------------------------------------
# South African tax rules
# Standard VAT rate is 15 percent. A full tax invoice is required where the
# consideration exceeds R5 000, and it must carry specific particulars before
# the input VAT may be claimed.
# ----------------------------------------------------------------------------
VAT_RATE = 0.15
FULL_TAX_INVOICE_THRESHOLD = 5000.00
VAT_ROUNDING_TOLERANCE = 0.05  # rand

REQUIRED_FULL_INVOICE_PARTICULARS = [
    "tax_invoice_wording",
    "supplier_name",
    "supplier_vat_number",
    "recipient_name",
    "invoice_number",
    "invoice_date",
    "line_description",
    "amount_ex_vat",
    "vat_amount",
    "total_incl_vat",
]

# ----------------------------------------------------------------------------
# Company approval policy. Used by the threshold splitting control.
# ----------------------------------------------------------------------------
APPROVAL_BANDS = [
    (0, 10_000, "Buyer"),
    (10_000, 50_000, "Department Manager"),
    (50_000, 250_000, "Finance Manager"),
    (250_000, float("inf"), "Chief Financial Officer"),
]
APPROVAL_THRESHOLDS = [10_000, 50_000, 250_000]
SPLIT_PROXIMITY = 0.04      # within 4 percent under a threshold counts as close
SPLIT_WINDOW_DAYS = 14      # invoices this close together are looked at as a set

# ----------------------------------------------------------------------------
# Three way matching tolerances
# ----------------------------------------------------------------------------
PRICE_TOLERANCE_PCT = 0.02   # 2 percent
PRICE_TOLERANCE_ABS = 50.00  # or R50 on the line, whichever is the larger
QTY_TOLERANCE = 0.0          # no tolerance on over delivery of quantity
DUPLICATE_WINDOW_DAYS = 10   # same supplier, same amount, this close together

# ----------------------------------------------------------------------------
# Exception catalogue
# ----------------------------------------------------------------------------
EXCEPTION_CATALOGUE = {
    "E01_PRICE_VARIANCE": {
        "name": "Price above the order",
        "severity": "HIGH",
        "control": "Three way match",
        "description": "The unit price invoiced is higher than the price agreed on the purchase order.",
    },
    "E02_QTY_OVER_BILLED": {
        "name": "Quantity over billed",
        "severity": "HIGH",
        "control": "Three way match",
        "description": "The quantity invoiced is greater than the quantity the warehouse actually received.",
    },
    "E03_DUPLICATE": {
        "name": "Duplicate invoice",
        "severity": "HIGH",
        "control": "Duplicate payment prevention",
        "description": "The same invoice appears to have been submitted more than once.",
    },
    "E04_NO_PO": {
        "name": "No valid purchase order",
        "severity": "MEDIUM",
        "control": "Procurement compliance",
        "description": "The invoice quotes no purchase order, or one that does not exist on the system.",
    },
    "E05_VAT_ERROR": {
        "name": "VAT incorrectly calculated",
        "severity": "MEDIUM",
        "control": "Tax accuracy",
        "description": "The VAT charged is not 15 percent of the amount excluding VAT.",
    },
    "E06_BANK_CHANGE": {
        "name": "Bank details changed",
        "severity": "HIGH",
        "control": "Payment redirection fraud",
        "description": "The bank account on the invoice is not the account held for this supplier.",
    },
    "E07_UNAPPROVED_SUPPLIER": {
        "name": "Supplier not approved",
        "severity": "HIGH",
        "control": "Vendor master control",
        "description": "The supplier is not on the approved vendor master file.",
    },
    "E08_ARITHMETIC": {
        "name": "Invoice does not add up",
        "severity": "MEDIUM",
        "control": "Mathematical accuracy",
        "description": "The line items do not sum to the stated subtotal, or the totals do not reconcile.",
    },
    "E09_DATE_ANOMALY": {
        "name": "Invoice date out of sequence",
        "severity": "MEDIUM",
        "control": "Cut off and backdating",
        "description": "The invoice is dated before the purchase order was raised or before the goods arrived.",
    },
    "E10_THRESHOLD_SPLIT": {
        "name": "Split to avoid approval",
        "severity": "HIGH",
        "control": "Delegation of authority",
        "description": "Several invoices from one supplier sit just below an approval limit within a short period.",
    },
    "E11_INVALID_TAX_INVOICE": {
        "name": "Not a valid tax invoice",
        "severity": "MEDIUM",
        "control": "VAT recoverability",
        "description": "The document is above R5 000 but is missing a particular required for a full tax invoice, so the input VAT cannot be claimed.",
    },
    "E12_GOODS_NOT_RECEIVED": {
        "name": "No goods received note",
        "severity": "HIGH",
        "control": "Three way match",
        "description": "There is a purchase order and an invoice, but the warehouse has never booked the goods in.",
    },
}

SEVERITY_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}

# ----------------------------------------------------------------------------
# Claude API
# ----------------------------------------------------------------------------
#
# Set ANTHROPIC_API_KEY in a .env file or as an environment variable. Without
# one the pipeline still runs, on the rules based fallback, and says so.
#
# Sonnet 5 is the default because invoice layouts vary and accuracy matters
# more here than speed. Haiku 4.5 costs roughly half and is a reasonable swap
# once the prompt has been proved.
CLAUDE_MODEL = "claude-sonnet-5"
CLAUDE_MODEL_CHEAP = "claude-haiku-4-5-20251001"

# Published list prices in US dollars per million tokens, used only to estimate
# what a run costs. Check the current figures before quoting them anywhere.
MODEL_PRICING = {
    "claude-sonnet-5": {"input": 2.00, "output": 10.00},
    "claude-haiku-4-5-20251001": {"input": 1.00, "output": 5.00},
    "claude-opus-5": {"input": 5.00, "output": 25.00},
}

CLAUDE_MAX_TOKENS = 2000
CLAUDE_TEMPERATURE = 0.0     # extraction must be repeatable, so no creativity
API_MAX_RETRIES = 3
API_RETRY_BACKOFF = 2.0
VISION_DPI = 150

RANDOM_SEED = 20260921
