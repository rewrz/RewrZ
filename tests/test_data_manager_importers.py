import json
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz.core.data_manager import RewrZImporter, WordPressImporter
from rewrz.models import Base, Media
from rewrz.crud import category as crud_category
from rewrz.crud import comment as crud_comment
from rewrz.crud import format as crud_format
from rewrz.crud import post as crud_post
from rewrz.crud import setting as crud_setting
from rewrz.crud import tag as crud_tag
from rewrz.crud import user as crud_user
from rewrz.schemas import CategoryCreate, TagCreate, UserCreate


@pytest.fixture(name="db")
def session_fixture(tmp_path):
    db_path = tmp_path / "importers_test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)
        engine.dispose()


def test_wordpress_import_skips_duplicate_tag_name_and_continues(db, tmp_path):
    crud_tag.create_tag(db, TagCreate(name="大模型", slug="llm-old"))

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <wp:tag>
      <wp:tag_slug>llm</wp:tag_slug>
      <wp:tag_name>大模型</wp:tag_name>
    </wp:tag>
    <wp:tag>
      <wp:tag_slug>ai</wp:tag_slug>
      <wp:tag_name>AI</wp:tag_name>
    </wp:tag>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["tags_imported"] == 1
    assert stats["errors"] == []
    assert crud_tag.get_tag_by_name(db, "大模型").slug == "llm-old"
    assert crud_tag.get_tag_by_name(db, "AI") is not None


def test_rewrz_import_skips_duplicate_category_name_and_continues(db, tmp_path):
    crud_category.create_category(db, CategoryCreate(name="技术", slug="tech-old"))

    payload = {
        "categories": [
            {"name": "技术", "slug": "tech"},
            {"name": "生活", "slug": "life"},
        ]
    }
    json_file = tmp_path / "rewrz.json"
    json_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    importer = RewrZImporter(db)
    stats = importer.import_from_json(str(json_file))

    assert stats["categories_imported"] == 1
    assert stats["errors"] == []
    assert crud_category.get_category_by_name(db, "技术").slug == "tech-old"
    assert crud_category.get_category_by_name(db, "生活") is not None


