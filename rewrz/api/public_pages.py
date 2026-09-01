from typing import Any, Callable, Dict, List
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.content_intents import normalize_public_intent_slug
from ..core.format_archive_metrics import (
    attach_format_comment_counts,
    build_format_category_topic_count,
    build_format_tag_metrics,
    build_micro_interaction_count,
)
from ..core.public_metrics_cache import (
    build_format_archive_cache_key,
    get_format_archive_stats_snapshot,
    get_homepage_stats_snapshot,
)
from ..core.media_attachments import (
    get_default_media_navigation,
    list_registered_media_attachment_keys,
)
from ..core.public_profile import get_public_profile_resolver
from ..core.template_context import build_base_template_context
from ..crud import format as crud_format
from ..crud import category as crud_category
from ..crud import comment as crud_comment
from ..crud import post as crud_post
from ..crud import tag as crud_tag
from ..models import Post

router = APIRouter()

_templates = None
_get_page_config: Callable[..., Any] | None = None
_resolve_homepage_posts_per_page: Callable[..., int] | None = None
_resolve_archive_posts_per_page: Callable[..., int] | None = None
_normalize_list_navigation_mode: Callable[[Any], str] | None = None
_build_public_pagination: Callable[..., tuple[int, dict]] | None = None
_attach_article_cover_urls: Callable[..., None] | None = None
_attach_post_author_profiles: Callable[..., None] | None = None
_sum_post_views_metrics: Callable[[Session], int] | None = None
_resolve_format_by_slug: Callable[..., Any] | None = None
_load_post_views_metrics_map: Callable[..., Dict[int, int]] | None = None


def _build_cover_url_map(posts: List[Post], attr_name: str = "archive_cover_url") -> Dict[int, str]:
    result: Dict[int, str] = {}
    for post in posts or []:
        post_id = getattr(post, "id", None)
        if post_id is None:
            continue
        value = str(getattr(post, attr_name, "") or "").strip()
        if value:
            result[int(post_id)] = value
    return result


def _attach_cover_url_attr(
    posts: List[Post],
    cover_url_map: Dict[int, str],
    *,
    attr_name: str = "archive_card_cover_url",
) -> None:
    for post in posts or []:
        post_id = getattr(post, "id", None)
        if post_id is None:
            continue
        setattr(post, attr_name, str(cover_url_map.get(int(post_id), "") or "").strip())


def _load_homepage_stats(db: Session) -> dict:
    homepage_stats = {
        "categories_count": crud_category.count_categories(db),
        "tags_count": crud_tag.count_tags(db),
        "comments_count": crud_comment.count_comments(db),
        "total_views": 0,
    }
    try:
        homepage_stats["total_views"] = _sum_post_views_metrics(db)
    except Exception:
        homepage_stats["total_views"] = 0
    return homepage_stats


def register_public_page_routes(
    *,
    templates,
    get_page_config: Callable[..., Any],
    resolve_homepage_posts_per_page: Callable[..., int],
    resolve_archive_posts_per_page: Callable[..., int],
    normalize_list_navigation_mode: Callable[[Any], str],
    build_public_pagination: Callable[..., tuple[int, dict]],
    attach_article_cover_urls: Callable[..., None],
    attach_post_author_profiles: Callable[..., None],
    sum_post_views_metrics: Callable[[Session], int],
    resolve_format_by_slug: Callable[..., Any],
    load_post_views_metrics_map: Callable[..., Dict[int, int]],
) -> None:
    global _templates
    global _get_page_config
    global _resolve_homepage_posts_per_page
    global _resolve_archive_posts_per_page
    global _normalize_list_navigation_mode
    global _build_public_pagination
    global _attach_article_cover_urls
    global _attach_post_author_profiles
    global _sum_post_views_metrics
    global _resolve_format_by_slug
    global _load_post_views_metrics_map

    _templates = templates
    _get_page_config = get_page_config
    _resolve_homepage_posts_per_page = resolve_homepage_posts_per_page
    _resolve_archive_posts_per_page = resolve_archive_posts_per_page
    _normalize_list_navigation_mode = normalize_list_navigation_mode
    _build_public_pagination = build_public_pagination
    _attach_article_cover_urls = attach_article_cover_urls
    _attach_post_author_profiles = attach_post_author_profiles
    _sum_post_views_metrics = sum_post_views_metrics
    _resolve_format_by_slug = resolve_format_by_slug
    _load_post_views_metrics_map = load_post_views_metrics_map


def _ensure_registered() -> None:
    if (
        _templates is None
        or _get_page_config is None
        or _resolve_homepage_posts_per_page is None
        or _resolve_archive_posts_per_page is None
        or _normalize_list_navigation_mode is None
        or _build_public_pagination is None
        or _attach_article_cover_urls is None
        or _attach_post_author_profiles is None
        or _sum_post_views_metrics is None
        or _resolve_format_by_slug is None
        or _load_post_views_metrics_map is None
    ):
        raise RuntimeError("公共页面路由尚未完成注册")


