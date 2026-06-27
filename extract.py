"""Text/PDF intent extraction with deterministic normalization."""
from __future__ import annotations

import json
import os
import re
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from bookkeeping import money, money_dict

MY_COMPANY = {
    "name": "DemoCo BV",
    "tax_id": "BE0999970129",
    "company_id": "0999970129",
    "address": "Wetstraat 1, 1000 Brussels",
    "peppol_id": "0208:0999970129",
}

DEFAULT_COUNTERPARTY = {
    "name": "Acme NV",
    "tax_id": "BE0987654394",
    "address": "Grote Markt 5, 2000 Antwerpen",
}

_COUNTER = {"n": 0}


def reset_counter() -> None:
    _COUNTER["n"] = 0


def _next_invoice_id() -> str:
    _COUNTER["n"] += 1
    return f"INV-{date.today().strftime('%Y%m%d')}-{_COUNTER['n']:03d}"


def _parse_amounts(message: str) -> list[Decimal]:
    text = re.sub(r"\bINV-\d[\w-]*\b", " ", message.replace("\u20ac", " "), flags=re.IGNORECASE)
    matches = re.findall(r"(?<![A-Z])\b\d{1,3}(?:[.,]\d{3})+(?:[.,]\d{1,2})?|\b\d+(?:[.,]\d{1,2})?", text, re.IGNORECASE)
    amounts: list[Decimal] = []
    for raw in matches:
        cleaned = raw
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(",", "")
        elif "," in cleaned and len(cleaned.rsplit(",", 1)[1]) == 3:
            cleaned = cleaned.replace(",", "")
        elif "," in cleaned:
            cleaned = cleaned.replace(",", ".")
        try:
            value = money(cleaned)
        except Exception:
            continue
        if value > 0 and value not in (Decimal("21.00"), Decimal("6.00"), Decimal("12.00")):
            amounts.append(value)
    return amounts


def canonicalize_vat_rate(value: object) -> Decimal:
    """Return a VAT rate as a decimal fraction: 21%/21 -> 0.21."""
    if value is None or value == "":
        value = 21
    if isinstance(value, str):
        value = value.strip().replace("%", "")
    try:
        rate = Decimal(str(value))
    except (InvalidOperation, ValueError):
        rate = Decimal("21")
    if rate > Decimal("1"):
        rate = rate / Decimal("100")
    return rate


def compute_vat_amounts(amount: object, rate: object, tax_inclusive: bool = True) -> tuple[Decimal, Decimal, Decimal]:
    vat_rate = canonicalize_vat_rate(rate)
    base_amount = money(amount or 0)
    if not base_amount:
        return Decimal("0.00"), Decimal("0.00"), Decimal("0.00")
    if tax_inclusive:
        gross = base_amount
        vat = money(gross * vat_rate / (Decimal("1") + vat_rate))
        net = money(gross - vat)
    else:
        net = base_amount
        vat = money(net * vat_rate)
        gross = money(net + vat)
    return net, vat, gross


def _counterparty(message: str) -> str | None:
    patterns = [
        r"credit\s+note\s+to\s+([A-Z][\w .&-]+?)(?:\s+for|\s+EUR|\s+\d|$)",
        r"from\s+([A-Z][\w .&-]+?)(?:\s+for|\s+EUR|\s+\d|$)",
        r"invoice\s+([A-Z][\w .&-]+?)(?:\s+EUR|\s+\d|\s+for|$)",
        r"paid\s+the\s+([a-z][\w .&-]+?)(?:\s+EUR|\s+\d|\s+for|$)",
        r"paid\s+([A-Z][\w .&-]+?)(?:\s+EUR|\s+\d|\s+for|$)",
    ]
    for pattern in patterns:
        match = re.search(pattern, message)
        if match:
            counterparty = match.group(1).strip()
            if re.match(r"^(INV-\d|EUR\b)", counterparty, re.IGNORECASE):
                continue
            titled = counterparty.title()
            return re.sub(r"\b(Nv|Bv|Sa|Ltd|Gmbh)\b", lambda m: m.group(1).upper(), titled)
    return None


