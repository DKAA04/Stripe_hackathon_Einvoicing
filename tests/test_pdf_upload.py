from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def setup_function():
    client.post("/reset")


def _pdf_bytes(text: str = "") -> bytes:
    import fitz

    doc = fitz.open()
    page = doc.new_page()
    if text:
        page.insert_text((72, 72), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _upload_pdf(text: str, filename: str = "invoice.pdf"):
    return client.post(
        "/chat/pdf",
        files={"file": (filename, _pdf_bytes(text), "application/pdf")},
    )


def test_text_based_supplier_pdf_extracts_and_uses_pipeline():
    text = """
    Invoice INV-2026-001
    Supplier: Proximus
    Customer: DemoCo BV
    Description: telecom and internet services
    Total EUR 121 incl. 21% VAT
    """
    response = _upload_pdf(text, "proximus.pdf")

    assert response.status_code == 200
    data = response.json()
    assert data["pdf_extraction"]["ok"] is True
    assert data["pdf_extraction"]["method"] == "pdf_text"
    assert data["invoice"]["invoice_total"] == "121.00"
    assert data["invoice"]["subtotal"] == "100.00"
    assert data["invoice"]["total_tax"] == "21.00"
    assert data["intent"] == "INBOUND_INVOICE"
    assert data["allocation"]["account"] == "612"
    assert len(data["journal_entries"]) == 1


def test_text_based_outbound_pdf_extracts_and_uses_pipeline():
    text = """
    Invoice Acme NV EUR 1210 incl. 21% VAT for website services
    Customer: Acme NV
    Vendor: DemoCo BV
    Due date: 2026-03-31
    IBAN: BE68539007547034
    """
    response = _upload_pdf(text, "acme.pdf")

    assert response.status_code == 200
    data = response.json()
    assert data["pdf_extraction"]["method"] == "pdf_text"
    assert data["intent"] == "OUTBOUND_INVOICE"
    assert data["invoice"]["invoice_total"] == "1210.00"
    assert data["allocation"]["account"] == "704"
    assert data["compliance"]["status"] == "demo_staged"


def test_empty_pdf_without_google_key_fails_honestly(monkeypatch):
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    response = client.post(
        "/chat/pdf",
        files={"file": ("empty.pdf", _pdf_bytes(""), "application/pdf")},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["intent"] == "UNKNOWN"
    assert data["pdf_extraction"]["ok"] is False
    assert data["pdf_extraction"]["method"] == "failed"
    assert "could not extract invoice data" in data["reply"].lower()
    assert "invoice" not in data or data.get("invoice") is None


def test_low_confidence_pdf_includes_warning():
    text = "Invoice EUR 121 incl. 21% VAT " + ("x " * 40)
    response = _upload_pdf(text, "weak.pdf")

    assert response.status_code == 200
    data = response.json()
    assert data["pdf_extraction"]["confidence"] in {"low", "medium"}
    if data["pdf_extraction"]["confidence"] == "low":
        assert data["pdf_extraction"]["warnings"]