@router.get("/", response_class=HTMLResponse)
async def homepage(request: Request, page: int = 1, append: int = 0, db: Session = Depends(get_db)):
    _ensure_registered()
    page = max(1, int(page or 1))
    homepage_posts_limit = _resolve_homepage_posts_per_page(_get_page_config(db, "homepage_posts_limit", 10), 10)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))

    total_posts_count = db.execute(
        select(func.count(Post.id)).where(*crud_post.get_public_post_conditions())
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        homepage_posts_limit,
        lambda target_page: f"/?page={target_page}",
    )
    offset = (page - 1) * homepage_posts_limit
    posts = crud_post.get_posts(
        db,
        skip=offset,
        limit=homepage_posts_limit,
        status="published",
        post_type="post",
    )

    _attach_article_cover_urls(db, posts, attr_name="homepage_cover_url")
    profile_resolver = get_public_profile_resolver()
    site_profile = profile_resolver.resolve_homepage_profile(request, db)

    homepage_stats = get_homepage_stats_snapshot(
        db,
        loader=_load_homepage_stats,
    )

    from ..api.seo import _generate_homepage_seo_data

    seo_data = _generate_homepage_seo_data(request, db)
    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "posts": posts,
            "seo_data": seo_data,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
            "timeline_start_index": offset,
            "site_profile": site_profile,
            "homepage_stats": homepage_stats,
        }
    )

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return _templates.TemplateResponse(request, "fragments/homepage_append.html", context)

    return _templates.TemplateResponse(request, "index.html", context)


@router.get("/archives/media/{media_slug}", response_class=HTMLResponse)
async def posts_by_media_attachment(
    request: Request,
    media_slug: str,
    page: int = 1,
    append: int = 0,
    db: Session = Depends(get_db),
):
    _ensure_registered()
    normalized_media_slug = (media_slug or "").strip().lower()
    registered_media_keys = set(list_registered_media_attachment_keys())
    if normalized_media_slug not in registered_media_keys:
        raise HTTPException(status_code=404, detail="Media attachment type not found")

    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_archive_posts_per_page(_get_page_config(db, "archive_posts_limit", 20), 20)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))
    total_matched_count = crud_post.count_posts_by_media_attachment(db, normalized_media_slug)
    page, pagination = _build_public_pagination(
        page,
        total_matched_count,
        archive_posts_limit,
        lambda target_page: f"/archives/media/{normalized_media_slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    matched_posts = crud_post.get_posts_by_media_attachment(
        db,
        normalized_media_slug,
        skip=offset,
        limit=archive_posts_limit,
    )
    for post in matched_posts:
        summary_dict = getattr(post, "media_attachment_summary", None)
        if not isinstance(summary_dict, dict):
            summary_dict = {}
        media_flags = summary_dict.get("flags", {})
        if not isinstance(media_flags, dict):
            media_flags = {}

        featured_image_url = str(getattr(post, "featured_image_url", "") or "").strip()
        all_image_urls: List[str] = []
        if featured_image_url:
            all_image_urls.append(featured_image_url)
        for image_url in list(summary_dict.get("image_urls", []) or []):
            normalized_image_url = str(image_url or "").strip()
            if not normalized_image_url or normalized_image_url in all_image_urls:
                continue
            all_image_urls.append(normalized_image_url)

        setattr(post, "media_flags", media_flags)
        setattr(post, "all_image_urls", list(all_image_urls))
        external_links = list(summary_dict.get("external_links", []) or [])
        primary_link = str(external_links[0] or "").strip() if external_links else ""
        setattr(post, "media_primary_external_link", primary_link)
        setattr(post, "media_primary_external_domain", urlparse(primary_link).netloc if primary_link else "")
    _attach_post_author_profiles(
        db,
        matched_posts,
        fallback_name=str(getattr(request.state, "site_title", "博主") or "博主"),
    )

    media_nav_items = get_default_media_navigation()
    selected_media_item = next(
        (item for item in media_nav_items if item.get("key") == normalized_media_slug),
        {"key": normalized_media_slug, "name": normalized_media_slug, "icon": "fa-photo-film"},
    )

    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "media_slug": normalized_media_slug,
            "media_item": selected_media_item,
            "media_nav_items": media_nav_items,
            "posts": matched_posts,
            "total_count": total_matched_count,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
        }
    )
    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return _templates.TemplateResponse(request, "fragments/media_archive_append.html", context)
    return _templates.TemplateResponse(request, "media_archive.html", context)


