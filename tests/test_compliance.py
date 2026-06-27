from decimal import Decimal

from chart_of_accounts import allocate_account
from compliance import _extract_external_doc_id, build_compliance_result, reset_sent_documents
from extract import MY_COMPANY, normalize_invoice


def setup_function():
    reset_sent_documents()


def _outbound_invoice() -> tuple[dict, dict]:
    invoice = normalize_invoice({
        "intent": "OUTBOUND_INVOICE",
        "invoice_total": Decimal("1210"),
        "tax_rate": Decimal("21"),
        "description": "Website services",
        "counterparty_name": "Acme NV",
    })
    allocation = allocate_account(invoice).to_dict()
    return invoice, allocation


def test_outbound_demo_stages_without_api_call(monkeypatch):
    invoice, allocation = _outbound_invoice()

    def fail_send(payload):
        raise AssertionError("API should not be called in demo mode")

    monkeypatch.setattr("compliance.send_einvoice_document", fail_send)
    result = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=False)

    assert result["status"] == "demo_staged"
    assert result["payload_preview"]
    assert result["payload_preview"]["customer_name"] == "Acme NV"
    assert result["payload_preview"]["customer_tax_id"] == "BE0999970129"
    assert result["payload_preview"]["customer_address"] == "Wetstraat 1, 1000 Brussels"
    assert result["payload_preview"]["customer_peppol_id"] == "0208:0999970129"
    assert result["sandbox_recipient_override"] == "Sandbox recipient override: Acme NV routed to configured test Peppol ID 0208:0999970129."
    assert result["transmission_attempted"] is False


def test_external_document_id_parsing_handles_common_shapes():
    assert _extract_external_doc_id({"id": "a"}) == "a"
    assert _extract_external_doc_id({"document_id": "b"}) == "b"
    assert _extract_external_doc_id({"uuid": "c"}) == "c"
    assert _extract_external_doc_id({"external_doc_id": "d"}) == "d"
    assert _extract_external_doc_id({"data": {"id": "e"}}) == "e"
    assert _extract_external_doc_id({"data": {"document_id": "f"}}) == "f"


def test_outbound_real_peppol_blocks_when_api_key_missing(monkeypatch):
    invoice, allocation = _outbound_invoice()
    monkeypatch.delenv("E_INVOICE_API_KEY", raising=False)
    monkeypatch.delenv("EINVOICE_API_KEY", raising=False)

    result = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)

    assert result["status"] == "blocked_missing_api_key"
    assert result["transmission_attempted"] is False
    assert "E_INVOICE_API_KEY" in result["missing_fields"]


def test_outbound_real_peppol_blocks_when_customer_address_missing(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "test-key")
    invoice = normalize_invoice({
        "intent": "OUTBOUND_INVOICE",
        "invoice_total": Decimal("1210"),
        "tax_rate": Decimal("21"),
        "description": "Consulting services",
        "counterparty_name": "Globex NV",
    })
    allocation = allocate_account(invoice).to_dict()
    invoice["customer_address"] = ""

    result = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)

    assert result["applicability"] == "applicable"
    assert result["peppol_action"] == "blocked_missing_data"
    assert result["status"] == "blocked_missing_master_data"
    assert result["transmission_attempted"] is False
    assert "customer_address" in result["missing_fields"]
    assert result["reason"] == "Real Peppol transmission blocked because required master data is missing."


def test_outbound_real_peppol_sends_with_successful_api(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "test-key")
    invoice, allocation = _outbound_invoice()

    def fake_send(payload):
        assert payload["customer_peppol_id"] == "0208:0999970129"
        return {
            "ok": True,
            "status_code": 201,
            "response": {"state": "SENT"},
            "create_response": {"id": "doc-123"},
            "send_response": {"state": "SENT"},
            "external_doc_id": "doc-123",
            "error": None,
        }

    monkeypatch.setattr("compliance.send_einvoice_document", fake_send)
    result = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)

    assert result["status"] == "sent"
    assert result["transmission_attempted"] is True
    assert result["external_doc_id"] == "doc-123"
    assert result["api_response"] == {"state": "SENT"}


