# Acceptance Checklist

- [ ] `python -m pytest -q` is green in the active Python environment.
- [ ] `http://localhost:8000` opens InvoiceAgent.
- [ ] Scenario buttons work.
- [ ] Plumber scenario books to `611 Maintenance and repairs`.
- [ ] Books balanced badge is green.
- [ ] Trial balance is visible.
- [ ] `CREATE_REAL_UBL=0` mode is honest and says UBL is skipped to save credits.
- [ ] `CREATE_REAL_UBL=1` mode attempts sandbox UBL and shows `doc_id`/validation or a clear error.
- [ ] PDF upload does not crash.
- [ ] Reset works.