@router.get("/formats/{format_slug}", response_class=HTMLResponse)
async def format_page(
    request: Request,
    format_slug: str,
    page: int = 1,
    append: int = 0,
    db: Session = Depends(get_db),
):
    _ensure_registered()
    format_obj, resolved_slug = _resolve_format_by_slug(db, format_slug)
    if format_obj is None:
        raise HTTPException(status_code=404, detail="Format not found")

    page = max(1, int(page or 1))
    canonical_format_slug = resolved_slug or normalize_public_intent_slug(format_slug) or format_slug
    archive_posts_limit = _resolve_archive_posts_per_page(_get_page_config(db, "archive_posts_limit", 20), 20)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))
    exclude_format_ids: List[int] = []

    if canonical_format_slug == "article":
        for excluded_slug in ("micro", "poem"):
            excluded_format = crud_format.get_format_by_slug(db, slug=excluded_slug)
            if excluded_format and excluded_format.id != format_obj.id:
                exclude_format_ids.append(excluded_format.id)

    count_query = select(func.count(Post.id)).where(
        Post.formats.any(id=format_obj.id),
        *crud_post.get_public_post_conditions(),
    )
    for excluded_format_id in exclude_format_ids:
        count_query = count_query.where(~Post.formats.any(id=excluded_format_id))

    total_posts_count = db.execute(count_query).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/formats/{canonical_format_slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_posts_by_format(
        db,
        format_id=format_obj.id,
        skip=offset,
        limit=archive_posts_limit,
        exclude_format_ids=exclude_format_ids,
    )
    attach_format_comment_counts(db, posts)

    format_post_ids_query = select(Post.id).where(
        Post.formats.any(id=format_obj.id),
        *crud_post.get_public_post_conditions(),
    )
    for excluded_format_id in exclude_format_ids:
        format_post_ids_query = format_post_ids_query.where(~Post.formats.any(id=excluded_format_id))

    def _load_format_archive_stats(metric_db: Session) -> Dict[str, Any]:
        micro_interaction_count = 0
        if canonical_format_slug == "micro":
            micro_interaction_count = build_micro_interaction_count(metric_db, format_post_ids_query)

        format_tag_topic_count = 0
        format_category_topic_count = 0
        format_hot_tags: List[Dict[str, Any]] = []
        if canonical_format_slug in {"micro", "poem", "article"}:
            format_tag_topic_count, format_hot_tags = build_format_tag_metrics(
                metric_db,
                format_post_ids_query=format_post_ids_query,
                load_post_views_metrics_map=_load_post_views_metrics_map,
            )

        if canonical_format_slug == "article":
            format_category_topic_count = build_format_category_topic_count(
                metric_db,
                format_post_ids_query=format_post_ids_query,
            )

        return {
            "micro_interaction_count": int(micro_interaction_count or 0),
            "format_tag_topic_count": int(format_tag_topic_count or 0),
            "format_category_topic_count": int(format_category_topic_count or 0),
            "format_hot_tags": list(format_hot_tags or []),
        }

    format_stats = get_format_archive_stats_snapshot(
        db,
        cache_key=build_format_archive_cache_key(
            canonical_format_slug,
            exclude_format_ids=exclude_format_ids,
        ),
        loader=_load_format_archive_stats,
    )

    profile_resolver = get_public_profile_resolver()
    format_profile = profile_resolver.resolve_format_profile(request, db, canonical_format_slug)
    _attach_post_author_profiles(db, posts, fallback_name=format_profile.get("display_name", "博主"))

    if canonical_format_slug == "article":
        _attach_article_cover_urls(db, posts, attr_name="archive_cover_url")
    archive_cover_url_map = _build_cover_url_map(posts)
    _attach_cover_url_attr(posts, archive_cover_url_map)

    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "format": format_obj,
            "format_slug": canonical_format_slug,
            "posts": posts,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
            "format_profile": format_profile,
            "micro_interaction_count": int(format_stats.get("micro_interaction_count", 0) or 0),
            "format_tag_topic_count": int(format_stats.get("format_tag_topic_count", 0) or 0),
            "format_category_topic_count": int(format_stats.get("format_category_topic_count", 0) or 0),
            "format_hot_tags": list(format_stats.get("format_hot_tags", []) or []),
            "format_stats_cache_hit": bool(format_stats.get("cache_hit", False)),
            "archive_cover_url_map": archive_cover_url_map,
        }
    )

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return _templates.TemplateResponse(request, "fragments/format_archive_append.html", context)

    return _templates.TemplateResponse(request, "format_archive.html", context)


