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


def test_micro_tags_ignore_url_fragments_and_keep_links_intact() -> None:
    content = "参考 https://example.com/page#section 与 docs/guide#install 两处"

    assert extract_micro_tags(content) == []
    assert strip_micro_tags(content) == content


def test_micro_tags_ignore_markdown_anchor_links() -> None:
    content = "见 [目录](#section) 与 <a href=\"#top\">顶部</a>"

    assert extract_micro_tags(content) == []
    assert strip_micro_tags(content) == content


def test_micro_tags_ignore_code_spans() -> None:
    content = "运行 `#npm# install`，再看 ```\n#代码块\n``` 最后 #真标签"

    tags = extract_micro_tags(content)
    stripped = strip_micro_tags(content)

    assert tags == ["真标签"]
    assert "#npm" in stripped
    assert "#代码块" in stripped
    assert "#真标签" not in stripped


def test_micro_tags_ignore_ascii_adjacent_hash() -> None:
    # C#、F# 这类英文紧跟的井号不应被识别为标签。
    assert extract_micro_tags("用 C# 写代码，F# 也可以") == []


def test_micro_tags_support_fullwidth_marker() -> None:
    content = "＃全角标签 正文内容"

    assert extract_micro_tags(content) == ["全角标签"]
    assert strip_micro_tags(content) == "正文内容"


def test_micro_tags_require_terminator_boundary() -> None:
    # 结束符（空白、标点、闭合井号）都能正确截断标签。
    assert extract_micro_tags("#网站# 和 #网站，以及 #网站 ") == ["网站"]


def test_micro_tag_without_separator_consumes_adjacent_chinese() -> None:
    # 中文没有分隔符时，#网站的时候 会整体成为一个标签；补上结束符才会只取“网站”。
    assert extract_micro_tags("#网站的时候") == ["网站的时候"]
    assert extract_micro_tags("#网站，的时候") == ["网站"]


def test_strip_micro_tags_keeps_tags_beyond_limit() -> None:
    content = " ".join(f"#标签{index}" for index in range(1, 11))

    tags = extract_micro_tags(content)
    stripped = strip_micro_tags(content)

    assert tags == [f"标签{index}" for index in range(1, 9)]
    # 超出上限的标签不应被创建，正文里也要原样保留，避免内容被静默吞掉。
    assert stripped == "#标签9 #标签10"
