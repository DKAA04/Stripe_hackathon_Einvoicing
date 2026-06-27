# InvoiceAgent

Chat-first e-invoicing and accounting automation prototype for Belgian-style VAT, PCMN account allocation, double-entry journals, and Peppol/UBL compliance proof.

## Run Locally

```powershell
cd C:\Users\Usuario\einvoice-hack
$env:PYTHONPATH='.'
python -m uvicorn main:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

## PDF Invoice Upload

PDF upload now performs real extraction. It does not create fake invoice data from the filename or a hardcoded amount.

- Text-based PDFs work locally through PyMuPDF (`pymupdf`).
- Scanned/image-only PDFs require `GOOGLE_API_KEY` for Gemini PDF/vision extraction.
- If extraction fails, the UI shows a clear failure and asks the user to upload a text-based invoice PDF or type the invoice details.
- For the best demo PDF, use visible text with supplier/customer, invoice number, total amount, VAT rate, and description.

Example text that extracts cleanly:

```text
Invoice INV-2026-001
Supplier: Proximus
Customer: DemoCo BV
Description: telecom and internet services
Total EUR 121 incl. 21% VAT
```

## Real Peppol Sending Through e-invoice.be

By default, outbound invoices and credit notes are staged only. To enable real e-invoice.be Peppol transmission:

```powershell
$env:CREATE_REAL_UBL="1"
$env:E_INVOICE_API_KEY="..."
$env:E_INVOICE_BASE_URL="https://api.e-invoice.be"
$env:E_INVOICE_COMPANY_NAME="DemoCo BV"
$env:E_INVOICE_COMPANY_VAT_ID="BE0999970129"
$env:E_INVOICE_COMPANY_ADDRESS="Wetstraat 1, 1000 Brussels"
$env:E_INVOICE_PEPPOL_ID="0208:0999970129"
$env:E_INVOICE_IBAN="BE68539007547034"
```

Use an outbound invoice or outbound credit note with complete customer master data, including `customer_name`, `customer_address`, and either `customer_tax_id` or `customer_peppol_id`.

The Compliance Proof tab should show:

- Status: `Sent through e-invoice.be`
- Transmission attempted: `Yes`
- External document ID: populated
- API response preview: visible

Troubleshooting notes:

- The API client ignores ambient `HTTP_PROXY` / `HTTPS_PROXY` variables because local dev environments may point them at a dead proxy.
- If Python cannot validate the e-invoice.be TLS chain in the local Windows environment, the client retries once with TLS verification disabled and exposes `tls_verify_disabled=true` in Compliance Proof.
- Belgian customer/vendor VAT numbers must pass Belgian checksum validation. The built-in Acme demo VAT ID is `BE0987654394`.
- For sandbox demos, outbound `Acme NV` invoices are routed to the configured sandbox receiver:
  - `DEMO_CUSTOMER_NAME=Acme NV`
  - `DEMO_CUSTOMER_VAT_ID=BE0999970129`
  - `DEMO_CUSTOMER_ADDRESS=Wetstraat 1, 1000 Brussels`
  - `DEMO_CUSTOMER_PEPPOL_ID=0208:0999970129`
  If these env vars are absent, the same defaults are used so the hackathon Acme invoice can be created and sent through the sandbox access point.

Inbound supplier invoices are never sent as DemoCo. Bank payments are not UBL/Peppol invoice documents and are marked not applicable.

Duplicate protection is in memory: if the same `invoice_id` has already been sent successfully, a second attempt returns `already_sent` and does not call the API again.
