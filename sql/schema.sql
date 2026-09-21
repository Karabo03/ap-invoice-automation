-- ---------------------------------------------------------------------------
-- Accounts payable automation, database schema
--
-- Three groups of tables:
--   1. What the company's own systems already know: suppliers, purchase orders,
--      goods received notes. This is the trusted side of the match.
--   2. What was read off the supplier's invoice by the extraction step. This is
--      the untrusted side.
--   3. What the controls found when the two were compared.
-- ---------------------------------------------------------------------------

DROP TABLE IF EXISTS exceptions;
DROP TABLE IF EXISTS extraction_log;
DROP TABLE IF EXISTS invoice_lines;
DROP TABLE IF EXISTS invoices;
DROP TABLE IF EXISTS grn_lines;
DROP TABLE IF EXISTS goods_received_notes;
DROP TABLE IF EXISTS po_lines;
DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS suppliers;

-- 1. Company records -------------------------------------------------------

CREATE TABLE suppliers (
    supplier_id        TEXT PRIMARY KEY,
    supplier_name      TEXT NOT NULL,
    category           TEXT,
    vat_number         TEXT,
    reg_number         TEXT,
    address            TEXT,
    contact_email      TEXT,
    bank_name          TEXT,
    branch_code        TEXT,
    account_number     TEXT,
    payment_terms_days INTEGER,
    approved           TEXT CHECK (approved IN ('Y', 'N')),
    date_approved      TEXT
);

CREATE TABLE purchase_orders (
    po_number      TEXT PRIMARY KEY,
    supplier_id    TEXT NOT NULL REFERENCES suppliers (supplier_id),
    supplier_name  TEXT,
    po_date        TEXT NOT NULL,
    requester      TEXT,
    department     TEXT,
    cost_centre    TEXT,
    total_ex_vat   REAL NOT NULL,
    approval_level TEXT,
    status         TEXT
);

CREATE TABLE po_lines (
    po_number          TEXT NOT NULL REFERENCES purchase_orders (po_number),
    line_no            INTEGER NOT NULL,
    item_code          TEXT,
    description        TEXT,
    qty_ordered        REAL NOT NULL,
    unit_price_ex_vat  REAL NOT NULL,
    line_total_ex_vat  REAL NOT NULL,
    PRIMARY KEY (po_number, line_no)
);

CREATE TABLE goods_received_notes (
    grn_number   TEXT PRIMARY KEY,
    po_number    TEXT NOT NULL REFERENCES purchase_orders (po_number),
    supplier_id  TEXT REFERENCES suppliers (supplier_id),
    receipt_date TEXT NOT NULL,
    received_by  TEXT,
    warehouse    TEXT
);

CREATE TABLE grn_lines (
    grn_number   TEXT NOT NULL REFERENCES goods_received_notes (grn_number),
    po_number    TEXT NOT NULL,
    line_no      INTEGER NOT NULL,
    item_code    TEXT,
    qty_received REAL NOT NULL,
    PRIMARY KEY (grn_number, line_no)
);

-- 2. What was read off the invoice -----------------------------------------

CREATE TABLE invoices (
    invoice_id            TEXT PRIMARY KEY,
    pdf_file              TEXT,
    invoice_number        TEXT,
    supplier_name_raw     TEXT,   -- exactly as printed on the document
    supplier_id           TEXT,   -- resolved against the master file, may be null
    supplier_vat_number   TEXT,
    recipient_name        TEXT,
    po_number             TEXT,
    invoice_date          TEXT,
    due_date              TEXT,
    bank_name             TEXT,
    branch_code           TEXT,
    account_number        TEXT,
    subtotal_ex_vat       REAL,
    vat_amount            REAL,
    total_incl_vat        REAL,
    currency              TEXT DEFAULT 'ZAR',
    has_tax_invoice_words INTEGER,
    document_type         TEXT,
    extraction_method     TEXT,   -- claude_text, claude_vision or rules_fallback
    extraction_confidence REAL,
    extraction_notes      TEXT,
    -- set by the control engine: clean, exception, or manual_capture when the
    -- document could not be read well enough to be checked at all
    processing_status     TEXT DEFAULT 'pending'
);

CREATE TABLE invoice_lines (
    invoice_id  TEXT NOT NULL REFERENCES invoices (invoice_id),
    line_no     INTEGER NOT NULL,
    item_code   TEXT,
    description TEXT,
    quantity    REAL,
    unit_price  REAL,
    line_total  REAL,
    PRIMARY KEY (invoice_id, line_no)
);

CREATE TABLE extraction_log (
    invoice_id     TEXT PRIMARY KEY REFERENCES invoices (invoice_id),
    method         TEXT,
    model          TEXT,
    input_tokens   INTEGER,
    output_tokens  INTEGER,
    seconds        REAL,
    attempts       INTEGER,
    text_chars     INTEGER,
    error          TEXT
);

-- 3. What the controls found -----------------------------------------------

CREATE TABLE exceptions (
    exception_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id     TEXT NOT NULL REFERENCES invoices (invoice_id),
    code           TEXT NOT NULL,
    control        TEXT,
    severity       TEXT,
    line_no        INTEGER,
    detail         TEXT NOT NULL,
    value_at_risk  REAL NOT NULL DEFAULT 0,
    recommendation TEXT
);

CREATE INDEX idx_po_lines_po        ON po_lines (po_number);
CREATE INDEX idx_grn_po             ON goods_received_notes (po_number);
CREATE INDEX idx_grn_lines_po       ON grn_lines (po_number, line_no);
CREATE INDEX idx_invoices_supplier  ON invoices (supplier_id);
CREATE INDEX idx_invoices_po        ON invoices (po_number);
CREATE INDEX idx_exceptions_invoice ON exceptions (invoice_id);
CREATE INDEX idx_exceptions_code    ON exceptions (code);