@router.get("/archives/by-category/{category_slug}", response_class=HTMLResponse)
async def posts_by_category(
    request: Request,
    category_slug: str,
    page: int = 1,
    append: int = 0,
    db: Session = Depends(get_db),
):
    _ensure_registered()
    category = crud_category.get_category_by_slug(db, slug=category_slug)
    if category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_archive_posts_per_page(_get_page_config(db, "archive_posts_limit", 20), 20)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))

    total_posts_count = db.execute(
        select(func.count(Post.id)).where(
            Post.categories.any(id=category.id),
            *crud_post.get_public_post_conditions(),
        )
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives/by-category/{category.slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_posts_by_category(
        db,
        category_id=category.id,
        skip=offset,
        limit=archive_posts_limit,
    )
    _attach_article_cover_urls(db, posts, attr_name="archive_cover_url")
    archive_cover_url_map = _build_cover_url_map(posts)
    _attach_cover_url_attr(posts, archive_cover_url_map)

    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "category": category,
            "posts": posts,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
            "archive_cover_url_map": archive_cover_url_map,
        }
    )

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return _templates.TemplateResponse(request, "fragments/category_archive_append.html", context)

    return _templates.TemplateResponse(request, "category_archive.html", context)


@router.get("/archives/by-tag/{tag_slug}", response_class=HTMLResponse)
async def posts_by_tag(
    request: Request,
    tag_slug: str,
    page: int = 1,
    append: int = 0,
    db: Session = Depends(get_db),
):
    _ensure_registered()
    tag = crud_tag.get_tag_by_slug(db, slug=tag_slug)
    if tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_archive_posts_per_page(_get_page_config(db, "archive_posts_limit", 20), 20)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))

    total_posts_count = db.execute(
        select(func.count(Post.id)).where(
            Post.tags.any(id=tag.id),
            *crud_post.get_public_post_conditions(),
        )
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives/by-tag/{tag.slug}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_posts_by_tag(
        db,
        tag_id=tag.id,
        skip=offset,
        limit=archive_posts_limit,
    )
    _attach_article_cover_urls(db, posts, attr_name="archive_cover_url")
    archive_cover_url_map = _build_cover_url_map(posts)
    _attach_cover_url_attr(posts, archive_cover_url_map)

    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "tag": tag,
            "posts": posts,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
            "archive_cover_url_map": archive_cover_url_map,
        }
    )

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return _templates.TemplateResponse(request, "fragments/tag_archive_append.html", context)

    return _templates.TemplateResponse(request, "tag_archive.html", context)


@router.get("/archives/{year}/{month}", response_class=HTMLResponse)
async def posts_by_month(
    request: Request,
    year: int,
    month: int,
    page: int = 1,
    append: int = 0,
    db: Session = Depends(get_db),
):
    _ensure_registered()
    if month < 1 or month > 12:
        raise HTTPException(status_code=404, detail="Invalid month")

    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_archive_posts_per_page(_get_page_config(db, "archive_posts_limit", 20), 20)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))

    all_posts = crud_post.get_posts_by_year_month(db, year=year, month=month)
    total_posts_count = len(all_posts)
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives/{year}/{month}?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = all_posts[offset : offset + archive_posts_limit]

    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "year": year,
            "month": month,
            "posts": posts,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
        }
    )

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        return _templates.TemplateResponse(request, "fragments/monthly_archive_append.html", context)

    return _templates.TemplateResponse(request, "monthly_archive.html", context)


@router.get("/archives", response_class=HTMLResponse)
async def archives_page(
    request: Request,
    page: int = 1,
    append: int = 0,
    append_view: str = "yearly",
    db: Session = Depends(get_db),
):
    _ensure_registered()
    page = max(1, int(page or 1))
    archive_posts_limit = _resolve_archive_posts_per_page(_get_page_config(db, "archive_posts_limit", 20), 20)
    list_navigation_mode = _normalize_list_navigation_mode(_get_page_config(db, "list_navigation_mode", "pagination"))
    total_posts_count = db.execute(
        select(func.count(Post.id)).where(*crud_post.get_public_post_conditions())
    ).scalar_one()
    page, pagination = _build_public_pagination(
        page,
        total_posts_count,
        archive_posts_limit,
        lambda target_page: f"/archives?page={target_page}",
    )
    offset = (page - 1) * archive_posts_limit
    posts = crud_post.get_archive_posts_paginated(
        db,
        skip=offset,
        limit=archive_posts_limit,
    )

    context = build_base_template_context(request)
    context.update(
        {
            "db": db,
            "posts": posts,
            "pagination": pagination,
            "list_navigation_mode": list_navigation_mode,
            "append_view": append_view if append_view in {"yearly", "monthly"} else "yearly",
        }
    )

    if request.headers.get("HX-Request") == "true" and int(append or 0) == 1 and list_navigation_mode == "infinite_scroll":
        if context["append_view"] == "monthly":
            return _templates.TemplateResponse(request, "fragments/archives_monthly_append.html", context)
        return _templates.TemplateResponse(request, "fragments/archives_yearly_append.html", context)

    return _templates.TemplateResponse(request, "archives.html", context)