def test_wordpress_import_posts_uses_available_default_user(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin", email="admin@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>导入测试文章</title>
      <link>https://example.com/import-post</link>
      <pubDate>Wed, 09 Jun 2021 15:35:35 +0000</pubDate>
      <content:encoded><![CDATA[<p>正文内容</p>]]></content:encoded>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_post.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []


def test_wordpress_import_preserves_status_visibility_and_timestamps(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin2", email="admin2@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>私密文章</title>
      <link>https://example.com/private-post</link>
      <pubDate>Wed, 09 Jun 2021 15:35:35 +0000</pubDate>
      <content:encoded><![CDATA[<p>private</p>]]></content:encoded>
      <wp:post_type>post</wp:post_type>
      <wp:status>private</wp:status>
      <wp:comment_status>closed</wp:comment_status>
      <wp:post_date>2021-06-09 23:35:35</wp:post_date>
      <wp:post_modified>2021-06-10 08:10:11</wp:post_modified>
    </item>
    <item>
      <title>草稿文章</title>
      <link>https://example.com/draft-post</link>
      <content:encoded><![CDATA[<p>draft</p>]]></content:encoded>
      <wp:post_type>post</wp:post_type>
      <wp:status>draft</wp:status>
      <wp:comment_status>open</wp:comment_status>
      <wp:post_date>2022-01-02 03:04:05</wp:post_date>
      <wp:post_modified>2022-01-03 04:05:06</wp:post_modified>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_status_time.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 2
    assert stats["errors"] == []

    private_post = crud_post.get_post_by_slug(db, "private-post")
    assert private_post is not None
    assert private_post.status == "published"
    assert private_post.visibility == "private"
    assert private_post.allow_comments is False
    assert private_post.created_at == datetime(2021, 6, 9, 23, 35, 35)
    assert private_post.updated_at == datetime(2021, 6, 10, 8, 10, 11)
    assert private_post.published_at == datetime(2021, 6, 9, 23, 35, 35)

    draft_post = crud_post.get_post_by_slug(db, "draft-post")
    assert draft_post is not None
    assert draft_post.status == "draft"
    assert draft_post.visibility == "public"
    assert draft_post.allow_comments is True
    assert draft_post.created_at == datetime(2022, 1, 2, 3, 4, 5)
    assert draft_post.updated_at == datetime(2022, 1, 3, 4, 5, 6)
    assert draft_post.published_at is None


def test_rewrz_import_preserves_created_updated_published(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin3", email="admin3@example.com", password="password123"),
    )

    payload = {
        "posts": [
            {
                "title": "RewrZ时间测试",
                "slug": "rewrz-time-post",
                "content_markdown": "content",
                "status": "published",
                "visibility": "public",
                "allow_comments": False,
                "created_at": "2020-01-01T10:00:00+08:00",
                "published_at": "2020-01-02T12:00:00Z",
                "updated_at": "2020-01-03T13:30:00+08:00",
            }
        ]
    }
    json_file = tmp_path / "rewrz_time.json"
    json_file.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    importer = RewrZImporter(db)
    stats = importer.import_from_json(str(json_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    imported = crud_post.get_post_by_slug(db, "rewrz-time-post")
    assert imported is not None
    assert imported.created_at == datetime(2020, 1, 1, 2, 0, 0)
    assert imported.published_at == datetime(2020, 1, 2, 12, 0, 0)
    assert imported.updated_at == datetime(2020, 1, 3, 5, 30, 0)


def test_wordpress_import_uses_post_name_creator_excerpt_and_preserves_html(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin4", email="admin4@example.com", password="password123"),
    )
    master_user = crud_user.create_user(
        db,
        UserCreate(username="master", email="master@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:dc="http://purl.org/dc/elements/1.1/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title><![CDATA[命运石之门]]></title>
      <link>https://rewrz.com/archive/steins-gate</link>
      <pubDate>Sun, 16 Oct 2016 14:04:33 +0000</pubDate>
      <dc:creator><![CDATA[master]]></dc:creator>
      <content:encoded><![CDATA[<h2>命运石之门</h2><p>正文</p><img src="/wp-content/uploads/a.jpg" alt="a" />[dm href='https://example.com']维基百科[/dm]。]]></content:encoded>
      <excerpt:encoded><![CDATA[这是摘要]]></excerpt:encoded>
      <wp:post_date><![CDATA[2016-10-16 22:04:33]]></wp:post_date>
      <wp:post_date_gmt><![CDATA[2016-10-16 14:04:33]]></wp:post_date_gmt>
      <wp:post_modified><![CDATA[2016-10-16 22:04:33]]></wp:post_modified>
      <wp:post_modified_gmt><![CDATA[2016-10-16 14:04:33]]></wp:post_modified_gmt>
      <wp:comment_status><![CDATA[open]]></wp:comment_status>
      <wp:post_name><![CDATA[steins-gate]]></wp:post_name>
      <wp:status><![CDATA[publish]]></wp:status>
      <wp:post_type><![CDATA[post]]></wp:post_type>
      <wp:post_password><![CDATA[]]></wp:post_password>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_rich.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "steins-gate")
    assert post is not None
    assert post.author_id == master_user.id
    assert post.excerpt == "这是摘要"
    assert post.post_type == "post"
    assert post.content_html == ""
    assert "## 命运石之门" in post.content_markdown
    assert post.created_at == datetime(2016, 10, 16, 14, 4, 33)
    assert post.updated_at == datetime(2016, 10, 16, 14, 4, 33)


def test_wordpress_import_page_type(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin5", email="admin5@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>关于我</title>
      <content:encoded><![CDATA[<p>页面正文</p>]]></content:encoded>
      <wp:post_name>about</wp:post_name>
      <wp:post_type>page</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_page.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    page = crud_post.get_post_by_slug(db, "about")
    assert page is not None
    assert page.post_type == "page"


def test_wordpress_import_maps_media_post_format_to_article_intent(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin_format", email="admin_format@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>格式映射测试</title>
      <content:encoded><![CDATA[<p>内容</p>]]></content:encoded>
      <wp:post_name>format-mapped-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>
      <category domain="post_format" nicename="post-format-video"><![CDATA[视频]]></category>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_post_format.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "format-mapped-post")
    assert post is not None
    assert any(fmt.slug == "article" for fmt in post.formats)
    assert crud_format.get_format_by_slug(db, "article") is not None


def test_wordpress_import_custom_post_type_whitelist_maps_to_post(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin_custom_type", email="admin_custom_type@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>自定义类型导入</title>
      <content:encoded><![CDATA[<p>自定义类型正文</p>]]></content:encoded>
      <wp:post_name>custom-type-post</wp:post_name>
      <wp:post_type>portfolio</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_custom_type.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_post_types": ["post", "page", "portfolio"],
            "import_comments": True,
            "import_views": True,
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
        },
    )
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    imported = crud_post.get_post_by_slug(db, "custom-type-post")
    assert imported is not None
    assert imported.post_type == "post"


def test_wordpress_import_custom_post_type_can_map_to_micro_post_format(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin_custom_map", email="admin_custom_map@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>说说映射格式</title>
      <content:encoded><![CDATA[<p>说说正文</p>]]></content:encoded>
      <wp:post_name>shuoshuo-1896</wp:post_name>
      <wp:post_type>shuoshuo</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2024-03-03 18:12:26</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_shuoshuo.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_post_types": ["post", "page", "shuoshuo"],
            "post_type_format_map": {"shuoshuo": "weibo"},
            "import_comments": True,
            "import_views": True,
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
        },
    )
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    imported = crud_post.get_post_by_slug(db, "shuoshuo-1896")
    assert imported is not None
    assert imported.post_type == "post"
    assert any(fmt.slug == "micro" for fmt in imported.formats)


def test_wordpress_import_defaults_format_to_article_when_missing_post_format(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin_default_fmt", email="admin_default_fmt@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>默认格式测试</title>
      <content:encoded><![CDATA[<p>正文</p>]]></content:encoded>
      <wp:post_name>default-format-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_default_format.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "default-format-post")
    assert post is not None
    assert any(fmt.slug == "article" for fmt in post.formats)
    assert crud_format.get_format_by_slug(db, "article") is not None


def test_wordpress_import_comments_and_views_meta(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin6", email="admin6@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>评论与阅读量测试</title>
      <content:encoded><![CDATA[<p>正文</p>]]></content:encoded>
      <wp:post_name>metrics-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>

      <wp:postmeta>
        <wp:meta_key>views</wp:meta_key>
        <wp:meta_value>584</wp:meta_value>
      </wp:postmeta>
      <wp:postmeta>
        <wp:meta_key>post_views_count</wp:meta_key>
        <wp:meta_value>0</wp:meta_value>
      </wp:postmeta>

      <wp:comment>
        <wp:comment_id>10</wp:comment_id>
        <wp:comment_parent>0</wp:comment_parent>
        <wp:comment_author><![CDATA[Alice]]></wp:comment_author>
        <wp:comment_author_email>alice@example.com</wp:comment_author_email>
        <wp:comment_author_url>https://alice.example.com</wp:comment_author_url>
        <wp:comment_author_IP>127.0.0.1</wp:comment_author_IP>
        <wp:comment_agent>UA-A</wp:comment_agent>
        <wp:comment_date>2021-01-02 01:02:03</wp:comment_date>
        <wp:comment_approved>1</wp:comment_approved>
        <wp:comment_content><![CDATA[父评论]]></wp:comment_content>
      </wp:comment>
      <wp:comment>
        <wp:comment_id>11</wp:comment_id>
        <wp:comment_parent>10</wp:comment_parent>
        <wp:comment_author><![CDATA[Bob]]></wp:comment_author>
        <wp:comment_author_email>bob@example.com</wp:comment_author_email>
        <wp:comment_date>2021-01-02 02:03:04</wp:comment_date>
        <wp:comment_approved>0</wp:comment_approved>
        <wp:comment_content><![CDATA[子评论]]></wp:comment_content>
      </wp:comment>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_comments_views.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["comments_imported"] == 2
    assert stats["views_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "metrics-post")
    assert post is not None
    assert post.views_count == 584
    assert post.views == 584

    all_comments = crud_comment.get_comments_for_post(db, post.id)
    assert len(all_comments) == 2
    parent = next(c for c in all_comments if c.author_name == "Alice")
    child = next(c for c in all_comments if c.author_name == "Bob")
    assert parent.status == "approved"
    assert child.status == "pending"
    assert child.parent_id == parent.id

    metric_setting = crud_setting.get_setting(db, f"post_views_count_{post.id}")
    assert metric_setting is not None
    assert metric_setting.value.get("value") == 584


def test_wordpress_import_options_can_disable_comments_and_views(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin7", email="admin7@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>配置测试</title>
      <description>desc 摘要</description>
      <content:encoded><![CDATA[<p>正文</p>]]></content:encoded>
      <wp:post_name>options-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>
      <wp:postmeta>
        <wp:meta_key>views</wp:meta_key>
        <wp:meta_value>100</wp:meta_value>
      </wp:postmeta>
      <wp:comment>
        <wp:comment_id>1</wp:comment_id>
        <wp:comment_parent>0</wp:comment_parent>
        <wp:comment_author>Alice</wp:comment_author>
        <wp:comment_author_email>alice@example.com</wp:comment_author_email>
        <wp:comment_approved>1</wp:comment_approved>
        <wp:comment_content>测试评论</wp:comment_content>
      </wp:comment>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_options.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": False,
            "import_views": False,
            "import_post_types": ["post"],
            "postmeta_whitelist": ["views"],
            "markdown_strategy": "html_to_markdown",
        },
    )
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["comments_imported"] == 0
    assert stats["views_imported"] == 0
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "options-post")
    assert post is not None
    assert post.excerpt == "desc 摘要"
    assert post.views_count == 0
    assert len(crud_comment.get_comments_for_post(db, post.id)) == 0


def test_wordpress_import_raw_html_strategy_uses_html_mode(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin8", email="admin8@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>HTML策略测试</title>
      <content:encoded><![CDATA[<h2>标题</h2><p>正文</p>]]></content:encoded>
      <wp:post_name>raw-html-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2021-01-01 00:00:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_raw_html.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "raw_html",
        },
    )
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "raw-html-post")
    assert post is not None
    assert post.content_markdown == ""
    assert "<h2>标题</h2>" in post.content_html


def test_wordpress_import_gutenberg_blocks_media_and_shortcode_to_markdown(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin9", email="admin9@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:excerpt="http://wordpress.org/export/1.2/excerpt/"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>Gutenberg 转换测试</title>
      <link>https://rewrz.com/archive/wp-gutenberg</link>
      <content:encoded><![CDATA[
        <!-- wp:heading -->
        <h2 class="wp-block-heading">2025年7月5日大灾难预言</h2>
        <!-- /wp:heading -->
        <!-- wp:list -->
        <ul class="wp-block-list"><li><strong>时间与地点</strong>：内容A</li><li>内容B</li></ul>
        <!-- /wp:list -->
        <!-- wp:quote -->
        <blockquote class="wp-block-quote"><p>引用段落</p></blockquote>
        <!-- /wp:quote -->
        <!-- wp:image -->
        <figure class="wp-block-image size-large"><img src="/wp-content/uploads/2025/04/sample-1024x768.jpg" alt="sample"/></figure>
        <!-- /wp:image -->
        <p>[dm href='https://example.com/wiki']维基百科[/dm]</p>
      ]]></content:encoded>
      <wp:post_name>wp-gutenberg</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_gutenberg.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "wp-gutenberg")
    assert post is not None
    assert "## 2025年7月5日大灾难预言" in post.content_markdown
    assert "- **时间与地点**" in post.content_markdown
    assert "内容A" in post.content_markdown
    assert "> 引用段落" in post.content_markdown
    assert "![sample](https://rewrz.com/wp-content/uploads/2025/04/sample-1024x768.jpg)" in post.content_markdown
    assert "[维基百科](https://example.com/wiki)" in post.content_markdown


def test_wordpress_import_uses_thumbnail_id_as_featured_image(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin10", email="admin10@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>Attachment</title>
      <wp:post_id>2217</wp:post_id>
      <wp:post_type>attachment</wp:post_type>
      <wp:status>inherit</wp:status>
      <wp:attachment_url>https://rewrz.com/wp-content/uploads/2025/04/1744906867-2025-04-17_213227.jpg</wp:attachment_url>
    </item>
    <item>
      <title>特色图恢复测试</title>
      <content:encoded><![CDATA[<p>正文</p>]]></content:encoded>
      <wp:post_name>featured-image-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
      <wp:postmeta>
        <wp:meta_key>_thumbnail_id</wp:meta_key>
        <wp:meta_value>2217</wp:meta_value>
      </wp:postmeta>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_thumbnail.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "featured-image-post")
    assert post is not None
    assert post.featured_image_url == "https://rewrz.com/wp-content/uploads/2025/04/1744906867-2025-04-17_213227.jpg"


def test_wordpress_import_can_download_remote_media_to_local(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin11", email="admin11@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>媒体下载测试</title>
      <link>https://rewrz.com/archive/media-download-post</link>
      <content:encoded><![CDATA[<p><img src="https://assets.example.com/images/a.png" alt="a"/></p>]]></content:encoded>
      <wp:post_name>media-download-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_media_download.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
            "download_remote_media": True,
        },
    )
    local_media_root = tmp_path / "media_uploads"
    importer._get_media_upload_root = lambda: str(local_media_root)
    importer._fetch_remote_media_bytes = lambda url, timeout_seconds, max_bytes: (b"fake-png-bytes", "image/png")

    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert stats.get("media_downloaded", 0) == 1

    post = crud_post.get_post_by_slug(db, "media-download-post")
    assert post is not None
    assert "/media/" in post.content_markdown
    assert "/media/2025/04/" in post.content_markdown
    assert "/imports/wordpress/" not in post.content_markdown
    assert post.featured_image_url and post.featured_image_url.startswith("/media/")
    assert "/media/2025/04/" in post.featured_image_url
    assert "/imports/wordpress/" not in post.featured_image_url

    media_items = db.query(Media).all()
    assert len(media_items) >= 1
    assert media_items[0].filepath.startswith(str(local_media_root))


def test_wordpress_import_download_media_decodes_percent_encoded_unicode_filename(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin11b", email="admin11b@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>中文文件名下载测试</title>
      <link>https://rewrz.com/archive/media-download-unicode-name</link>
      <content:encoded><![CDATA[<p><img src="https://assets.example.com/images/2020%E5%B9%B4%E6%97%A5%E9%A3%9F.jpg" alt="a"/></p>]]></content:encoded>
      <wp:post_name>media-download-unicode-name</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2020-07-10 00:00:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_media_download_unicode.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
            "download_remote_media": True,
        },
    )
    local_media_root = tmp_path / "media_uploads"
    importer._get_media_upload_root = lambda: str(local_media_root)
    importer._fetch_remote_media_bytes = lambda url, timeout_seconds, max_bytes: (b"fake-jpg-bytes", "image/jpeg")

    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert stats.get("media_downloaded", 0) == 1

    post = crud_post.get_post_by_slug(db, "media-download-unicode-name")
    assert post is not None
    assert post.content_markdown and "/media/2020/07/" in post.content_markdown
    assert "2020年日食" in post.content_markdown
    assert "%E5%B9%B4" not in post.content_markdown

    media_items = db.query(Media).all()
    assert len(media_items) >= 1
    normalized_path = media_items[0].filepath.replace("\\", "/")
    assert "/2020/07/" in normalized_path
    assert "2020年日食" in normalized_path


