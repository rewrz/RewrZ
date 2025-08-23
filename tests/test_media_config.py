"""
文件上传安全配置测试模块
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from rewrz.core.media_config import (
    get_allowed_file_types,
    get_max_file_size,
    is_file_type_allowed,
    format_file_size
)
from rewrz.crud.setting import update_setting, get_setting

# 导入主应用
from rewrz.main import app

client = TestClient(app)


def test_get_allowed_file_types_default():
    """测试获取默认允许的文件类型"""
    # 测试默认配置
    default_types = get_allowed_file_types()
    assert isinstance(default_types, list)
    assert len(default_types) > 0
    # 检查一些常见的文件类型是否在默认列表中
    common_types = ['image/jpeg', 'image/png', 'image/gif', 'text/plain']
    for file_type in common_types:
        assert file_type in default_types


def test_get_max_file_size_default():
    """测试获取默认最大文件大小"""
    # 测试默认配置
    max_size = get_max_file_size()
    assert isinstance(max_size, int)
    # 默认最大文件大小应该是50MB
    assert max_size == 50 * 1024 * 1024  # 50MB in bytes


def test_is_file_type_allowed():
    """测试文件类型检查功能"""
    # 测试允许的文件类型
    assert is_file_type_allowed('image/jpeg') == True
    assert is_file_type_allowed('image/png') == True
    assert is_file_type_allowed('text/plain') == True
    
    # 测试不允许的文件类型
    assert is_file_type_allowed('application/x-msdownload') == False
    assert is_file_type_allowed('text/x-php') == False


def test_format_file_size():
    """测试文件大小格式化功能"""
    # 测试不同大小的文件
    assert format_file_size(1024) == "1.0 KB"
    assert format_file_size(1024 * 1024) == "1.0 MB"
    assert format_file_size(1024 * 1024 * 1024) == "1.0 GB"
    assert format_file_size(512) == "512.0 B"


# 如果需要测试数据库配置，可以添加以下测试
# 注意：这些测试需要数据库访问权限

def test_media_config_crud():
    """测试媒体配置的CRUD操作"""
    # 这个测试需要数据库会话
    pass


if __name__ == "__main__":
    pytest.main([__file__])