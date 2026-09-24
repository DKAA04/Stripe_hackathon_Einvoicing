# InvoiceAgent

**A conversational e-invoicing and bookkeeping prototype.**

InvoiceAgent turns short invoice/payment descriptions or uploaded PDFs into structured records, account allocations, double-entry journal entries and a visible ledger. It demonstrates a useful separation: optional language-model extraction handles semantics, while monetary calculations and posting follow deterministic Python logic.

This is a hackathon prototype. It is not a certified accounting product or a guarantee of tax or Peppol compliance.

## What is implemented

- Text input with a local rule-based extractor and optional Gemini extraction.
- Text-PDF extraction with PyMuPDF; optional Gemini support for scanned PDFs.
- Belgian-style VAT calculations and PCMN account allocation.
- Journal construction, an in-memory ledger and invoice/credit-note payload previews.
- Optional e-invoice.be transmission, disabled by default.
- Tests covering extraction, bookkeeping, compliance logic, PDF uploads and API behavior.

## Processing flow

```text
Text / PDF → extraction → normalization → account allocation
                                          ├→ journal entries → in-memory ledger
                                          └→ document checks / payload preview
```

**Stack:** Python, FastAPI, PyMuPDF, Gemini (optional), HTTPX, HTML and JavaScript.

## Run locally

Use Python 3.11+ in a fresh environment without production credentials.

```bash
git clone https://github.com/DKAA04/Stripe_hackathon_Einvoicing.git
cd Stripe_hackathon_Einvoicing
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

On Windows PowerShell, activate with `.venv\Scripts\Activate.ps1`.

Open http://localhost:8000. For a local demonstration, leave `GOOGLE_API_KEY` unset and `CREATE_REAL_UBL` unset or `0`. Text extraction falls back to local rules and outbound documents are staged rather than sent.

Try a synthetic example: `I paid the plumber EUR 242 incl. 21% VAT.`

## Optional integrations

| Setting | Purpose |
| --- | --- |
| `GOOGLE_API_KEY` | Gemini text and scanned-PDF extraction; input may be sent to the provider |
| `GEMINI_MODEL` | Override the model used by the text extractor |
| `CREATE_REAL_UBL` | `1` enables the external transmission path; keep `0` for local demonstrations |
| `E_INVOICE_API_KEY` | Credential for e-invoice.be |
| `E_INVOICE_BASE_URL` | Override the external API endpoint |

Company and recipient master-data settings are read in [compliance.py](compliance.py). Use only approved sandbox identities and credentials for integration testing. Never commit actual invoices, bank details, API responses containing client information, or credentials.

## Checks

```bash
python -m pytest tests
```

Tests are included in the repository; passing tests do not establish regulatory compliance or successful live Peppol delivery.

## Known limitations

- The ledger and duplicate-send protection are in memory and reset on process restart.
- Rule-based extraction supports a limited input vocabulary; review extracted amounts and counterparties.
- The current external API client retries some certificate failures with TLS verification disabled. **Do not enable real transmission until this fallback is removed and certificate trust is configured correctly.**
- PDF upload handling, authentication, access controls and retention need hardening before a public deployment.
- Demo recipient overrides exist in the integration code; inspect them before any external-service test.

## Explore the implementation

| Area | Entry point |
| --- | --- |
| HTTP endpoints and orchestration | [main.py](main.py) |
| Extraction and normalization | [extract.py](extract.py), [pdf_extract.py](pdf_extract.py) |
| Account allocation and journal logic | [chart_of_accounts.py](chart_of_accounts.py), [bookkeeping.py](bookkeeping.py) |
| Document checks and integration | [compliance.py](compliance.py) |
| Test suite | [tests/](tests/) |
