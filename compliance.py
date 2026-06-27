"""Generic e-invoice/UBL compliance decision engine."""
from __future__ import annotations

import os
from decimal import Decimal
from typing import Iterable

import httpx

from bookkeeping import money, money_dict

SENT_DOCUMENTS: dict[str, dict] = {}
DEMO_CUSTOMER_DEFAULTS = {
    "name": "Acme NV",
    "tax_id": "BE0999970129",
    "address": "Wetstraat 1, 1000 Brussels",
    "peppol_id": "0208:0999970129",
}


def create_real_ubl_enabled() -> bool:
    return os.environ.get("CREATE_REAL_UBL", "0").strip() == "1"


def reset_sent_documents() -> None:
    SENT_DOCUMENTS.clear()


def _api_key() -> str | None:
    return os.environ.get("E_INVOICE_API_KEY") or os.environ.get("EINVOICE_API_KEY")


def _base_url() -> str:
    return (os.environ.get("E_INVOICE_BASE_URL") or os.environ.get("EINVOICE_BASE_URL") or "https://api.e-invoice.be").rstrip("/")


def _demo_customer_config() -> dict:
    return {
        "name": os.environ.get("DEMO_CUSTOMER_NAME") or DEMO_CUSTOMER_DEFAULTS["name"],
        "tax_id": os.environ.get("DEMO_CUSTOMER_VAT_ID") or DEMO_CUSTOMER_DEFAULTS["tax_id"],
        "address": os.environ.get("DEMO_CUSTOMER_ADDRESS") or DEMO_CUSTOMER_DEFAULTS["address"],
        "peppol_id": os.environ.get("DEMO_CUSTOMER_PEPPOL_ID") or os.environ.get("E_INVOICE_PEPPOL_ID") or os.environ.get("PEPPOL_ID") or DEMO_CUSTOMER_DEFAULTS["peppol_id"],
    }


def tenant_info() -> dict:
    return {
        "configured": bool(os.environ.get("E_INVOICE_API_KEY") or os.environ.get("EINVOICE_API_KEY")),
        "tenant_id": os.environ.get("E_INVOICE_TENANT_ID") or os.environ.get("EINVOICE_TENANT_ID"),
        "base_url": os.environ.get("E_INVOICE_BASE_URL") or os.environ.get("EINVOICE_BASE_URL"),
        "company_name": os.environ.get("E_INVOICE_COMPANY_NAME") or os.environ.get("COMPANY_NAME") or "DemoCo BV",
        "vat_id": os.environ.get("E_INVOICE_COMPANY_VAT_ID") or os.environ.get("COMPANY_VAT_ID") or "BE0999970129",
        "address": os.environ.get("E_INVOICE_COMPANY_ADDRESS") or os.environ.get("COMPANY_ADDRESS") or "Wetstraat 1, 1000 Brussels",
        "peppol_id": os.environ.get("E_INVOICE_PEPPOL_ID") or os.environ.get("PEPPOL_ID") or "0208:0999970129",
        "iban": os.environ.get("E_INVOICE_IBAN") or os.environ.get("COMPANY_IBAN") or "BE68539007547034",
    }


def _extract_external_doc_id(response: object) -> str | None:
    if not isinstance(response, dict):
        return None
    for key in ("id", "document_id", "uuid", "external_doc_id"):
        if response.get(key):
            return str(response[key])
    data = response.get("data")
    if isinstance(data, dict):
        for key in ("id", "document_id"):
            if data.get(key):
                return str(data[key])
    return None


def _parse_response(response: httpx.Response) -> object:
    try:
        return response.json()
    except ValueError:
        return response.text


def _post_json(url: str, payload: dict | None, headers: dict, verify: bool) -> httpx.Response:
    with httpx.Client(timeout=15.0, trust_env=False, verify=verify) as client:
        return client.post(url, json=payload, headers=headers)


