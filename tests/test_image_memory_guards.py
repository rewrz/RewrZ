"""图片解码内存保护相关测试。"""

import io
import threading
import time
from pathlib import Path

import pytest
from PIL import Image, JpegImagePlugin

from rewrz import main as main_module
from rewrz.core import media_processor as media_processor_module
from rewrz.core import thumbnail_service
from rewrz.core.media_processor import MediaProcessor
from rewrz.core.thumbnail_service import ThumbnailPreset, ThumbnailServiceError, _generate_variant_file


def _image_bytes(size: tuple[int, int], fmt: str) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, (90, 140, 200)).save(buffer, fmt)
    return buffer.getvalue()


def _spy_jpeg_draft(monkeypatch):
    calls: list[tuple[str, tuple[int, int]]] = []
    original_draft = JpegImagePlugin.JpegImageFile.draft

    def _draft(self, mode, size):
        calls.append((mode, size))
        return original_draft(self, mode, size)

    monkeypatch.setattr(JpegImagePlugin.JpegImageFile, "draft", _draft)
    return calls


def _wait_until(predicate, timeout: float = 3.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return False


def _prefetch_inflight_empty() -> bool:
    with main_module._ARTICLE_API_CACHE_PREFETCH_LOCK:
        return not main_module._ARTICLE_API_CACHE_PREFETCH_INFLIGHT


def test_article_cover_prefetch_limits_concurrency(monkeypatch, tmp_path):
    release = threading.Event()
    started = threading.Event()
    state = {"active": 0, "max_active": 0, "calls": 0}
    state_lock = threading.Lock()

    def fake_resolve(**kwargs):
        with state_lock:
            state["active"] += 1
            state["max_active"] = max(state["max_active"], state["active"])
            state["calls"] += 1
        started.set()
        release.wait(5)
        with state_lock:
            state["active"] -= 1
        return "", True

    class FakeDB:
        def close(self):
            pass

    monkeypatch.setattr(main_module, "_resolve_cached_remote_article_image", fake_resolve)
    monkeypatch.setattr(main_module, "_ensure_article_api_cache_dir", lambda: tmp_path)
    monkeypatch.setattr(main_module, "_load_article_api_cache_index", lambda db: {})
    monkeypatch.setattr(main_module, "_upsert_runtime_setting", lambda *args, **kwargs: None)
    monkeypatch.setattr(main_module.db_manager, "reload_if_needed", lambda: None)
    monkeypatch.setattr(main_module.db_manager, "get_session", lambda: FakeDB())
    monkeypatch.setattr(
        main_module,
        "_ARTICLE_API_CACHE_PREFETCH_SEMAPHORE",
        threading.BoundedSemaphore(1),
    )
    with main_module._ARTICLE_API_CACHE_PREFETCH_LOCK:
        main_module._ARTICLE_API_CACHE_PREFETCH_INFLIGHT.clear()

    def schedule(seed: str) -> None:
        main_module._schedule_article_api_cache_prefetch(
            seed_value=seed,
            fallback_api_url="https://example.com/{seed}",
            cache_ttl_minutes=60,
        )

    try:
        schedule("a")
        assert started.wait(2)
        # 唯一名额已被占用，后续预取应直接放弃
        schedule("b")
        schedule("c")
        time.sleep(0.2)
        assert state["calls"] == 1
        assert state["max_active"] == 1
    finally:
        release.set()

    assert _wait_until(_prefetch_inflight_empty)
    assert state["max_active"] == 1

    # 任务结束会归还名额，后续预取仍可继续（重试规避名额归还与 inflight 清理的瞬时竞争）
    deadline = time.monotonic() + 3
    while state["calls"] < 2 and time.monotonic() < deadline:
        schedule("d")
        time.sleep(0.05)
    assert state["calls"] == 2
    assert _wait_until(_prefetch_inflight_empty)
    assert state["max_active"] == 1


def test_article_cover_jpeg_uses_decode_time_draft(monkeypatch):
    calls = _spy_jpeg_draft(monkeypatch)

    compressed = main_module._compress_article_cache_image(_image_bytes((400, 300), "JPEG"))

    assert calls == [("RGB", (main_module._ARTICLE_API_CACHE_MAX_WIDTH,) * 2)]
    assert compressed
    with Image.open(io.BytesIO(compressed)) as image:
        assert image.width <= main_module._ARTICLE_API_CACHE_MAX_WIDTH
        assert image.height <= main_module._ARTICLE_API_CACHE_MAX_WIDTH


def test_article_cover_oversize_image_rejected_before_decode(monkeypatch):
    monkeypatch.setattr(main_module, "_ARTICLE_API_CACHE_MAX_PIXELS", 100)

    def fail_thumbnail(self, *args, **kwargs):
        raise AssertionError("超大图片不应进入解码与缩图流程")

    monkeypatch.setattr(Image.Image, "thumbnail", fail_thumbnail)

    assert main_module._compress_article_cache_image(_image_bytes((20, 20), "PNG")) is None


def test_media_processor_rejects_oversize_before_decode(monkeypatch, tmp_path, test_db):
    monkeypatch.setattr(media_processor_module, "_DEFAULT_MAX_IMAGE_PIXELS", 100)

    def fail_transpose(*args, **kwargs):
        raise AssertionError("超大图片不应触发全尺寸解码")

    monkeypatch.setattr(media_processor_module.ImageOps, "exif_transpose", fail_transpose)

    source = tmp_path / "oversize.png"
    Image.new("RGB", (20, 20), (10, 20, 30)).save(source)
    processor = MediaProcessor(test_db)

    result = processor.process_image(str(source), str(tmp_path / "out.jpg"), format="JPEG")

    assert result["success"] is False
    assert "像素" in result["error"]


def test_media_processor_uses_exif_transpose_in_place(monkeypatch, tmp_path, test_db):
    calls = _spy_jpeg_draft(monkeypatch)
    transpose_calls: list[bool] = []
    original_transpose = media_processor_module.ImageOps.exif_transpose

    def _transpose(image, in_place=False):
        transpose_calls.append(in_place)
        return original_transpose(image, in_place=in_place)

    monkeypatch.setattr(media_processor_module.ImageOps, "exif_transpose", _transpose)

    source = tmp_path / "photo.jpg"
    source.write_bytes(_image_bytes((400, 300), "JPEG"))
    processor = MediaProcessor(test_db)

    result = processor.process_image(
        str(source),
        str(tmp_path / "out.jpg"),
        max_size=(2048, 2048),
        format="JPEG",
    )

    assert result["success"] is True
    assert calls == [("RGB", (2048, 2048))]
    assert transpose_calls == [True]


def test_thumbnail_rejects_oversize_before_decode(monkeypatch, tmp_path):
    def fail_transpose(*args, **kwargs):
        raise AssertionError("超限图片不应触发全尺寸解码")

    monkeypatch.setattr(thumbnail_service.ImageOps, "exif_transpose", fail_transpose)

    source = tmp_path / "oversize.png"
    Image.new("RGB", (1100, 1100), (10, 20, 30)).save(source)
    preset = ThumbnailPreset("test", "cover", 100, 100, 80)

    with pytest.raises(ThumbnailServiceError) as exc_info:
        _generate_variant_file(
            source,
            tmp_path / "out.jpg",
            preset,
            1,
            "jpg",
            megapixel_limit=1,
        )

    assert exc_info.value.error_code == "source_too_large"


def test_thumbnail_jpeg_uses_decode_time_draft(monkeypatch, tmp_path):
    calls = _spy_jpeg_draft(monkeypatch)

    source = tmp_path / "photo.jpg"
    source.write_bytes(_image_bytes((400, 300), "JPEG"))
    output = tmp_path / "variant.jpg"
    preset = ThumbnailPreset("test", "cover", 100, 100, 80)

    _generate_variant_file(source, output, preset, 1, "jpg", megapixel_limit=25)

    assert calls == [("RGB", (100, 100))]
    assert output.exists()


def test_sqlite_pool_defaults_keep_read_concurrency(monkeypatch, tmp_path):
    from rewrz.core.config import DynamicSettings

    monkeypatch.setenv("REWRZ_ENV_FILE", str(tmp_path / "missing.env"))
    monkeypatch.delenv("DB_POOL_SIZE", raising=False)
    monkeypatch.delenv("DB_MAX_OVERFLOW", raising=False)

    monkeypatch.setenv("DATABASE_URL", "sqlite:///./data/test.db")
    sqlite_settings = DynamicSettings()
    assert sqlite_settings.DB_POOL_SIZE == 10
    assert sqlite_settings.DB_MAX_OVERFLOW == 10
    assert sqlite_settings.SQLITE_CACHE_SIZE_KIB == 1024
    assert sqlite_settings.SQLITE_SYNCHRONOUS == "NORMAL"

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@127.0.0.1/db")
    network_settings = DynamicSettings()
    assert network_settings.DB_POOL_SIZE == 10
    assert network_settings.DB_MAX_OVERFLOW == 20


def test_sqlite_pragmas_bound_cache_and_reduce_fsync(monkeypatch, tmp_path):
    from sqlalchemy import create_engine, text

    from rewrz.core import database as database_module

    monkeypatch.setattr(database_module.settings, "SQLITE_CACHE_SIZE_KIB", 1024, raising=False)
    monkeypatch.setattr(database_module.settings, "SQLITE_SYNCHRONOUS", "NORMAL", raising=False)
    monkeypatch.setattr(database_module.settings, "SQLITE_JOURNAL_MODE", "WAL", raising=False)
    monkeypatch.setattr(database_module.settings, "SQLITE_BUSY_TIMEOUT_MS", 30000, raising=False)

    engine = create_engine(f"sqlite:///{tmp_path / 'pragma.db'}")
    database_module.db_manager._configure_sqlite(engine)
    try:
        with engine.connect() as connection:
            assert connection.execute(text("PRAGMA cache_size")).scalar() == -1024
            assert connection.execute(text("PRAGMA synchronous")).scalar() == 1
            assert str(connection.execute(text("PRAGMA journal_mode")).scalar()).lower() == "wal"
            assert connection.execute(text("PRAGMA busy_timeout")).scalar() == 30000
    finally:
        engine.dispose()


def test_file_hash_cache_is_bounded(monkeypatch, tmp_path):
    from rewrz.api import media as media_api

    monkeypatch.setattr(media_api, "FILE_HASH_CACHE_MAX_ENTRIES", 2)
    media_api.FILE_HASH_CACHE.clear()
    try:
        for index in range(3):
            target = tmp_path / f"hash-{index}.bin"
            target.write_bytes(b"same-content")
            media_api._compute_sha256_from_file(target)
        assert len(media_api.FILE_HASH_CACHE) <= 2
    finally:
        media_api.FILE_HASH_CACHE.clear()


def test_ip_geo_cache_is_bounded(monkeypatch):
    from rewrz.core import ip_geo

    monkeypatch.setattr(ip_geo, "_IP_GEO_CACHE_MAX_ENTRIES", 2)
    monkeypatch.setattr(ip_geo, "_lookup_ip_api", lambda ip: "测试位置")
    monkeypatch.setattr(ip_geo, "_lookup_ipwhois", lambda ip: None)
    ip_geo._IP_GEO_CACHE.clear()
    try:
        for ip_text in ("8.8.8.8", "1.1.1.1", "9.9.9.9"):
            assert ip_geo.lookup_ip_location(ip_text) == "测试位置"
        assert len(ip_geo._IP_GEO_CACHE) <= 2
    finally:
        ip_geo._IP_GEO_CACHE.clear()
