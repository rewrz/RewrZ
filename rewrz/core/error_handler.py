"""
错误处理模块

提供统一的错误处理机制，包括：
1. 自定义异常类
2. 全局异常处理器
3. 错误日志记录
4. 本地化错误信息
"""

import logging
import traceback
import json
from typing import Optional
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
import os
from starlette.exceptions import HTTPException as StarletteHTTPException
# 新增导入：FastAPI 与 RequestValidationError
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from .database import get_db
from ..crud import setting as setting_crud

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建错误处理模块的模板目录
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)

DEFAULT_ERROR_HANDLING_CONFIG = {
    "enable_custom_error_pages": False,
    "error_page_template": "default",
    "custom_error_messages": {
        "404": {"title": "页面未找到", "message": "抱歉，您访问的页面不存在。"},
        "500": {"title": "服务器内部错误", "message": "抱歉，服务器遇到了一些问题，请稍后再试。"},
        "403": {"title": "访问被禁止", "message": "抱歉，您没有权限访问此页面。"},
        "400": {"title": "请求错误", "message": "抱歉，您的请求存在问题，请检查后重试。"},
        "422": {"title": "参数验证失败", "message": "请求参数验证失败，请检查输入后重试。"},
    },
    "enable_error_caching": True,
    "error_cache_duration": 3600,
    "enable_error_logging": True,
    "log_level": "INFO",
}


def _load_error_handling_config_from_request(request: Request) -> dict:
    """从数据库加载错误处理配置，加载失败时回退默认值。"""
    config = dict(DEFAULT_ERROR_HANDLING_CONFIG)
    db = getattr(request.state, "db", None)
    db_gen = None

    try:
        if db is None:
            db_gen = get_db()
            db = next(db_gen)
        if db is None:
            return config

        setting = setting_crud.get_setting(db, key="error_handling_config")
        if not setting or not setting.value:
            return config

        saved = setting.value.get("value", {})
        if not isinstance(saved, dict):
            return config

        for key, value in saved.items():
            if key == "custom_error_messages" and isinstance(value, dict):
                merged_messages = dict(config["custom_error_messages"])
                for status_code, msg_data in value.items():
                    if not isinstance(msg_data, dict):
                        continue
                    base_msg = merged_messages.get(status_code, {"title": "", "message": ""})
                    merged_messages[status_code] = {
                        "title": msg_data.get("title", base_msg.get("title", "")),
                        "message": msg_data.get("message", base_msg.get("message", "")),
                    }
                config["custom_error_messages"] = merged_messages
            else:
                config[key] = value

        return config
    except Exception:
        return config
    finally:
        if db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass


class BlogHTTPException(HTTPException):
    """博客系统自定义HTTP异常类"""
    
    def __init__(
        self,
        status_code: int,
        detail: str = None,
        headers: Optional[dict] = None,
        error_code: str = None
    ) -> None:
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.error_code = error_code


class NotFoundError(BlogHTTPException):
    """资源未找到异常"""
    
    def __init__(self, detail: str = "请求的资源未找到", error_code: str = "NOT_FOUND"):
        super().__init__(status_code=404, detail=detail, error_code=error_code)


class InternalServerError(BlogHTTPException):
    """内部服务器错误"""
    
    def __init__(self, detail: str = "服务器内部错误", error_code: str = "INTERNAL_ERROR"):
        super().__init__(status_code=500, detail=detail, error_code=error_code)


class ForbiddenError(BlogHTTPException):
    """禁止访问错误"""
    
    def __init__(self, detail: str = "访问被禁止", error_code: str = "FORBIDDEN"):
        super().__init__(status_code=403, detail=detail, error_code=error_code)


class BadRequestError(BlogHTTPException):
    """错误请求"""
    
    def __init__(self, detail: str = "请求参数错误", error_code: str = "BAD_REQUEST"):
        super().__init__(status_code=400, detail=detail, error_code=error_code)


class ValidationError(BlogHTTPException):
    """验证错误"""
    
    def __init__(self, detail: str = "请求参数验证失败", error_code: str = "VALIDATION_ERROR"):
        super().__init__(status_code=422, detail=detail, error_code=error_code)


async def global_exception_handler(request: Request, exc: Exception):
    """
    全局异常处理器
    
    Args:
        request: 请求对象
        exc: 异常对象
        
    Returns:
        JSONResponse or HTMLResponse: 错误响应
    """
    # 记录错误日志
    log_error(request, exc)
    
    # 根据Accept头判断返回JSON还是HTML
    accept_header = request.headers.get("accept", "")
    
    if "application/json" in accept_header:
        return await _handle_json_response(exc)
    else:
        return await _handle_html_response(request, exc)


