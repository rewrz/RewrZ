from types import SimpleNamespace

from rewrz.core.content_access import render_markdown_with_hide_blocks
from rewrz.core.content_utils import (
    get_effective_content_html,
    get_effective_plain_text,
    render_markdown_html,
    strip_empty_paragraphs,
)
from rewrz.core.micro_text import _render_micro_inline_text, enhance_micro_html, extract_micro_tags, strip_micro_tags
from rewrz.core.template_filters import post_summary_text_filter


def test_get_effective_plain_text_renders_markdown_before_stripping_html() -> None:
    markdown_content = "这是一个 #测试 例子"

    plain_text = get_effective_plain_text(markdown_content, "")

    assert plain_text == "这是一个 #测试 例子"
    assert "href=" not in plain_text
    assert "<a" not in plain_text


def test_strip_empty_paragraphs_removes_editor_blank_lines() -> None:
    html_content = '<p>第一段</p><p><br></p><p>&nbsp;</p><p><img src="/media/a.png"></p>'

    cleaned = strip_empty_paragraphs(html_content)

    assert "<br>" not in cleaned
    assert "&nbsp;" not in cleaned
    assert '<img src="/media/a.png">' in cleaned


def test_get_effective_content_html_strips_empty_paragraphs() -> None:
    html_content = "<p>第一段</p><p><br></p><p>第二段</p>"

    rendered = get_effective_content_html("", html_content)

    assert rendered == "<p>第一段</p><p>第二段</p>"


def test_render_markdown_html_restores_escaped_tildes() -> None:
    rendered = render_markdown_html(r"测试\~\~ 和 \~单个\~")

    assert "\\~" not in rendered
    assert "测试~~ 和 ~单个~" in rendered


def test_render_markdown_html_supports_strikethrough() -> None:
    rendered = render_markdown_html("~~删除线~~")

    assert "<del>删除线</del>" in rendered


def test_hide_block_inside_directive_keeps_layout() -> None:
    markdown_content = ":::notice warn\n\n[hide]\n隐藏内容\n[/hide]\n\n:::\n\n公开段落"

    rendered = render_markdown_with_hide_blocks(
        markdown_content,
        post_id=1,
        can_view_hidden=False,
    )

    assert ":::notice" not in rendered
    assert "md-block-notice" in rendered
    assert "content-hide-placeholder" in rendered


def test_hide_block_unlocked_renders_inside_directive() -> None:
    markdown_content = ":::notice warn\n\n[hide]\n隐藏内容\n[/hide]\n\n:::"

    rendered = render_markdown_with_hide_blocks(
        markdown_content,
        post_id=1,
        can_view_hidden=True,
    )

    assert "隐藏内容" in rendered
    assert "md-block-notice" in rendered
    assert "content-hide-placeholder" not in rendered


def test_render_markdown_html_supports_indented_directive() -> None:
    rendered = render_markdown_html("  :::notice info\n\n  提示内容\n\n  :::")

    assert "md-block-notice" in rendered
    assert ":::notice" not in rendered


def test_render_markdown_html_ignores_directive_in_tilde_fence() -> None:
    rendered = render_markdown_html("~~~markdown\n\n:::notice\n示例\n:::\n\n~~~")

    assert "md-block-notice" not in rendered
    assert ":::notice" in rendered


def test_interview_block_renders_question_and_answer() -> None:
    rendered = render_markdown_html(
        ":::interview\n\n**问：** 请介绍一下项目。\n\n**答：** 这是一个写作博客。\n\n:::"
    )

    assert "md-block-interview" in rendered
    assert "is-question" in rendered
    assert "is-answer" in rendered
    assert "请介绍一下项目。" in rendered
    assert "这是一个写作博客。" in rendered


def test_interview_block_supports_named_roles() -> None:
    rendered = render_markdown_html(
        ":::interview\n\n:::question 张三\n在做什么？\n:::\n\n:::answer 李四\n写代码。\n:::\n\n:::"
    )

    assert "md-block-interview" in rendered
    assert "张三" in rendered
    assert "李四" in rendered
    assert "is-question" in rendered
    assert "is-answer" in rendered


def test_interview_block_supports_spaced_role_names() -> None:
    rendered = render_markdown_html(
        ":::interview\n\n:::answer 首席产品经理 张伟\n结论是保留版式块。\n:::\n\n:::"
    )

    assert "md-interview-item is-answer" in rendered
    assert "首席产品经理 张伟" in rendered
    assert "结论是保留版式块。" in rendered


def test_chat_block_renders_bubbles_with_media() -> None:
    rendered = render_markdown_html(
        ":::chat\n\n**我：** 在吗？\n\n**对方：** 在的 ![表情包](/media/x.png)\n\n:::"
    )

    assert "md-block-chat" in rendered
    assert "is-right" in rendered
    assert "is-left" in rendered
    assert "在吗？" in rendered
    assert "<img" in rendered


def test_chat_block_supports_timestamp_speaker() -> None:
    rendered = render_markdown_html(":::chat\n\n**我（10:30）：** 晚点聊\n\n:::")

    assert "md-block-chat" in rendered
    assert "晚点聊" in rendered
    assert "10:30" not in rendered


