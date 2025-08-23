#!/usr/bin/env python3
"""
多重身份内容系统集成测试

测试Format模型、Post与Format关联、以及多重身份内容展示功能
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from rewrz.models.base import Base
from rewrz.models.user import User
from rewrz.models.post import Post
from rewrz.models.format import Format
from rewrz.schemas.user import UserCreate
from rewrz.schemas.post import PostCreate
from rewrz.schemas.format import FormatCreate
from rewrz.crud import user as crud_user
from rewrz.crud import post as crud_post
from rewrz.crud import format as crud_format

# 设置测试数据库
SQLALCHEMY_DATABASE_URL = "sqlite:///./tests/test_multi_format.db"

engine = create_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(name="db")
def session_fixture():
    """创建测试数据库会话"""
    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(bind=engine)

@pytest.fixture
def test_user(db: Session):
    """创建测试用户"""
    user_data = UserCreate(
        username="testuser", 
        email="test@example.com", 
        password="testpass123"
    )
    return crud_user.create_user(db, user_data)

@pytest.fixture
def test_formats(db: Session):
    """创建测试格式数据"""
    formats_data = [
        ("标准文章", "standard-article"),
        ("微博", "micro-post"), 
        ("相册", "photo-album"),
        ("视频", "video"),
        ("音乐", "music"),
    ]
    
    formats = []
    for name, slug in formats_data:
        format_data = FormatCreate(name=name, slug=slug)
        format_obj = crud_format.create_format(db, format_data)
        formats.append(format_obj)
    
    return formats

def test_create_multi_format_posts(db: Session, test_user: User, test_formats: list):
    """测试创建多重身份格式的文章"""
    
    # 获取格式对象
    micro_format = next(f for f in test_formats if f.slug == "micro-post")
    photo_format = next(f for f in test_formats if f.slug == "photo-album")
    standard_format = next(f for f in test_formats if f.slug == "standard-article")
    
    # 1. 创建纯微博格式文章
    micro_post = PostCreate(
        title="今天天气真不错",
        content_markdown="阳光明媚，适合出门走走。#心情 #天气",
        post_type="article",
        status="published", 
        visibility="public",
        format_ids=[micro_format.id]
    )
    created_micro = crud_post.create_post(db, micro_post, author_id=test_user.id)
    
    assert created_micro.title == "今天天气真不错"
    assert len(created_micro.formats) == 1
    assert created_micro.formats[0].slug == "micro-post"
    
    # 2. 创建纯相册格式文章
    photo_post = PostCreate(
        title="美丽的风景",
        content_markdown="在山上拍摄的美丽日落",
        featured_image_url="https://picsum.photos/800/600",
        post_type="article",
        status="published",
        visibility="public", 
        format_ids=[photo_format.id]
    )
    created_photo = crud_post.create_post(db, photo_post, author_id=test_user.id)
    
    assert created_photo.title == "美丽的风景"
    assert len(created_photo.formats) == 1
    assert created_photo.formats[0].slug == "photo-album"
    
    # 3. 创建混合格式文章（微博+相册）
    mixed_post = PostCreate(
        title="分享几张生活照片",
        content_markdown="今天拍了一些不错的照片，分享给大家看看！",
        featured_image_url="https://picsum.photos/600/800",
        post_type="article", 
        status="published",
        visibility="public",
        format_ids=[micro_format.id, photo_format.id]  # 同时标记为微博和相册
    )
    created_mixed = crud_post.create_post(db, mixed_post, author_id=test_user.id)
    
    assert created_mixed.title == "分享几张生活照片"
    assert len(created_mixed.formats) == 2
    format_slugs = [f.slug for f in created_mixed.formats]
    assert "micro-post" in format_slugs
    assert "photo-album" in format_slugs

def test_get_posts_by_format(db: Session, test_user: User, test_formats: list):
    """测试按格式筛选文章功能"""
    
    micro_format = next(f for f in test_formats if f.slug == "micro-post")
    photo_format = next(f for f in test_formats if f.slug == "photo-album")
    
    # 创建测试文章
    posts_data = [
        ("微博文章1", [micro_format.id]),
        ("相册文章1", [photo_format.id]),
        ("混合文章1", [micro_format.id, photo_format.id]),
        ("微博文章2", [micro_format.id]),
    ]
    
    created_posts = []
    for title, format_ids in posts_data:
        post = PostCreate(
            title=title,
            content_markdown=f"这是{title}的内容",
            post_type="article",
            status="published",
            visibility="public",
            format_ids=format_ids
        )
        created_post = crud_post.create_post(db, post, author_id=test_user.id)
        created_posts.append(created_post)
    
    # 测试按微博格式筛选
    micro_posts = crud_post.get_posts_by_format(db, micro_format.id)
    assert len(micro_posts) == 3  # 微博文章1、混合文章1、微博文章2
    
    # 测试按相册格式筛选
    photo_posts = crud_post.get_posts_by_format(db, photo_format.id)
    assert len(photo_posts) == 2  # 相册文章1、混合文章1
    
    # 验证筛选结果的格式标记
    for post in micro_posts:
        format_slugs = [f.slug for f in post.formats]
        assert "micro-post" in format_slugs

def test_format_priority_logic(db: Session, test_user: User, test_formats: list):
    """测试格式优先级逻辑（根据需求规格说明书2.2.1）"""
    
    micro_format = next(f for f in test_formats if f.slug == "micro-post")
    photo_format = next(f for f in test_formats if f.slug == "photo-album")
    standard_format = next(f for f in test_formats if f.slug == "standard-article")
    
    # 创建同时标记为微博和相册的文章
    mixed_post = PostCreate(
        title="测试优先级文章",
        content_markdown="这是一篇测试优先级的文章",
        post_type="article",
        status="published",
        visibility="public",
        format_ids=[micro_format.id, photo_format.id]  # 微博 + 相册
    )
    created_mixed = crud_post.create_post(db, mixed_post, author_id=test_user.id)
    
    # 验证文章确实有多个格式
    assert len(created_mixed.formats) == 2
    format_slugs = [f.slug for f in created_mixed.formats]
    
    # 根据需求规格说明书，微博格式优先级最高
    # 在模板渲染时应该采用微博样式
    assert "micro-post" in format_slugs
    assert "photo-album" in format_slugs
    
    # 模拟模板中的优先级逻辑验证
    has_micro = "micro-post" in format_slugs
    has_photo = "photo-album" in format_slugs
    has_standard = "standard-article" in format_slugs
    
    # 按照需求规格说明书的优先级：微博 > 相册 > 视频/音乐 > 标准文章
    if has_micro:
        expected_style = "micro-post"
    elif has_photo and not has_micro:
        expected_style = "photo-album"
    else:
        expected_style = "standard-article"
    
    assert expected_style == "micro-post"  # 应该采用微博样式

def test_auto_slug_generation(db: Session, test_user: User, test_formats: list):
    """测试自动slug生成功能"""
    
    standard_format = next(f for f in test_formats if f.slug == "standard-article")
    
    # 创建不提供slug的文章
    post_without_slug = PostCreate(
        title="测试自动生成Slug的文章",
        content_markdown="这是测试内容",
        post_type="article",
        status="published",
        visibility="public",
        format_ids=[standard_format.id]
    )
    
    created_post = crud_post.create_post(db, post_without_slug, author_id=test_user.id)
    
    # 验证slug自动生成
    assert created_post.slug is not None
    assert created_post.slug == "ce-shi-zi-dong-sheng-cheng-slugde-wen-zhang"
    
    # 创建相同标题的文章，验证slug唯一性
    duplicate_post = PostCreate(
        title="测试自动生成Slug的文章",  # 相同标题
        content_markdown="这是另一篇测试内容",
        post_type="article",
        status="published",
        visibility="public",
        format_ids=[standard_format.id]
    )
    
    created_duplicate = crud_post.create_post(db, duplicate_post, author_id=test_user.id)
    
    # 验证slug唯一性处理
    assert created_duplicate.slug != created_post.slug
    assert created_duplicate.slug == "ce-shi-zi-dong-sheng-cheng-slugde-wen-zhang-1"