def send_einvoice_document(payload: dict) -> dict:
    api_key = _api_key()
    if not api_key:
        return {
            "ok": False,
            "status_code": 0,
            "response": None,
            "external_doc_id": None,
            "error": "E_INVOICE_API_KEY is missing.",
        }

    create_url = f"{_base_url()}/api/documents/"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    tls_verify_disabled = False
    try:
        try:
            create_response = _post_json(create_url, payload, headers, True)
        except httpx.ConnectError as exc:
            if "CERTIFICATE_VERIFY_FAILED" not in str(exc):
                raise
            tls_verify_disabled = True
            create_response = _post_json(create_url, payload, headers, False)
        create_parsed = _parse_response(create_response)
        external_doc_id = _extract_external_doc_id(create_parsed)
        if not 200 <= create_response.status_code < 300:
            return {
                "ok": False,
                "phase": "create",
                "status_code": create_response.status_code,
                "response": create_parsed,
                "create_response": create_parsed,
                "send_response": None,
                "external_doc_id": None,
                "error": create_response.text or f"HTTP {create_response.status_code}",
                "tls_verify_disabled": tls_verify_disabled,
            }
        if not external_doc_id:
            return {
                "ok": False,
                "phase": "create",
                "status_code": create_response.status_code,
                "response": create_parsed,
                "create_response": create_parsed,
                "send_response": None,
                "external_doc_id": None,
                "error": "Document created but e-invoice.be did not return an external document id for sending.",
                "tls_verify_disabled": tls_verify_disabled,
            }

        send_url = f"{_base_url()}/api/documents/{external_doc_id}/send"
        send_response = _post_json(send_url, None, headers, not tls_verify_disabled)
        send_parsed = _parse_response(send_response)
        if 200 <= send_response.status_code < 300:
            return {
                "ok": True,
                "phase": "send",
                "status_code": send_response.status_code,
                "response": send_parsed,
                "create_response": create_parsed,
                "send_response": send_parsed,
                "external_doc_id": external_doc_id,
                "error": None,
                "tls_verify_disabled": tls_verify_disabled,
            }
        return {
            "ok": False,
            "phase": "send",
            "status_code": send_response.status_code,
            "response": send_parsed,
            "create_response": create_parsed,
            "send_response": send_parsed,
            "external_doc_id": external_doc_id,
            "error": send_response.text or f"HTTP {send_response.status_code}",
            "tls_verify_disabled": tls_verify_disabled,
        }
    except Exception as exc:
        return {
            "ok": False,
            "phase": "request",
            "status_code": 0,
            "response": None,
            "create_response": None,
            "send_response": None,
            "external_doc_id": None,
            "error": str(exc),
            "tls_verify_disabled": tls_verify_disabled,
        }


def _blank(value: object) -> bool:
    return value is None or value == "" or value == []


def _rate_percent(value: object) -> Decimal:
    rate = Decimal(str(value or "0"))
    if rate <= Decimal("1"):
        rate *= Decimal("100")
    return money(rate)


def _allocation_value(allocation: object, key: str, default: str = "") -> str:
    if isinstance(allocation, dict):
        return str(allocation.get(key) or default)
    return str(getattr(allocation, key, default) or default)


def _payload_items(invoice: dict, allocation: object | None) -> list[dict]:
    items = invoice.get("items") or []
    payload_items = []
    for item in items:
        if not isinstance(item, dict):
            continue
        payload_items.append({
            "description": item.get("description") or invoice.get("description") or "",
            "quantity": item.get("quantity") or 1,
            "unit_price": float(money(item.get("unit_price") or item.get("amount") or 0)),
            "tax_rate": float(_rate_percent(item.get("tax_rate") or invoice.get("tax_rate") or 0)),
            "account_code": _allocation_value(allocation, "account"),
            "account_name": _allocation_value(allocation, "account_name"),
        })
    return payload_items


def _tax_breakdown(invoice: dict) -> list[dict]:
    by_rate: dict[str, dict[str, Decimal]] = {}
    for item in invoice.get("items") or []:
        if not isinstance(item, dict):
            continue
        rate = money_dict(_rate_percent(item.get("tax_rate") or invoice.get("tax_rate") or 0))
        bucket = by_rate.setdefault(rate, {"taxable_amount": Decimal("0.00"), "tax_amount": Decimal("0.00")})
        bucket["taxable_amount"] += money(item.get("amount") or item.get("unit_price") or 0) * Decimal(str(item.get("quantity") or 1))
        bucket["tax_amount"] += money(item.get("tax") or 0)
    if not by_rate and money(invoice.get("total_tax")):
        rate = money_dict(_rate_percent(invoice.get("tax_rate") or 0))
        by_rate[rate] = {
            "taxable_amount": money(invoice.get("subtotal")),
            "tax_amount": money(invoice.get("total_tax")),
        }
    return [
        {
            "tax_rate": rate,
            "taxable_amount": money_dict(values["taxable_amount"]),
            "tax_amount": money_dict(values["tax_amount"]),
        }
        for rate, values in sorted(by_rate.items())
    ]


