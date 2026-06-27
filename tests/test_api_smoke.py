from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def setup_function():
    client.post("/reset")


def test_health_defaults_to_demo_mode():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["create_real_ubl"] is False


def test_chat_books_plumber_to_specific_account_and_clears_payment():
    response = client.post("/chat", json={"message": "I paid the plumber EUR 242 incl. 21% VAT"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "INBOUND_INVOICE"
    assert data["invoice"]["document_type"] == "INVOICE"
    assert data["invoice"]["direction"] == "INBOUND"
    assert data["invoice"]["invoice_total"] == "242.00"
    assert data["invoice"]["tax_rate"] == "0.21"
    assert data["invoice"]["subtotal"] == "200.00"
    assert data["invoice"]["total_tax"] == "42.00"
    assert data["allocation"]["account"] == "611"
    assert len(data["journal_entries"]) == 2
    assert data["journal_entries"][0]["lines"][0]["account"] == "611"
    assert data["journal_entries"][0]["lines"][1]["account"] == "411"
    assert data["journal_entries"][0]["lines"][2]["account"] == "440"
    assert data["journal_entries"][1]["lines"][0]["account"] == "440"
    assert data["journal_entries"][1]["lines"][1]["account"] == "550"
    assert data["journal"]["balanced"] is True
    assert data["compliance"]["create_real_ubl"] is False
    assert data["compliance"]["applicability"] == "applicable"
    assert data["compliance"]["peppol_action"] == "inbound_evidence_only"
    assert data["compliance"]["status"] == "inbound_staged"
    assert data["compliance"]["transmission_attempted"] is False
    assert data["compliance"]["payload_preview"]["vendor_name"] == "Plumber"
    assert data["compliance"]["payload_preview"]["customer_name"] == "DemoCo BV"
    assert data["ledger"]["balanced"] is True
    assert data["ledger"]["totals"]["debit"] == data["ledger"]["totals"]["credit"]
    assert data["ledger"]["payables_open"] == "0.00"
    assert data["ledger"]["cash_position"] == "-242.00"
    assert data["warnings"] == []
    assert "EUR 42.00 VAT" in data["reply"]
    assert "Inbound supplier document staged; no outbound Peppol transmission" in data["reply"]
    assert "Invoice and bank payment were posted separately." in data["reply"]


def test_outbound_sales_invoice_stages_ubl_payload_in_demo_mode():
    response = client.post("/chat", json={"message": "Invoice Acme NV EUR 1,210 incl. 21% VAT for website"})
    assert response.status_code == 200
    data = response.json()
    payload = data["compliance"]["payload_preview"]
    assert data["intent"] == "OUTBOUND_INVOICE"
    assert data["invoice"]["document_type"] == "INVOICE"
    assert data["compliance"]["applicability"] == "applicable"
    assert data["compliance"]["mode"] == "demo"
    assert data["compliance"]["peppol_action"] == "sendable"
    assert data["compliance"]["status"] == "demo_staged"
    assert data["compliance"]["transmission_attempted"] is False
    assert payload["document_type"] == "INVOICE"
    assert payload["vendor_name"] == "DemoCo BV"
    assert payload["customer_name"] == "Acme NV"
    assert payload["customer_tax_id"] == "BE0999970129"
    assert payload["customer_address"] == "Wetstraat 1, 1000 Brussels"
    assert payload["customer_peppol_id"] == "0208:0999970129"
    assert payload["items"][0]["account_code"] == "704"
    assert payload["tax_exclusive_total"] == "1000.00"
    assert payload["tax_total"] == "210.00"
    assert payload["tax_inclusive_total"] == "1210.00"
    accounts = {line["account"]: line for line in data["journal_entries"][0]["lines"]}
    assert accounts["400"]["debit"] == "1210.00"
    assert accounts["704"]["credit"] == "1000.00"
    assert accounts["451"]["credit"] == "210.00"


def test_supplier_payment_without_vat_can_remain_payment_only():
    response = client.post("/chat", json={"message": "I paid invoice INV-001 by bank transfer"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "PAYMENT_MADE"
    assert data["invoice"]["document_type"] == "PAYMENT"
    assert data["compliance"]["applicability"] == "not_applicable"
    assert data["compliance"]["peppol_action"] == "not_applicable_payment"
    assert data["compliance"]["mode"] == "not_applicable"
    assert data["compliance"]["status"] == "not_applicable"
    assert data["compliance"]["payload_preview"] is None
    assert data["compliance"]["transmission_attempted"] is False
    assert "Not applicable: payment is not a UBL invoice" in data["reply"]
    assert len(data["journal_entries"]) == 1
    assert data["journal_entries"][0]["lines"][0]["account"] == "440"
    assert data["journal_entries"][0]["narrative"] == "Payment to supplier"


def test_proximus_invoice_stays_inbound_invoice_with_vat():
    response = client.post("/chat", json={"message": "I received an invoice from Proximus for EUR 121 incl. 21% VAT"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "INBOUND_INVOICE"
    assert data["invoice"]["invoice_total"] == "121.00"
    assert data["invoice"]["subtotal"] == "100.00"
    assert data["invoice"]["total_tax"] == "21.00"
    assert data["compliance"]["applicability"] == "applicable"
    assert data["compliance"]["peppol_action"] == "inbound_evidence_only"
    assert data["compliance"]["status"] == "inbound_staged"
    assert data["compliance"]["transmission_attempted"] is False
    assert data["compliance"]["payload_preview"]["vendor_name"] == "Proximus"
    assert data["compliance"]["payload_preview"]["customer_name"] == "DemoCo BV"
    assert data["allocation"]["account"] == "612"
    assert len(data["journal_entries"]) == 1


def test_client_payment_is_not_applicable_for_ubl():
    response = client.post("/chat", json={"message": "Client paid invoice INV-001 by bank transfer"})
    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "PAYMENT_RECEIVED"
    assert data["invoice"]["document_type"] == "PAYMENT"
    assert data["compliance"]["applicability"] == "not_applicable"
    assert data["compliance"]["peppol_action"] == "not_applicable_payment"
    assert data["compliance"]["status"] == "not_applicable"
    assert data["compliance"]["payload_preview"] is None


def test_outbound_credit_note_stages_ubl_payload():
    response = client.post("/chat", json={"message": "Issue a credit note to Acme NV for EUR 121 incl. 21% VAT"})
    assert response.status_code == 200
    data = response.json()
    payload = data["compliance"]["payload_preview"]
    assert data["intent"] == "OUTBOUND_CREDIT_NOTE"
    assert data["invoice"]["document_type"] == "CREDIT_NOTE"
    assert data["invoice"]["direction"] == "OUTBOUND"
    assert data["compliance"]["applicability"] == "applicable"
    assert data["compliance"]["peppol_action"] == "sendable"
    assert data["compliance"]["status"] == "demo_staged"
    assert payload["document_type"] == "CREDIT_NOTE"
    assert payload["vendor_name"] == "DemoCo BV"
    assert payload["customer_name"] == "Acme NV"
    assert payload["tax_exclusive_total"] == "100.00"
    assert payload["tax_total"] == "21.00"
    assert payload["tax_inclusive_total"] == "121.00"


def test_chart_and_demo_endpoints():
    chart = client.get("/chart-of-accounts").json()
    scenarios = client.get("/demo/scenarios").json()
    assert any(account["code"] == "611" for account in chart["accounts"])
    assert any(account["code"] == "704" for account in chart["accounts"])
    assert len(scenarios["scenarios"]) == 4
