"""PII Redaction Engine for Indian Fintech & Review Privacy."""

import hashlib
import re
from typing import Set

# Whitelist of common Indian stock tickers and fintech terms to prevent false-positive PAN redaction
FINTECH_WHITELIST: Set[str] = {
    "NIFTY",
    "BANKNIFTY",
    "SENSEX",
    "FINNIFTY",
    "MIDCPNIFTY",
    "RELIANCE",
    "HDFCBANK",
    "ICICIBANK",
    "KOTAKBANK",
    "AXISBANK",
    "SBIN",
    "INFY",
    "TCS",
    "WIPRO",
    "HCLTECH",
    "TATAMOTORS",
    "TATASTEEL",
    "MARUTI",
    "BAJFINANCE",
    "BAJAJFINSV",
    "GROWW",
    "ZERODHA",
    "UPSTOX",
    "ANGELONE",
    "PAYTM",
    "PHONEPE",
    "GOOGLEPAY",
    "BHIM",
    "MUTUALFUND",
}


class PIIScrubber:
    """Detects and scrubs Personally Identifiable Information (PII) from review texts."""

    def __init__(self):
        # Email pattern
        self.email_regex = re.compile(
            r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b",
            re.IGNORECASE,
        )

        # UPI VPAs (e.g. user@okhdfcbank, 9876543210@paytm, user@ybl, name@upi)
        self.upi_regex = re.compile(
            r"\b[a-zA-Z0-9.\-_]{2,35}@(ok[a-zA-Z]+|paytm|ybl|axl|ibl|icici|hdfcbank|sbi|axisbank|barodampay|postbank|upi)\b",
            re.IGNORECASE,
        )

        # Standard contiguous Indian phone numbers (+91, 0, or 10-digit starting 6,7,8,9)
        self.phone_regex = re.compile(
            r"(?:\+91[\-\s]?)?(?:0)?[6-9]\d{9}\b"
        )

        # Spaced out phone numbers (e.g. 9 8 7 6 5 4 3 2 1 0 or 98765 43210)
        self.spaced_phone_regex = re.compile(
            r"\b[6-9](?:\s*\d){9}\b"
        )

        # Indian PAN Card: 5 letters, 4 numbers, 1 letter (e.g. ABCDE1234F)
        self.pan_regex = re.compile(
            r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
            re.IGNORECASE,
        )

        # Indian Aadhaar: 12 digits (often 4-4-4)
        self.aadhaar_regex = re.compile(
            r"\b[2-9][0-9]{3}[\s\-]?[0-9]{4}[\s\-]?[0-9]{4}\b"
        )

        # 16-digit Demat / BOID numbers
        self.demat_regex = re.compile(
            r"\b\d{16}\b"
        )

        # Bank account numbers with context (A/c, account no, acc, account number)
        self.bank_acc_regex = re.compile(
            r"(?:a/c|acc(?:ount)?)(?:\s*(?:no|num|number))?\.?\s*[:#-]?\s*(\d{9,18})\b",
            re.IGNORECASE,
        )

    def redact(self, text: str) -> str:
        """Applies complete multi-stage PII scrubbing to the input text."""
        if not text:
            return ""

        redacted = text

        # 1. Redact Emails
        redacted = self.email_regex.sub("[REDACTED_EMAIL]", redacted)

        # 2. Redact UPI VPAs
        redacted = self.upi_regex.sub("[REDACTED_UPI]", redacted)

        # 3. Redact Bank Accounts with prefix
        def _replace_bank_acc(match):
            prefix = match.group(0)
            digits = match.group(1)
            return prefix.replace(digits, "[REDACTED_ACCOUNT]")

        redacted = self.bank_acc_regex.sub(_replace_bank_acc, redacted)

        # 4. Redact Demat 16-digit numbers
        redacted = self.demat_regex.sub("[REDACTED_DEMAT]", redacted)

        # 5. Redact Aadhaar Numbers
        redacted = self.aadhaar_regex.sub("[REDACTED_AADHAAR]", redacted)

        # 6. Redact PAN Cards (checking whitelist to avoid stock symbol collisions)
        def _replace_pan(match):
            word = match.group(0).upper()
            if word in FINTECH_WHITELIST:
                return match.group(0)
            return "[REDACTED_PAN]"

        redacted = self.pan_regex.sub(_replace_pan, redacted)

        # 7. Redact Phone numbers (spaced & contiguous)
        redacted = self.spaced_phone_regex.sub("[REDACTED_PHONE]", redacted)
        redacted = self.phone_regex.sub("[REDACTED_PHONE]", redacted)

        return redacted

    @staticmethod
    def mask_username(username: str) -> str:
        """Converts an authentic user display name to a deterministic anonymous ID."""
        if not username or username.strip().lower() in ("a google user", "anonymous", ""):
            return "User_Anon"
        
        # Create deterministic 4-character hex hash
        hash_digest = hashlib.sha256(username.strip().encode("utf-8")).hexdigest()[:4].upper()
        return f"User_{hash_digest}"
