from __future__ import annotations

from datetime import datetime

from rewrz.core.cache import clear_cache, cache_key_for_setting
from rewrz.core.public_metrics_cache import (
    HOMEPAGE_STATS_CACHE_KEY,
    build_format_archive_cache_key,
    get_format_archive_stats_snapshot,
    get_homepage_stats_snapshot,
)
from rewrz.models.setting import Setting


def test_homepage_stats_snapshot_uses_cache_until_expired(test_db):
    call_count = {"value": 0}

    def loader(_db):
        call_count["value"] += 1
        return {
            "categories_count": 3,
            "tags_count": 4,
            "comments_count": 5,
            "total_views": 6,
        }

    first = get_homepage_stats_snapshot(test_db, loader=loader, ttl_seconds=900)
    assert first["cache_hit"] is False
    assert first["total_views"] == 6
    assert call_count["value"] == 1

    second = get_homepage_stats_snapshot(test_db, loader=loader, ttl_seconds=900)
    assert second["cache_hit"] is True
    assert second["total_views"] == 6
    assert call_count["value"] == 1

    cache_setting = test_db.query(Setting).filter(Setting.key == HOMEPAGE_STATS_CACHE_KEY).one()
    cached_value = dict(cache_setting.value)
    cached_payload = dict(cached_value.get("value", {}))
    cached_payload["checked_at_iso"] = "2000-01-01T00:00:00+00:00"
    cache_setting.value = {"value": cached_payload}
    test_db.commit()
    clear_cache(cache_key_for_setting(HOMEPAGE_STATS_CACHE_KEY))

    third = get_homepage_stats_snapshot(test_db, loader=loader, ttl_seconds=900)
    assert third["cache_hit"] is False
    assert call_count["value"] == 2


def test_format_archive_stats_snapshot_uses_cache_until_expired(test_db):
    call_count = {"value": 0}
    cache_key = build_format_archive_cache_key("micro", exclude_format_ids=[2, 3])

    def loader(_db):
        call_count["value"] += 1
        return {
            "micro_interaction_count": 12,
            "format_tag_topic_count": 4,
            "format_category_topic_count": 0,
            "format_hot_tags": [{"slug": "hot", "heat_score": 99}],
        }

    first = get_format_archive_stats_snapshot(test_db, cache_key=cache_key, loader=loader, ttl_seconds=900)
    assert first["cache_hit"] is False
    assert first["micro_interaction_count"] == 12
    assert call_count["value"] == 1

    second = get_format_archive_stats_snapshot(test_db, cache_key=cache_key, loader=loader, ttl_seconds=900)
    assert second["cache_hit"] is True
    assert second["format_hot_tags"][0]["slug"] == "hot"
    assert call_count["value"] == 1

    cache_setting = test_db.query(Setting).filter(Setting.key == cache_key).one()
    cached_value = dict(cache_setting.value)
    cached_payload = dict(cached_value.get("value", {}))
    cached_payload["checked_at_iso"] = "2000-01-01T00:00:00+00:00"
    cache_setting.value = {"value": cached_payload}
    test_db.commit()
    clear_cache(cache_key_for_setting(cache_key))

    third = get_format_archive_stats_snapshot(test_db, cache_key=cache_key, loader=loader, ttl_seconds=900)
    assert third["cache_hit"] is False
    assert call_count["value"] == 2
