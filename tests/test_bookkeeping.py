from decimal import Decimal

import pytest

from bookkeeping import Ledger, invoice_to_journal, invoice_to_journal_entries, money
from chart_of_accounts import allocate_account, get_account_meta
from extract import normalize_invoice


def test_pcmn_account_metadata_baseline_classifications():
    expectations = {
        "411": ("asset", "balance_sheet", "debit"),
        "451": ("liability", "balance_sheet", "credit"),
        "440": ("liability", "balance_sheet", "credit"),
        "400": ("asset", "balance_sheet", "debit"),
        "550": ("asset", "balance_sheet", "debit"),
        "611": ("expense", "income_statement", "debit"),
        "700": ("revenue", "income_statement", "credit"),
    }
    for code, expected in expectations.items():
        meta = get_account_meta(code)
        assert (meta.category, meta.statement, meta.normal_side) == expected


def test_plumber_paid_posts_invoice_and_payment_clears_payable():
    invoice = normalize_invoice({
        "intent": "INBOUND_INVOICE",
        "invoice_total": Decimal("242"),
        "tax_rate": Decimal("21"),
        "description": "Plumber repair and maintenance",
        "counterparty_name": "Plumber",
        "payment_included": True,
    })
    allocation = allocate_account(invoice)
    entries = invoice_to_journal_entries(invoice, allocation)
    ledger = Ledger()
    for entry in entries:
        ledger.post(entry)

    recognition = entries[0]
    assert allocation.account == "611"
    assert recognition.lines[0].account == "611"
    assert recognition.lines[0].account_name == "Maintenance and repairs"
    assert recognition.lines[0].debit == Decimal("200.00")
    assert recognition.lines[1].account == "411"
    assert recognition.lines[1].account_name == "VAT recoverable / input VAT"
    assert recognition.lines[1].debit == Decimal("42.00")
    assert recognition.lines[2].account == "440"
    assert recognition.lines[2].account_name == "Trade payables / Suppliers"
    assert recognition.lines[2].credit == Decimal("242.00")
    assert entries[1].lines[0].account == "440"
    assert entries[1].lines[0].account_name == "Trade payables / Suppliers"
    assert entries[1].lines[0].debit == Decimal("242.00")
    assert entries[1].lines[1].account == "550"
    assert entries[1].lines[1].account_name == "Bank"
    assert entries[1].lines[1].credit == Decimal("242.00")
    snapshot = ledger.snapshot()
    assert snapshot["payables_open"] == "0.00"
    assert snapshot["totals"] == {"debit": "484.00", "credit": "484.00"}
    assert snapshot["trial_balance"]["411"]["meta"]["category"] == "asset"
    assert snapshot["trial_balance"]["411"]["debit"] == "42.00"
    assert snapshot["trial_balance"]["440"]["meta"]["category"] == "liability"
    assert snapshot["trial_balance"]["440"]["debit"] == "242.00"
    assert snapshot["trial_balance"]["440"]["credit"] == "242.00"
    assert snapshot["trial_balance"]["440"]["balance"] == "0.00"
    assert snapshot["trial_balance"]["550"]["meta"]["category"] == "asset"
    assert snapshot["trial_balance"]["550"]["credit"] == "242.00"
    assert snapshot["trial_balance"]["550"]["balance"] == "-242.00"
    assert snapshot["trial_balance"]["611"]["meta"]["category"] == "expense"
    assert snapshot["trial_balance"]["611"]["debit"] == "200.00"
    assert snapshot["balance_sheet"]["assets"]["total"] == "-200.00"
    assert snapshot["balance_sheet"]["liabilities"]["total"] == "0.00"
    assert snapshot["balance_sheet"]["net_assets"] == "-200.00"
    assert snapshot["profit_loss"]["expenses"]["total"] == "200.00"
    assert snapshot["profit_loss"]["revenue"]["total"] == "0.00"
    assert snapshot["profit_loss"]["profit_loss"] == "-200.00"


