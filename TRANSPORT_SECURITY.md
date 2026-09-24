# Transport-security maintenance

The original e-invoice client caught certificate-validation errors and retried both document creation and sending with verification disabled. That could send authorization headers and invoice data over an unverified connection.

The client now fails closed: both operations keep certificate verification enabled. A certificate error returns a failed request without an insecure retry. Fix the server certificate or trust configuration rather than disabling validation.

`test_transport_security.py` simulates a certificate failure and checks that only one verified request is attempted. A second test checks verified create/send calls. The regression test failed before the fix (requests used `True, False, False`) and passes after it (`True` only on failure). All 41 tests passed locally on Python 3.13 with no real invoice delivery.

This is a narrow maintenance improvement, not a full security audit. Authentication, upload handling, retention, persistent state and deployment controls still need review before public server hosting.
