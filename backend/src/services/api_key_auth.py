import hashlib
import secrets

from fastapi.security import APIKeyHeader


def generate_api_key() -> str:
    return "oqb_" + secrets.token_urlsafe(32)

def hash_api_key(api_key: str) -> str:
    return hashlib.sha256(api_key.encode()).hexdigest()

api_key_scheme = APIKeyHeader(
    name="X-API-Key",
    auto_error=False,
)