def test_proximus_invoice_allocates_to_utilities_telecom():
    invoice = normalize_invoice({
        "intent": "INBOUND_INVOICE",
        "invoice_total": Decimal("121"),
        "tax_rate": Decimal("21"),
        "description": "Proximus telecom and internet",
        "counterparty_name": "Proximus",
    })
    allocation = allocate_account(invoice)
    entry = invoice_to_journal(invoice, allocation)

    assert allocation.account == "612"
    assert entry.lines[0].account == "612"
    assert entry.balanced


def test_outbound_website_service_invoice_uses_704_revenue_and_vat():
    invoice = normalize_invoice({
        "intent": "OUTBOUND_INVOICE",
        "invoice_total": Decimal("1210"),
        "tax_rate": Decimal("21"),
        "description": "Website services and design",
        "counterparty_name": "Acme NV",
    })
    allocation = allocate_account(invoice)
    entry = invoice_to_journal(invoice, allocation)
    accounts = {line.account: line for line in entry.lines}

    assert allocation.account == "704"
    assert accounts["400"].debit == Decimal("1210.00")
    assert accounts["704"].credit == Decimal("1000.00")
    assert accounts["451"].credit == Decimal("210.00")
    assert entry.balanced


def test_payment_received_clears_receivable():
    invoice = normalize_invoice({
        "intent": "OUTBOUND_INVOICE",
        "invoice_total": Decimal("1210"),
        "tax_rate": Decimal("21"),
        "description": "Website services",
        "counterparty_name": "Acme NV",
    })
    payment = normalize_invoice({
        "intent": "PAYMENT_RECEIVED",
        "invoice_total": Decimal("1210"),
        "description": "Client paid invoice INV-001 by bank transfer",
        "invoice_id": "INV-001",
    })
    ledger = Ledger()
    ledger.post(invoice_to_journal(invoice, allocate_account(invoice)))
    ledger.post(invoice_to_journal(payment, allocate_account(payment)))

    snapshot = ledger.snapshot()
    assert snapshot["receivables_open"] == "0.00"
    assert snapshot["cash_position"] == "1210.00"


def test_ledger_remains_balanced_after_mixed_postings():
    ledger = Ledger()
    purchase = normalize_invoice({
        "intent": "INBOUND_INVOICE",
        "invoice_total": "121.00",
        "tax_rate": "21",
        "description": "Proximus internet",
    })
    sale = normalize_invoice({
        "intent": "OUTBOUND_INVOICE",
        "invoice_total": "242.00",
        "tax_rate": "21",
        "description": "Consulting service",
    })
    payment = normalize_invoice({
        "intent": "PAYMENT_RECEIVED",
        "invoice_total": "242.00",
        "description": "Client paid invoice",
    })
    for invoice in (purchase, sale, payment):
        ledger.post(invoice_to_journal(invoice, allocate_account(invoice)))

    snapshot = ledger.snapshot()
    assert snapshot["balanced"] is True
    assert snapshot["account_count"] >= 6
    assert snapshot["vat_position"] == "21.00"


def test_money_values_round_to_cents():
    assert money("10.005") == Decimal("10.01")
    assert money(Decimal("10.004")) == Decimal("10.00")


def test_unknown_expense_falls_back_with_warning():
    invoice = normalize_invoice({
        "intent": "INBOUND_INVOICE",
        "invoice_total": "121.00",
        "tax_rate": "21",
        "description": "Unclear vendor cost",
    })
    allocation = allocate_account(invoice)

    assert allocation.account in ("615", "616")
    assert allocation.warning


def test_ledger_rejects_unbalanced_entry():
    invoice = normalize_invoice({
        "intent": "OUTBOUND_INVOICE",
        "invoice_total": Decimal("121.00"),
        "tax_rate": Decimal("21"),
        "description": "Website services",
    })
    entry = invoice_to_journal(invoice, allocate_account(invoice))
    entry.lines[0] = type(entry.lines[0])(entry.lines[0].account, entry.lines[0].account_name, money("120"), Decimal("0"))
    ledger = Ledger()
    with pytest.raises(ValueError):
        ledger.post(entry)
