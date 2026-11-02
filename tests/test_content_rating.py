"""内容分级与图片尺寸档位的回归测试。

覆盖三件事：
1. Markdown 启用 attr_list 后，图片尺寸语义类与原生 width 属性都能落地。
2. content_rating 在 schema 层收敛取值，在 CRUD 层正确持久化。
3. NSFW 内容在详情页、sitemap、RSS、SEO 元数据侧都被隔离。
"""

import re
from datetime import datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from rewrz import main as main_module
from rewrz.core.content_utils import render_markdown_html
from rewrz.core.database import Base, get_db
from rewrz.crud import post as crud_post
from rewrz.models import Post, Tag, User as DbUser
from rewrz.models.setting import Setting
from rewrz.schemas.post import PostCreate, PostUpdate

PUBLISHED_AT = datetime(2026, 1, 1, 8, 0, 0)


@pytest.fixture(name="site_client")
def site_client_fixture(monkeypatch, tmp_path):
    """构造带独立数据库的站点客户端，预置 SEO / RSS 所需设置。"""
    monkeypatch.setattr(
        type(main_module.settings),
        "installation_complete",
        property(lambda self: True),
    )
    engine = create_engine(
        f"sqlite:///{tmp_path / f'content-rating-{uuid4().hex}.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(bind=engine)
    session_local = sessionmaker(autocommit=False, autoflush=False, bind=engine)

    with session_local() as db:
        db.add(
            DbUser(
                id=1,
                username="rating-admin",
                hashed_password="hashed",
                email="rating-admin@example.com",
                is_active=True,
                role="super_admin",
                use_gravatar="auto",
            )
        )
        db.add_all(
            [
                Setting(key="sitemap_enabled", value={"value": True}),
                Setting(key="site_url", value={"value": "https://example.com"}),
                Setting(key="rss_enabled", value={"value": True}),
            ]
        )
        db.commit()

    def override_get_db():
        db = session_local()
        try:
            yield db
        finally:
            db.close()

    main_module.app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(main_module.app), session_local
    finally:
        main_module.app.dependency_overrides.pop(get_db, None)
        engine.dispose()


def _insert_post(
    session_local,
    *,
    slug: str,
    rating: str,
    title: str,
    tag_ids: list[int] | None = None,
) -> int:
    """直接写库构造已发布文章，避免经过 CRUD 的额外副作用。"""
    with session_local() as db:
        post = Post(
            title=title,
            slug=slug,
            content_markdown=f"![配图](/media/{slug}.jpg)",
            content_html=f'<p><img alt="配图" src="/media/{slug}.jpg" /></p>',
            excerpt=title,
            post_type="post",
            status="published",
            visibility="public",
            content_rating=rating,
            author_id=1,
            published_at=PUBLISHED_AT,
        )
        if tag_ids:
            post.tags = db.query(Tag).filter(Tag.id.in_(tag_ids)).all()
        db.add(post)
        db.commit()
        db.refresh(post)
        return post.id


def test_attr_list_renders_size_class_and_width():
    """attr_list 生效后，语义类与原生 width 都能输出到 img 标签。"""
    fragment_html = render_markdown_html("![演示](/media/demo.jpg#md-img-lg)")
    assert 'class="md-img-lg"' in fragment_html
    assert "#md-img-lg" not in fragment_html

    class_html = render_markdown_html("![演示](/media/demo.jpg){: .md-img-sm }")
    assert 'class="md-img-sm"' in class_html

    width_html = render_markdown_html('![演示](/media/demo.jpg){: width="320" }')
    assert 'width="320"' in width_html


def test_content_rating_schema_normalizes_and_rejects_unknown():
    """分级取值在 schema 层归一化，非法值直接拒绝。"""
    assert PostCreate(title="分级", content_markdown="正文", content_rating=" NSFW ").content_rating == "nsfw"
    assert PostUpdate(title="分级", content_rating="Sensitive").content_rating == "sensitive"

    with pytest.raises(ValidationError):
        PostCreate(title="分级", content_markdown="正文", content_rating="adult")


def test_crud_post_persists_and_updates_content_rating(site_client):
    """创建与更新都要落到数据库，且更新后能读回归一化后的取值。"""
    _client, session_local = site_client
    with session_local() as db:
        created = crud_post.create_post(
            db,
            PostCreate(
                title="分级文章",
                slug="rating-post",
                content_markdown="正文",
                content_rating="nsfw",
                author_id=1,
            ),
            author_id=1,
        )
        assert created.content_rating == "nsfw"

        updated = crud_post.update_post(
            db,
            created.id,
            PostUpdate(title="分级文章", content_rating="Sensitive"),
        )
        assert updated.content_rating == "sensitive"


def test_list_cards_show_content_rating_badge(site_client):
    """列表卡片必须带可见分级标签，读者在点击前就能识别内容性质。"""
    from rewrz.core import public_list_cache

    client, session_local = site_client
    _insert_post(session_local, slug="badge-nsfw", rating="nsfw", title="分级标签 NSFW")
    _insert_post(session_local, slug="badge-sensitive", rating="sensitive", title="分级标签 敏感")
    # 首页列表有进程内缓存，先失效保证读到本次写入的数据。
    public_list_cache.invalidate_public_list_cache()

    response = client.get("/")

    assert response.status_code == 200
    assert 'class="content-rating-badge is-nsfw"' in response.text
    assert 'aria-label="内容分级：NSFW"' in response.text
    assert 'aria-label="内容分级：敏感"' in response.text

    # 归档页用的是另一套内联列表结构，同样要带分级标签。
    archive_response = client.get("/archives")
    assert archive_response.status_code == 200
    assert 'class="content-rating-badge is-nsfw"' in archive_response.text
    assert 'aria-label="内容分级：敏感"' in archive_response.text


def test_general_post_card_has_no_rating_badge(site_client):
    """通用分级不渲染分级标签，避免给普通内容增加噪音。"""
    from rewrz.core import public_list_cache

    client, session_local = site_client
    _insert_post(session_local, slug="badge-general", rating="general", title="分级标签 通用")
    public_list_cache.invalidate_public_list_cache()

    response = client.get("/")

    assert response.status_code == 200
    assert "分级标签 通用" in response.text
    assert "content-rating-badge" not in response.text


def test_sitemap_excludes_nsfw_posts(site_client):
    """NSFW 文章不进入 sitemap，避免搜索引擎收录入口。"""
    client, session_local = site_client
    _insert_post(session_local, slug="general-post", rating="general", title="公开文章")
    _insert_post(session_local, slug="nsfw-post", rating="nsfw", title="NSFW 文章")

    response = client.get("/sitemap.xml")

    assert response.status_code == 200
    assert "/article/general-post" in response.text
    assert "/article/nsfw-post" not in response.text


def test_rss_feed_excludes_nsfw_posts(site_client):
    """NSFW 文章不进入 RSS 订阅源，避免敏感封面被阅读器二次分发。"""
    client, session_local = site_client
    _insert_post(session_local, slug="general-feed", rating="general", title="公开订阅文章")
    _insert_post(session_local, slug="nsfw-feed", rating="nsfw", title="NSFW 订阅文章")

    response = client.get("/feed")

    assert response.status_code == 200
    assert "公开订阅文章" in response.text
    assert "NSFW 订阅文章" not in response.text


def test_nsfw_detail_page_applies_overlay_and_notice(site_client):
    """NSFW 详情页要带 is-nsfw、提示条、揭晓按钮与 noindex。"""
    client, session_local = site_client
    _insert_post(session_local, slug="nsfw-detail", rating="nsfw", title="NSFW 详情")

    response = client.get("/article/nsfw-detail")

    assert response.status_code == 200
    assert 'class="site-shell' in response.text
    assert "is-nsfw" in response.text
    assert "content-rating-notice" in response.text
    assert "data-nsfw-reveal" in response.text
    assert 'content="noindex, nofollow"' in response.text
    # 提示条本身要带可见分级标签
    assert 'class="content-rating-badge is-nsfw"' in response.text
    # 揭晓状态不写入浏览器存储，刷新后必须重新遮挡
    assert "sessionStorage" not in response.text


def test_nsfw_detail_does_not_blur_general_related_covers(site_client):
    """NSFW 详情页的分级不能扩散到页面容器，相关推荐里的普通文章封面必须保持清晰。"""
    client, session_local = site_client
    suffix = uuid4().hex[:8]
    with session_local() as db:
        tag = Tag(name=f"关联标签-{suffix}", slug=f"related-{suffix}")
        db.add(tag)
        db.commit()
        tag_id = tag.id

    _insert_post(
        session_local,
        slug=f"nsfw-host-{suffix}",
        rating="nsfw",
        title="NSFW 主文",
        tag_ids=[tag_id],
    )
    _insert_post(
        session_local,
        slug=f"general-related-{suffix}",
        rating="general",
        title="普通相关文章",
        tag_ids=[tag_id],
    )

    response = client.get(f"/article/nsfw-host-{suffix}")
    assert response.status_code == 200

    # 页面容器不能带分级属性，否则 [data-content-rating="nsfw"] 会命中所有后代卡片封面
    body_tag = response.text.split("<body", 1)[1].split(">", 1)[0]
    assert "data-content-rating" not in body_tag

    related_card = re.search(
        r'<article[^>]*class="[^"]*related-post-card[^"]*"[^>]*data-content-rating="general"',
        response.text,
    )
    assert related_card, "普通相关文章卡片必须保留 general 分级标记"


def test_general_detail_page_has_no_rating_notice(site_client):
    """通用分级不渲染提示条，也不加 noindex。"""
    client, session_local = site_client
    _insert_post(session_local, slug="general-detail", rating="general", title="通用详情")

    response = client.get("/article/general-detail")

    assert response.status_code == 200
    assert "content-rating-notice" not in response.text
    assert 'content="noindex, nofollow"' not in response.text


def test_seo_meta_omits_nsfw_cover_image(site_client):
    """NSFW 的 SEO 元数据不输出封面图，避免 Open Graph 抓走敏感缩略图。"""
    from rewrz.api.seo import _generate_post_seo_data

    _client, session_local = site_client
    _insert_post(session_local, slug="nsfw-seo", rating="nsfw", title="NSFW SEO")
    with session_local() as db:
        db_post = crud_post.get_post_by_slug(db, slug="nsfw-seo")
        db_post.featured_image_url = "/media/nsfw-cover.jpg"
        db.commit()

        seo_data = _generate_post_seo_data(
            db_post,
            SimpleNamespace(base_url="https://example.com/"),
            db,
        )

    assert seo_data["meta_data"]["image"] is None
    assert "og:image" not in seo_data["open_graph"]
    assert "twitter:image" not in seo_data["twitter_cards"]
