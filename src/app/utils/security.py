import bcrypt
from datetime import datetime, timedelta
from typing import Any, Union
from jose import jwt

from app.config import settings

ALGORITHM = "HS256"

def create_access_token(subject: Union[str, Any], expires_delta: timedelta = None) -> str:
    """Tạo JWT access token."""
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        # JWT_EXPIRATION_TIME trong .env ví dụ '3600s'
        # Parse giây từ chuỗi cấu hình
        try:
            seconds = int(settings.JWT_EXPIRATION_TIME.replace("s", ""))
        except ValueError:
            seconds = 3600
        expire = datetime.utcnow() + timedelta(seconds=seconds)
        
    to_encode = {"exp": expire, "sub": str(subject)}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=ALGORITHM)
    return encoded_jwt

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Kiểm tra mật khẩu thô và mật khẩu đã hash."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Hash mật khẩu bằng Bcrypt."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