def test_wordpress_import_download_media_can_preserve_original_relative_path(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin12", email="admin12@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>媒体路径还原测试</title>
      <link>https://rewrz.com/archive/media-preserve-path-post</link>
      <content:encoded><![CDATA[
        <p>
          <img src="https://cdn.example.com/wp-content/uploads/2024/03/gallery/pic-a.png" alt="a"/>
        </p>
      ]]></content:encoded>
      <wp:post_name>media-preserve-path-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_media_preserve_path.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
            "download_remote_media": True,
            "remote_media_path_strategy": "preserve_relative_path",
        },
    )
    local_media_root = tmp_path / "media_uploads"
    importer._get_media_upload_root = lambda: str(local_media_root)
    importer._fetch_remote_media_bytes = lambda url, timeout_seconds, max_bytes: (b"fake-png-bytes-2", "image/png")

    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert stats.get("media_downloaded", 0) == 1

    post = crud_post.get_post_by_slug(db, "media-preserve-path-post")
    assert post is not None
    assert "/media/2024/03/gallery/" in (post.content_markdown or "")
    assert post.featured_image_url and "/media/2024/03/gallery/" in post.featured_image_url

    media_items = db.query(Media).all()
    assert len(media_items) >= 1
    normalized_path = media_items[0].filepath.replace("\\", "/")
    assert "/2024/03/gallery/" in normalized_path


