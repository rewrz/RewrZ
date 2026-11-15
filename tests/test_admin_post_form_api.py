"""后台表单字段容错的单元测试。

覆盖后台写接口不能把用户的正常编辑判成参数错误：
- 表单里的空分类值被忽略，而不是整次提交落成 422
- 列表页内联编辑同样忽略空分类值
"""

from __future__ import annotations

from rewrz.api.posts import _normalize_category_ids_for_intent
from rewrz.schemas.post import PostInlineUpdate


def test_normalize_category_ids_ignores_blank_and_invalid_values() -> None:
    normalized = _normalize_category_ids_for_intent(
        ["", "2", "abc", "3", 1, 0, -1],
        "article",
    )

    assert normalized == [1, 2, 3]


def test_normalize_category_ids_drops_everything_for_micro_intent() -> None:
    assert _normalize_category_ids_for_intent(["1", 2], "micro") == []
    assert _normalize_category_ids_for_intent(["1", 2], "poem") == []


def test_inline_update_drops_blank_category_ids() -> None:
    payload = PostInlineUpdate(category_ids=["", "7", "x"])

    assert payload.category_ids == [7]