def _apply_demo_customer_override(payload: dict, direction: str, document_type: str) -> tuple[dict, str | None]:
    if direction != "OUTBOUND" or document_type not in {"INVOICE", "CREDIT_NOTE"}:
        return payload, None
    customer_name = str(payload.get("customer_name") or "").strip().lower()
    demo = _demo_customer_config()
    if customer_name and customer_name != demo["name"].lower():
        return payload, None
    updated = dict(payload)
    updated.update({
        "customer_name": demo["name"],
        "customer_tax_id": demo["tax_id"],
        "customer_address": demo["address"],
        "customer_peppol_id": demo["peppol_id"],
    })
    note = f"Sandbox recipient override: {demo['name']} routed to configured test Peppol ID {demo['peppol_id']}."
    return updated, note


def build_payload_preview(invoice: dict, company: dict, allocation: object | None = None) -> dict:
    document_type = str(invoice.get("document_type") or "UNKNOWN").upper()
    company_name = company.get("name") or company.get("company_name")
    company_peppol = company.get("peppol_id")
    payload = {
        "document_type": document_type,
        "invoice_id": invoice.get("invoice_id"),
        "invoice_date": invoice.get("invoice_date"),
        "due_date": invoice.get("due_date"),
        "currency": invoice.get("currency") or "EUR",
        "vendor_name": invoice.get("vendor_name"),
        "vendor_tax_id": invoice.get("vendor_tax_id"),
        "vendor_address": invoice.get("vendor_address"),
        "vendor_peppol_id": (invoice.get("vendor_peppol_id") or company_peppol) if invoice.get("vendor_name") == company_name else invoice.get("vendor_peppol_id"),
        "customer_name": invoice.get("customer_name"),
        "customer_tax_id": invoice.get("customer_tax_id"),
        "customer_address": invoice.get("customer_address"),
        "customer_peppol_id": (invoice.get("customer_peppol_id") or company_peppol) if invoice.get("customer_name") == company_name else invoice.get("customer_peppol_id"),
        "items": _payload_items(invoice, allocation),
        "tax_exclusive_total": money_dict(money(invoice.get("subtotal"))),
        "tax_total": money_dict(money(invoice.get("total_tax"))),
        "tax_inclusive_total": money_dict(money(invoice.get("invoice_total"))),
        "payable_amount": money_dict(money(invoice.get("amount_due") or invoice.get("invoice_total"))),
        "tax_breakdown": _tax_breakdown(invoice),
        "payment_means": {
            "iban": company.get("iban"),
            "payment_reference": invoice.get("payment_reference") or invoice.get("invoice_id"),
        },
    }
    payload, _ = _apply_demo_customer_override(payload, str(invoice.get("direction") or "UNKNOWN").upper(), document_type)
    return payload


def _missing(payload: dict, rules: Iterable[tuple[str, object]]) -> list[str]:
    return [name for name, value in rules if _blank(value)]


def _outbound_required_missing(payload: dict) -> list[str]:
    first_line = (payload.get("items") or [{}])[0]
    first_tax = (payload.get("tax_breakdown") or [{}])[0]
    return _missing(payload, [
        ("document_type", payload.get("document_type")),
        ("invoice_id", payload.get("invoice_id")),
        ("invoice_date", payload.get("invoice_date")),
        ("currency", payload.get("currency")),
        ("vendor_name", payload.get("vendor_name")),
        ("vendor_tax_id", payload.get("vendor_tax_id")),
        ("vendor_address", payload.get("vendor_address")),
        ("customer_name", payload.get("customer_name")),
        ("customer_tax_id_or_peppol_id", payload.get("customer_tax_id") or payload.get("customer_peppol_id")),
        ("customer_address", payload.get("customer_address")),
        ("items", payload.get("items")),
        ("line_description", first_line.get("description")),
        ("line_quantity", first_line.get("quantity")),
        ("line_net_unit_price", first_line.get("unit_price")),
        ("line_vat_rate", first_line.get("tax_rate")),
        ("tax_total", payload.get("tax_total")),
        ("tax_exclusive_total", payload.get("tax_exclusive_total")),
        ("tax_inclusive_total", payload.get("tax_inclusive_total")),
        ("payable_amount", payload.get("payable_amount")),
        ("tax_breakdown", payload.get("tax_breakdown")),
        ("tax_breakdown_rate", first_tax.get("tax_rate")),
        ("tax_breakdown_taxable_amount", first_tax.get("taxable_amount")),
        ("tax_breakdown_tax_amount", first_tax.get("tax_amount")),
    ])


def _inbound_missing(payload: dict) -> list[str]:
    return _missing(payload, [
        ("vendor_tax_id", payload.get("vendor_tax_id")),
        ("vendor_address", payload.get("vendor_address")),
        ("vendor_peppol_id", payload.get("vendor_peppol_id")),
    ])


