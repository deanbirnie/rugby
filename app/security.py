import hashlib
import hmac
import re
from functools import lru_cache

from cryptography.fernet import Fernet
from fastapi import Request

from app import config


class NotAuthenticated(Exception):
    """Raised when an admin-only route is hit without a valid session."""


def verify_admin_password(password: str) -> bool:
    return hmac.compare_digest(password, config.ADMIN_PASSWORD)


def require_admin(request: Request) -> None:
    if not request.session.get("is_admin"):
        raise NotAuthenticated()


def normalize_phone(raw: str) -> str:
    """Collapse a human-entered phone number down to bare digits with a
    country code, so the same person's number always matches regardless of
    how they typed it: 082 123 4567, +27 82 123 4567, 0027821234567 and
    821234567 all normalize to 27821234567.
    """
    digits = re.sub(r"\D", "", raw or "")
    cc = config.DEFAULT_COUNTRY_CODE
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = cc + digits[1:]
    elif digits.startswith(cc + "0") and len(digits) == len(cc) + 10:
        # "+27 (0)82 123 4567" style: drop the redundant 0 after the code.
        digits = cc + digits[len(cc) + 1 :]
    elif len(digits) == 9 and not digits.startswith("0"):
        # Local number typed without the leading 0 or country code.
        digits = cc + digits
    return digits


def is_valid_sa_cell(normalized_phone: str) -> bool:
    """True if a normalized number looks like a South African cellphone:
    country code 27 followed by 9 digits, the first of which is never 0.
    """
    return re.fullmatch(r"27[1-9]\d{8}", normalized_phone) is not None


@lru_cache
def _fernet() -> Fernet:
    key = config.PHONE_ENCRYPTION_KEY
    if not key:
        raise RuntimeError(
            "PHONE_ENCRYPTION_KEY is not set. Generate one with:\n"
            '  python -c "from cryptography.fernet import Fernet; '
            'print(Fernet.generate_key().decode())"'
        )
    return Fernet(key.encode() if isinstance(key, str) else key)


def hash_phone(normalized_phone: str) -> str:
    """Deterministic HMAC used only to recognise a returning predictor.
    One-way: cannot be turned back into the phone number.
    """
    return hmac.new(
        config.PHONE_HASH_SECRET, normalized_phone.encode(), hashlib.sha256
    ).hexdigest()


def encrypt_phone(normalized_phone: str) -> str:
    """Recoverable encryption, kept out of the web UI entirely. Only usable
    via scripts/decrypt_phone.py with the PHONE_ENCRYPTION_KEY secret.
    """
    return _fernet().encrypt(normalized_phone.encode()).decode()


def decrypt_phone(token: str) -> str:
    return _fernet().decrypt(token.encode()).decode()
