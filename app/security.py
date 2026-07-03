import base64
import binascii
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
    if not key or key.strip() in ("", "change-me"):
        raise RuntimeError(
            "PHONE_ENCRYPTION_KEY is not set (or still the change-me "
            "placeholder). Set it to any long random string in .env, e.g.:\n"
            '  python3 -c "import secrets; print(secrets.token_hex(32))"'
        )
    raw = key.encode() if isinstance(key, str) else key
    try:
        # A literal Fernet key (output of Fernet.generate_key()) is used
        # as-is, so existing deployments keep decrypting their data.
        return Fernet(raw)
    except (ValueError, binascii.Error):
        # Anything else is treated as a passphrase and deterministically
        # stretched into a Fernet key, so any random string works.
        return Fernet(base64.urlsafe_b64encode(hashlib.sha256(raw).digest()))


def ensure_crypto_ready() -> None:
    """Called at startup so a missing/placeholder PHONE_ENCRYPTION_KEY stops
    the app from booting with a clear message, instead of surfacing as a 500
    the first time someone submits a prediction.
    """
    _fernet()


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
