from datetime import datetime, timedelta, timezone
from typing import Optional
import logging
from jose import JWTError, jwt
from passlib.context import CryptContext
from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
import secrets # For CSRF token generation
from starlette.responses import RedirectResponse
from urllib.parse import urlparse

# Configuration for JWT
from .config import settings
from .database import get_db  # 导入get_db函数

# 静音passlib的bcrypt警告
logging.getLogger('passlib').setLevel(logging.ERROR)

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = settings.ACCESS_TOKEN_EXPIRE_MINUTES
CSRF_TOKEN_LENGTH = 32 # Length of CSRF token in bytes

# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# OAuth2 scheme 配置（注意：实际登录端点现在是动态的，格式为 {ADMIN_PATH}/auth）
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth")  # 这只是示例，实际使用动态路径

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

async def get_token_from_cookie(request: Request):
    token = request.cookies.get("access_token")
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"}
        )
    return token

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=int(settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, str(settings.SECRET_KEY), algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str):
    try:
        payload = jwt.decode(token, str(settings.SECRET_KEY), algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None


def is_user_token_payload_valid(db_user, payload: dict | None) -> bool:
    """校验令牌载荷是否仍与当前用户状态一致。"""
    if db_user is None or payload is None:
        return False
    if not bool(getattr(db_user, "is_active", False)):
        return False

    payload_version_raw = payload.get("token_version", 1)
    try:
        payload_version = int(payload_version_raw)
    except (TypeError, ValueError):
        return False

    user_version = int(getattr(db_user, "token_version", 1) or 1)
    return payload_version == user_version


def should_use_secure_cookie(request: Request) -> bool:
    """根据配置和请求上下文决定是否启用 Secure Cookie。"""
    if bool(getattr(settings, "COOKIE_SECURE", False)):
        return True
    forwarded_proto = str(request.headers.get("x-forwarded-proto", "")).split(",")[0].strip().lower()
    if forwarded_proto == "https":
        return True
    return str(getattr(request.url, "scheme", "")).lower() == "https"

# Dependency to get current user (for protected routes)
async def get_current_user(token: str = Depends(get_token_from_cookie), db: Session = Depends(get_db)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    payload = decode_access_token(token)
    if payload is None:
        raise credentials_exception
    
    user_id = payload.get("sub")
    if user_id is None:
        raise credentials_exception
    
    from ..crud import user as crud_user
    from ..schemas import User as UserSchema # 导入Pydantic User schema
    
    db_user = crud_user.get_user(db, user_id=int(user_id))
    if not is_user_token_payload_valid(db_user, payload):
        raise credentials_exception
    
    # 确保use_gravatar是字符串类型，以匹配schema
    if db_user.use_gravatar is None:
        db_user.use_gravatar = "auto" # 或者其他默认字符串值
    
    # 显式地将SQLAlchemy模型对象转换为Pydantic schema对象
    return UserSchema.model_validate(db_user)

def generate_csrf_token() -> str:
    """Generates a URL-safe CSRF token."""
    return secrets.token_urlsafe(CSRF_TOKEN_LENGTH)

def verify_csrf_token(request: Request, form_csrf_token: str):
    """Verifies the CSRF token from the form against the one in the session."""
    session_csrf_token = request.session.get("csrf_token")
    if not session_csrf_token or not secrets.compare_digest(session_csrf_token, form_csrf_token):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="CSRF 令牌缺失或不匹配。"
        )


def is_admin_user(user) -> bool:
    role = str(getattr(user, "role", "") or "").strip().lower()
    return role in {"admin", "super_admin"}


def ensure_admin_user(user) -> None:
    if not is_admin_user(user):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")


def get_client_ip(request: Request) -> str:
    forwarded = str(request.headers.get("x-forwarded-for", "") or "").strip()
    if forwarded:
        return forwarded.split(",")[0].strip()[:128]

    real_ip = str(request.headers.get("x-real-ip", "") or "").strip()
    if real_ip:
        return real_ip[:128]

    client = getattr(request, "client", None)
    host = getattr(client, "host", "") if client is not None else ""
    return str(host or "")[:128]


def get_request_origin(request: Request) -> str:
    origin = str(request.headers.get("origin", "") or "").strip()
    if origin:
        return origin
    referer = str(request.headers.get("referer", "") or "").strip()
    if not referer:
        return ""
    parsed = urlparse(referer)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"
