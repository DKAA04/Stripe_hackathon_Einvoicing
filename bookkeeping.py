"""Deterministic double-entry bookkeeping for the demo ledger."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from typing import Iterable

from chart_of_accounts import ACCOUNT_BY_CODE, Allocation, allocate_account, get_account_meta

CENT = Decimal("0.01")
ZERO = Decimal("0.00")


def money(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value.quantize(CENT, rounding=ROUND_HALF_UP)
    if value is None or value == "":
        return ZERO
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def money_dict(value: Decimal) -> str:
    return str(money(value))


@dataclass(frozen=True)
class JournalLine:
    account: str
    account_name: str
    debit: Decimal = ZERO
    credit: Decimal = ZERO

    def to_dict(self) -> dict:
        return {
            "account": self.account,
            "account_name": self.account_name,
            "debit": money_dict(self.debit),
            "credit": money_dict(self.credit),
        }


@dataclass
class JournalEntry:
    ref: str
    date: str
    intent: str
    narrative: str
    lines: list[JournalLine] = field(default_factory=list)

    @property
    def total_debit(self) -> Decimal:
        return money(sum((line.debit for line in self.lines), ZERO))

    @property
    def total_credit(self) -> Decimal:
        return money(sum((line.credit for line in self.lines), ZERO))

    @property
    def balanced(self) -> bool:
        return self.total_debit == self.total_credit

    def to_dict(self) -> dict:
        return {
            "ref": self.ref,
            "date": self.date,
            "intent": self.intent,
            "narrative": self.narrative,
            "lines": [line.to_dict() for line in self.lines],
            "total_debit": money_dict(self.total_debit),
            "total_credit": money_dict(self.total_credit),
            "balanced": self.balanced,
        }


def _account_name(code: str) -> str:
    return ACCOUNT_BY_CODE[code].name


def _allocation_account(allocation: Allocation | dict) -> str:
    if isinstance(allocation, dict):
        return str(allocation["account"])
    return allocation.account


def invoice_to_journal(invoice: dict, allocation: Allocation | dict | None = None) -> JournalEntry:
    intent = str(invoice.get("intent") or "").upper()
    direction = str(invoice.get("direction", "INBOUND")).upper()
    net = money(invoice.get("subtotal"))
    vat = money(invoice.get("total_tax"))
    gross = money(invoice.get("invoice_total") or (net + vat))
    ref = str(invoice.get("invoice_id") or "-")
    entry_date = str(invoice.get("invoice_date") or date.today().isoformat())

    if not allocation:
        allocation = allocate_account(invoice)
    account = _allocation_account(allocation)

    if intent == "PAYMENT_MADE":
        party = invoice.get("vendor_name") or invoice.get("counterparty_name") or "supplier"
        narrative = f"Payment to {party}"
        lines = [
            JournalLine("440", _account_name("440"), debit=gross),
            JournalLine("550", _account_name("550"), credit=gross),
        ]
    elif intent == "PAYMENT_RECEIVED":
        party = invoice.get("customer_name") or invoice.get("counterparty_name") or "client"
        narrative = f"Payment received from {party}"
        lines = [
            JournalLine("550", _account_name("550"), debit=gross),
            JournalLine("400", _account_name("400"), credit=gross),
        ]
    elif direction == "OUTBOUND" and "CREDIT_NOTE" in intent:
        party = invoice.get("customer_name") or invoice.get("counterparty_name") or "customer"
        revenue_account = account if account.startswith("7") else "704"
        narrative = f"Sales credit note {ref} to {party}"
        lines = [
            JournalLine(revenue_account, _account_name(revenue_account), debit=net),
            JournalLine("451", _account_name("451"), debit=vat),
            JournalLine("400", _account_name("400"), credit=gross),
        ]
    elif direction == "INBOUND" and "CREDIT_NOTE" in intent:
        party = invoice.get("vendor_name") or invoice.get("counterparty_name") or "supplier"
        expense_account = account if account.startswith("6") else "615"
        narrative = f"Purchase credit note {ref} from {party}"
        lines = [
            JournalLine("440", _account_name("440"), debit=gross),
            JournalLine(expense_account, _account_name(expense_account), credit=net),
            JournalLine("411", _account_name("411"), credit=vat),
        ]
    elif direction == "OUTBOUND":
        party = invoice.get("customer_name") or invoice.get("counterparty_name") or "customer"
        revenue_account = account if account.startswith("7") else "704"
        narrative = f"Sales invoice {ref} to {party}"
        lines = [
            JournalLine("400", _account_name("400"), debit=gross),
            JournalLine(revenue_account, _account_name(revenue_account), credit=net),
            JournalLine("451", _account_name("451"), credit=vat),
        ]
    else:
        party = invoice.get("vendor_name") or invoice.get("counterparty_name") or "supplier"
        expense_account = account if account.startswith("6") else "615"
        narrative = f"Purchase invoice {ref} from {party}"
        lines = [
            JournalLine(expense_account, _account_name(expense_account), debit=net),
            JournalLine("411", _account_name("411"), debit=vat),
            JournalLine("440", _account_name("440"), credit=gross),
        ]

    return JournalEntry(ref=ref, date=entry_date, intent=intent or direction, narrative=narrative, lines=lines)


def invoice_to_journal_entries(invoice: dict, allocation: Allocation | dict | None = None) -> list[JournalEntry]:
    """Return one or more entries for an extracted business event.

    A paid supplier invoice is intentionally split into accrual recognition and
    bank settlement so the ledger shows VAT, payable creation, and clearing.
    """
    if not allocation:
        allocation = allocate_account(invoice)
    primary = invoice_to_journal(invoice, allocation)
    if invoice.get("payment_included") and str(invoice.get("intent")).upper() == "INBOUND_INVOICE":
        gross = money(invoice.get("invoice_total"))
        ref = str(invoice.get("invoice_id") or "-")
        entry_date = str(invoice.get("invoice_date") or date.today().isoformat())
        party = invoice.get("vendor_name") or invoice.get("counterparty_name") or "supplier"
        clearing = JournalEntry(
            ref=f"{ref}-PAY",
            date=entry_date,
            intent="PAYMENT_MADE",
            narrative=f"Payment clearing payable to {party}",
            lines=[
                JournalLine("440", _account_name("440"), debit=gross),
                JournalLine("550", _account_name("550"), credit=gross),
            ],
        )
        return [primary, clearing]
    if invoice.get("payment_included") and str(invoice.get("intent")).upper() == "OUTBOUND_INVOICE":
        gross = money(invoice.get("invoice_total"))
        ref = str(invoice.get("invoice_id") or "-")
        entry_date = str(invoice.get("invoice_date") or date.today().isoformat())
        party = invoice.get("customer_name") or invoice.get("counterparty_name") or "customer"
        clearing = JournalEntry(
            ref=f"{ref}-PAY",
            date=entry_date,
            intent="PAYMENT_RECEIVED",
            narrative=f"Payment clearing receivable from {party}",
            lines=[
                JournalLine("550", _account_name("550"), debit=gross),
                JournalLine("400", _account_name("400"), credit=gross),
            ],
        )
        return [primary, clearing]
    return [primary]


class Ledger:
    def __init__(self) -> None:
        self.entries: list[JournalEntry] = []

    def post(self, entry: JournalEntry) -> JournalEntry:
        if not entry.balanced:
            raise ValueError(f"Refusing to post unbalanced entry {entry.ref}: D{entry.total_debit} != C{entry.total_credit}")
        self.entries.append(entry)
        return entry

    def reset(self) -> None:
        self.entries.clear()

    def trial_balance(self) -> dict:
        rows: dict[str, dict] = {}
        for entry in self.entries:
            for line in entry.lines:
                meta = get_account_meta(line.account)
                row = rows.setdefault(
                    line.account,
                    {
                        "name": line.account_name,
                        "debit": ZERO,
                        "credit": ZERO,
                        "balance": ZERO,
                        "meta": asdict(meta),
                    },
                )
                row["debit"] = money(row["debit"] + line.debit)
                row["credit"] = money(row["credit"] + line.credit)
                row["balance"] = money(row["debit"] - row["credit"])
        return {
            code: {
                "name": row["name"],
                "debit": money_dict(row["debit"]),
                "credit": money_dict(row["credit"]),
                "balance": money_dict(row["balance"]),
                "meta": row["meta"],
            }
            for code, row in sorted(rows.items())
        }

    def grouped_trial_balance(self) -> dict:
        groups = {name: [] for name in ("Assets", "Liabilities", "Equity", "Expenses", "Revenue", "Mixed/Unclassified")}
        for code, row in self.trial_balance().items():
            group = row["meta"].get("display_group") or "Mixed/Unclassified"
            groups.setdefault(group, []).append({"code": code, **row})
        return groups

    def _account_balance(self, code: str) -> Decimal:
        debit = ZERO
        credit = ZERO
        for entry in self.entries:
            for line in entry.lines:
                if line.account == code:
                    debit += line.debit
                    credit += line.credit
        return money(debit - credit)

    @property
    def totals(self) -> dict:
        debits = sum((entry.total_debit for entry in self.entries), ZERO)
        credits = sum((entry.total_credit for entry in self.entries), ZERO)
        return {"debit": money_dict(debits), "credit": money_dict(credits)}

    @property
    def is_balanced(self) -> bool:
        return self.totals["debit"] == self.totals["credit"]

    def snapshot(self) -> dict:
        trial = self.trial_balance()
        grouped_trial = self.grouped_trial_balance()
        vat_recoverable = self._account_balance("411")
        vat_payable = money(-self._account_balance("451"))
        vat_position = money(vat_payable - vat_recoverable)
        cash_position = self._account_balance("550")
        receivables_open = self._account_balance("400")
        payables_open = money(-self._account_balance("440"))
        balance_sheet = self.balance_sheet_summary(trial)
        profit_loss = self.profit_loss_summary(trial)
        return {
            "balanced": self.is_balanced,
            "totals": self.totals,
            "trial_balance": trial,
            "grouped_trial_balance": grouped_trial,
            "balance_sheet": balance_sheet,
            "profit_loss": profit_loss,
            "entries": [entry.to_dict() for entry in self.entries],
            "account_count": len(trial),
            "latest_entry": self.entries[-1].to_dict() if self.entries else None,
            "vat_recoverable": money_dict(vat_recoverable),
            "vat_payable": money_dict(vat_payable),
            "vat_position": money_dict(vat_position),
            "cash_position": money_dict(cash_position),
            "receivables_open": money_dict(receivables_open),
            "payables_open": money_dict(payables_open),
        }

    def balance_sheet_summary(self, trial: dict | None = None) -> dict:
        trial = trial or self.trial_balance()
        sections = {
            "assets": {"total": ZERO, "accounts": []},
            "liabilities": {"total": ZERO, "accounts": []},
            "equity": {"total": ZERO, "accounts": []},
            "mixed_unclassified": {"total": ZERO, "accounts": []},
        }
        for code, row in trial.items():
            meta = row["meta"]
            if meta["statement"] != "balance_sheet":
                continue
            balance = money(row["balance"])
            category = meta["category"]
            if category in {"asset", "contra_asset"}:
                amount = -balance if category == "contra_asset" else balance
                key = "assets"
            elif category == "liability":
                amount = money(-balance)
                key = "liabilities"
            elif category == "equity":
                amount = money(-balance)
                key = "equity"
            else:
                amount = balance
                key = "mixed_unclassified"
            sections[key]["total"] = money(sections[key]["total"] + amount)
            sections[key]["accounts"].append({
                "code": code,
                "name": row["name"],
                "amount": money_dict(amount),
                "balance": row["balance"],
                "normal_side": meta["normal_side"],
                "category": category,
            })
        net_assets = money(sections["assets"]["total"] - sections["liabilities"]["total"] - sections["equity"]["total"])
        return {
            key: {"total": money_dict(value["total"]), "accounts": value["accounts"]}
            for key, value in sections.items()
        } | {"net_assets": money_dict(net_assets)}

    def profit_loss_summary(self, trial: dict | None = None) -> dict:
        trial = trial or self.trial_balance()
        expenses = {"total": ZERO, "accounts": []}
        revenue = {"total": ZERO, "accounts": []}
        for code, row in trial.items():
            meta = row["meta"]
            if meta["statement"] != "income_statement":
                continue
            balance = money(row["balance"])
            if meta["category"] == "expense":
                amount = balance
                expenses["total"] = money(expenses["total"] + amount)
                expenses["accounts"].append({"code": code, "name": row["name"], "amount": money_dict(amount), "balance": row["balance"]})
            elif meta["category"] == "revenue":
                amount = money(-balance)
                revenue["total"] = money(revenue["total"] + amount)
                revenue["accounts"].append({"code": code, "name": row["name"], "amount": money_dict(amount), "balance": row["balance"]})
        profit_loss = money(revenue["total"] - expenses["total"])
        return {
            "expenses": {"total": money_dict(expenses["total"]), "accounts": expenses["accounts"]},
            "revenue": {"total": money_dict(revenue["total"]), "accounts": revenue["accounts"]},
            "profit_loss": money_dict(profit_loss),
        }


def post_all(entries: Iterable[JournalEntry]) -> Ledger:
    ledger = Ledger()
    for entry in entries:
        ledger.post(entry)
    return ledger
