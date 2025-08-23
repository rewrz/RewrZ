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

# 配置日志
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# 创建错误处理模块的模板目录
TEMPLATES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates")
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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
    print(f"DEBUG: Handling exception {type(exc).__name__}: {exc}")
    print(f"DEBUG: exc type module: {type(exc).__module__}")
    print(f"DEBUG: HTTPException type: {HTTPException}")
    print(f"DEBUG: StarletteHTTPException type: {StarletteHTTPException}")
    print(f"DEBUG: HTTPException type module: {HTTPException.__module__}")
    print(f"DEBUG: isinstance(exc, HTTPException): {isinstance(exc, HTTPException)}")
    print(f"DEBUG: isinstance(exc, StarletteHTTPException): {isinstance(exc, StarletteHTTPException)}")
    # 根据异常类型选择不同的错误页面
    if isinstance(exc, BlogHTTPException):
        status_code = exc.status_code
        error_message = exc.detail
        error_code = exc.error_code
        print(f"DEBUG: BlogHTTPException - status_code={status_code}, error_message={error_message}, error_code={error_code}")
    elif isinstance(exc, (HTTPException, StarletteHTTPException)):
        status_code = exc.status_code
        error_message = exc.detail
        error_code = getattr(exc, 'error_code', 'HTTP_ERROR')
        print(f"DEBUG: HTTPException - status_code={status_code}, error_message={error_message}, error_code={error_code}")
    else:
        status_code = 500
        error_message = "服务器内部错误"
        error_code = "INTERNAL_ERROR"
        print(f"DEBUG: Other exception - status_code={status_code}, error_message={error_message}, error_code={error_code}")
    
    # 尝试获取自定义错误消息
    custom_message = await _get_custom_error_message(request, status_code)
    if custom_message:
        error_message = custom_message.get("message", error_message)
        # 可以在这里使用自定义标题等
    
    # 尝试渲染对应的错误页面模板
    template_name = f"errors/{status_code}.html"
    template_path = os.path.join(TEMPLATES_DIR, template_name)
    print(f"DEBUG: Template path {template_path} exists: {os.path.exists(template_path)}")
    
    # 如果特定状态码的模板不存在，使用通用模板
    if not os.path.exists(template_path):
        template_name = "errors/error.html"
        # 检查通用模板是否存在
        template_path = os.path.join(TEMPLATES_DIR, template_name)
        if not os.path.exists(template_path):
            # 如果连通用模板都不存在，返回简单的错误信息
            print(f"DEBUG: No template found, returning simple HTML response")
            return HTMLResponse(
                content=f"<h1>错误 {status_code}</h1><p>{error_message}</p>",
                status_code=status_code
            )
    
    try:
        print(f"DEBUG: Rendering template {template_name} with status_code={status_code}")
        return templates.TemplateResponse(
            request,
            template_name,
            {
                "status_code": status_code,
                "error_message": error_message,
                "error_code": error_code
            },
            status_code=status_code
        )
    except Exception as template_exc:
        # 如果模板渲染也失败，返回简单的错误信息
        logger.error(f"模板渲染失败: {str(template_exc)}")
        return HTMLResponse(
            content=f"<h1>错误 {status_code}</h1><p>{error_message}</p>",
            status_code=status_code
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
        # 尝试从数据库获取自定义错误配置
        # 这里需要访问数据库会话，但我们没有直接的访问权限
        # 在实际应用中，可以通过request.state.db访问数据库会话
        # 为了简化，我们返回None
        return None
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
    if os.getenv("ENVIRONMENT", "production") == "development":
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
    return ERROR_MESSAGES.get(status_code, "未知错误")


# 导出常用的响应类，方便其他模块使用
JSONResponse = JSONResponse
HTMLResponse = HTMLResponse