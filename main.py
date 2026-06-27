from __future__ import annotations

import tempfile
from pathlib import Path
from dotenv import load_dotenv
from fastapi import Body, FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from bookkeeping import Ledger, invoice_to_journal_entries
from bookkeeping import money, money_dict
from chart_of_accounts import allocate_account, catalog
from compliance import build_compliance_result, create_real_ubl_enabled, reset_sent_documents, tenant_info
from demo_scenarios import DEMO_SCENARIOS
from extract import MY_COMPANY, canonicalize_vat_rate, compute_vat_amounts, llm_extract, naive_extract, normalize_invoice, reset_counter
from pdf_extract import extract_pdf_invoice_message

load_dotenv()

app = FastAPI(title="InvoiceAgent", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.mount("/static", StaticFiles(directory="static"), name="static")

LEDGER = Ledger()


@app.get("/")
def index():
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": "InvoiceAgent",
        "create_real_ubl": create_real_ubl_enabled(),
        "mode": "sandbox" if create_real_ubl_enabled() else "demo",
        "tenant": tenant_info(),
    }


def _reply(intent: str, invoice: dict, allocation: dict, compliance: dict, journals: list[dict]) -> str:
    amount = invoice["invoice_total"]
    vat = invoice["total_tax"]
    account = f"{allocation['account']} {allocation['account_name']}"
    status_text = {
        "demo_staged": "Outbound UBL-ready payload staged; real Peppol transmission is disabled",
        "inbound_staged": "Inbound supplier document staged; no outbound Peppol transmission",
        "not_applicable": "Not applicable: payment is not a UBL invoice",
        "blocked_missing_api_key": "Blocked: missing e-invoice.be API key",
        "blocked_missing_master_data": "Blocked: missing master data for real Peppol transmission",
        "sent": "Sent through e-invoice.be",
        "sent_pending_id": "Accepted by e-invoice.be; external document ID is pending",
        "already_sent": "Already sent; duplicate Peppol transmission prevented",
        "send_error": "Peppol send step failed",
        "error": "Peppol/API transmission failed",
    }.get(compliance.get("status"), compliance.get("reason") or "UBL/Peppol compliance decision recorded")
    if intent == "PAYMENT_RECEIVED":
        return f"Booked the client payment for EUR {amount}. Bank and receivables balance. {status_text}."
    if intent == "PAYMENT_MADE":
        return f"Booked the supplier payment for EUR {amount}. It settles payables through bank. {status_text}."
    if "CREDIT_NOTE" in intent:
        return f"Booked the credit note for EUR {amount} incl. EUR {vat} VAT and allocated it to {account}. {status_text}."
    if intent == "OUTBOUND_INVOICE":
        return f"Created the sales invoice for EUR {amount} incl. EUR {vat} VAT and posted revenue to {account}. {status_text}."
    if intent == "INBOUND_INVOICE":
        suffix = " Invoice and bank payment were posted separately." if len(journals) > 1 else ""
        return f"Booked the purchase invoice for EUR {amount} incl. EUR {vat} VAT and allocated it to {account}. {status_text}.{suffix}"
    return f"I could not classify the message confidently, but booked a balanced draft using {account}. {status_text}."


def _has_vat_evidence(message: str, invoice: dict, extracted: dict) -> bool:
    lower = message.lower()
    explicit_text = any(token in lower for token in ("vat", "incl.", "incl ", "including vat"))
    explicit_data = bool(extracted.get("vat_evidence") or invoice.get("vat_evidence"))
    computed_vat = money(invoice.get("total_tax")) > 0
    return explicit_text or explicit_data or computed_vat


def _override_paid_supplier_invoice(message: str, invoice: dict, extracted: dict) -> dict:
    intent = str(invoice.get("intent") or "").upper()
    payment_like = intent in {"PAYMENT_MADE", "SUPPLIER_PAYMENT", "PAYMENT"}
    if not payment_like or not _has_vat_evidence(message, invoice, extracted):
        return invoice

    rate = canonicalize_vat_rate(invoice.get("tax_rate") or extracted.get("tax_rate") or 21)
    amount = money(invoice.get("invoice_total") or extracted.get("invoice_total"))
    net, vat, gross = compute_vat_amounts(amount, rate, bool(extracted.get("tax_inclusive", True)))
    description = invoice.get("description") or extracted.get("description") or "Supplier expense"

    updated = dict(invoice)
    updated.update({
        "intent": "INBOUND_INVOICE",
        "direction": "INBOUND",
        "document_type": "INVOICE",
        "tax_code": "S" if vat else "O",
        "tax_rate": money_dict(rate),
        "subtotal": money_dict(net),
        "total_tax": money_dict(vat),
        "invoice_total": money_dict(gross),
        "amount_due": money_dict(gross),
        "description": description,
        "payment_included": True,
        "vat_evidence": True,
        "items": [{
            "description": description,
            "quantity": 1,
            "unit_price": money_dict(net),
            "amount": money_dict(net),
            "tax_rate": money_dict(rate),
            "tax": money_dict(vat),
        }],
    })
    counterparty = invoice.get("vendor_name") or invoice.get("counterparty_name") or extracted.get("counterparty_name") or "supplier"
    updated["counterparty_name"] = counterparty
    updated["vendor_name"] = counterparty
    return updated


