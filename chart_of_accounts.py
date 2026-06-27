"""Belgian PCMN-style chart and deterministic account allocation rules."""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class Account:
    code: str
    name: str
    category: str
    kind: str
    keywords: tuple[str, ...] = ()


@dataclass(frozen=True)
class AccountMeta:
    code: str
    name: str
    class_code: str
    category: str
    statement: str
    normal_side: str
    liquidity_group: str | None = None
    working_capital_group: str | None = None
    display_group: str = "Mixed/Unclassified"
    flagged: bool = False


@dataclass(frozen=True)
class Allocation:
    account: str
    account_name: str
    category: str
    confidence: float
    matched_keywords: tuple[str, ...]
    explanation: str
    warning: str | None = None

    @property
    def reason(self) -> str:
        return self.explanation

    def to_dict(self) -> dict:
        data = asdict(self)
        data["matched_keywords"] = list(self.matched_keywords)
        data["reason"] = self.explanation
        return data


ACCOUNTS: tuple[Account, ...] = (
    Account("400", "Trade receivables / Customers", "working capital", "asset"),
    Account("440", "Trade payables / Suppliers", "working capital", "liability"),
    Account("411", "VAT recoverable / input VAT", "VAT", "asset"),
    Account("451", "VAT payable / output VAT", "VAT", "liability"),
    Account("550", "Bank", "cash", "asset"),
    Account("604", "Purchases of goods for resale", "cost of goods", "expense", ("inventory", "stock", "goods for resale")),
    Account("610", "Rent and rental charges", "premises", "expense", ("rent", "office lease")),
    Account("611", "Maintenance and repairs", "maintenance", "expense", ("plumber", "repair", "maintenance", "fix", "plumbing")),
    Account("612", "Utilities / energy / telecom", "utilities and telecom", "expense", ("electricity", "gas", "water", "energy", "utility", "proximus", "orange", "telecom", "internet", "phone")),
    Account("613", "Insurance", "insurance", "expense", ("insurance",)),
    Account("614", "Transport and travel", "travel", "expense", ("taxi", "train", "flight", "travel", "transport")),
    Account("615", "Professional fees and external services", "external services", "expense", ("lawyer", "accountant", "consultant", "freelance", "agency")),
    Account("616", "Office/admin expenses", "office and admin", "expense", ("office", "software", "subscription", "supplies")),
    Account("620", "Remuneration and payroll costs", "payroll", "expense", ("salary", "payroll", "wage")),
    Account("630", "Depreciation", "depreciation", "expense", ("depreciation", "amortisation", "amortization")),
    Account("640", "Taxes and operating charges", "operating taxes", "expense", ("tax", "operating charge", "levy")),
    Account("657", "Bank/payment fees", "financial charges", "expense", ("stripe fee", "bank fee", "payment fee")),
    Account("700", "Sales revenue", "goods revenue", "revenue", ("product sale", "goods sold")),
    Account("704", "Services revenue", "services revenue", "revenue", ("client work", "website", "consulting", "design", "service", "services")),
    Account("740", "Operating subsidies / other operating income", "other operating income", "revenue", ("subsidy", "grant", "other operating income")),
)

ACCOUNT_BY_CODE = {account.code: account for account in ACCOUNTS}