def test_wordpress_import_preserve_relative_path_prefers_year_month_segments(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin13", email="admin13@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>年月路径优先测试</title>
      <link>https://rewrz.com/archive/media-year-month-post</link>
      <content:encoded><![CDATA[
        <p>
          <img src="https://cdn.example.com/custom/path/assets/25/03/gallery/pic-b.png" alt="b"/>
        </p>
      ]]></content:encoded>
      <wp:post_name>media-year-month-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_media_year_month.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
            "download_remote_media": True,
            "remote_media_path_strategy": "preserve_relative_path",
        },
    )
    local_media_root = tmp_path / "media_uploads"
    importer._get_media_upload_root = lambda: str(local_media_root)
    importer._fetch_remote_media_bytes = lambda url, timeout_seconds, max_bytes: (b"fake-png-bytes-3", "image/png")

    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert stats.get("media_downloaded", 0) == 1

    post = crud_post.get_post_by_slug(db, "media-year-month-post")
    assert post is not None
    assert "/media/25/03/gallery/" in (post.content_markdown or "")
    assert post.featured_image_url and "/media/25/03/gallery/" in post.featured_image_url

    media_items = db.query(Media).all()
    assert len(media_items) >= 1
    normalized_path = media_items[0].filepath.replace("\\", "/")
    assert "/25/03/gallery/" in normalized_path


