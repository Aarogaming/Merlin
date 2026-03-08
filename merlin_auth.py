import hashlib
import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path
from jose import jwt
from passlib.context import CryptContext

# Secret key to sign JWT tokens
SECRET_KEY = os.environ.get("MERLIN_SECRET_KEY", "super-secret-merlin-key")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")


def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password):
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def parse_api_key_collection(raw: str | None) -> list[str]:
    if raw is None:
        return []
    keys: list[str] = []
    seen: set[str] = set()
    normalized = raw.replace("\n", ",")
    for token in normalized.split(","):
        key = token.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        keys.append(key)
    return keys


def load_api_key_collection_from_file(path: str | None) -> list[str]:
    if not path:
        return []
    file_path = Path(path)
    try:
        content = file_path.read_text(encoding="utf-8")
    except OSError:
        return []
    return parse_api_key_collection(content)
