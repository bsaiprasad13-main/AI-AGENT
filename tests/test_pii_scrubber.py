"""Unit tests for PII Scrubber and fintech regex redactor."""

from src.preprocessing.pii_scrubber import PIIScrubber


def test_pii_phone_redaction():
    scrubber = PIIScrubber()

    # Standard contiguous
    t1 = "Please call my mobile 9876543210 immediately."
    assert "[REDACTED_PHONE]" in scrubber.redact(t1)
    assert "9876543210" not in scrubber.redact(t1)

    # With +91
    t2 = "Contact me on +91 9123456789 or +91-9876543210."
    res2 = scrubber.redact(t2)
    assert "9123456789" not in res2
    assert "9876543210" not in res2

    # Spaced out phone number
    t3 = "Call me at 9 8 7 6 5 4 3 2 1 0 for help."
    res3 = scrubber.redact(t3)
    assert "[REDACTED_PHONE]" in res3
    assert "9 8 7 6" not in res3


def test_pii_email_redaction():
    scrubber = PIIScrubber()
    t = "Send the statement to john.doe@example.com or support@groww.in."
    res = scrubber.redact(t)
    assert "[REDACTED_EMAIL]" in res
    assert "john.doe@example.com" not in res
    assert "support@groww.in" not in res


def test_pii_upi_vpa_redaction():
    scrubber = PIIScrubber()
    t = "UPI payment failed for rahul99@okhdfcbank and 9876543210@paytm and user@ybl."
    res = scrubber.redact(t)
    assert "[REDACTED_UPI]" in res
    assert "rahul99@okhdfcbank" not in res
    assert "9876543210@paytm" not in res
    assert "user@ybl" not in res


def test_pii_demat_and_bank_account():
    scrubber = PIIScrubber()
    # 16-digit Demat BOID
    t1 = "My Demat BOID is 1208160012345678 and shares are not credited."
    res1 = scrubber.redact(t1)
    assert "[REDACTED_DEMAT]" in res1
    assert "1208160012345678" not in res1

    # Bank Account
    t2 = "Amount debited from A/C no: 987654321012345 but not in wallet."
    res2 = scrubber.redact(t2)
    assert "[REDACTED_ACCOUNT]" in res2
    assert "987654321012345" not in res2


def test_pii_pan_and_stock_whitelist():
    scrubber = PIIScrubber()
    # Real PAN pattern
    t1 = "My PAN card is ABCDE1234F for KYC verification."
    res1 = scrubber.redact(t1)
    assert "[REDACTED_PAN]" in res1
    assert "ABCDE1234F" not in res1

    # Stock Tickers should NOT be redacted
    t2 = "Bought shares of HDFCBANK, INFY, TCS, and RELIANCE on NIFTY."
    res2 = scrubber.redact(t2)
    assert "HDFCBANK" in res2
    assert "INFY" in res2
    assert "TCS" in res2
    assert "RELIANCE" in res2
    assert "NIFTY" in res2


def test_username_masking():
    u1 = PIIScrubber.mask_username("Suresh Raina")
    u2 = PIIScrubber.mask_username("Suresh Raina")
    u3 = PIIScrubber.mask_username("Rohit Sharma")

    # Deterministic hashing
    assert u1 == u2
    assert u1 != u3
    assert u1.startswith("User_")
    assert PIIScrubber.mask_username("A Google user") == "User_Anon"