def test_wordpress_import_preserve_relative_path_without_year_month_falls_back_to_post_month(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin13b", email="admin13b@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <link>https://rewrz.com</link>
    <item>
      <title>外链无年月路径回落测试</title>
      <link>https://rewrz.com/archive/media-fallback-month-post</link>
      <content:encoded><![CDATA[
        <p>
          <img src="https://cdn.example.com/custom/path/assets/gallery/pic-c.png" alt="c"/>
        </p>
      ]]></content:encoded>
      <wp:post_name>media-fallback-month-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2019-12-26 08:00:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_media_fallback_month.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
            "download_remote_media": True,
            "remote_media_path_strategy": "preserve_relative_path",
        },
    )
    local_media_root = tmp_path / "media_uploads"
    importer._get_media_upload_root = lambda: str(local_media_root)
    importer._fetch_remote_media_bytes = lambda url, timeout_seconds, max_bytes: (b"fake-png-bytes-4", "image/png")

    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert stats.get("media_downloaded", 0) == 1

    post = crud_post.get_post_by_slug(db, "media-fallback-month-post")
    assert post is not None
    assert "/media/2019/12/" in (post.content_markdown or "")
    assert post.featured_image_url and "/media/2019/12/" in post.featured_image_url

    media_items = db.query(Media).all()
    assert len(media_items) >= 1
    normalized_path = media_items[0].filepath.replace("\\", "/")
    assert "/2019/12/" in normalized_path


