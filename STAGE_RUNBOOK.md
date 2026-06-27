# InvoiceAgent Stage Runbook

## 1. Start the app

```powershell
cd C:\Users\Usuario\einvoice-hack
python -m uvicorn main:app --reload --port 8000
```

Open:

```text
http://localhost:8000
```

Keep `CREATE_REAL_UBL=0` for dry runs. Set `CREATE_REAL_UBL=1` only when you intentionally want to spend e-invoice.be sandbox credits.

## 2. Exact demo sequence

1. Click `Supplier bill: plumber`.
   - Message: `I paid the plumber EUR 242 incl. 21% VAT`
   - Expected: account `611 Maintenance and repairs`, VAT `42.00`, two journal entries, payable clears to zero.

2. Click `Supplier bill: telecom`.
   - Message: `I received an invoice from Proximus for EUR 121 incl. 21% VAT`
   - Expected: account `612 Utilities / energy / telecom`, payable remains open.

3. Click `Client invoice: website`.
   - Message: `Invoice Acme NV EUR 1,210 incl. 21% VAT for website services`
   - Expected: account `704 Services revenue`, customer receivable opens, output VAT posts to `451`.

4. Click `Client payment`.
   - Message: `Client paid invoice INV-001 by bank transfer`
   - Expected: bank increases, receivable clears.

5. Open the tabs:
   - `Compliance Proof`
   - `Journal`
   - `Trial Balance`
   - `VAT/Cash/AR/AP`
   - `Allocation`

## 3. What to say while demoing

Start:

> InvoiceAgent is e-invoicing that feels like WhatsApp, but behind every message it produces audit-grade proof: compliance state, PEPPOL evidence, deterministic VAT, Belgian account allocation, and balanced double-entry.

Supplier bill:

> I type one sentence: I paid the plumber EUR 242 including VAT. The system recognizes this is not just a cash movement. It first books the supplier invoice on accrual accounting, then posts the payment clearing the payable.

Accounting proof:

> Notice the allocation: it did not dump everything into a generic 600 account. It matched plumber, repair, and maintenance to Belgian PCMN-style account 611. VAT is computed deterministically: 200 net, 42 input VAT, 242 gross.

Compliance proof:

> In demo mode we do not spend e-invoice.be credits. The screen says that honestly. If real mode is enabled, this same pipeline attempts sandbox UBL creation and validation and shows the doc ID or the error.

Books:

> The judge can inspect journal lines, the running trial balance, VAT position, cash movement, open payables, open receivables, and the books balanced badge.

Close:

> The LLM can help understand the sentence, but it never does the money. VAT, account mapping, journal entries, and balances are deterministic Python.

## 4. Fallback if real UBL fails

If `CREATE_REAL_UBL=1` and e-invoice.be fails:

1. Keep the UI open.
2. Point to `Compliance Proof`.
3. Say:

> The API failure is shown, not hidden. InvoiceAgent continues safely: it still computes VAT, allocates the Belgian account, posts balanced books, and preserves audit evidence. This is the stage-safe behavior we want in production too.

If needed, switch back to demo mode:

```powershell
$env:CREATE_REAL_UBL="0"
python -m uvicorn main:app --reload --port 8000
```

## 5. Final 5-minute pitch skeleton

1. Problem: e-invoicing is becoming mandatory, but SMEs do not want accounting software complexity.
2. Product: InvoiceAgent turns a chat sentence or PDF into PEPPOL-ready invoice data and real bookkeeping.
3. Demo: run plumber, telecom, website invoice, client payment.
4. Differentiator: deterministic Belgian PCMN allocation, VAT, double-entry, and trial balance proof.
5. Compliance: e-invoice.be sandbox integration is explicit, honest, and stage-safe.
6. Business value: fewer manual bookings, fewer VAT mistakes, faster invoice workflows, accountant-ready ledger.
7. Close: WhatsApp-simple input, audit-grade output.
