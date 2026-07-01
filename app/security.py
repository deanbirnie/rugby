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
    spacing, dashes, +27 vs 0 prefixes, etc.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("00"):
        digits = digits[2:]
    if digits.startswith("0") and len(digits) == 10:
        digits = config.DEFAULT_COUNTRY_CODE + digits[1:]
    return digits


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
