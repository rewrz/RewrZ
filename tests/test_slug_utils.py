from rewrz.core.slug_utils import slugify_with_dots


def test_slugify_with_dots_keeps_version_and_domain_dots() -> None:
    assert slugify_with_dots("Node.js") == "node.js"
    assert slugify_with_dots("v1.2") == "v1.2"
    assert slugify_with_dots("release.2026") == "release.2026"


def test_slugify_with_dots_normalizes_chinese_and_repeated_dots() -> None:
    assert slugify_with_dots("版本.1") == "ban-ben.1"
    assert slugify_with_dots("a..b") == "a.b"


def test_slugify_with_dots_rejects_dot_only_input() -> None:
    assert slugify_with_dots("..") == ""
    assert slugify_with_dots("   ") == ""