def test_outbound_real_peppol_records_failed_api(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "test-key")
    invoice, allocation = _outbound_invoice()

    def fake_send(payload):
        return {
            "ok": False,
            "status_code": 422,
            "response": {"detail": "invalid"},
            "external_doc_id": None,
            "error": "invalid payload",
        }

    monkeypatch.setattr("compliance.send_einvoice_document", fake_send)
    result = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)

    assert result["status"] == "error"
    assert result["transmission_attempted"] is True
    assert result["api_error"] == "invalid payload"
    assert result["api_status_code"] == 422


def test_outbound_send_rejecting_same_participant_is_send_error(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "test-key")
    invoice, allocation = _outbound_invoice()

    def fake_send(payload):
        assert payload["vendor_peppol_id"] == payload["customer_peppol_id"]
        return {
            "ok": False,
            "phase": "send",
            "status_code": 409,
            "response": {"detail": "sender and receiver cannot be the same participant"},
            "create_response": {"id": "doc-created"},
            "send_response": {"detail": "sender and receiver cannot be the same participant"},
            "external_doc_id": "doc-created",
            "error": "sender and receiver cannot be the same participant",
        }

    monkeypatch.setattr("compliance.send_einvoice_document", fake_send)
    result = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)

    assert result["status"] == "send_error"
    assert result["reason"] == "Sandbox receiver rejected; sender and receiver may not be allowed to be the same participant."
    assert result["api_error"] == "sender and receiver cannot be the same participant"


def test_duplicate_invoice_id_is_not_sent_twice(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "test-key")
    invoice, allocation = _outbound_invoice()
    calls = {"count": 0}

    def fake_send(payload):
        calls["count"] += 1
        return {
            "ok": True,
            "status_code": 201,
            "response": {"document_id": "doc-abc"},
            "external_doc_id": "doc-abc",
            "error": None,
        }

    monkeypatch.setattr("compliance.send_einvoice_document", fake_send)
    first = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)
    second = build_compliance_result(invoice, MY_COMPANY, allocation, create_real_ubl=True)

    assert first["status"] == "sent"
    assert second["status"] == "already_sent"
    assert second["external_doc_id"] == "doc-abc"
    assert second["transmission_attempted"] is False
    assert calls["count"] == 1


def test_inbound_and_payment_documents_do_not_call_api(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "test-key")

    def fail_send(payload):
        raise AssertionError("API should not be called")

    monkeypatch.setattr("compliance.send_einvoice_document", fail_send)
    inbound = normalize_invoice({
        "intent": "INBOUND_INVOICE",
        "invoice_total": Decimal("242"),
        "tax_rate": Decimal("21"),
        "description": "Plumber repair",
        "counterparty_name": "Plumber",
        "payment_included": True,
    })
    payment = normalize_invoice({
        "intent": "PAYMENT_RECEIVED",
        "invoice_total": Decimal("242"),
        "description": "Client paid invoice",
    })

    inbound_result = build_compliance_result(inbound, MY_COMPANY, allocate_account(inbound).to_dict(), create_real_ubl=True)
    payment_result = build_compliance_result(payment, MY_COMPANY, allocate_account(payment).to_dict(), create_real_ubl=True)

    assert inbound_result["status"] == "inbound_staged"
    assert inbound_result["peppol_action"] == "inbound_evidence_only"
    assert inbound_result["transmission_attempted"] is False
    assert inbound_result["payload_preview"]["customer_name"] == "DemoCo BV"
    assert inbound_result["payload_preview"].get("customer_peppol_id") == "0208:0999970129"
    assert inbound_result["sandbox_recipient_override"] is None
    assert payment_result["status"] == "not_applicable"
    assert payment_result["payload_preview"] is None
    assert payment_result["sandbox_recipient_override"] is None
