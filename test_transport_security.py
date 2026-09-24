"""Transport regression tests; all HTTP responses are simulated."""
import httpx
import compliance


def test_certificate_failure_never_retries_without_verification(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "unit-test-placeholder")
    calls = []

    def fake_post(url, payload, headers, verify):
        calls.append(verify)
        if verify:
            raise httpx.ConnectError("CERTIFICATE_VERIFY_FAILED")
        return httpx.Response(201, json={"id": "test-document"})

    monkeypatch.setattr(compliance, "_post_json", fake_post)
    result = compliance.send_einvoice_document({"invoice_id": "synthetic-test"})
    assert calls == [True]
    assert result["ok"] is False
    assert result["tls_verify_disabled"] is False


def test_create_and_send_both_verify_certificates(monkeypatch):
    monkeypatch.setenv("E_INVOICE_API_KEY", "unit-test-placeholder")
    calls = []

    def fake_post(url, payload, headers, verify):
        calls.append((url, verify))
        return httpx.Response(201, json={"id": "test-document"})

    monkeypatch.setattr(compliance, "_post_json", fake_post)
    result = compliance.send_einvoice_document({"invoice_id": "synthetic-test"})
    assert result["ok"] is True
    assert len(calls) == 2
    assert all(verify for _, verify in calls)
