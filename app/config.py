import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("DATA_DIR", BASE_DIR / "data"))
DATA_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_PATH = DATA_DIR / "bokke_predictions.db"
DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

APP_NAME = "Bokke Predictions"

ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "springbok")
SESSION_SECRET = os.environ.get("SESSION_SECRET", "change-me-please-dev-only-secret")

# Used for the deterministic phone-number lookup hash (HMAC key).
PHONE_HASH_SECRET = os.environ.get("PHONE_HASH_SECRET", "change-me-please-dev-only-secret").encode()

# Fernet key for recoverable (but never web-exposed) phone number encryption.
# Generate one with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
PHONE_ENCRYPTION_KEY = os.environ.get("PHONE_ENCRYPTION_KEY")

DEFAULT_COUNTRY_CODE = os.environ.get("DEFAULT_COUNTRY_CODE", "27")