def _process_message(message: str) -> dict:
    warnings: list[str] = []
    extracted = llm_extract(message)
    invoice = normalize_invoice(extracted)
    invoice = _override_paid_supplier_invoice(message, invoice, extracted)
    allocation = allocate_account(invoice)
    allocation_dict = allocation.to_dict()
    compliance = build_compliance_result(invoice, MY_COMPANY, allocation_dict, create_real_ubl_enabled())
    entries = invoice_to_journal_entries(invoice, allocation)
    for entry in entries:
        LEDGER.post(entry)
    journals = [entry.to_dict() for entry in entries]
    ledger = LEDGER.snapshot()
    intent = invoice["intent"]
    if allocation_dict.get("warning"):
        warnings.append(allocation_dict["warning"])
    return {
        "reply": _reply(intent, invoice, allocation_dict, compliance, journals),
        "intent": intent,
        "invoice": invoice,
        "allocation": allocation_dict,
        "compliance": compliance,
        "journal": journals[-1],
        "journal_entries": journals,
        "ledger": ledger,
        "warnings": warnings,
    }


@app.post("/chat")
def chat(payload: dict = Body(...)):
    message = (payload or {}).get("message", "").strip()
    if not message:
        return {
            "reply": "Send a sentence like: I paid the plumber EUR 242 incl. 21% VAT.",
            "intent": "UNKNOWN",
            "warnings": ["Empty message."],
        }
    return _process_message(message)


@app.post("/chat/pdf")
async def chat_pdf(file: UploadFile = File(...)):
    contents = await file.read()
    tmp = Path(tempfile.gettempdir()) / (file.filename or "invoice.pdf")
    tmp.write_bytes(contents)
    extraction = extract_pdf_invoice_message(str(tmp))
    metadata = {
        "ok": extraction.get("ok"),
        "method": extraction.get("method"),
        "confidence": extraction.get("confidence"),
        "pages": extraction.get("pages"),
        "text_preview": (extraction.get("text") or "")[:1000],
        "warnings": extraction.get("warnings") or [],
        "error": extraction.get("error"),
    }
    if not extraction.get("ok"):
        return {
            "reply": "I could not extract invoice data from this PDF. Please upload a text-based invoice PDF or type the invoice details.",
            "intent": "UNKNOWN",
            "pdf_extraction": metadata,
            "warnings": metadata["warnings"] + ([metadata["error"]] if metadata["error"] else []),
        }
    message = extraction.get("message") or extraction.get("text") or ""
    preview_extracted = llm_extract(message)
    preview_invoice = normalize_invoice(preview_extracted)
    preview_invoice = _override_paid_supplier_invoice(message, preview_invoice, preview_extracted)
    if preview_invoice.get("document_type") != "PAYMENT" and money(preview_invoice.get("invoice_total")) <= 0:
        return {
            "reply": "I extracted text from this PDF, but could not identify a usable invoice amount. Please upload a clearer text-based invoice PDF or type the invoice details.",
            "intent": "UNKNOWN",
            "pdf_extraction": metadata,
            "warnings": metadata["warnings"] + ["PDF text extraction did not identify a usable invoice total."],
        }
    result = _process_message(message)
    result["pdf_extraction"] = metadata
    result["warnings"].extend(metadata["warnings"])
    result["source_file"] = {"filename": file.filename, "bytes": len(contents)}
    return result


@app.get("/ledger")
def ledger():
    return LEDGER.snapshot()


@app.post("/reset")
def reset():
    LEDGER.reset()
    reset_counter()
    reset_sent_documents()
    return {"ok": True, "ledger": LEDGER.snapshot()}


@app.get("/chart-of-accounts")
def chart_of_accounts():
    return catalog()


@app.get("/demo/scenarios")
def demo_scenarios():
    return {"scenarios": DEMO_SCENARIOS}
