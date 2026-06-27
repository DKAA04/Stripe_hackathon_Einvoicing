"""Real PDF invoice text extraction for uploaded invoice documents."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path


INVOICE_SIGNALS = (
    "invoice",
    "vat",
    "tva",
    "btw",
    "total",
    "amount due",
    "due date",
    "supplier",
    "vendor",
    "customer",
    "eur",
    "iban",
    "tax rate",
)


def _clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def _signal_count(text: str) -> int:
    lower = text.lower()
    return sum(1 for signal in INVOICE_SIGNALS if signal in lower)


def _confidence(text: str) -> str:
    signals = _signal_count(text)
    if len(text) > 160 and signals >= 3:
        return "high"
    if len(text) > 80 and signals >= 2:
        return "medium"
    return "low"


def extract_pdf_text(file_path: str) -> dict:
    warnings: list[str] = []
    try:
        import fitz
    except Exception as exc:
        return {
            "ok": False,
            "method": "failed",
            "text": "",
            "pages": 0,
            "confidence": "low",
            "warnings": ["PyMuPDF is not installed; install pymupdf to extract text-based PDFs."],
            "error": str(exc),
        }

    try:
        doc = fitz.open(file_path)
        pages = len(doc)
        parts = []
        for page in doc:
            parts.append(page.get_text("text"))
        doc.close()
        text = _clean_text("\n".join(parts))
        if len(text) <= 80:
            warnings.append("PDF text extraction was weak or empty.")
            return {
                "ok": False,
                "method": "pdf_text",
                "text": text,
                "pages": pages,
                "confidence": "low",
                "warnings": warnings,
                "error": "Extracted PDF text is too short to identify invoice data reliably.",
            }
        confidence = _confidence(text)
        if confidence == "low":
            warnings.append("Extracted PDF text has few invoice signals; review parsed result carefully.")
        return {
            "ok": True,
            "method": "pdf_text",
            "text": text,
            "pages": pages,
            "confidence": confidence,
            "warnings": warnings,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "failed",
            "text": "",
            "pages": 0,
            "confidence": "low",
            "warnings": warnings,
            "error": str(exc),
        }


def _extract_label(text: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"\b(?:{label_pattern})\s*[:\-]\s*([A-Z][\w .&-]+?)(?:\s+(?:Invoice|Customer|Buyer|Supplier|Vendor|Total|Amount|VAT|TVA|BTW|EUR|€|\d)|$)", text, re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def _extract_amount(text: str) -> str | None:
    patterns = [
        r"(?:amount due|total incl\.? vat|total including vat|total)\s*[:\-]?\s*(?:EUR|€)?\s*([\d.,]+)",
        r"(?:EUR|€)\s*([\d.,]+)",
        r"([\d.,]+)\s*(?:EUR|€)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _extract_rate(text: str) -> str:
    match = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*%\s*(?:VAT|TVA|BTW|tax)?", text, re.IGNORECASE)
    return match.group(1).replace(",", ".") if match else "21"


def _extract_description(text: str) -> str:
    lower = text.lower()
    if "website" in lower:
        return "website services"
    if "telecom" in lower or "internet" in lower or "proximus" in lower:
        return "telecom and internet services"
    if "plumber" in lower or "plumbing" in lower:
        return "plumbing repair and maintenance"
    match = re.search(r"(?:description|item|service)\s*[:\-]\s*(.+?)(?:\s+(?:Total|VAT|TVA|BTW|EUR|€)|$)", text, re.IGNORECASE)
    return match.group(1).strip() if match else "goods/services"


def _message_from_text(text: str) -> str:
    invoice_id = re.search(r"\b(INV-\d[\w-]*)\b", text, re.IGNORECASE)
    supplier = _extract_label(text, ("supplier", "vendor"))
    customer = _extract_label(text, ("customer", "buyer", "client"))
    amount = _extract_amount(text)
    rate = _extract_rate(text)
    description = _extract_description(text)
    lower = text.lower()

    if not amount:
        return text

    reference = f" {invoice_id.group(1).upper()}" if invoice_id else ""
    if supplier and "democo" not in supplier.lower():
        return f"I received an invoice{reference} from {supplier} for EUR {amount} incl. {rate}% VAT for {description}"
    if customer and "democo" not in customer.lower():
        return f"Invoice {customer} EUR {amount} incl. {rate}% VAT for {description}"
    if re.search(r"\binvoice\s+[A-Z][\w .&-]+\s+EUR\b", text):
        return text
    return f"I received an invoice{reference} for EUR {amount} incl. {rate}% VAT for {description}"


def _gemini_extract(file_path: str, existing_warnings: list[str]) -> dict:
    if not os.environ.get("GOOGLE_API_KEY"):
        return {
            "ok": False,
            "method": "failed",
            "text": "",
            "pages": 0,
            "confidence": "low",
            "warnings": existing_warnings + ["No GOOGLE_API_KEY configured for scanned PDF extraction."],
            "error": "PDF has no reliable embedded text and Gemini extraction is not configured.",
        }
    try:
        from google import genai

        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        uploaded = client.files.upload(file=Path(file_path))
        prompt = (
            "Extract readable invoice text and key fields from this PDF. Return JSON only with keys: "
            "document_type, direction, supplier_name, customer_name, invoice_id, invoice_date, due_date, "
            "currency, gross_total, vat_rates, vat_amounts, net_amounts, line_descriptions, iban, "
            "payment_reference, plain_text. Extract only; do not calculate VAT or journal entries."
        )
        response = client.models.generate_content(
            model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
            contents=[uploaded, prompt],
        )
        raw = response.text.strip().replace("```json", "").replace("```", "").strip()
        try:
            data = json.loads(raw)
            text = data.get("plain_text") or raw
        except Exception:
            text = raw
        text = _clean_text(text)
        if not text:
            raise ValueError("Gemini returned no invoice text.")
        return {
            "ok": True,
            "method": "gemini_pdf",
            "text": text,
            "message": _message_from_text(text),
            "pages": 0,
            "confidence": "medium",
            "warnings": existing_warnings,
            "error": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "failed",
            "text": "",
            "pages": 0,
            "confidence": "low",
            "warnings": existing_warnings,
            "error": str(exc),
        }


def extract_pdf_invoice_message(file_path: str) -> dict:
    extracted = extract_pdf_text(file_path)
    if extracted["ok"]:
        extracted["message"] = _message_from_text(extracted["text"])
        return extracted
    gemini = _gemini_extract(file_path, list(extracted.get("warnings") or []))
    if gemini["ok"]:
        return gemini
    return {
        **extracted,
        "method": "failed",
        "warnings": list(dict.fromkeys((extracted.get("warnings") or []) + (gemini.get("warnings") or []))),
        "error": gemini.get("error") or extracted.get("error"),
        "message": "",
    }
