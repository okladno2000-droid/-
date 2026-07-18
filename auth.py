import os
import random
import string
from datetime import datetime, timedelta

from passlib.context import CryptContext
from jose import jwt

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# ВАЖНО: смени этот секрет на свой перед деплоем — например, случайную
# длинную строку в переменной окружения JWT_SECRET
JWT_SECRET = os.getenv("JWT_SECRET", "change-me-before-deploy")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_MINUTES = 60 * 24 * 7  # токен живёт неделю

CODE_EXPIRE_MINUTES = 15


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    return pwd_context.verify(password, password_hash)


def generate_verification_code() -> str:
    return "".join(random.choices(string.digits, k=6))


def code_expiry() -> datetime:
    return datetime.utcnow() + timedelta(minutes=CODE_EXPIRE_MINUTES)


def create_access_token(subject: str) -> str:
    expire = datetime.utcnow() + timedelta(minutes=JWT_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> str | None:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload.get("sub")
    except Exception:
        return None
