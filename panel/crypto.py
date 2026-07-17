from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import tomllib
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SECRETS_PATH = PROJECT_ROOT / ".streamlit" / "secrets.toml"
DATA_ENCRYPTION_KEY_NAME = "DATA_ENCRYPTION_KEY"


class EncryptionConfigError(RuntimeError):
    pass


def generate_data_encryption_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")


def _read_key_from_secrets_file() -> str:
    if not SECRETS_PATH.exists():
        return ""
    data = tomllib.loads(SECRETS_PATH.read_text(encoding="utf-8"))
    direct_value = str(data.get(DATA_ENCRYPTION_KEY_NAME, "")).strip()
    if direct_value:
        return direct_value
    return _find_key_recursively(data)


def _find_key_recursively(value: Any) -> str:
    if not isinstance(value, dict):
        return ""
    for key, item in value.items():
        if str(key) == DATA_ENCRYPTION_KEY_NAME:
            return str(item).strip()
        nested = _find_key_recursively(item)
        if nested:
            return nested
    return ""


def load_data_encryption_key() -> str:
    return str(os.getenv(DATA_ENCRYPTION_KEY_NAME, "") or _read_key_from_secrets_file()).strip()


def _fernet():
    try:
        from cryptography.fernet import Fernet
    except ModuleNotFoundError as error:
        raise EncryptionConfigError(
            "Falta instalar cryptography. Ejecuta: py -m pip install -r requirements.txt"
        ) from error

    key = load_data_encryption_key()
    if not key:
        raise EncryptionConfigError("Falta DATA_ENCRYPTION_KEY en .streamlit/secrets.toml.")

    try:
        return Fernet(key.encode("ascii"))
    except Exception as error:
        raise EncryptionConfigError("DATA_ENCRYPTION_KEY no tiene formato valido de Fernet.") from error


def encryption_status() -> tuple[bool, str]:
    try:
        fernet = _fernet()
        token = fernet.encrypt(b"check")
        if fernet.decrypt(token) != b"check":
            return False, "No se pudo validar el cifrado local."
        return True, "Cifrado local activo."
    except EncryptionConfigError as error:
        return False, str(error)


def encrypt_bytes(value: bytes) -> bytes:
    return _fernet().encrypt(value)


def decrypt_bytes(value: bytes) -> bytes:
    return _fernet().decrypt(value)


def encrypt_text(value: str) -> str:
    return encrypt_bytes(value.encode("utf-8")).decode("ascii")


def decrypt_text(value: str) -> str:
    if not value:
        return ""
    return decrypt_bytes(value.encode("ascii")).decode("utf-8")


def stable_digest(value: str) -> str:
    key = _b64_decode_key(load_data_encryption_key())
    return hmac.new(key, value.strip().casefold().encode("utf-8"), hashlib.sha256).hexdigest()


def _b64_decode_key(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def encrypt_json_line(value: dict[str, Any]) -> str:
    raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return encrypt_bytes(raw).decode("ascii")


def decrypt_json_line(value: str) -> dict[str, Any]:
    raw = decrypt_bytes(value.strip().encode("ascii"))
    decoded = json.loads(raw.decode("utf-8"))
    return decoded if isinstance(decoded, dict) else {}
