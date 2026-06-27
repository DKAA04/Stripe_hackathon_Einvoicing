from extract import naive_extract, normalize_invoice


def test_extracts_outbound_invoice_with_thousands_separator():
    extracted = naive_extract("Invoice Acme NV EUR 1,210 incl. 21% VAT for website services")
    invoice = normalize_invoice(extracted)

    assert invoice["intent"] == "OUTBOUND_INVOICE"
    assert invoice["direction"] == "OUTBOUND"
    assert invoice["customer_name"] == "Acme NV"
    assert invoice["invoice_total"] == "1210.00"
    assert invoice["subtotal"] == "1000.00"
    assert invoice["total_tax"] == "210.00"


def test_extracts_proximus_inbound_invoice():
    extracted = naive_extract("I received an invoice from Proximus for EUR 121 incl. 21% VAT")
    invoice = normalize_invoice(extracted)

    assert invoice["intent"] == "INBOUND_INVOICE"
    assert invoice["vendor_name"] == "Proximus"
    assert invoice["subtotal"] == "100.00"
    assert invoice["total_tax"] == "21.00"


def test_extracts_plumber_inclusive_vat_amounts():
    extracted = naive_extract("I paid the plumber EUR 242 incl. 21% VAT")
    invoice = normalize_invoice(extracted)

    assert invoice["invoice_total"] == "242.00"
    assert invoice["tax_rate"] == "0.21"
    assert invoice["subtotal"] == "200.00"
    assert invoice["total_tax"] == "42.00"


def test_extracts_exclusive_vat_amounts():
    extracted = naive_extract("Invoice EUR 100 excl. 21% VAT")
    invoice = normalize_invoice(extracted)

    assert invoice["subtotal"] == "100.00"
    assert invoice["total_tax"] == "21.00"
    assert invoice["invoice_total"] == "121.00"


def test_paid_supplier_invoice_marks_payment_included():
    extracted = naive_extract("I paid the plumber EUR 242 incl. 21% VAT")
    invoice = normalize_invoice(extracted)

    assert invoice["intent"] == "INBOUND_INVOICE"
    assert invoice["payment_included"] is True


def test_payment_does_not_recompute_vat():
    extracted = naive_extract("Client paid invoice INV-001 by bank transfer")
    invoice = normalize_invoice(extracted)

    assert invoice["intent"] == "PAYMENT_RECEIVED"
    assert invoice["invoice_id"] == "INV-001"
    assert invoice["total_tax"] == "0.00"


def test_supplier_payment_without_vat_stays_payment_only():
    extracted = naive_extract("I paid invoice INV-001 by bank transfer")
    invoice = normalize_invoice(extracted)

    assert invoice["intent"] == "PAYMENT_MADE"
    assert invoice["direction"] == "PAYMENT"
    assert invoice["document_type"] == "PAYMENT"
    assert invoice["total_tax"] == "0.00"


def test_extracts_outbound_credit_note():
    extracted = naive_extract("Issue a credit note to Acme NV for EUR 121 incl. 21% VAT")
    invoice = normalize_invoice(extracted)

    assert invoice["intent"] == "OUTBOUND_CREDIT_NOTE"
    assert invoice["direction"] == "OUTBOUND"
    assert invoice["document_type"] == "CREDIT_NOTE"
    assert invoice["customer_name"] == "Acme NV"
    assert invoice["subtotal"] == "100.00"
    assert invoice["total_tax"] == "21.00"