def _description(message: str) -> str:
    lower = message.lower()
    if "proximus" in lower:
        return "Telecom and internet services"
    if "plumber" in lower or "plumbing" in lower:
        return "Plumbing repair and maintenance"
    if "website" in lower:
        return "Website services"
    if "software" in lower or "subscription" in lower:
        return "Software subscription"
    if "bank transfer" in lower or "paid invoice" in lower:
        return "Bank transfer settlement"
    match = re.search(r"for\s+(.+)$", message, re.IGNORECASE)
    return match.group(1).strip() if match else "Goods/services"


def naive_extract(message: str) -> dict:
    lower = message.lower()
    has_vat_invoice_clue = "vat" in lower or "incl" in lower or "invoice from" in lower
    if "credit note" in lower and any(term in lower for term in ("issue", "send", "to ")):
        intent = "OUTBOUND_CREDIT_NOTE"
        direction = "OUTBOUND"
    elif "credit note" in lower and any(term in lower for term in ("received", "from ")):
        intent = "INBOUND_CREDIT_NOTE"
        direction = "INBOUND"
    elif any(term in lower for term in ("client paid", "customer paid", "received payment")):
        intent = "PAYMENT_RECEIVED"
        direction = "PAYMENT"
    elif any(term in lower for term in ("i paid invoice", "we paid invoice", "paid invoice")) and not has_vat_invoice_clue:
        intent = "PAYMENT_MADE"
        direction = "PAYMENT"
    elif any(term in lower for term in ("i paid", "we paid", "paid the", "paid ")) and not has_vat_invoice_clue:
        intent = "PAYMENT_MADE"
        direction = "PAYMENT"
    elif any(term in lower for term in ("i paid", "we paid", "paid the", "paid ")) and has_vat_invoice_clue:
        intent = "INBOUND_INVOICE"
        direction = "INBOUND"
    elif any(term in lower for term in ("received an invoice", "bill from", "supplier invoice")):
        intent = "INBOUND_INVOICE"
        direction = "INBOUND"
    elif lower.startswith("invoice ") or any(term in lower for term in ("bill acme", "charge ", "sales invoice")):
        intent = "OUTBOUND_INVOICE"
        direction = "OUTBOUND"
    else:
        intent = "UNKNOWN"
        direction = "INBOUND"

    vat_match = re.search(r"(\d{1,2}(?:[.,]\d+)?)\s*%\s*vat", lower)
    rate = Decimal(vat_match.group(1)) if vat_match else Decimal("21")
    amounts = _parse_amounts(message)
    gross = amounts[0] if amounts else Decimal("0.00")
    tax_inclusive = not any(term in lower for term in ("excl", "excluding vat", "exclusive of vat", "plus vat"))
    invoice_ref = None
    ref_match = re.search(r"\b(INV-\d[\w-]*)\b", message, re.IGNORECASE)
    if ref_match:
        invoice_ref = ref_match.group(1).upper()

    return {
        "intent": intent,
        "direction": direction,
        "invoice_total": gross,
        "tax_rate": rate,
        "description": _description(message),
        "counterparty_name": _counterparty(message),
        "invoice_id": invoice_ref,
        "payment_included": intent == "INBOUND_INVOICE" and any(term in lower for term in ("i paid", "we paid", "paid the", "paid ")),
        "vat_evidence": bool(vat_match or "vat" in lower or "incl." in lower or "incl " in lower or "including vat" in lower),
        "tax_inclusive": tax_inclusive,
        "source": "regex",
    }


