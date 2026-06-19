"""文章CRUD操作模块

本模块提供文章相关的数据库操作功能，包括创建、读取、更新、删除文章。
支持多重身份内容系统和版本快照功能。
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func, delete
from ..models import Post, Format, Category, Tag, Setting, Comment
from ..schemas import PostCreate, PostUpdate, FormatCreate
from datetime import datetime
from slugify import slugify
from ..core.security import get_password_hash, verify_password
from ..crud import format as crud_format
from ..core.content_utils import (
    infer_editor_mode,
    normalize_editor_mode,
    get_effective_plain_text,
    get_effective_content_html,
    render_markdown_html,
)
from ..core.content_intents import choose_primary_intent_slug, normalize_intent_slug, INTENT_NAME_MAP
from ..core.media_attachments import detect_media_flags, summarize_media_attachments
from ..core.page_templates import normalize_page_template

from typing import Optional, List


def _normalize_post_type_value(post_type: Optional[str], *, allow_none: bool = False) -> Optional[str]:
    if post_type is None:
        if allow_none:
            return None
        raise ValueError("post_type 不能为空")

    normalized = str(post_type).strip().lower()
    if not normalized:
        if allow_none:
            return None
        raise ValueError("post_type 不能为空")
    if normalized not in {"post", "page"}:
        raise ValueError("post_type 仅允许为 post（文章）或 page（页面）")
    return normalized


def get_public_post_conditions(*, published_only: bool = True):
    """公开文章列表统一过滤条件。"""
    conditions = [Post.post_type == "post", Post.visibility == "public"]
    if published_only:
        conditions.extend([
            Post.status == "published",
            Post.published_at.isnot(None),
        ])
    return tuple(conditions)


def _normalize_featured_image_url(url: Optional[str]) -> Optional[str]:
    if url is None:
        return None

    normalized = str(url).strip()
    if not normalized or normalized.lower() == "none":
        return None

    return normalized


def _normalize_page_template_for_post(post_type: Optional[str], template_value: Optional[str]) -> str:
    if str(post_type or "").strip().lower() != "page":
        return "default"
    return normalize_page_template(template_value)


def _normalize_excerpt_value(excerpt: Optional[str]) -> str:
    if excerpt is None:
        return ""
    return str(excerpt).strip()


def _build_media_attachment_summary_payload(
    *,
    content_markdown: Optional[str],
    content_html: Optional[str],
    featured_image_url: Optional[str],
) -> dict:
    rendered_html = get_effective_content_html(content_markdown, content_html)
    summary = summarize_media_attachments(
        rendered_html,
        content_markdown=content_markdown,
        featured_image_url=featured_image_url,
    )
    flags = detect_media_flags(summary)
    payload = summary.to_dict()
    payload["flags"] = flags
    return payload


def _get_media_summary_flag_filter(media_slug: str):
    normalized = str(media_slug or "").strip().lower()
    if normalized not in {"images", "gallery", "videos", "link", "audio"}:
        raise ValueError("不支持的媒体类型")
    return f'$.flags.{normalized}'


def _extract_setting_int_value(raw) -> int:
    if isinstance(raw, dict):
        value = raw.get("value")
    else:
        value = raw
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _resolve_storage_contents(
    editor_mode: str,
    content_markdown: Optional[str],
    content_html: Optional[str],
) -> tuple[str, str]:
    mode = normalize_editor_mode(editor_mode)
    markdown_content = content_markdown or ""
    html_content = content_html or ""

    if mode == "html":
        resolved_html = html_content.strip() or render_markdown_html(markdown_content)
        return "", resolved_html

    resolved_markdown = markdown_content
    if not resolved_markdown.strip() and html_content.strip():
        resolved_markdown = get_effective_plain_text("", html_content)
    return resolved_markdown, ""


def _attach_views_metrics(db: Session, posts: List[Post]) -> None:
    if not posts:
        return

    post_ids = [p.id for p in posts if getattr(p, "id", None) is not None]
    if not post_ids:
        return

    metric_keys = [f"post_views_count_{post_id}" for post_id in post_ids]
    try:
        settings = db.execute(select(Setting).where(Setting.key.in_(metric_keys))).scalars().all()
    except Exception:
        for post in posts:
            setattr(post, "views_count", 0)
            setattr(post, "views", 0)
        return
    views_map = {}
    for setting in settings:
        if not setting.key.startswith("post_views_count_"):
            continue
        suffix = setting.key.replace("post_views_count_", "", 1)
        try:
            post_id = int(suffix)
        except (TypeError, ValueError):
            continue
        views_map[post_id] = _extract_setting_int_value(setting.value)

    for post in posts:
        views = views_map.get(post.id, 0)
        setattr(post, "views_count", views)
        setattr(post, "views", views)


def _delete_post_views_metrics_by_ids(db: Session, post_ids: List[int]) -> None:
    normalized_ids = sorted({int(post_id) for post_id in post_ids if isinstance(post_id, int) and post_id > 0})
    if not normalized_ids:
        return

    metric_keys = [f"post_views_count_{post_id}" for post_id in normalized_ids]
    db.execute(delete(Setting).where(Setting.key.in_(metric_keys)))


def _ensure_intent_format(db: Session, intent_slug: str) -> Optional[Format]:
    normalized_slug = normalize_intent_slug(intent_slug)
    if not normalized_slug:
        normalized_slug = "article"
    fmt = crud_format.get_format_by_slug(db, slug=normalized_slug)
    if fmt is not None:
        return fmt
    try:
        return crud_format.create_format(
            db,
            FormatCreate(name=INTENT_NAME_MAP.get(normalized_slug, normalized_slug), slug=normalized_slug),
            auto_commit=False,
        )
    except Exception:
        db.rollback()
        return crud_format.get_format_by_slug(db, slug=normalized_slug)


def _normalize_intent_format_ids(db: Session, raw_format_ids: Optional[List[int]]) -> Optional[List[int]]:
    if raw_format_ids is None:
        return None

    if not raw_format_ids:
        article = _ensure_intent_format(db, "article")
        return [article.id] if article else []

    input_formats = db.execute(
        select(Format).filter(Format.id.in_(list({int(x) for x in raw_format_ids if isinstance(x, int)})))
    ).scalars().all()
    input_slugs = [fmt.slug for fmt in input_formats if getattr(fmt, "slug", None)]
    primary_intent = choose_primary_intent_slug(input_slugs)
    intent_format = _ensure_intent_format(db, primary_intent)
    if intent_format is None:
        return []
    return [intent_format.id]

def get_post(db: Session, post_id: int):
    """根据文章ID获取文章信息，包含关联的格式、分类、标签和评论"""
    from sqlalchemy.orm import selectinload
    from ..models import Comment
    post = db.execute(
        select(Post)
        .options(
            joinedload(Post.formats), 
            joinedload(Post.categories), 
            joinedload(Post.tags),
            selectinload(Post.comments).selectinload(Comment.children)  # 加载评论及其子评论
        )
        .filter(Post.id == post_id)
    ).unique().scalar_one_or_none()
    if post:
        _attach_views_metrics(db, [post])
    return post

def get_post_by_slug(db: Session, slug: str):
    """根据文章别名获取文章信息，包含关联的格式、分类、标签和评论"""
    from sqlalchemy.orm import selectinload
    from ..models import Comment
    post = db.execute(
        select(Post)
        .options(
            joinedload(Post.formats), 
            joinedload(Post.categories), 
            joinedload(Post.tags),
            selectinload(Post.comments).selectinload(Comment.children)  # 加载评论及其子评论
        )
        .filter(Post.slug == slug)
    ).unique().scalar_one_or_none()
    if post:
        _attach_views_metrics(db, [post])
    return post

def get_posts(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None, post_type: Optional[str] = None):
    """获取文章列表，支持分页和状态过滤"""
    query = select(Post).options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
    normalized_post_type = _normalize_post_type_value(post_type, allow_none=True) if post_type is not None else None

    # 公开文章列表统一走公共 helper，避免各处条件漂移。
    if status == "published" and normalized_post_type == "post":
        query = query.filter(*get_public_post_conditions())
    else:
        if status:
            # 仅已发布内容要求 published_at 非空
            if status == "published":
                query = query.filter(Post.status == status, Post.published_at.isnot(None))
            else:
                query = query.filter(Post.status == status)
        if normalized_post_type:
            query = query.filter(Post.post_type == normalized_post_type)
    # 默认按发布时间降序排列
    query = query.order_by(Post.published_at.desc())
    posts = db.execute(query.offset(skip).limit(limit)).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts


def get_posts_by_type(db: Session, post_type: str, limit: int = 100, skip: int = 0) -> List[Post]:
    """根据文章类型获取文章列表

    Args:
        db: 数据库会话
        post_type: 文章类型（例如 "post" 或 "page"）
        limit: 返回的最大数量
        skip: 跳过的数量

    Returns:
        符合条件的文章列表
    """
    return get_posts(db=db, post_type=post_type, limit=limit, skip=skip)

def get_all_posts(db: Session):
    """获取所有文章（不分页）"""
    query = select(Post).options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags), joinedload(Post.author))
    posts = db.execute(query).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts

def count_posts_by_status(db: Session, status: str) -> int:
    """
    根据状态计算文章数量
    """
    return db.execute(select(func.count(Post.id)).filter(Post.status == status)).scalar_one()

def get_posts_by_category(db: Session, category_id: int, skip: int = 0, limit: int = 100):
    """根据分类ID获取已发布文章列表"""
    posts = db.execute(
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(Post.categories.any(id=category_id))
        .filter(*get_public_post_conditions())
        .order_by(Post.published_at.desc())
        .offset(skip)
        .limit(limit)
    ).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts

def get_posts_by_format(
    db: Session,
    format_id: int,
    skip: int = 0,
    limit: int = 100,
    exclude_format_ids: Optional[List[int]] = None,
):
    """根据格式ID获取文章列表，仅返回已发布的文章"""
    query = (
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(Post.formats.any(id=format_id))
        .filter(*get_public_post_conditions())
    )
    for excluded_id in sorted({int(fid) for fid in (exclude_format_ids or []) if fid is not None}):
        if excluded_id == format_id:
            continue
        query = query.filter(~Post.formats.any(id=excluded_id))
    posts = db.execute(
        query
        .order_by(Post.published_at.desc())
        .offset(skip)
        .limit(limit)
    ).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts


def get_posts_by_tag(db: Session, tag_id: int, skip: int = 0, limit: int = 100):
    """根据标签ID获取已发布文章列表"""
    posts = db.execute(
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(Post.tags.any(id=tag_id))
        .filter(*get_public_post_conditions())
        .order_by(Post.published_at.desc())
        .offset(skip)
        .limit(limit)
    ).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts

def create_post(
    db: Session,
    post: PostCreate,
    author_id: int,
    tag_names: Optional[List[str]] = None,
    format_ids: Optional[List[int]] = None,
    *,
    auto_commit: bool = True
):
    """创建新文章
    
    自动处理：
    - Markdown转换为HTML
    - 自动生成摘要
    - 自动生成唯一别名
    - 密码哈希加密
    """
    normalized_post_type = _normalize_post_type_value(post.post_type)

    editor_mode = infer_editor_mode(
        requested_mode=post.editor_mode,
        content_markdown=post.content_markdown,
        content_html=post.content_html,
        fallback="markdown",
    )
    resolved_markdown, resolved_html = _resolve_storage_contents(
        editor_mode=editor_mode,
        content_markdown=post.content_markdown,
        content_html=post.content_html,
    )

    excerpt = _normalize_excerpt_value(post.excerpt)

    # 如果没有提供别名，则从标题生成，并确保唯一性
    if post.slug:
        base_slug = post.slug
    else:
        base_slug = slugify(post.title)
    
    slug = base_slug
    i = 1
    # 检查别名是否已存在，如果存在则添加数字后缀
    while db.execute(select(Post).filter(Post.slug == slug)).scalar_one_or_none():
        slug = f"{base_slug}-{i}"
        i += 1

    resolved_published_at = post.published_at
    if post.status == "published" and resolved_published_at is None:
        resolved_published_at = datetime.now()

    post_kwargs = {
        "title": post.title,
        "slug": slug,
        "content_markdown": resolved_markdown,
        "content_html": resolved_html,
        "excerpt": excerpt,
        "featured_image_url": _normalize_featured_image_url(post.featured_image_url),
        "post_type": normalized_post_type,
        "page_template": _normalize_page_template_for_post(normalized_post_type, post.page_template),
        "status": post.status,
        "visibility": post.visibility,
        "password": get_password_hash(post.password) if post.password else None,
        "allow_comments": post.allow_comments,
        "version_snapshots": post.version_snapshots,
        "author_id": author_id,
        "published_at": resolved_published_at,
    }
    if post.created_at is not None:
        post_kwargs["created_at"] = post.created_at
    if post.updated_at is not None:
        post_kwargs["updated_at"] = post.updated_at
    post_kwargs["media_attachment_summary"] = _build_media_attachment_summary_payload(
        content_markdown=resolved_markdown,
        content_html=resolved_html,
        featured_image_url=post_kwargs["featured_image_url"],
    )

    db_post = Post(**post_kwargs)
    db.add(db_post)
    db.flush()
    _delete_post_views_metrics_by_ids(db, [int(db_post.id)])

    # 如果指定了分类ID，则关联对应的分类
    if post.category_ids:
        categories = db.execute(select(Category).filter(Category.id.in_(post.category_ids))).scalars().all()
        db_post.categories.extend(categories)

    # 如果指定了标签ID，则关联对应的标签
    if post.tag_ids is not None:
        tags = db.execute(select(Tag).filter(Tag.id.in_(post.tag_ids))).scalars().all()
        db_post.tags.extend(tags)
    # 兼容旧调用：通过标签名关联
    elif tag_names:
        for tag_name in tag_names:
            tag = db.execute(select(Tag).filter(Tag.name == tag_name)).scalar_one_or_none()
            if not tag:
                tag = Tag(name=tag_name, slug=slugify(tag_name))
                db.add(tag)
                db.flush() # 确保tag有ID
            db_post.tags.append(tag)
    
    resolved_format_ids = format_ids if format_ids is not None else post.format_ids
    normalized_format_ids = _normalize_intent_format_ids(db, resolved_format_ids)
    if normalized_format_ids is not None:
        formats = db.execute(select(Format).filter(Format.id.in_(normalized_format_ids))).scalars().all()
        db_post.formats.extend(formats)
    elif normalized_post_type == "post":
        default_intent = _ensure_intent_format(db, "article")
        if default_intent is not None:
            db_post.formats.append(default_intent)

    if auto_commit:
        db.commit()
        db.refresh(db_post)
    return db_post

def update_post(db: Session, post_id: int, post: PostUpdate, tag_names: Optional[List[str]] = None, format_ids: Optional[List[int]] = None):
    """更新文章信息
    
    自动处理：
    - 版本快照保存
    - Markdown转换
    - 别名更新
    - 发布时间管理
    """
    db_post = db.execute(select(Post).filter(Post.id == post_id)).scalar_one_or_none()
    if db_post:
        # 保存旧内容作为版本快照
        old_content = db_post.content_markdown or db_post.content_html
        if old_content:
            db_post.version_snapshots.insert(0, {"timestamp": datetime.now().isoformat(), "content": old_content})
            if len(db_post.version_snapshots) > 5:
                db_post.version_snapshots.pop()

        update_data = post.model_dump(exclude_unset=True)
        incoming_title = update_data.pop("title", None)
        incoming_slug = update_data.pop("slug", None)
        incoming_content_markdown = update_data.pop("content_markdown", None)
        incoming_content_html = update_data.pop("content_html", None)
        incoming_editor_mode = update_data.pop("editor_mode", None)
        incoming_status = update_data.get("status")
        incoming_visibility = update_data.get("visibility")
        incoming_post_type = _normalize_post_type_value(update_data.get("post_type"), allow_none=True)
        if incoming_post_type is not None:
            update_data["post_type"] = incoming_post_type
        incoming_page_template = update_data.pop("page_template", None)
        incoming_password = update_data.pop("password", None)
        
        # 可见性为 public/private 时，清空访问密码
        if incoming_visibility and incoming_visibility != "password":
            db_post.password = None
        # 处理密码哈希更新（仅在提供了新密码时）
        elif incoming_password:
            if not db_post.password or not verify_password(incoming_password, db_post.password):
                db_post.password = get_password_hash(incoming_password)

        # 确保featured_image_url字段被处理
        if hasattr(post, 'featured_image_url') and post.featured_image_url is not None:
            db_post.featured_image_url = _normalize_featured_image_url(post.featured_image_url)
        elif hasattr(post, 'featured_image_url') and post.featured_image_url is None:
            db_post.featured_image_url = None

        if incoming_title is not None:
            db_post.title = incoming_title

        if incoming_slug is not None:
            base_slug = slugify(incoming_slug)
            slug = base_slug
            i = 1
            while db.execute(select(Post).filter(Post.slug == slug, Post.id != db_post.id)).scalar_one_or_none():
                slug = f"{base_slug}-{i}"
                i += 1
            db_post.slug = slug
        elif incoming_title is not None:
            base_slug = slugify(incoming_title)
            slug = base_slug
            i = 1
            while db.execute(select(Post).filter(Post.slug == slug, Post.id != db_post.id)).scalar_one_or_none():
                slug = f"{base_slug}-{i}"
                i += 1
            db_post.slug = slug

        should_update_content = (
            incoming_editor_mode is not None
            or incoming_content_markdown is not None
            or incoming_content_html is not None
        )
        if should_update_content:
            resolved_mode = infer_editor_mode(
                requested_mode=incoming_editor_mode,
                content_markdown=incoming_content_markdown if incoming_content_markdown is not None else db_post.content_markdown,
                content_html=incoming_content_html if incoming_content_html is not None else db_post.content_html,
                fallback="html" if (db_post.content_html or "").strip() and not (db_post.content_markdown or "").strip() else "markdown",
            )
            next_markdown, next_html = _resolve_storage_contents(
                editor_mode=resolved_mode,
                content_markdown=incoming_content_markdown if incoming_content_markdown is not None else db_post.content_markdown,
                content_html=incoming_content_html if incoming_content_html is not None else db_post.content_html,
            )
            db_post.content_markdown = next_markdown
            db_post.content_html = next_html

        for key, value in update_data.items():
            if key == "excerpt":
                db_post.excerpt = _normalize_excerpt_value(value)
            # 跳过featured_image_url，因为它已经在上面处理过了
            elif key not in {"featured_image_url", "category_ids", "tag_ids", "format_ids", "content_markdown", "content_html", "editor_mode"}:
                setattr(db_post, key, value)

        if incoming_page_template is not None:
            target_post_type = incoming_post_type if incoming_post_type is not None else db_post.post_type
            db_post.page_template = _normalize_page_template_for_post(target_post_type, incoming_page_template)
        elif incoming_post_type is not None and str(incoming_post_type).strip().lower() != "page":
            db_post.page_template = "default"

        db_post.media_attachment_summary = _build_media_attachment_summary_payload(
            content_markdown=db_post.content_markdown,
            content_html=db_post.content_html,
            featured_image_url=db_post.featured_image_url,
        )
        
        # 如果状态变为已发布，更新发布时间
        if incoming_status == "published" and db_post.published_at is None:
            db_post.published_at = datetime.now()
        elif incoming_status is not None and incoming_status != "published" and db_post.published_at is not None:
            db_post.published_at = None # 或者保持不变，取决于具体取消发布的需求

        if post.category_ids is not None:
            db_post.categories.clear()
            if post.category_ids:
                categories = db.execute(select(Category).filter(Category.id.in_(post.category_ids))).scalars().all()
                db_post.categories.extend(categories)

        # 更新标签（优先按ID）
        if post.tag_ids is not None:
            db_post.tags.clear()
            if post.tag_ids:
                tags = db.execute(select(Tag).filter(Tag.id.in_(post.tag_ids))).scalars().all()
                db_post.tags.extend(tags)
        elif tag_names is not None:
            db_post.tags.clear()
            for tag_name in tag_names:
                tag = db.execute(select(Tag).filter(Tag.name == tag_name)).scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name, slug=slugify(tag_name))
                    db.add(tag)
                    db.flush()
                db_post.tags.append(tag)

        # 更新内容类型（仅保留一个主类型）
        resolved_format_ids = format_ids if format_ids is not None else post.format_ids
        normalized_format_ids = _normalize_intent_format_ids(db, resolved_format_ids)
        if normalized_format_ids is not None:
            db_post.formats.clear()
            if normalized_format_ids:
                formats = db.execute(select(Format).filter(Format.id.in_(normalized_format_ids))).scalars().all()
                db_post.formats.extend(formats)
        elif db_post.post_type == "post" and not db_post.formats:
            default_intent = _ensure_intent_format(db, "article")
            if default_intent is not None:
                db_post.formats.append(default_intent)

        # 确保 updated_at 设置为当前时间
        db_post.updated_at = datetime.now()
        db.commit()
        db.refresh(db_post)
    return db_post


def get_posts_by_year_month(
    db: Session,
    year: int,
    month: int,
    limit: Optional[int] = None,
) -> List[Post]:
    """按年/月获取已发布文章（不包含页面）"""
    if month < 1 or month > 12:
        return []

    start = datetime(year, month, 1)
    if month == 12:
        end = datetime(year + 1, 1, 1)
    else:
        end = datetime(year, month + 1, 1)

    query = (
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(*get_public_post_conditions())
        .filter(Post.published_at >= start, Post.published_at < end)
        .order_by(Post.published_at.desc())
    )
    if limit is not None:
        query = query.limit(limit)

    posts = db.execute(query).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts


def get_archive_posts(db: Session) -> List[Post]:
    """获取归档页使用的全部已发布文章（不包含页面）"""
    query = (
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(*get_public_post_conditions())
        .order_by(Post.published_at.desc())
    )
    posts = db.execute(query).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts


def get_archive_posts_paginated(db: Session, skip: int = 0, limit: int = 20) -> List[Post]:
    """获取归档页使用的分页文章（仅 post）。"""
    query = (
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(*get_public_post_conditions())
        .order_by(Post.published_at.desc())
        .offset(skip)
        .limit(limit)
    )
    posts = db.execute(query).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts


def count_posts_by_media_attachment(db: Session, media_slug: str) -> int:
    media_key = str(media_slug or "").strip().lower()
    query = select(func.count(Post.id)).where(*get_public_post_conditions())

    if media_key == "images":
        query = query.where(func.json_extract(Post.media_attachment_summary, "$.image_count") == 1)
    elif media_key == "gallery":
        query = query.where(func.json_extract(Post.media_attachment_summary, "$.image_count") >= 2)
    else:
        query = query.where(func.json_extract(Post.media_attachment_summary, _get_media_summary_flag_filter(media_key)) == 1)

    return int(db.execute(query).scalar_one() or 0)


def get_posts_by_media_attachment(
    db: Session,
    media_slug: str,
    *,
    skip: int = 0,
    limit: int = 20,
) -> List[Post]:
    media_key = str(media_slug or "").strip().lower()
    query = (
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags), joinedload(Post.author))
        .filter(*get_public_post_conditions())
    )

    if media_key == "images":
        query = query.where(func.json_extract(Post.media_attachment_summary, "$.image_count") == 1)
    elif media_key == "gallery":
        query = query.where(func.json_extract(Post.media_attachment_summary, "$.image_count") >= 2)
    else:
        query = query.where(func.json_extract(Post.media_attachment_summary, _get_media_summary_flag_filter(media_key)) == 1)

    posts = db.execute(
        query
        .order_by(Post.published_at.desc())
        .offset(skip)
        .limit(limit)
    ).unique().scalars().all()
    _attach_views_metrics(db, posts)
    return posts

def delete_post(db: Session, post_id: int, *, auto_commit: bool = True):
    """删除文章
    
    Args:
        db: 数据库会话
        post_id: 文章ID
        auto_commit: 是否在删除后立即提交事务
        
    Returns:
        被删除的文章对象
    """
    db_post = db.execute(select(Post).filter(Post.id == post_id)).scalar_one_or_none()
    if db_post:
        # 先清理评论，避免遗留孤儿评论或外键约束问题。
        db.execute(delete(Comment).where(Comment.post_id == post_id))
        _delete_post_views_metrics_by_ids(db, [post_id])
        db.delete(db_post)
        if auto_commit:
            db.commit()
    return db_post


def delete_posts_by_ids(db: Session, post_ids: List[int], author_id: Optional[int] = None) -> int:
    """按ID批量删除文章，并使用单次提交以降低事务开销。"""
    normalized_ids = sorted({post_id for post_id in post_ids if post_id is not None})
    if not normalized_ids:
        return 0

    query = select(Post).filter(Post.id.in_(normalized_ids))
    if author_id is not None:
        query = query.filter(Post.author_id == author_id)

    db_posts = db.execute(query).scalars().all()
    if not db_posts:
        return 0

    deletable_post_ids = [post.id for post in db_posts if getattr(post, "id", None) is not None]
    if deletable_post_ids:
        db.execute(delete(Comment).where(Comment.post_id.in_(deletable_post_ids)))
        _delete_post_views_metrics_by_ids(db, deletable_post_ids)

    for db_post in db_posts:
        db.delete(db_post)
    db.commit()
    return len(db_posts)


def bulk_update_posts_status_by_ids(
    db: Session,
    post_ids: List[int],
    status: str,
    author_id: Optional[int] = None,
) -> int:
    """按ID批量更新文章状态，并使用单次提交降低事务开销。"""
    if status not in {"published", "draft"}:
        raise ValueError("Unsupported status")

    normalized_ids = sorted({post_id for post_id in post_ids if isinstance(post_id, int) and post_id > 0})
    if not normalized_ids:
        return 0

    query = select(Post).filter(Post.id.in_(normalized_ids))
    if author_id is not None:
        query = query.filter(Post.author_id == author_id)

    db_posts = db.execute(query).scalars().all()
    if not db_posts:
        return 0

    now = datetime.now()
    for db_post in db_posts:
        db_post.status = status
        if status == "published":
            if db_post.published_at is None:
                db_post.published_at = now
        else:
            db_post.published_at = None
        db_post.updated_at = now

    db.commit()
    return len(db_posts)


