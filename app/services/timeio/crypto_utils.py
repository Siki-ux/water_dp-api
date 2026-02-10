import base64
import hashlib
import secrets

from cryptography.fernet import Fernet

from app.core.config import settings


def get_fernet() -> Fernet:
    """Get Fernet instance using the shared secret."""
    key = settings.fernet_encryption_secret
    if not key:
        raise ValueError("FERNET_ENCRYPTION_SECRET is not set in environment")
    return Fernet(key)


def encrypt_password(password: str) -> str:
    """Encrypt password using Fernet (used for ConfigDB)."""
    return get_fernet().encrypt(password.encode()).decode()


def decrypt_password(token: str) -> str:
    """Decrypt password using Fernet."""
    return get_fernet().decrypt(token.encode()).decode()


def hash_password_pbkdf2(password: str, iterations: int = 1000) -> str:
    """
    Hash password using PBKDF2-SHA256 (Mosquitto Go Auth format).
    Format: PBKDF2$sha256$iterations$salt$hash
    """
    # Generate 12 bytes of random salt
    salt_bytes = secrets.token_bytes(12)
    # Encode salt in base64
    salt_b64 = base64.b64encode(salt_bytes).decode("utf-8")

    # Hash the password
    dk = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt_b64.encode("utf-8"), iterations
    )
    # Encode hash in base64
    dk_b64 = base64.b64encode(dk).decode("utf-8")

    return f"PBKDF2$sha256${iterations}${salt_b64}${dk_b64}"
