from decimal import Decimal

from main import _override_paid_supplier_invoice
from extract import normalize_invoice


def test_payment_made_with_vat_evidence_is_reclassified_as_paid_supplier_invoice():
    extracted = {
        "intent": "PAYMENT_MADE",
        "direction": "PAYMENT",
        "invoice_total": Decimal("242"),
        "tax_rate": Decimal("21"),
        "description": "Plumbing repair and maintenance",
        "counterparty_name": "plumber",
        "vat_evidence": True,
    }
    invoice = normalize_invoice(extracted)
    updated = _override_paid_supplier_invoice("I paid the plumber EUR 242 incl. 21% VAT", invoice, extracted)

    assert updated["intent"] == "INBOUND_INVOICE"
    assert updated["direction"] == "INBOUND"
    assert updated["document_type"] == "INVOICE"
    assert updated["payment_included"] is True
    assert updated["subtotal"] == "200.00"
    assert updated["total_tax"] == "42.00"
    assert updated["vendor_name"] == "plumber"