async def _handle_json_response(exc: Exception):
    """
    处理JSON响应
    
    Args:
        exc: 异常对象
        
    Returns:
        JSONResponse: JSON格式错误响应
    """
    # 检查是否为HTTP异常（包括FastAPI和Starlette的HTTPException）
    if isinstance(exc, (HTTPException, StarletteHTTPException)):
        # 对于404错误，使用特定的错误代码
        if exc.status_code == 404:
            error_code = "NOT_FOUND"
        elif exc.status_code == 500:
            error_code = "INTERNAL_ERROR"
        elif exc.status_code == 403:
            error_code = "FORBIDDEN"
        elif exc.status_code == 400:
            error_code = "BAD_REQUEST"
        elif exc.status_code == 422:
            error_code = "VALIDATION_ERROR"
        else:
            error_code = getattr(exc, 'error_code', 'HTTP_ERROR')
            
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": error_code,
                    "message": exc.detail,
                    "status_code": exc.status_code
                }
            }
        )
    elif isinstance(exc, BlogHTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": exc.error_code,
                    "message": exc.detail,
                    "status_code": exc.status_code
                }
            }
        )
    else:
        # 未知异常
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误",
                    "status_code": 500
                }
            }
        )


async def _handle_html_response(request: Request, exc: Exception):
    """
    处理HTML响应
    
    Args:
        request: 请求对象
        exc: 异常对象
        
    Returns:
        HTMLResponse: HTML格式错误响应
    """
    error_config = _load_error_handling_config_from_request(request)

    # 根据异常类型选择不同的错误页面
    if isinstance(exc, BlogHTTPException):
        status_code = exc.status_code
        error_message = exc.detail
        error_code = exc.error_code
    elif isinstance(exc, (HTTPException, StarletteHTTPException)):
        status_code = exc.status_code
        error_message = exc.detail
        error_code = getattr(exc, 'error_code', 'HTTP_ERROR')
    else:
        status_code = 500
        error_message = "服务器内部错误"
        error_code = "INTERNAL_ERROR"
    
    # 尝试获取自定义错误消息
    custom_message = await _get_custom_error_message(request, status_code)
    if custom_message:
        error_message = custom_message.get("message", error_message)

    custom_title = custom_message.get("title") if custom_message else None
    error_title = custom_title or f"{status_code} 错误"
    headers = None
    if error_config.get("enable_error_caching", True):
        try:
            cache_duration = max(60, min(int(error_config.get("error_cache_duration", 3600)), 86400))
            headers = {"Cache-Control": f"public, max-age={cache_duration}"}
        except (TypeError, ValueError):
            headers = {"Cache-Control": "public, max-age=3600"}

    # 启用自定义错误页面时，统一使用可配置模板
    if error_config.get("enable_custom_error_pages", False):
        template_variant = error_config.get("error_page_template", "default")
        return templates.TemplateResponse(
            request,
            "errors/error.html",
            {
                "request": request,
                "status_code": status_code,
                "error_title": error_title,
                "error_message": error_message,
                "error_code": error_code,
                "error_page_template": template_variant,
                "site_title": getattr(request.state, "site_title", "RewrZ"),
            },
            status_code=status_code,
            headers=headers,
        )

    # 尝试渲染对应的错误页面模板
    template_name = f"errors/{status_code}.html"
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    
    # 如果特定状态码的模板不存在，使用通用模板
    if not os.path.exists(template_path):
        template_name = "errors/error.html"
        # 检查通用模板是否存在
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            # 如果连通用模板都不存在，返回简单的错误信息
            return HTMLResponse(
                content=f"<h1>错误 {status_code}</h1><p>{error_message}</p>",
                status_code=status_code,
                headers=headers,
            )
    
    try:
        return templates.TemplateResponse(
            request,
            template_name,
            {
                "request": request,
                "status_code": status_code,
                "error_title": error_title,
                "error_message": error_message,
                "error_code": error_code,
                "site_title": getattr(request.state, "site_title", "RewrZ"),
            },
            status_code=status_code,
            headers=headers,
        )
    except Exception as template_exc:
        # 如果模板渲染也失败，返回简单的错误信息
        logger.error(f"模板渲染失败: {str(template_exc)}")
        return HTMLResponse(
            content=f"<h1>错误 {status_code}</h1><p>{error_message}</p>",
            status_code=status_code,
            headers=headers,
        )