def test_chat_block_renders_time_system_and_rich_messages() -> None:
    rendered = render_markdown_html(
        ":::chat\n\n"
        "[时间] 昨天 14:30\n\n"
        "[系统] 你已添加了对方为好友\n\n"
        "**我：** 在吗？\n\n"
        "**对方：** 在的\n\n"
        "**对方：** 刚看到\n\n"
        "**对方：** [文件] 季度报告.pdf\n\n"
        "**对方：** [链接] 项目主页 | https://example.com\n\n"
        "**对方：** ![表情包](/media/x.png)\n\n"
        ":::"
    )

    assert 'md-chat-time">昨天 14:30' in rendered
    assert 'md-chat-system">你已添加了对方为好友' in rendered
    assert "md-chat-file" in rendered
    assert "季度报告.pdf" in rendered
    assert "md-chat-link" in rendered
    assert "is-image" in rendered
    # 同一人连续发言只保留第一组头像与名字
    assert rendered.count("md-chat-avatar") == 2


def test_chat_block_keeps_long_speaker_names_inside_bubbles() -> None:
    rendered = render_markdown_html(
        ":::chat\n\n**产品经理张伟：** 名字很长也不会破版。\n\n:::"
    )

    assert "md-chat-avatar" in rendered
    assert ">产</div>" in rendered
    assert "md-chat-name" in rendered
    assert "产品经理张伟" in rendered
    assert "名字很长也不会破版。" in rendered


def test_interview_block_shows_initial_and_full_role_name() -> None:
    rendered = render_markdown_html(
        ":::interview\n\n:::question 首席产品经理张伟\n重点是什么？\n:::\n\n:::"
    )

    assert "md-interview-role" in rendered
    assert ">首</span>" in rendered
    assert "md-interview-name" in rendered
    assert "首席产品经理张伟" in rendered
    assert "重点是什么？" in rendered


def test_chat_block_does_not_treat_urls_or_time_as_speakers() -> None:
    rendered = render_markdown_html(
        ":::chat\n\n**对方：** 看这个\nhttps://example.com/a\n\n"
        "[时间] 14:30\n今天下雨了\n\n10:30 开会\n\n:::"
    )

    assert "https://example.com/a" in rendered
    assert ">H</div>" not in rendered
    assert "md-chat-name\">https" not in rendered
    assert 'md-chat-time">14:30' in rendered
    assert "md-chat-name\">10" not in rendered
    assert "10:30 开会" in rendered


def test_chat_block_supports_tight_colon_for_common_roles() -> None:
    rendered = render_markdown_html(":::chat\n\n我：在吗\n\n对方：在的\n\n:::")

    assert rendered.count("md-chat-avatar") == 2
    assert "is-right" in rendered
    assert "md-chat-name\">对方" in rendered
    assert "在吗" in rendered
    assert "在的" in rendered


def test_chat_block_keeps_unruled_colon_inside_message() -> None:
    rendered = render_markdown_html(":::chat\n\n我的意思是：这句其实是正文。\n\n:::")

    # 冒号后没有空格、也不是常见对话角色，按普通消息处理，不生成气泡名字
    assert "md-chat-name" not in rendered
    assert "我的意思是：这句其实是正文。" in rendered


def test_chat_block_link_message_falls_back_on_unsafe_protocol() -> None:
    rendered = render_markdown_html(
        ":::chat\n\n**我：** [链接] 点我 | javascript:alert(1)\n\n"
        "**我：** [链接] 项目主页 | https://example.com\n\n:::"
    )

    assert "javascript:" not in rendered
    assert 'href="https://example.com"' in rendered
    assert "点我" in rendered


def test_chat_block_keeps_nested_directive_content() -> None:
    rendered = render_markdown_html(
        ":::chat\n\n**我：** 你好\n\n:::gallery\n![配图](/media/a.png)\n\n:::\n\n:::"
    )

    assert "md-chat-embed" in rendered
    assert "md-block-gallery" in rendered
    assert "/media/a.png" in rendered


def test_interview_block_keeps_nested_directive_content() -> None:
    rendered = render_markdown_html(
        ":::interview\n\n**问：** 你好\n\n:::quote\n引用一段\n\n:::\n\n:::"
    )

    assert "is-question" in rendered
    assert "md-block-quote" in rendered
    assert "引用一段" in rendered


def test_columns_keeps_content_outside_left_right_blocks() -> None:
    rendered = render_markdown_html(
        ":::columns\n\n:::left\n左列内容\n:::\n\n:::right\n右列内容\n:::\n\n普通说明\n\n:::"
    )

    assert "左列内容" in rendered
    assert "右列内容" in rendered
    assert "普通说明" in rendered


def test_task_list_checkbox_attributes_survive_sanitizing() -> None:
    rendered = render_markdown_html("- [x] 已完成\n- [ ] 待办")

    assert 'class="task-list-checkbox"' in rendered
    assert "checked" in rendered
    assert "disabled" in rendered


def test_markdown_output_blocks_script_and_event_attributes() -> None:
    rendered = render_markdown_html(
        '<p>正文</p><script>alert(1)</script><img src="x" onerror="alert(1)">'
    )

    assert "<script" not in rendered
    assert "onerror" not in rendered
    assert "alert(1)" not in rendered


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
