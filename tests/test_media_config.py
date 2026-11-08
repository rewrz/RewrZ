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


def test_thumbnail_runtime_settings_defaults(monkeypatch):
    from rewrz.core import thumbnail_service as ts

    monkeypatch.setattr(ts, "_get_cached_setting_value", lambda db, key, default: default)
    config = ts.get_thumbnail_runtime_settings(object())

    assert config["enabled"] is True
    assert config["allowed_dpr"] == {1, 2}
    assert {"auto", "webp", "avif", "jpg", "png"} <= config["allowed_fmt"]
    assert config["default_fmt"] == "auto"
    assert config["generate_timeout_ms"] == 4000
    assert config["cleanup_interval_hours"] == 168


def test_thumbnail_runtime_settings_honors_configured_values(monkeypatch):
    from rewrz.core import thumbnail_service as ts

    values = {
        "thumbnail_enabled": False,
        "thumbnail_allowed_dpr": "1,3",
        "thumbnail_allowed_fmt": "auto,webp",
        "thumbnail_default_fmt": "webp",
        "thumbnail_generate_timeout_ms": 99999,
        "thumbnail_cleanup_interval_hours": 0,
    }
    monkeypatch.setattr(
        ts, "_get_cached_setting_value", lambda db, key, default: values.get(key, default)
    )
    config = ts.get_thumbnail_runtime_settings(object())

    assert config["enabled"] is False
    assert config["allowed_dpr"] == {1, 3}
    assert config["allowed_fmt"] == {"auto", "webp"}
    assert config["default_fmt"] == "webp"
    assert config["generate_timeout_ms"] == 30000
    assert config["cleanup_interval_hours"] == 1


def test_generate_variant_file_honors_deadline(tmp_path):
    import time
    from PIL import Image
    from rewrz.core import thumbnail_service as ts

    source = tmp_path / "source.png"
    Image.new("RGB", (8, 8), (12, 34, 56)).save(source)

    with pytest.raises(ts.ThumbnailServiceError) as error:
        ts._generate_variant_file(
            source_path=source,
            output_path=tmp_path / "variant.jpg",
            preset=ts.DEFAULT_PRESETS["media_lib_card"],
            dpr=1,
            output_fmt="jpg",
            megapixel_limit=25,
            deadline=time.monotonic() - 1,
        )

    assert error.value.status_code == 504
    assert error.value.error_code == "variant_generate_timeout"
    assert not (tmp_path / "variant.jpg").exists()


def test_maybe_cleanup_variant_cache_removes_expired_files(tmp_path, monkeypatch):
    import os
    from rewrz.core import thumbnail_service as ts

    monkeypatch.setattr(ts, "_resolve_cache_root", lambda db: tmp_path)
    monkeypatch.setattr(ts, "_LAST_CLEANUP_CHECK_TS", 0.0)

    expired = tmp_path / "1" / "post_cover" / "old.jpg"
    fresh = tmp_path / "2" / "post_cover" / "new.jpg"
    expired.parent.mkdir(parents=True)
    fresh.parent.mkdir(parents=True)
    expired.write_bytes(b"old")
    fresh.write_bytes(b"new")
    os.utime(expired, (0, 0))

    ts.maybe_cleanup_variant_cache(object(), 1)

    assert not expired.exists()
    assert fresh.exists()
    assert (tmp_path / ".last_cleanup").exists()


def test_thumb_srcset_filter_skips_disallowed_dpr(monkeypatch):
    from rewrz.core import thumbnail_service as ts
    from rewrz.core.template_filters import thumb_srcset_filter

    monkeypatch.setattr(
        ts,
        "_get_cached_setting_value",
        lambda db, key, default: {"thumbnail_allowed_dpr": "1"}.get(key, default),
    )

    srcset = thumb_srcset_filter(225, preset="archive_card", db=object(), dprs="1,2")

    assert srcset.endswith(" 1x")
    assert " 2x" not in srcset


if __name__ == "__main__":
    pytest.main([__file__])