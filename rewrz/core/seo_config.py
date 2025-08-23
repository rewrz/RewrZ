"""
SEO功能默认配置

定义SEO优化功能相关的默认设置，包括：
1. sitemap.xml配置
2. robots.txt配置
3. Open Graph标签配置
4. 结构化数据配置
5. 搜索引擎优化设置
"""

# SEO功能默认设置
DEFAULT_SEO_SETTINGS = [
    {
        "key": "sitemap_enabled",
        "value": {"value": True},
        "description": "是否启用sitemap.xml自动生成功能",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "noindex_site",
        "value": {"value": False},
        "description": "是否阻止搜索引擎索引整个站点",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "block_ai_crawlers",
        "value": {"value": False},
        "description": "是否阻止AI爬虫抓取内容",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "site_url",
        "value": {"value": ""},
        "description": "站点的完整URL地址（用于生成sitemap和canonical链接）",
        "category": "seo",
        "type": "text"
    },
    {
        "key": "enable_open_graph",
        "value": {"value": True},
        "description": "是否启用Open Graph元标签（Facebook分享优化）",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "enable_twitter_cards",
        "value": {"value": True},
        "description": "是否启用Twitter Cards元标签（Twitter分享优化）",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "enable_structured_data",
        "value": {"value": True},
        "description": "是否启用JSON-LD结构化数据（增强搜索结果显示）",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "default_meta_description",
        "value": {"value": "RewrZ - 一个功能强大的个人博客系统"},
        "description": "默认的页面描述（当页面没有指定描述时使用）",
        "category": "seo",
        "type": "text"
    },
    {
        "key": "keywords",
        "value": {"value": "博客,个人博客,RewrZ,技术博客"},
        "description": "站点关键词（用逗号分隔）",
        "category": "seo",
        "type": "text"
    },
    {
        "key": "author_name",
        "value": {"value": ""},
        "description": "站点作者姓名（用于结构化数据）",
        "category": "seo",
        "type": "text"
    },
    {
        "key": "sitemap_changefreq_posts",
        "value": {"value": "weekly"},
        "description": "文章页面的更新频率（用于sitemap.xml）",
        "category": "seo",
        "type": "select",
        "options": ["always", "hourly", "daily", "weekly", "monthly", "yearly", "never"]
    },
    {
        "key": "sitemap_priority_posts",
        "value": {"value": 0.8},
        "description": "文章页面的优先级（0.0-1.0，用于sitemap.xml）",
        "category": "seo",
        "type": "number"
    },
    {
        "key": "sitemap_priority_homepage",
        "value": {"value": 1.0},
        "description": "首页的优先级（0.0-1.0，用于sitemap.xml）",
        "category": "seo",
        "type": "number"
    },
    {
        "key": "sitemap_priority_categories",
        "value": {"value": 0.6},
        "description": "分类页面的优先级（0.0-1.0，用于sitemap.xml）",
        "category": "seo",
        "type": "number"
    },
    {
        "key": "sitemap_priority_tags",
        "value": {"value": 0.5},
        "description": "标签页面的优先级（0.0-1.0，用于sitemap.xml）",
        "category": "seo",
        "type": "number"
    },
    {
        "key": "canonical_urls",
        "value": {"value": True},
        "description": "是否启用canonical链接（防止重复内容）",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "meta_generator",
        "value": {"value": "RewrZ"},
        "description": "HTML生成器标识",
        "category": "seo",
        "type": "text"
    },
    {
        "key": "enable_breadcrumbs",
        "value": {"value": True},
        "description": "是否启用面包屑导航结构化数据",
        "category": "seo",
        "type": "boolean"
    },
    {
        "key": "facebook_app_id",
        "value": {"value": ""},
        "description": "Facebook应用ID（可选，用于Open Graph优化）",
        "category": "seo",
        "type": "text"
    },
    {
        "key": "twitter_site",
        "value": {"value": ""},
        "description": "Twitter账号（如@username，用于Twitter Cards）",
        "category": "seo",
        "type": "text"
    }
]