def test_wordpress_import_invalid_url_text_does_not_break_post_import(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin15b", email="admin15b@example.com", password="password123"),
    )

    wxr_content = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>异常URL容错测试</title>
      <content:encoded><![CDATA[
        <p>今天上了一下http://moeacg.eu5.org，也就是我以前架设的免费博客，记录一下。</p>
      ]]></content:encoded>
      <wp:post_name>invalid-url-tolerance-post</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2012-12-12 23:33:00</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_invalid_url_tolerance.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(
        db,
        options={
            "import_comments": True,
            "import_views": True,
            "import_post_types": ["post", "page"],
            "postmeta_whitelist": ["views", "post_views_count"],
            "markdown_strategy": "html_to_markdown",
            "download_remote_media": True,
        },
    )
    local_media_root = tmp_path / "media_uploads"
    importer._get_media_upload_root = lambda: str(local_media_root)

    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []

    post = crud_post.get_post_by_slug(db, "invalid-url-tolerance-post")
    assert post is not None


def test_wordpress_import_decodes_percent_encoded_post_name_slug(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin14", email="admin14@example.com", password="password123"),
    )

    encoded_slug = "%E6%B5%8B%E8%AF%95-%E6%96%87%E7%AB%A0-2025"
    decoded_slug = "测试-文章-2025"
    wxr_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>编码别名测试</title>
      <link>https://rewrz.com/article/{encoded_slug}</link>
      <content:encoded><![CDATA[<p>slug test</p>]]></content:encoded>
      <wp:post_name>{encoded_slug}</wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_percent_post_name.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert crud_post.get_post_by_slug(db, decoded_slug) is not None
    assert crud_post.get_post_by_slug(db, encoded_slug) is None