PCMN_ACCOUNT_META: dict[str, AccountMeta] = {
    "400": AccountMeta("400", "Trade receivables / Customers", "4", "asset", "balance_sheet", "debit", working_capital_group="receivables", display_group="Assets"),
    "404": AccountMeta("404", "Bills to be collected", "4", "asset", "balance_sheet", "debit", working_capital_group="receivables", display_group="Assets"),
    "407": AccountMeta("407", "Doubtful debtors", "4", "asset", "balance_sheet", "debit", working_capital_group="receivables", display_group="Assets"),
    "409": AccountMeta("409", "Allowances on receivables", "4", "contra_asset", "balance_sheet", "credit", working_capital_group="receivables", display_group="Assets"),
    "410": AccountMeta("410", "Called unpaid capital / contributions", "4", "asset", "balance_sheet", "debit", display_group="Assets"),
    "411": AccountMeta("411", "VAT recoverable / input VAT", "4", "asset", "balance_sheet", "debit", working_capital_group="taxes", display_group="Assets"),
    "412": AccountMeta("412", "Taxes and withholding taxes recoverable", "4", "asset", "balance_sheet", "debit", working_capital_group="taxes", display_group="Assets"),
    "414": AccountMeta("414", "Income receivable", "4", "asset", "balance_sheet", "debit", working_capital_group="receivables", display_group="Assets"),
    "416": AccountMeta("416", "Sundry receivables", "4", "asset", "balance_sheet", "debit", working_capital_group="receivables", display_group="Assets"),
    "418": AccountMeta("418", "Guarantees / deposits paid", "4", "asset", "balance_sheet", "debit", working_capital_group="receivables", display_group="Assets"),
    "420": AccountMeta("420", "Current portion of long-term debt", "4", "liability", "balance_sheet", "credit", working_capital_group="current_debt", display_group="Liabilities"),
    "430": AccountMeta("430", "Financial debts / current loans", "4", "liability", "balance_sheet", "credit", working_capital_group="current_debt", display_group="Liabilities"),
    "440": AccountMeta("440", "Trade payables / Suppliers", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "441": AccountMeta("441", "Bills of exchange payable", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "444": AccountMeta("444", "Invoices to be received", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "450": AccountMeta("450", "Estimated taxes payable", "4", "liability", "balance_sheet", "credit", working_capital_group="taxes", display_group="Liabilities"),
    "451": AccountMeta("451", "VAT payable / output VAT", "4", "liability", "balance_sheet", "credit", working_capital_group="taxes", display_group="Liabilities"),
    "452": AccountMeta("452", "Taxes payable", "4", "liability", "balance_sheet", "credit", working_capital_group="taxes", display_group="Liabilities"),
    "453": AccountMeta("453", "Taxes withheld", "4", "liability", "balance_sheet", "credit", working_capital_group="taxes", display_group="Liabilities"),
    "454": AccountMeta("454", "Social security payable", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "455": AccountMeta("455", "Remuneration payable", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "456": AccountMeta("456", "Holiday pay payable", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "459": AccountMeta("459", "Other social debts", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "460": AccountMeta("460", "Advances received on contracts", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "470": AccountMeta("470", "Debts from allocation of result", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "480": AccountMeta("480", "Sundry debts", "4", "liability", "balance_sheet", "credit", working_capital_group="payables", display_group="Liabilities"),
    "490": AccountMeta("490", "Deferred charges / accrued income", "4", "asset", "balance_sheet", "debit", working_capital_group="accruals", display_group="Assets"),
    "491": AccountMeta("491", "Accrued income / deferred charges", "4", "asset", "balance_sheet", "debit", working_capital_group="accruals", display_group="Assets"),
    "492": AccountMeta("492", "Accrued charges", "4", "liability", "balance_sheet", "credit", working_capital_group="accruals", display_group="Liabilities"),
    "493": AccountMeta("493", "Deferred income", "4", "liability", "balance_sheet", "credit", working_capital_group="accruals", display_group="Liabilities"),
    "550": AccountMeta("550", "Bank", "5", "asset", "balance_sheet", "debit", liquidity_group="cash", display_group="Assets"),
    "604": AccountMeta("604", "Purchases of goods for resale", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "610": AccountMeta("610", "Rent and rental charges", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "611": AccountMeta("611", "Maintenance and repairs", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "612": AccountMeta("612", "Utilities / energy / telecom", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "613": AccountMeta("613", "Insurance", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "614": AccountMeta("614", "Transport and travel", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "615": AccountMeta("615", "Professional fees and external services", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "616": AccountMeta("616", "Office/admin expenses", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "620": AccountMeta("620", "Remuneration and payroll costs", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "630": AccountMeta("630", "Depreciation", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "640": AccountMeta("640", "Taxes and operating charges", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "657": AccountMeta("657", "Bank/payment fees", "6", "expense", "income_statement", "debit", display_group="Expenses"),
    "700": AccountMeta("700", "Sales revenue", "7", "revenue", "income_statement", "credit", display_group="Revenue"),
    "704": AccountMeta("704", "Services revenue", "7", "revenue", "income_statement", "credit", display_group="Revenue"),
    "740": AccountMeta("740", "Operating subsidies / other operating income", "7", "revenue", "income_statement", "credit", display_group="Revenue"),
}


def _name_for_code(code: str) -> str:
    return ACCOUNT_BY_CODE.get(code, Account(code, f"Account {code}", "unknown", "unknown")).name


def get_account_meta(account_code: str) -> AccountMeta:
    code = str(account_code)
    if code in PCMN_ACCOUNT_META:
        return PCMN_ACCOUNT_META[code]
    class_code = code[:1] if code else "?"
    prefix2 = int(code[:2]) if code[:2].isdigit() else None
    prefix3 = int(code[:3]) if code[:3].isdigit() else None
    if class_code == "1":
        sub = prefix2 or 10
        category = "equity" if 10 <= sub <= 15 else "liability"
        return AccountMeta(code, _name_for_code(code), class_code, category, "balance_sheet", "credit", display_group="Equity" if category == "equity" else "Liabilities")
    if class_code in {"2", "3", "5"}:
        liquidity = "cash" if class_code == "5" else None
        return AccountMeta(code, _name_for_code(code), class_code, "asset", "balance_sheet", "debit", liquidity_group=liquidity, display_group="Assets")
    if class_code == "4":
        if prefix3 in {400, 404, 407, 410, 411, 412, 414, 416, 418, 490, 491}:
            return AccountMeta(code, _name_for_code(code), class_code, "asset", "balance_sheet", "debit", working_capital_group="receivables" if prefix3 != 411 else "taxes", display_group="Assets")
        if prefix3 == 409:
            return AccountMeta(code, _name_for_code(code), class_code, "contra_asset", "balance_sheet", "credit", working_capital_group="receivables", display_group="Assets")
        if prefix3 is not None and (
            420 <= prefix3 <= 429
            or 430 <= prefix3 <= 439
            or prefix3 in {440, 441, 444, 450, 451, 452, 453, 454, 455, 456, 459, 492, 493}
            or prefix2 in {46, 47, 48}
        ):
            group = "taxes" if prefix3 in {450, 451, 452, 453} else "payables"
            return AccountMeta(code, _name_for_code(code), class_code, "liability", "balance_sheet", "credit", working_capital_group=group, display_group="Liabilities")
        return AccountMeta(code, _name_for_code(code), class_code, "mixed", "balance_sheet", "debit", working_capital_group="unclassified_4xx", display_group="Mixed/Unclassified", flagged=True)
    if class_code == "6":
        return AccountMeta(code, _name_for_code(code), class_code, "expense", "income_statement", "debit", display_group="Expenses")
    if class_code == "7":
        return AccountMeta(code, _name_for_code(code), class_code, "revenue", "income_statement", "credit", display_group="Revenue")
    return AccountMeta(code, _name_for_code(code), class_code, "unknown", "balance_sheet", "debit", display_group="Mixed/Unclassified", flagged=True)


def _search_text(invoice: dict) -> str:
    parts = [
        invoice.get("description"),
        invoice.get("counterparty_name"),
        invoice.get("vendor_name"),
        invoice.get("customer_name"),
        " ".join(str(item.get("description", "")) for item in invoice.get("items", []) if isinstance(item, dict)),
    ]
    return " ".join(str(part or "") for part in parts).lower()


def _allocation_for(code: str, confidence: float, keywords: tuple[str, ...], explanation: str, warning: str | None = None) -> Allocation:
    account = ACCOUNT_BY_CODE[code]
    return Allocation(
        account=account.code,
        account_name=account.name,
        category=account.category,
        confidence=confidence,
        matched_keywords=keywords,
        explanation=explanation,
        warning=warning,
    )


def allocate_account(invoice: dict) -> Allocation:
    intent = str(invoice.get("intent") or "").upper()
    direction = str(invoice.get("direction") or "").upper()
    text = _search_text(invoice)

    if intent == "PAYMENT_MADE":
        return _allocation_for("440", 0.98, ("payment",), "Supplier payment clears trade payables.")
    if intent == "PAYMENT_RECEIVED":
        return _allocation_for("400", 0.98, ("payment",), "Customer payment clears trade receivables.")

    pool_kind = "revenue" if direction == "OUTBOUND" else "expense"
    best: Account | None = None
    matches: list[str] = []
    for account in ACCOUNTS:
        if account.kind != pool_kind:
            continue
        account_matches = [keyword for keyword in account.keywords if keyword in text]
        if account_matches and (best is None or len(max(account_matches, key=len)) > len(max(matches, key=len))):
            best = account
            matches = account_matches

    if best:
        return _allocation_for(
            best.code,
            0.93,
            tuple(matches),
            f"Matched {', '.join(matches)} against invoice description/counterparty.",
        )

    if direction == "OUTBOUND":
        return _allocation_for(
            "704",
            0.64,
            (),
            "No revenue keyword matched; defaulted to services revenue for a conservative demo posting.",
            "Unknown revenue allocation; defaulted to 704.",
        )
    return _allocation_for(
        "615",
        0.58,
        (),
        "No expense keyword matched; defaulted to professional/external services.",
        "Unknown expense allocation; defaulted to 615.",
    )


def catalog() -> dict:
    return {
        "standard": "Belgian PCMN-style demo chart",
        "accounts": [{**asdict(account), "meta": asdict(get_account_meta(account.code))} for account in ACCOUNTS],
        "rules": [
            "Inbound invoices: Dr expense net, Dr 411 input VAT, Cr 440 supplier payable gross.",
            "Outbound invoices: Dr 400 customer receivable gross, Cr revenue net, Cr 451 output VAT.",
            "Supplier payments: Dr 440, Cr 550.",
            "Customer payments: Dr 550, Cr 400.",
            "Keyword allocation is deterministic and returns matched keywords, confidence, and warnings.",
        ],
    }