def llm_extract(message: str) -> dict:
    """Use an LLM for semantics only. Math and posting stay deterministic."""
    if not os.environ.get("GOOGLE_API_KEY"):
        return naive_extract(message)
    try:
        from google import genai

        client = genai.Client(api_key=os.environ["GOOGLE_API_KEY"])
        prompt = (
            "Extract invoice/payment data as strict JSON only. Keys: intent "
            "(INBOUND_INVOICE, OUTBOUND_INVOICE, PAYMENT_MADE, PAYMENT_RECEIVED, UNKNOWN), "
            "counterparty_name, description, gross, tax_rate, invoice_id. Do not calculate VAT.\n"
            f"Message: {message}"
        )
        response = client.models.generate_content(model=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"), contents=prompt)
        text = response.text.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(text)
        fallback = naive_extract(message)
        return {
            "intent": str(data.get("intent") or fallback["intent"]).upper(),
            "direction": fallback["direction"],
            "invoice_total": money(data.get("gross") or fallback["invoice_total"]),
            "tax_rate": canonicalize_vat_rate(data.get("tax_rate") or fallback["tax_rate"]),
            "description": data.get("description") or fallback["description"],
            "counterparty_name": data.get("counterparty_name") or fallback["counterparty_name"],
            "invoice_id": data.get("invoice_id") or fallback.get("invoice_id"),
            "payment_included": bool(fallback.get("payment_included")),
            "vat_evidence": bool(fallback.get("vat_evidence")),
            "tax_inclusive": bool(fallback.get("tax_inclusive", True)),
            "source": "llm",
        }
    except Exception:
        return naive_extract(message)


def normalize_invoice(extracted: dict) -> dict:
    intent = str(extracted.get("intent") or "UNKNOWN").upper()
    direction = str(extracted.get("direction") or "").upper()
    if intent in ("INBOUND_INVOICE", "INBOUND_CREDIT_NOTE"):
        direction = "INBOUND"
    elif intent in ("OUTBOUND_INVOICE", "OUTBOUND_CREDIT_NOTE"):
        direction = "OUTBOUND"
    elif intent in ("PAYMENT_MADE", "PAYMENT_RECEIVED"):
        direction = "PAYMENT"
    elif direction not in ("INBOUND", "OUTBOUND", "PAYMENT"):
        direction = "INBOUND"

    rate = canonicalize_vat_rate(extracted.get("tax_rate") or 21)
    amount = money(extracted.get("invoice_total") or 0)
    if amount and intent not in ("PAYMENT_MADE", "PAYMENT_RECEIVED"):
        net, vat, gross = compute_vat_amounts(amount, rate, bool(extracted.get("tax_inclusive", True)))
    else:
        net = amount
        gross = amount
        vat = Decimal("0.00")

    if extracted.get("counterparty_name"):
        counterparty = extracted["counterparty_name"]
    elif intent == "PAYMENT_MADE":
        counterparty = "supplier"
    elif intent == "PAYMENT_RECEIVED":
        counterparty = "client"
    else:
        counterparty = DEFAULT_COUNTERPARTY["name"]
    invoice_id = extracted.get("invoice_id") or _next_invoice_id()
    description = extracted.get("description") or "Goods/services"

    invoice = {
        "intent": intent,
        "direction": direction,
        "document_type": "CREDIT_NOTE" if "CREDIT_NOTE" in intent else "INVOICE" if "INVOICE" in intent else "PAYMENT",
        "state": "DRAFT",
        "invoice_id": invoice_id,
        "invoice_date": date.today().isoformat(),
        "due_date": (date.today() + timedelta(days=30)).isoformat(),
        "currency": "EUR",
        "tax_code": "S" if vat else "O",
        "tax_rate": money_dict(rate),
        "description": description,
        "counterparty_name": counterparty,
        "items": [{
            "description": description,
            "quantity": 1,
            "unit_price": money_dict(net),
            "amount": money_dict(net),
            "tax_rate": money_dict(rate),
            "tax": money_dict(vat),
        }],
        "subtotal": money_dict(net),
        "total_tax": money_dict(vat),
        "invoice_total": money_dict(gross),
        "amount_due": money_dict(gross),
        "extraction_source": extracted.get("source", "regex"),
        "payment_included": bool(extracted.get("payment_included")),
        "vat_evidence": bool(extracted.get("vat_evidence")),
    }

    if direction == "OUTBOUND":
        invoice.update({
            "vendor_name": MY_COMPANY["name"],
            "vendor_tax_id": MY_COMPANY["tax_id"],
            "vendor_address": MY_COMPANY["address"],
            "customer_name": counterparty,
            "customer_tax_id": DEFAULT_COUNTERPARTY["tax_id"],
            "customer_address": DEFAULT_COUNTERPARTY["address"],
        })
    else:
        invoice.update({
            "vendor_name": counterparty,
            "vendor_tax_id": DEFAULT_COUNTERPARTY["tax_id"],
            "vendor_address": DEFAULT_COUNTERPARTY["address"],
            "customer_name": MY_COMPANY["name"],
            "customer_tax_id": MY_COMPANY["tax_id"],
            "customer_address": MY_COMPANY["address"],
        })
    return invoice
