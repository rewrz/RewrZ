"""
安装向导「初始内容设置」的单一数据源。

约定：
- 步骤页预览与实际创建共用同一份定义，避免前端硬编码与后端数据漂移。
- 内容类型（formats）直接复用 `content_intents` 的权威规则，
  与项目内容模型保持一致：`post_type` 只有 post/page，
  article/micro/poem 属于内容意图，图片/视频/音频属于媒体附件层。
"""

from __future__ import annotations

from typing import Final

from .content_intents import INTENT_NAME_MAP, INTENT_SLUGS


DEFAULT_CATEGORIES: Final[tuple[dict[str, str], ...]] = (
    {"name": "技术", "slug": "tech", "description": "技术相关文章"},
    {"name": "生活", "slug": "life", "description": "生活随笔和感悟"},
    {"name": "思考", "slug": "thoughts", "description": "个人思考和观点"},
)

DEFAULT_TAGS: Final[tuple[dict[str, str], ...]] = (
    {"name": "Python", "slug": "python"},
    {"name": "Web开发", "slug": "web-dev"},
    {"name": "编程", "slug": "programming"},
    {"name": "教程", "slug": "tutorial"},
)

SAMPLE_POST: Final[dict[str, str]] = {
    "title": "欢迎使用 RewrZ",
    "slug": "welcome-to-rewrz",
    "excerpt": "这是一篇由安装向导自动创建的示例文章，用于展示 RewrZ 的基础排版与内容类型能力。",
    "content_markdown": """欢迎使用 **RewrZ**，一个简洁中庸的开源个人博客系统。

## 你可以先做这几件事

1. 在后台修改或删除这篇示例文章
2. 上传一张封面图，看看响应式图片的效果
3. 写一篇微博长度的短文，体验不同内容类型的排版

## 关于内容类型

RewrZ 的 `post_type` 只有两种：文章（`post`）与页面（`page`）。
内容的表达意图由「内容类型」决定，当前支持：

- **标准文章**：长内容、深度表达
- **微博**：短内容、即时更新
- **诗词歌赋**：文学体裁、特殊排版

图片、视频、音频与外链都属于媒体附件层能力，不作为独立内容类型。

> 这是一段引用示例。

```python
print("Hello, RewrZ!")
```

祝你写得开心。
""",
}


def get_default_formats() -> tuple[dict[str, str], ...]:
    """按 `content_intents` 的权威定义生成默认内容类型。"""
    return tuple(
        {"name": INTENT_NAME_MAP.get(slug, slug), "slug": slug} for slug in INTENT_SLUGS
    )
