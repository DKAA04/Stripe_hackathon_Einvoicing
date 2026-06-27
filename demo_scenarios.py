DEMO_SCENARIOS = [
    {
        "title": "Supplier bill: plumber",
        "message": "I paid the plumber EUR 242 incl. 21% VAT",
        "expected_account": "611",
    },
    {
        "title": "Supplier bill: telecom",
        "message": "I received an invoice from Proximus for EUR 121 incl. 21% VAT",
        "expected_account": "612",
    },
    {
        "title": "Client invoice: website",
        "message": "Invoice Acme NV EUR 1,210 incl. 21% VAT for website services",
        "expected_account": "704",
    },
    {
        "title": "Client payment",
        "message": "Client paid invoice INV-001 by bank transfer",
        "expected_account": "400",
    },
]