def test_wordpress_import_decodes_percent_encoded_link_slug_when_post_name_missing(db, tmp_path):
    crud_user.create_user(
        db,
        UserCreate(username="admin15", email="admin15@example.com", password="password123"),
    )

    encoded_slug = "%E6%B5%8B%E8%AF%95-%E5%9B%BE%E9%9B%86-02"
    decoded_slug = "测试-图集-02"
    wxr_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"
     xmlns:content="http://purl.org/rss/1.0/modules/content/"
     xmlns:wp="http://wordpress.org/export/1.2/">
  <channel>
    <item>
      <title>链接别名测试</title>
      <link>https://rewrz.com/article/{encoded_slug}</link>
      <content:encoded><![CDATA[<p>slug test by link</p>]]></content:encoded>
      <wp:post_name></wp:post_name>
      <wp:post_type>post</wp:post_type>
      <wp:status>publish</wp:status>
      <wp:post_date>2025-04-18 00:41:41</wp:post_date>
    </item>
  </channel>
</rss>
"""
    wxr_file = tmp_path / "wordpress_percent_link_slug.xml"
    wxr_file.write_text(wxr_content, encoding="utf-8")

    importer = WordPressImporter(db)
    stats = importer.import_from_wxr(str(wxr_file))

    assert stats["posts_imported"] == 1
    assert stats["errors"] == []
    assert crud_post.get_post_by_slug(db, decoded_slug) is not None
    assert crud_post.get_post_by_slug(db, encoded_slug) is None

