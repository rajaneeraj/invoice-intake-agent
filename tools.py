"""
tools.py — Agent tools for invoice extraction and notification generation.

Tool 1: extract_invoice_data
    - Reads email JSON + PDF (text + vision)
    - Calls the primary LLM to extract structured fields
    - Returns a JSON string matching InvoiceSchema

Tool 2: send_cs_notification
    - Accepts extracted invoice JSON
    - Writes a human-readable summary and structured payload to output/
"""

from __future__ import annotations

import base64
import json
import os
import pathlib

import fitz  # PyMuPDF
from agents import function_tool
from dotenv import load_dotenv
from openai import OpenAI
from pydantic import ValidationError

from schemas import InvoiceSchema

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
load_dotenv()

PRIMARY_MODEL = os.getenv("PRIMARY_MODEL", "gpt-5-mini")
OUTPUT_DIR = pathlib.Path("output")


# ═══════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _load_email(email_path: str) -> dict:
    """Read and return the email JSON file."""
    path = pathlib.Path(email_path)
    if not path.exists():
        raise FileNotFoundError(f"Email file not found: {email_path}")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _resolve_attachment_path(email_path: str, email_data: dict) -> pathlib.Path:
    """
    Locate the supported attachment referenced in the email JSON.

    Looks in the same directory as the email JSON file.
    """
    attachments = email_data.get("Message", {}).get("Attachments", [])
    attachment_name = None
    for att in attachments:
        name = att.get("Name", "")
        if name.lower().endswith((".pdf", ".xlsx", ".xls", ".png", ".jpg", ".jpeg")):
            attachment_name = name
            break

    if not attachment_name:
        raise FileNotFoundError("No supported attachment found in email JSON.")

    attachment_path = pathlib.Path(email_path).parent / attachment_name
    if not attachment_path.exists():
        raise FileNotFoundError(
            f"Attachment '{attachment_name}' referenced in email but not found at {attachment_path}"
        )
    return attachment_path


def _extract_pdf_text(pdf_path: pathlib.Path) -> str:
    """Extract all text from a PDF using PyMuPDF."""
    try:
        doc = fitz.open(str(pdf_path))
    except Exception as exc:
        raise RuntimeError(f"Cannot open PDF '{pdf_path}': {exc}") from exc

    pages_text: list[str] = []
    for i, page in enumerate(doc):
        text = page.get_text()
        if text.strip():
            pages_text.append(f"--- Page {i + 1} ---\n{text}")
    doc.close()
    return "\n\n".join(pages_text) if pages_text else "(No extractable text found in PDF)"


def _pdf_pages_to_base64(pdf_path: pathlib.Path, dpi: int = 150) -> list[str]:
    """
    Convert each PDF page to a base64-encoded PNG image.

    These are sent to the vision model so it can read fields embedded
    in images (e.g., invoice numbers in header barcodes).
    """
    images: list[str] = []
    try:
        doc = fitz.open(str(pdf_path))
    except Exception:
        return images

    for page in doc:
        pix = page.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        b64 = base64.b64encode(img_bytes).decode("ascii")
        images.append(b64)
    doc.close()
    return images


def _build_extraction_prompt(email_data: dict, pdf_text: str) -> str:
    """Build the system prompt for the extraction LLM call."""
    msg = email_data.get("Message", {})
    sender = msg.get("From", {}).get("EmailAddress", {})
    subject = msg.get("Subject", "")
    body = msg.get("Body", {}).get("Content", "")
    sent = msg.get("SentDateTime", "")

    return f"""You are a precise invoice-data extractor.

You will receive:
1. An email (metadata + body) that accompanies the invoice.
2. The full extracted text of the attached PDF invoice.
3. Images of each PDF page (look carefully for fields embedded in images,
   especially the invoice number which may only appear in a header image).

EXTRACT every field listed in the JSON schema below.
If a field is not present in the source, leave it as an empty string or 0.
Do NOT hallucinate values — only report what is explicitly in the documents.

--- EMAIL METADATA ---
From: {sender.get('Name', '')} <{sender.get('Address', '')}>
Subject: {subject}
Sent: {sent}

--- EMAIL BODY ---
{body}

--- PDF TEXT ---
{pdf_text}
"""


# ═══════════════════════════════════════════════════════════════════════════
# Tool 1 — Document & Vision Extractor
# ═══════════════════════════════════════════════════════════════════════════

@function_tool
def extract_invoice_data(email_path: str) -> str:
    """
    Extract structured invoice data from an email JSON and its attached PDF.

    Reads the email at `email_path`, locates the PDF attachment in the same
    directory, extracts text + page images, and calls the primary LLM with
    vision to produce a structured JSON output matching InvoiceSchema.

    Args:
        email_path: Path to the input email JSON file.

    Returns:
        A JSON string containing all extracted invoice fields.
    """
    # 1. Load email
    email_data = _load_email(email_path)

    # 2. Locate and read the attachment
    attachment_path = _resolve_attachment_path(email_path, email_data)
    pdf_text = _extract_pdf_text(attachment_path)
    page_images = _pdf_pages_to_base64(attachment_path)

    # 3. Build the prompt
    system_prompt = _build_extraction_prompt(email_data, pdf_text)

    # 4. Construct the user message content (Responses API format)
    #    - Text items use type="input_text"
    #    - Image items use type="input_image" with image_url as a data URL string
    user_content: list[dict] = [
        {
            "type": "input_text",
            "text": (
                "Here are the PDF page images. Examine them carefully for any "
                "fields not captured in the text (especially invoice number, "
                "barcodes, logos, stamps, or handwritten notes)."
            ),
        }
    ]
    for b64_img in page_images:
        user_content.append({
            "type": "input_image",
            "image_url": f"data:image/png;base64,{b64_img}",
            "detail": "high",
        })

    # 5. Call the LLM with structured output (Responses API)
    client = OpenAI()

    response = client.responses.parse(
        model=PRIMARY_MODEL,
        instructions=system_prompt,
        input=[{"role": "user", "content": user_content}],
        text_format=InvoiceSchema,
    )

    # 6. Parse and validate
    parsed = response.output_parsed
    if parsed is None:
        # Fallback: try to parse the raw text output
        raw_text = response.output_text
        try:
            parsed = InvoiceSchema.model_validate_json(raw_text)
        except (ValidationError, json.JSONDecodeError) as exc:
            return json.dumps({
                "error": f"LLM output could not be parsed into InvoiceSchema: {exc}",
                "raw_output": raw_text[:2000],
            })

    return parsed.model_dump_json(indent=2)


