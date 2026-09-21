"""
Step 3. Read every invoice PDF and write what was found into the database.

Each invoice takes one of three routes:

    claude_text     the PDF has a text layer, so the text goes to Claude
    claude_vision   the PDF is a scan, so the page image goes to Claude
    rules_fallback  no API key, so a pattern matching parser has a go

Nothing here judges the invoice. It only records what the document says.

    python src/step3_extract_invoices.py
    python src/step3_extract_invoices.py --limit 20
    python src/step3_extract_invoices.py --fallback      force the no API route
    python src/step3_extract_invoices.py --model claude-haiku-4-5-20251001
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from difflib import SequenceMatcher
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config as cfg
from src.extraction import claude_client, fallback_parser, pdf_reader


# ---------------------------------------------------------------------------
# Matching the name on the invoice back to the supplier master file
# ---------------------------------------------------------------------------

def resolve_supplier(data: dict, suppliers: list[dict]) -> str | None:
    """VAT number first, because it is unique. Name only as a second best."""
    vat = (data.get("supplier_vat_number") or "").strip()
    if vat:
        for s in suppliers:
            if s["vat_number"] == vat:
                return s["supplier_id"]

    name = (data.get("supplier_name") or "").strip().lower()
    if not name:
        return None
    name = name.replace("(pty) ltd", "").replace("(pty)ltd", "").strip()

    best_id, best_score = None, 0.0
    for s in suppliers:
        target = s["supplier_name"].lower().replace("(pty) ltd", "").strip()
        score = SequenceMatcher(None, name, target).ratio()
        if score > best_score:
            best_id, best_score = s["supplier_id"], score
    return best_id if best_score >= 0.86 else None


def clean_number(value) -> float | None:
    if value is None:
        return None
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# One invoice
# ---------------------------------------------------------------------------

def extract_one(pdf_path: Path, use_api: bool, model: str):
    text = pdf_reader.page_text(pdf_path)
    has_text = pdf_reader.has_text_layer(text)

    if not use_api:
        started = time.time()
        data = fallback_parser.parse(text)
        return claude_client.ExtractionResult(
            data=data, method="rules_fallback", model=None,
            seconds=round(time.time() - started, 3), attempts=1,
        ), len(text)

    if has_text:
        result = claude_client.extract_from_text(text, model=model)
    else:
        result = claude_client.extract_from_image(
            pdf_reader.page_png_base64(pdf_path), model=model)

    # If the API could not be reached at all, fall back rather than lose the row.
    if result.data is None:
        data = fallback_parser.parse(text)
        note = (data.get("notes") or "") + f" API failed: {result.error}"
        data["notes"] = note.strip()
        result.data = data
        result.method = "rules_fallback"

    return result, len(text)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0,
                    help="only process this many invoices, useful while testing")
    ap.add_argument("--fallback", action="store_true",
                    help="ignore any API key and use the pattern matching parser")
    ap.add_argument("--model", default=cfg.CLAUDE_MODEL)
    ap.add_argument("--workers", type=int, default=6)
    args = ap.parse_args()

    if not cfg.DB_PATH.exists():
        raise SystemExit("No database. Run step2_build_database.py first.")

    key = claude_client.api_key()
    use_api = bool(key) and not args.fallback

    if use_api:
        print(f"Using the Claude API, model {args.model}")
    elif args.fallback:
        print("Forced onto the rules based parser")
    else:
        print("No ANTHROPIC_API_KEY found, so the rules based parser is being used.")
        print("Set a key in a .env file to run the language model route.")
    print()

    conn = sqlite3.connect(cfg.DB_PATH)
    conn.row_factory = sqlite3.Row
    suppliers = [dict(r) for r in conn.execute(
        "SELECT supplier_id, supplier_name, vat_number FROM suppliers")]

    conn.execute("DELETE FROM invoice_lines")
    conn.execute("DELETE FROM extraction_log")
    conn.execute("DELETE FROM exceptions")
    conn.execute("DELETE FROM invoices")
    conn.commit()

    pdfs = sorted(cfg.INVOICE_PDF_DIR.glob("*.pdf"))
    if args.limit:
        pdfs = pdfs[: args.limit]
    if not pdfs:
        raise SystemExit("No invoice PDFs. Run step1_generate_data.py first.")

    started = time.time()
    rows, line_rows, log_rows = [], [], []
    done = 0
    workers = args.workers if use_api else 1

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(extract_one, p, use_api, args.model): p for p in pdfs}
        for fut in as_completed(futures):
            pdf_path = futures[fut]
            invoice_id = pdf_path.stem
            try:
                result, text_chars = fut.result()
            except Exception as exc:
                result = claude_client.ExtractionResult(
                    data=None, method="failed", model=None,
                    error=f"{type(exc).__name__}: {exc}")
                text_chars = 0

            data = result.data or {}
            supplier_id = resolve_supplier(data, suppliers) if data else None

            rows.append((
                invoice_id, pdf_path.name,
                data.get("invoice_number"),
                data.get("supplier_name"),
                supplier_id,
                data.get("supplier_vat_number"),
                data.get("recipient_name"),
                data.get("po_number"),
                data.get("invoice_date"),
                data.get("due_date"),
                data.get("bank_name"),
                data.get("branch_code"),
                str(data.get("account_number")) if data.get("account_number") else None,
                clean_number(data.get("subtotal_ex_vat")),
                clean_number(data.get("vat_amount")),
                clean_number(data.get("total_incl_vat")),
                data.get("currency") or "ZAR",
                1 if data.get("has_tax_invoice_words") else 0,
                data.get("document_type"),
                result.method,
                clean_number(data.get("confidence")),
                data.get("notes"),
            ))

            for n, line in enumerate(data.get("lines") or [], start=1):
                if not isinstance(line, dict):
                    continue
                line_rows.append((
                    invoice_id, n, line.get("item_code"), line.get("description"),
                    clean_number(line.get("quantity")),
                    clean_number(line.get("unit_price")),
                    clean_number(line.get("line_total")),
                ))

            log_rows.append((
                invoice_id, result.method, result.model,
                result.input_tokens, result.output_tokens, result.seconds,
                result.attempts, text_chars, result.error,
            ))

            done += 1
            if done % 20 == 0 or done == len(pdfs):
                print(f"  {done:>4} of {len(pdfs)}")

    conn.executemany(
        "INSERT INTO invoices (invoice_id, pdf_file, invoice_number, "
        "supplier_name_raw, supplier_id, supplier_vat_number, recipient_name, "
        "po_number, "
        "invoice_date, due_date, bank_name, branch_code, account_number, "
        "subtotal_ex_vat, vat_amount, total_incl_vat, currency, "
        "has_tax_invoice_words, document_type, extraction_method, "
        "extraction_confidence, extraction_notes) VALUES ("
        + ",".join("?" * 22) + ")", rows)
    conn.executemany(
        "INSERT INTO invoice_lines VALUES (?,?,?,?,?,?,?)", line_rows)
    conn.executemany(
        "INSERT INTO extraction_log VALUES (?,?,?,?,?,?,?,?,?)", log_rows)
    conn.commit()

    elapsed = time.time() - started
    summary = dict(conn.execute(
        "SELECT extraction_method, COUNT(*) FROM invoices GROUP BY 1").fetchall())
    tokens_in, tokens_out = conn.execute(
        "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) "
        "FROM extraction_log").fetchone()
    unresolved = conn.execute(
        "SELECT COUNT(*) FROM invoices WHERE supplier_id IS NULL").fetchone()[0]
    errors = conn.execute(
        "SELECT COUNT(*) FROM extraction_log WHERE error IS NOT NULL").fetchone()[0]

    print()
    print(f"{len(rows)} invoices read in {elapsed:.1f} seconds")
    for method, count in sorted(summary.items()):
        print(f"  {method:<16} {count:>4}")
    print(f"  {'invoice lines':<16} {len(line_rows):>4}")
    print(f"  {'supplier unresolved':<16} {unresolved:>4}")
    if errors:
        print(f"  {'api errors':<16} {errors:>4}")
    if tokens_in:
        cost = claude_client.estimate_cost(args.model, tokens_in, tokens_out)
        print(f"  tokens in {tokens_in:,}, out {tokens_out:,}")
        print(f"  estimated cost of this run about ${cost:,.2f}")

    conn.close()


if __name__ == "__main__":
    main()