def _base_result(invoice: dict, payload: dict | None, create_real_ubl: bool) -> dict:
    document_type = str(invoice.get("document_type") or "UNKNOWN").upper()
    direction = str(invoice.get("direction") or "UNKNOWN").upper()
    applicability = "applicable" if document_type in {"INVOICE", "CREDIT_NOTE"} else "not_applicable"
    return {
        "applicability": applicability,
        "reason": "",
        "mode": "demo" if not create_real_ubl else "real",
        "peppol_action": "sendable" if applicability == "applicable" else "not_applicable_payment",
        "status": "demo_staged" if applicability == "applicable" else "not_applicable",
        "direction": direction,
        "document_type": document_type,
        "payload_preview": payload,
        "missing_fields": [],
        "validation_messages": [],
        "transmission_attempted": False,
        "external_doc_id": None,
        "api_error": None,
        "api_status_code": None,
        "api_response": None,
        "tls_verify_disabled": False,
        "sandbox_recipient_override": None,
        "api_create_response": None,
        "api_send_response": None,
        "create_real_ubl": create_real_ubl,
        "ubl_available": False,
        "doc_id": None,
        "evidence": [],
        "validation": {"checked": True, "valid": True, "issues": []},
    }


def build_compliance_result(invoice: dict, company: dict, allocation: object | None = None, create_real_ubl: bool = False) -> dict:
    document_type = str(invoice.get("document_type") or "UNKNOWN").upper()
    payload = None if document_type == "PAYMENT" else build_payload_preview(invoice, company, allocation)
    result = _base_result(invoice, payload, create_real_ubl)
    document_type = result["document_type"]
    direction = result["direction"]
    sandbox_note = None
    if payload:
        demo = _demo_customer_config()
        if (
            direction == "OUTBOUND"
            and document_type in {"INVOICE", "CREDIT_NOTE"}
            and payload.get("customer_name") == demo["name"]
            and payload.get("customer_peppol_id") == demo["peppol_id"]
            and payload.get("customer_tax_id") == demo["tax_id"]
        ):
            sandbox_note = f"Sandbox recipient override: {demo['name']} routed to configured test Peppol ID {demo['peppol_id']}."
            result["sandbox_recipient_override"] = sandbox_note

    if document_type == "PAYMENT" or direction == "PAYMENT":
        reason = "Bank payments are not UBL/Peppol invoice documents."
        result.update({
            "mode": "not_applicable",
            "applicability": "not_applicable",
            "peppol_action": "not_applicable_payment",
            "status": "not_applicable",
            "reason": reason,
            "payload_preview": None,
            "validation_messages": [reason],
            "evidence": [reason],
        })
        return result

    if document_type not in {"INVOICE", "CREDIT_NOTE"}:
        reason = "Unsupported document type for UBL/Peppol compliance decision."
        result.update({
            "mode": "not_applicable",
            "status": "error",
            "applicability": "not_applicable",
            "peppol_action": "blocked_missing_data",
            "reason": reason,
            "validation_messages": [reason],
            "validation": {"checked": True, "valid": False, "issues": [reason]},
        })
        return result

    if direction == "INBOUND":
        missing = _inbound_missing(payload)
        reason = "Inbound supplier document staged for audit; no outbound Peppol transmission because DemoCo is not the seller."
        result.update({
            "mode": "demo" if not create_real_ubl else "real",
            "applicability": "applicable",
            "peppol_action": "inbound_evidence_only",
            "status": "inbound_staged",
            "reason": reason,
            "missing_fields": missing,
            "transmission_attempted": False,
            "validation_messages": ([sandbox_note] if sandbox_note else []) + [reason],
            "evidence": ([sandbox_note] if sandbox_note else []) + [reason],
        })
        return result

    if direction != "OUTBOUND":
        reason = "Direction is not OUTBOUND or INBOUND for an invoice-like document."
        result.update({
            "mode": "not_applicable",
            "status": "error",
            "peppol_action": "blocked_missing_data",
            "reason": reason,
            "validation_messages": [reason],
        })
        return result

    missing = _outbound_required_missing(payload)
    if create_real_ubl and not _api_key():
        reason = "Real Peppol transmission blocked because e-invoice.be API key is missing."
        result.update({
            "mode": "blocked",
            "status": "blocked_missing_api_key",
            "applicability": "applicable",
            "peppol_action": "blocked_missing_data",
            "reason": reason,
            "missing_fields": ["E_INVOICE_API_KEY"],
            "transmission_attempted": False,
            "validation_messages": [reason],
            "validation": {"checked": True, "valid": False, "issues": ["E_INVOICE_API_KEY"]},
            "evidence": [reason],
        })
        return result

    if create_real_ubl and missing:
        reason = "Real Peppol transmission blocked because required master data is missing."
        result.update({
            "mode": "blocked",
            "status": "blocked_missing_master_data",
            "applicability": "applicable",
            "peppol_action": "blocked_missing_data",
            "reason": reason,
            "missing_fields": missing,
            "transmission_attempted": False,
            "validation_messages": [reason],
            "validation": {"checked": True, "valid": False, "issues": missing},
            "evidence": [reason],
        })
        return result

    if not create_real_ubl:
        reason = "UBL-ready payload staged; real Peppol transmission disabled in demo mode."
        result.update({
            "mode": "demo",
            "status": "demo_staged",
            "applicability": "applicable",
            "peppol_action": "sendable",
            "reason": reason,
            "transmission_attempted": False,
            "validation_messages": [reason],
            "evidence": [reason],
        })
        return result

    invoice_id = str(payload.get("invoice_id") or "")
    if invoice_id in SENT_DOCUMENTS:
        sent = SENT_DOCUMENTS[invoice_id]
        reason = "This invoice was already sent; duplicate Peppol transmission prevented."
        result.update({
            "mode": "real",
            "status": "already_sent",
            "applicability": "applicable",
            "peppol_action": "sendable",
            "reason": reason,
            "transmission_attempted": False,
            "external_doc_id": sent.get("external_doc_id"),
            "doc_id": sent.get("external_doc_id"),
            "api_response": sent.get("api_response"),
            "validation_messages": [reason],
            "evidence": [reason],
        })
        return result

    result["transmission_attempted"] = True
    validation_messages = []
    if sandbox_note:
        validation_messages.append(sandbox_note)
    if payload.get("customer_peppol_id"):
        validation_messages.append("Customer Peppol ID not verified before transmission.")
    api_result = send_einvoice_document(payload)
    result["api_status_code"] = api_result.get("status_code")
    result["api_response"] = api_result.get("response")
    result["api_create_response"] = api_result.get("create_response")
    result["api_send_response"] = api_result.get("send_response")
    result["tls_verify_disabled"] = bool(api_result.get("tls_verify_disabled"))
    if api_result.get("ok"):
        doc_id = api_result.get("external_doc_id")
        reason = "Document sent through e-invoice.be Peppol API."
        result.update({
            "mode": "real",
            "status": "sent",
            "applicability": "applicable",
            "peppol_action": "sendable",
            "reason": reason,
            "external_doc_id": doc_id,
            "doc_id": doc_id,
            "ubl_available": bool(doc_id),
            "validation_messages": validation_messages + [reason],
            "evidence": ([reason] + (["TLS certificate verification failed in this environment; request was retried with verification disabled."] if api_result.get("tls_verify_disabled") else [])),
        })
        if doc_id:
            SENT_DOCUMENTS[invoice_id] = {"external_doc_id": doc_id, "api_response": api_result.get("response")}
    else:
        same_participant = payload.get("vendor_peppol_id") and payload.get("vendor_peppol_id") == payload.get("customer_peppol_id")
        send_phase = api_result.get("phase") == "send"
        reason = "Sandbox receiver rejected; sender and receiver may not be allowed to be the same participant." if send_phase and same_participant else "e-invoice.be API transmission failed."
        status = "send_error" if send_phase else "error"
        result.update({
            "mode": "real",
            "status": status,
            "applicability": "applicable",
            "peppol_action": "sendable",
            "reason": reason,
            "api_error": api_result.get("error") or str(api_result.get("response") or ""),
            "api_status_code": api_result.get("status_code"),
            "api_response": api_result.get("response"),
            "external_doc_id": None,
            "doc_id": None,
            "ubl_available": False,
            "validation_messages": validation_messages + [reason],
            "validation": {"checked": True, "valid": False, "issues": [api_result.get("error") or "API request failed"]},
            "evidence": ([reason] + (["TLS certificate verification failed in this environment; request was retried with verification disabled."] if api_result.get("tls_verify_disabled") else [])),
        })
    return result


def maybe_create_ubl(invoice: dict, company: dict | None = None, allocation: object | None = None) -> dict:
    if company is None:
        company = {
            "name": tenant_info()["company_name"],
            "tax_id": tenant_info()["vat_id"],
            "address": tenant_info()["address"],
            "peppol_id": tenant_info()["peppol_id"],
            "iban": tenant_info()["iban"],
        }
    return build_compliance_result(invoice, company, allocation, create_real_ubl_enabled())