async def _get_custom_error_message(request: Request, status_code: int) -> Optional[dict]:
    """
    获取自定义错误消息
    
    Args:
        request: 请求对象
        status_code: HTTP状态码
        
    Returns:
        dict: 自定义错误消息，如果未找到则返回None
    """
    try:
        config = _load_error_handling_config_from_request(request)
        if not config.get("enable_custom_error_pages", False):
            return None
        custom_messages = config.get("custom_error_messages", {})
        message = custom_messages.get(str(status_code))
        return message if isinstance(message, dict) else None
    except Exception as e:
        logger.error(f"获取自定义错误消息失败: {str(e)}")
        return None


def log_error(request: Request, exc: Exception):
    """
    记录错误日志
    
    Args:
        request: 请求对象
        exc: 异常对象
    """
    config = _load_error_handling_config_from_request(request)
    if not config.get("enable_error_logging", True):
        return

    # 依据配置更新日志级别
    log_level_name = str(config.get("log_level", "INFO")).upper()
    log_level_value = getattr(logging, log_level_name, logging.INFO)
    logger.setLevel(log_level_value)

    # 获取请求相关信息
    url = str(request.url)
    method = request.method
    user_agent = request.headers.get('user-agent', 'N/A')
    client_ip = request.client.host if request.client else 'N/A'
    
    # 记录错误详情
    logger.error(
        f"错误详情 - "
        f"状态码: {getattr(exc, 'status_code', 'N/A')}, "
        f"错误代码: {getattr(exc, 'error_code', 'N/A')}, "
        f"错误信息: {str(exc)}, "
        f"请求URL: {url}, "
        f"请求方法: {method}, "
        f"用户代理: {user_agent}, "
        f"客户端IP: {client_ip}"
    )
    
    # 记录堆栈跟踪（仅在开发环境中）
    if os.getenv("ENVIRONMENT", "production") == "development" or log_level_name == "DEBUG":
        logger.error(f"详细堆栈信息:\n{traceback.format_exc()}")


# 本地化错误信息映射
ERROR_MESSAGES = {
    400: "请求参数错误，请检查您的输入",
    401: "未授权访问，请先登录",
    403: "访问被禁止，您没有权限执行此操作",
    404: "页面未找到，您访问的资源不存在",
    405: "请求方法不被允许",
    422: "请求参数验证失败",
    429: "请求过于频繁，请稍后再试",
    500: "服务器内部错误，请稍后再试",
    502: "网关错误，请稍后再试",
    503: "服务暂时不可用，请稍后再试",
    504: "网关超时，请稍后再试"
}


def get_localized_error_message(status_code: int) -> str:
    """
    获取本地化的错误信息
    
    Args:
        status_code: HTTP状态码
        
    Returns:
        str: 本地化错误信息
    """
    return ERROR_MESSAGES.get(status_code, "发生未知错误")

# 暴露响应类，保持对外接口兼容
JSONResponse = JSONResponse
HTMLResponse = HTMLResponse

# 新增：统一注册异常处理器的便捷函数

def register_error_handlers(app: FastAPI) -> None:
    """
    注册全局异常处理器（最小改动整合）。
    - 404、HTTPException 与其它未捕获异常统一交由 global_exception_handler 处理
    - 422 验证异常沿用原有逻辑（根据 Accept 头返回 JSON 或 HTML 模板）
    """
    
    @app.exception_handler(404)
    async def _not_found_exception_handler(request: Request, exc: HTTPException):
        return await global_exception_handler(request, exc)

    @app.exception_handler(Exception)
    async def _global_exception_handler(request: Request, exc: Exception):
        return await global_exception_handler(request, exc)

    @app.exception_handler(HTTPException)
    async def _http_exception_handler(request: Request, exc: HTTPException):
        return await global_exception_handler(request, exc)

    @app.exception_handler(RequestValidationError)
    async def _validation_exception_handler(request: Request, exc: RequestValidationError):
        # 记录验证错误日志
        log_error(request, exc)
        
        # 根据Accept头判断返回JSON还是HTML
        accept_header = request.headers.get("accept", "")
        
        if "application/json" in accept_header:
            return JSONResponse(
                status_code=422,
                content={
                    "error": {
                        "code": "VALIDATION_ERROR",
                        "message": "请求参数验证失败",
                        "details": exc.errors()
                    }
                }
            )
        else:
            # HTML 响应统一走可配置错误页逻辑，确保模板风格/缓存策略一致
            return await _handle_html_response(request, ValidationError("请求参数验证失败"))
