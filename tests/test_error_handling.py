"""
错误处理测试模块
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from rewrz import main as main_module
from rewrz.crud import post as crud_post
from rewrz.core.error_handler import (
    BlogHTTPException, 
    NotFoundError, 
    InternalServerError,
    ForbiddenError,
    BadRequestError,
    ValidationError,
    global_exception_handler
)
from rewrz.main import app

client = TestClient(app)


def _set_installation_complete(monkeypatch, value: bool) -> None:
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: value),
    )


def test_custom_exceptions():
    """测试自定义异常类"""
    # 测试 NotFoundError
    not_found = NotFoundError("测试未找到错误")
    assert not_found.status_code == 404
    assert not_found.detail == "测试未找到错误"
    assert not_found.error_code == "NOT_FOUND"
    
    # 测试 InternalServerError
    internal_error = InternalServerError("测试内部错误")
    assert internal_error.status_code == 500
    assert internal_error.detail == "测试内部错误"
    assert internal_error.error_code == "INTERNAL_ERROR"
    
    # 测试 ForbiddenError
    forbidden_error = ForbiddenError("测试禁止访问错误")
    assert forbidden_error.status_code == 403
    assert forbidden_error.detail == "测试禁止访问错误"
    assert forbidden_error.error_code == "FORBIDDEN"
    
    # 测试 BadRequestError
    bad_request_error = BadRequestError("测试错误请求")
    assert bad_request_error.status_code == 400
    assert bad_request_error.detail == "测试错误请求"
    assert bad_request_error.error_code == "BAD_REQUEST"
    
    # 测试 ValidationError
    validation_error = ValidationError("测试验证错误")
    assert validation_error.status_code == 422
    assert validation_error.detail == "测试验证错误"
    assert validation_error.error_code == "VALIDATION_ERROR"


def test_404_error_page(monkeypatch):
    """测试404错误页面"""
    _set_installation_complete(monkeypatch, True)
    monkeypatch.setattr(crud_post, "get_post_by_slug", lambda db, slug: None)
    response = client.get("/non-existent-page")
    assert response.status_code == 404
    assert "404" in response.text
    assert "页面未找到" in response.text
    assert main_module.settings.ADMIN_PATH.rstrip("/") not in response.text


def test_500_error_page():
    """测试500错误页面"""
    # 这个测试需要模拟一个内部服务器错误
    # 在实际应用中，我们可以通过创建一个故意抛出异常的路由来测试
    pass


def test_error_handler_json_response(monkeypatch):
    """测试JSON格式错误响应"""
    # 测试自定义异常的JSON响应
    _set_installation_complete(monkeypatch, True)
    monkeypatch.setattr(crud_post, "get_post_by_slug", lambda db, slug: None)
    headers = {"Accept": "application/json"}
    response = client.get("/non-existent-page", headers=headers)
    assert response.status_code == 404
    json_data = response.json()
    assert "error" in json_data
    assert json_data["error"]["code"] == "NOT_FOUND"
    assert json_data["error"]["status_code"] == 404


def test_public_error_page_does_not_redirect_to_admin_login(monkeypatch):
    """公共错误页不能暴露后台入口。"""
    _set_installation_complete(monkeypatch, True)
    monkeypatch.setattr(crud_post, "get_post_by_slug", lambda db, slug: None)
    response = client.get("/totally-missing-page", follow_redirects=False)
    assert response.status_code == 404
    assert "location" not in response.headers
    assert main_module.settings.ADMIN_PATH.rstrip("/") not in response.text


if __name__ == "__main__":
    pytest.main([__file__])
