from types import SimpleNamespace

from rewrz.core.content_utils import get_effective_plain_text
from rewrz.core.micro_text import _render_micro_inline_text, enhance_micro_html, extract_micro_tags, strip_micro_tags
from rewrz.core.template_filters import post_summary_text_filter


def test_get_effective_plain_text_renders_markdown_before_stripping_html() -> None:
    markdown_content = "这是一个 #测试 例子"

    plain_text = get_effective_plain_text(markdown_content, "")

    assert plain_text == "这是一个 #测试 例子"
    assert "href=" not in plain_text
    assert "<a" not in plain_text


def test_post_summary_text_filter_strips_html_from_manual_excerpt() -> None:
    post_obj = SimpleNamespace(
        excerpt='<a href="/archives/by-tag/test">#测试</a> 这是一个测试',
        content_markdown="",
        content_html="",
    )

    summary_text = post_summary_text_filter(post_obj, 200)

    assert summary_text == "#测试 这是一个测试"
    assert "href=" not in summary_text
    assert "<a" not in summary_text


def test_strip_micro_tags_removes_topics_but_keeps_mentions() -> None:
    content = "#测试 这是一个 @alice 的动态\n第二行 #标签"

    stripped = strip_micro_tags(content)

    assert stripped == "这是一个 @alice 的动态\n第二行"
    assert "#测试" not in stripped
    assert "#标签" not in stripped
    assert "@alice" in stripped


def test_micro_tag_parsing_supports_inline_topics() -> None:
    content = "句首#话题#继续，正文里再来#第二个话题，收尾#第三个"

    tags = extract_micro_tags(content)
    stripped = strip_micro_tags(content)

    assert tags == ["话题", "第二个话题", "第三个"]
    assert stripped == "句首继续，正文里再来，收尾"


def test_enhance_micro_html_links_inline_mentions_but_skips_email() -> None:
    mention_map = {"alice": "https://example.com/alice"}

    rendered_html, changed = _render_micro_inline_text(
        "句中@alice 可以识别，邮箱 test@example.com 不应识别。",
        db=None,
        mention_link_map=mention_map,
    )

    assert changed is True
    assert 'class="micro-mention-link"' in rendered_html
    assert "@alice" in rendered_html
    assert "test@example.com" in rendered_html
    assert 'href="https://example.com/alice"' in rendered_html
    assert 'href="https://example.com/example"' not in rendered_html


def test_render_micro_inline_text_prefers_external_mention_map() -> None:
    mention_map = {"终极改写": "https://weibo.example.com/u/rewrz"}

    rendered_html, changed = _render_micro_inline_text(
        "这里提到@终极改写",
        db=None,
        mention_link_map=mention_map,
    )

    assert changed is True
    assert '@终极改写</a>' in rendered_html
    assert 'href="https://weibo.example.com/u/rewrz"' in rendered_html


def test_enhance_micro_html_merges_markdown_style_external_mentions() -> None:
    enhanced_html = enhance_micro_html('<p>@<a href="https://x.com/chuanpu">特朗普</a>你家喊你回家吃饭。</p>')

    assert '@特朗普</a>' in enhanced_html
    assert 'class="micro-mention-link"' in enhanced_html
    assert '>特朗普</a>' not in enhanced_html
