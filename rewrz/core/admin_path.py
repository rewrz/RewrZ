"""后台路径辅助工具。"""

from fastapi import Request

from .config import settings


def normalize_admin_path(raw_value: str | None) -> str:
    """统一规范后台路径格式。"""
    normalized = str(raw_value or "").strip() or "/admin"
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if normalized != "/":
        normalized = normalized.rstrip("/")
    return normalized or "/admin"


def get_admin_path() -> str:
    """获取当前生效的后台路径。"""
    return normalize_admin_path(getattr(settings, "ADMIN_PATH", "/admin"))


def get_request_admin_path(request: Request | None) -> str:
    """获取当前请求应使用的后台路径。"""
    if request is not None:
        request_state = getattr(request, "state", None)
        state_path = getattr(request_state, "admin_path", "") if request_state is not None else ""
        if str(state_path or "").strip():
            return normalize_admin_path(state_path)
    return get_admin_path()