# ═══════════════════════════════════════════════════════════════════════════
# Tool 2 — Notification Generator
# ═══════════════════════════════════════════════════════════════════════════

def _format_summary(data: dict) -> str:
    """Build a human-readable bulleted summary from extracted invoice data."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("  INVOICE PROCESSING NOTIFICATION")
    lines.append("=" * 60)
    lines.append("")

    # Header
    lines.append("VENDOR & INVOICE DETAILS")
    lines.append(f"  • Vendor:           {data.get('vendor_name', 'N/A')}")
    lines.append(f"  • Invoice #:        {data.get('invoice_number', 'N/A')}")
    lines.append(f"  • Invoice Date:     {data.get('invoice_date', 'N/A')}")
    lines.append(f"  • Due Date:         {data.get('due_date', 'N/A')}")
    lines.append(f"  • Payment Terms:    {data.get('payment_terms', 'N/A')}")
    lines.append(f"  • Currency:         {data.get('currency', 'N/A')}")
    lines.append(f"  • Customer PO #:    {data.get('customer_po_number', 'N/A')}")
    lines.append("")

    # Financials
    lines.append("FINANCIAL SUMMARY")
    lines.append(f"  • Subtotal:         {data.get('subtotal', 0):.2f}")
    for tax in data.get("taxes", []):
        label = f"{tax.get('tax_type', '')} ({tax.get('jurisdiction', '')})"
        lines.append(f"  • {label}:  {tax.get('rate', '')}  →  {tax.get('amount', 0):.2f}")
    lines.append(f"  • TOTAL DUE:        {data.get('total_due', 0):.2f}")
    lines.append("")

    # Line Items
    items = data.get("line_items", [])
    if items:
        lines.append("LINE ITEMS")
        lines.append(f"  {'SKU':<15} {'Description':<35} {'Qty':>6} {'Unit $':>10} {'Total':>12}")
        lines.append("  " + "-" * 80)
        for item in items:
            lines.append(
                f"  {item.get('sku', ''):<15} "
                f"{item.get('description', ''):<35} "
                f"{item.get('quantity', 0):>6.0f} "
                f"{item.get('unit_price', 0):>10.2f} "
                f"{item.get('line_total', 0):>12.2f}"
            )
        lines.append("")

    # Ship-To
    locations = data.get("ship_to_locations", [])
    if locations:
        lines.append("SHIP-TO LOCATIONS")
        for loc in locations:
            lines.append(f"  ▸ {loc.get('site_name', 'N/A')}")
            lines.append(f"    {loc.get('address', '')}, {loc.get('city', '')}, "
                         f"{loc.get('province_or_state', '')} {loc.get('postal_code', '')}")
            alloc = loc.get("allocated_items", [])
            if alloc:
                lines.append(f"    Items: {', '.join(alloc)}")
        lines.append("")

    # Notes
    notes = data.get("notes", [])
    if notes:
        lines.append("NOTES & SPECIAL INSTRUCTIONS")
        for note in notes:
            lines.append(f"  ⚠ {note}")
        lines.append("")

    lines.append("=" * 60)
    lines.append("  END OF NOTIFICATION")
    lines.append("=" * 60)
    return "\n".join(lines)


@function_tool
def send_cs_notification(extracted_invoice_json: str) -> str:
    """
    Generate and save notification files from extracted invoice data.

    Accepts the structured JSON output from the extraction tool and writes:
      1. output/cs_notification.txt  — human-readable bulleted summary
      2. output/ap_payload.json      — structured JSON for downstream ERP

    Args:
        extracted_invoice_json: JSON string of extracted invoice data
                                (matches InvoiceSchema).

    Returns:
        Confirmation message with paths to the generated files.
    """
    # Parse the input
    try:
        data = json.loads(extracted_invoice_json)
    except json.JSONDecodeError as exc:
        return f"ERROR: Could not parse invoice JSON — {exc}"

    # Validate against schema (best-effort)
    try:
        validated = InvoiceSchema.model_validate(data)
        data = validated.model_dump()
    except ValidationError as exc:
        # Proceed with raw data but warn
        print(f"[WARNING] Invoice data had validation issues: {exc}")

    # Ensure output directory exists
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Write human-readable summary
    summary = _format_summary(data)
    summary_path = OUTPUT_DIR / "cs_notification.txt"
    summary_path.write_text(summary, encoding="utf-8")

    # 2. Write structured JSON payload
    payload_path = OUTPUT_DIR / "ap_payload.json"
    payload_path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return (
        f"✅ Notification files generated successfully:\n"
        f"  • Summary:  {summary_path}\n"
        f"  • Payload:  {payload_path}\n"
        f"\n--- SUMMARY PREVIEW ---\n{summary}"
    )
