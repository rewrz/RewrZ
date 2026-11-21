"""
RSS订阅 API 模块

提供RSS/Atom订阅功能，支持：
1. 全站RSS订阅
2. 分类RSS订阅
3. 标签RSS订阅  
4. 格式RSS订阅
5. RSS配置管理
"""
import html
import threading
import time
from collections import OrderedDict
from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session
from ..core import public_list_cache
from ..core.database import get_db
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..core.content_access import strip_hide_blocks
from ..core.content_utils import get_effective_content_html, get_effective_plain_text, is_nsfw_rating
from ..core.time_utils import as_utc, utc_iso
from ..crud import setting as crud_setting
from ..models import Post
from ..core.template_context import DEFAULT_BASE_SETTINGS, normalize_rss_content_mode
from ..core.content_intents import choose_primary_intent_slug, to_public_post_segment

router = APIRouter()

# 单条订阅源最多输出多少篇。后台可以填任意数字，读取端必须收口：
# 一次请求读取并逐篇渲染上千篇正文会把单 worker 的渲染线程占满。
RSS_ITEMS_LIMIT_MAX = 100

# 订阅源 XML 缓存。爬虫与阅读器会反复抓 /feed、/rss、/atom.xml，
# 每次请求都重新查文章并渲染 Markdown 是纯浪费；缓存最终 XML 即可。
# 版本号复用 public_list_cache：发布/修改文章、保存站点设置都会递增，
# 缓存随内容变更立即失效，不需要维护第二套失效链路。
_RSS_CACHE_TTL_SECONDS = 60
_RSS_CACHE_MAX_ENTRIES = 32
_RSS_CACHE_MAX_CHARS = 4 * 1024 * 1024
_rss_cache: "OrderedDict[str, tuple[float, str]]" = OrderedDict()
_rss_cache_chars = 0
_rss_cache_lock = threading.Lock()


def _build_feed_cache_key(
    kind: str,
    *,
    filter_key: str,
    limit: int,
    content_mode: str,
    cache_duration: int,
    base_url: str,
) -> str:
    return "|".join(
        [
            kind,
            filter_key or "",
            str(int(limit or 0)),
            str(content_mode or ""),
            str(int(cache_duration or 0)),
            str(base_url or ""),
            str(public_list_cache.get_public_list_cache_version()),
        ]
    )


def _drop_feed_cache_entry(cache_key: str) -> None:
    """移除条目并同步字符计数，调用方必须持有缓存锁。"""
    global _rss_cache_chars
    entry = _rss_cache.pop(cache_key, None)
    if entry is not None:
        _rss_cache_chars -= len(entry[1])


def _read_feed_cache(cache_key: str) -> Optional[str]:
    now = time.monotonic()
    with _rss_cache_lock:
        entry = _rss_cache.get(cache_key)
        if entry is None:
            return None
        expires_at, xml = entry
        if expires_at <= now:
            _drop_feed_cache_entry(cache_key)
            return None
        _rss_cache.move_to_end(cache_key)
        return xml


def _write_feed_cache(cache_key: str, xml: str) -> None:
    global _rss_cache_chars
    size = len(xml)
    if size <= 0 or size > _RSS_CACHE_MAX_CHARS:
        return
    with _rss_cache_lock:
        _drop_feed_cache_entry(cache_key)
        _rss_cache[cache_key] = (time.monotonic() + _RSS_CACHE_TTL_SECONDS, xml)
        _rss_cache_chars += size
        while _rss_cache and (
            len(_rss_cache) > _RSS_CACHE_MAX_ENTRIES or _rss_cache_chars > _RSS_CACHE_MAX_CHARS
        ):
            _, (_, removed_xml) = _rss_cache.popitem(last=False)
            _rss_cache_chars -= len(removed_xml)


def clear_rss_feed_cache() -> None:
    """清空订阅源 XML 缓存，供测试与配置重载使用。"""
    global _rss_cache_chars
    with _rss_cache_lock:
        _rss_cache.clear()
        _rss_cache_chars = 0


def _build_feed_response(
    xml: str,
    *,
    media_type: str,
    cache_duration: int,
) -> Response:
    return Response(
        content=xml,
        media_type=media_type,
        headers={"Cache-Control": f"max-age={max(0, int(cache_duration or 0)) * 60}"},
    )

def check_rss_enabled(db: Session) -> bool:
    """检查RSS是否启用"""
    rss_enabled_setting = crud_setting.get_setting(db, key="rss_enabled")
    return rss_enabled_setting.value.get("value", True) if rss_enabled_setting and rss_enabled_setting.value else True

def _resolve_rss_items_limit(raw_value) -> int:
    """收口订阅条数：后台可填任意值，输出端必须限制在安全范围内。"""
    try:
        limit = int(raw_value)
    except (TypeError, ValueError):
        return 20
    return max(1, min(limit, RSS_ITEMS_LIMIT_MAX))


def _resolve_rss_cache_duration(raw_value) -> int:
    """收口缓存时长（分钟）。

    历史站点可能存在字符串或空值；缓存键与响应头都要用整数，
    这里统一转换为 0–1440 分钟，避免脏值直接触发 500。
    """
    try:
        duration = int(raw_value)
    except (TypeError, ValueError):
        return 60
    return max(0, min(duration, 1440))


def get_rss_config(db: Session) -> dict:
    """获取RSS配置"""
    rss_items_limit_setting = crud_setting.get_setting(db, key="rss_items_limit")
    rss_cache_duration_setting = crud_setting.get_setting(db, key="rss_cache_duration")
    rss_description_setting = crud_setting.get_setting(db, key="rss_description")
    rss_content_mode_setting = crud_setting.get_setting(db, key="rss_content_mode")
    
    return {
        "items_limit": _resolve_rss_items_limit(
            rss_items_limit_setting.value.get("value", 20)
            if rss_items_limit_setting and rss_items_limit_setting.value
            else 20
        ),
        "cache_duration": _resolve_rss_cache_duration(
            rss_cache_duration_setting.value.get("value", 60)
            if rss_cache_duration_setting and rss_cache_duration_setting.value
            else 60
        ),
        "description": rss_description_setting.value.get("value", "") if rss_description_setting and rss_description_setting.value else "",
        "content_mode": normalize_rss_content_mode(
            rss_content_mode_setting.value.get("value")
            if rss_content_mode_setting and rss_content_mode_setting.value
            else DEFAULT_BASE_SETTINGS["rss_content_mode"]
        )
    }

@router.get("/feed.xml")
@router.get("/feed")
def rss_feed(request: Request, db: Session = Depends(get_db)):
    """
    全站RSS订阅源

    裸 /feed 与 /feed.xml 共用同一逻辑，兼容阅读器默认探测路径。
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/rss.xml") 
@router.get("/rss")
def rss_feed_alt(request: Request, db: Session = Depends(get_db)):
    """RSS订阅源（备用路径，兼容 /rss 与 /rss.xml）"""
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/atom.xml")
def atom_feed(request: Request, db: Session = Depends(get_db)):
    """
    Atom格式订阅源
    
    生成包含最新文章的Atom 1.0格式订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
    
    rss_config = get_rss_config(db)
    return generate_atom_feed(request, db, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/feed/category/{category_slug}")
def category_rss_feed(category_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    分类RSS订阅源
    
    生成指定分类的RSS订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
        
    category = crud_category.get_category_by_slug(db, slug=category_slug)
    if not category:
        raise HTTPException(status_code=404, detail="分类不存在")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, category=category, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/feed/tag/{tag_slug}")
def tag_rss_feed(tag_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    标签RSS订阅源
    
    生成指定标签的RSS订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
        
    tag = crud_tag.get_tag_by_slug(db, slug=tag_slug)
    if not tag:
        raise HTTPException(status_code=404, detail="标签不存在")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, tag=tag, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

@router.get("/feed/format/{format_slug}")
def format_rss_feed(format_slug: str, request: Request, db: Session = Depends(get_db)):
    """
    格式RSS订阅源
    
    生成指定格式的RSS订阅源
    """
    if not check_rss_enabled(db):
        raise HTTPException(status_code=404, detail="RSS订阅功能已禁用")
        
    format_obj = crud_format.get_format_by_slug(db, slug=format_slug)
    if not format_obj:
        raise HTTPException(status_code=404, detail="格式不存在")
    
    rss_config = get_rss_config(db)
    return generate_rss_feed(request, db, format_obj=format_obj, limit=rss_config["items_limit"], cache_duration=rss_config["cache_duration"], content_mode=rss_config["content_mode"])

def generate_rss_feed(
    request: Request,
    db: Session,
    category=None,
    tag=None,
    format_obj=None,
    limit: int = 20,
    cache_duration: int = 60,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
):
    """
    生成RSS 2.0格式的订阅源
    
    Args:
        request: FastAPI请求对象
        db: 数据库会话
        category: 分类筛选
        tag: 标签筛选
        format_obj: 格式筛选
        limit: 文章数量限制
        cache_duration: 缓存时间（分钟）
    """
    # 获取站点信息（单键设置缓存 300s，命中时不产生 SQL）
    site_info = get_site_info(db, request)
    normalized_mode = normalize_rss_content_mode(content_mode)
    limit = _resolve_rss_items_limit(limit)
    cache_duration = _resolve_rss_cache_duration(cache_duration)
    filter_key = (
        f"cat:{category.slug}"
        if category
        else f"tag:{tag.slug}"
        if tag
        else f"fmt:{format_obj.slug}"
        if format_obj
        else ""
    )
    cache_key = _build_feed_cache_key(
        "rss",
        filter_key=filter_key,
        limit=limit,
        content_mode=normalized_mode,
        cache_duration=cache_duration,
        base_url=site_info["base_url"],
    )
    cached_xml = _read_feed_cache(cache_key)
    if cached_xml is not None:
        return _build_feed_response(
            cached_xml,
            media_type="application/rss+xml; charset=utf-8",
            cache_duration=cache_duration,
        )

    # 获取文章列表
    posts = get_filtered_posts(db, category, tag, format_obj, limit)
    
    # 构建RSS标题和描述
    if category:
        feed_title = f"{site_info['title']} - {category.name}"
        feed_description = f"{site_info['description']} - {category.name}分类"
        feed_link = f"{site_info['base_url']}/archives/by-category/{category.slug}"
    elif tag:
        feed_title = f"{site_info['title']} - {tag.name}"
        feed_description = f"{site_info['description']} - {tag.name}标签"
        feed_link = f"{site_info['base_url']}/archives/by-tag/{tag.slug}"
    elif format_obj:
        feed_title = f"{site_info['title']} - {format_obj.name}"
        feed_description = f"{site_info['description']} - {format_obj.name}格式"
        feed_link = f"{site_info['base_url']}/formats/{format_obj.slug}"
    else:
        feed_title = site_info['title']
        feed_description = site_info['description']
        feed_link = site_info['base_url']
    
    # 生成RSS XML
    rss_xml = generate_rss_xml(
        title=feed_title,
        description=feed_description,
        link=feed_link,
        posts=posts,
        site_info=site_info,
        content_mode=normalized_mode
    )
    _write_feed_cache(cache_key, rss_xml)

    return _build_feed_response(
        rss_xml,
        media_type="application/rss+xml; charset=utf-8",
        cache_duration=cache_duration,
    )

def generate_atom_feed(
    request: Request,
    db: Session,
    limit: int = 20,
    cache_duration: int = 60,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
):
    """生成Atom 1.0格式的订阅源"""
    site_info = get_site_info(db, request)
    normalized_mode = normalize_rss_content_mode(content_mode)
    limit = _resolve_rss_items_limit(limit)
    cache_duration = _resolve_rss_cache_duration(cache_duration)
    cache_key = _build_feed_cache_key(
        "atom",
        filter_key="",
        limit=limit,
        content_mode=normalized_mode,
        cache_duration=cache_duration,
        base_url=site_info["base_url"],
    )
    cached_xml = _read_feed_cache(cache_key)
    if cached_xml is not None:
        return _build_feed_response(
            cached_xml,
            media_type="application/atom+xml; charset=utf-8",
            cache_duration=cache_duration,
        )

    posts = get_filtered_posts(db, limit=limit)

    atom_xml = generate_atom_xml(
        title=site_info['title'],
        subtitle=site_info['description'],
        link=site_info['base_url'],
        posts=posts,
        site_info=site_info,
        content_mode=normalized_mode
    )
    _write_feed_cache(cache_key, atom_xml)

    return _build_feed_response(
        atom_xml,
        media_type="application/atom+xml; charset=utf-8",
        cache_duration=cache_duration,
    )

def get_site_info(db: Session, request: Request) -> dict:
    """获取站点信息"""
    # 获取站点设置
    site_title_setting = crud_setting.get_setting(db, key="site_title")
    tagline_setting = crud_setting.get_setting(db, key="tagline")
    site_url_setting = crud_setting.get_setting(db, key="site_url")
    admin_email_setting = crud_setting.get_setting(db, key="admin_email")
    rss_description_setting = crud_setting.get_setting(db, key="rss_description")
    
    title = site_title_setting.value.get("value") if site_title_setting and site_title_setting.value else DEFAULT_BASE_SETTINGS["site_title"]
    default_description = tagline_setting.value.get("value") if tagline_setting and tagline_setting.value else DEFAULT_BASE_SETTINGS["tagline"]
    # 如果设置了自定义RSS描述，则使用自定义描述，否则使用站点标语
    description = rss_description_setting.value.get("value") if rss_description_setting and rss_description_setting.value and rss_description_setting.value.get("value") else default_description
    base_url = site_url_setting.value.get("value") if site_url_setting and site_url_setting.value else str(request.base_url).rstrip('/')
    admin_email = admin_email_setting.value.get("value") if admin_email_setting and admin_email_setting.value else "admin@example.com"
    
    return {
        "title": title,
        "description": description,
        "base_url": base_url,
        "admin_email": admin_email
    }

def get_filtered_posts(
    db: Session,
    category=None,
    tag=None,
    format_obj=None,
    limit: int = 20
) -> List[Post]:
    """获取筛选后的文章列表，订阅源不含 NSFW 内容。"""
    # 筛选条件必须下沉到查询，否则最新 N 篇之外的分类/标签/格式会得到空订阅源
    if category:
        posts = crud_post.get_posts_by_category(db, category_id=category.id, limit=limit)
    elif tag:
        posts = crud_post.get_posts_by_tag(db, tag_id=tag.id, limit=limit)
    elif format_obj:
        posts = crud_post.get_posts_by_format(db, format_id=format_obj.id, limit=limit)
    else:
        posts = crud_post.get_posts(
            db,
            skip=0,
            limit=limit,
            status="published",
            post_type="post",
        )
    # NSFW 内容不进入 RSS / Atom，避免敏感正文与封面被第三方阅读器二次分发
    return [post for post in posts if not is_nsfw_rating(getattr(post, "content_rating", "general"))]

def _resolve_public_excerpt(post: Post, fallback_text: str) -> str:
    """RSS 摘要：剔除手写摘要中的评论后可见块，再回退到公开正文。"""
    excerpt = strip_hide_blocks(post.excerpt or "").strip()
    return excerpt or fallback_text


def _build_entry_title(post: Post, fallback_text: str) -> str:
    """RSS 条目标题：无标题内容用摘要兜底，避免订阅器出现空白标题。"""
    title = (post.title or "").strip()
    if title:
        return title
    candidate = _resolve_public_excerpt(post, fallback_text)
    candidate = " ".join(candidate.split())
    return candidate[:100] if candidate else "无标题"


def _resolve_public_content(post: Post) -> tuple[str, str]:
    """返回可公开分发的正文 HTML 与纯文本，剔除评论后可见块。"""
    raw_markdown = post.content_markdown or ""
    raw_html = post.content_html or ""
    public_markdown = strip_hide_blocks(raw_markdown)
    if public_markdown != raw_markdown:
        # 存在 [hide] 块时只使用清洗后的 Markdown，避免回退到含隐藏内容的 HTML
        return (
            get_effective_content_html(public_markdown, ""),
            get_effective_plain_text(public_markdown, ""),
        )
    return (
        get_effective_content_html(raw_markdown, raw_html),
        get_effective_plain_text(raw_markdown, raw_html),
    )


def generate_rss_xml(
    title: str,
    description: str,
    link: str,
    posts: List[Post],
    site_info: dict,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
) -> str:
    """生成RSS 2.0 XML"""
    now = datetime.now(timezone.utc)
    
    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<rss version="2.0" xmlns:atom="http://www.w3.org/2005/Atom">',
        '<channel>',
        f'<title>{html.escape(title)}</title>',
        f'<link>{html.escape(link)}</link>',
        f'<description>{html.escape(description)}</description>',
        f'<language>zh-cn</language>',
        f'<lastBuildDate>{now.strftime("%a, %d %b %Y %H:%M:%S %z")}</lastBuildDate>',
        f'<atom:link href="{site_info["base_url"]}/feed.xml" rel="self" type="application/rss+xml" />',
        f'<managingEditor>{site_info["admin_email"]} ({title})</managingEditor>',
        f'<webMaster>{site_info["admin_email"]}</webMaster>',
        f'<generator>{html.escape(DEFAULT_BASE_SETTINGS["site_title"])}</generator>',
    ]
    
    # 添加文章项
    for post in posts:
        format_slugs = [fmt.slug for fmt in post.formats if getattr(fmt, "slug", None)] if post.formats else []
        primary_intent = choose_primary_intent_slug(format_slugs)
        post_url = f'{site_info["base_url"]}/{to_public_post_segment(primary_intent)}/{post.slug}'
        pub_date = post.published_at or post.created_at
        public_html, public_text = _resolve_public_content(post)
        fallback_excerpt = public_text[:500]
        entry_title = _build_entry_title(post, fallback_excerpt)
        # 全文模式与 Atom 对齐，正文为空时回退到摘要
        item_description = public_html if content_mode == "full" and public_html else _resolve_public_excerpt(post, fallback_excerpt)
        
        xml_lines.extend([
            '<item>',
            f'<title>{html.escape(entry_title)}</title>',
            f'<link>{html.escape(post_url)}</link>',
            f'<description>{html.escape(item_description)}</description>',
            f'<guid isPermaLink="true">{html.escape(post_url)}</guid>',
            f'<pubDate>{as_utc(pub_date).strftime("%a, %d %b %Y %H:%M:%S %z")}</pubDate>',
        ])
        
        # 添加分类信息
        for category in post.categories:
            xml_lines.append(f'<category>{html.escape(category.name)}</category>')
        
        xml_lines.append('</item>')
    
    xml_lines.extend([
        '</channel>',
        '</rss>'
    ])
    
    return '\n'.join(xml_lines)

def generate_atom_xml(
    title: str,
    subtitle: str,
    link: str,
    posts: List[Post],
    site_info: dict,
    content_mode: str = DEFAULT_BASE_SETTINGS["rss_content_mode"]
) -> str:
    """生成Atom 1.0 XML"""
    now = datetime.now(timezone.utc)
    
    xml_lines = [
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f'<title>{html.escape(title)}</title>',
        f'<subtitle>{html.escape(subtitle)}</subtitle>',
        f'<link href="{html.escape(link)}" />',
        f'<link href="{site_info["base_url"]}/atom.xml" rel="self" />',
        f'<updated>{utc_iso(now)}</updated>',
        f'<id>{site_info["base_url"]}/</id>',
        '<author>',
        f'<name>{html.escape(title)}</name>',
        f'<email>{site_info["admin_email"]}</email>',
        '</author>',
        f'<generator>{html.escape(DEFAULT_BASE_SETTINGS["site_title"])}</generator>',
    ]
    
    # 添加文章项
    for post in posts:
        format_slugs = [fmt.slug for fmt in post.formats if getattr(fmt, "slug", None)] if post.formats else []
        primary_intent = choose_primary_intent_slug(format_slugs)
        post_url = f'{site_info["base_url"]}/{to_public_post_segment(primary_intent)}/{post.slug}'
        pub_date = post.published_at or post.created_at
        public_html, public_text = _resolve_public_content(post)
        fallback_excerpt = public_text[:500]
        entry_title = _build_entry_title(post, fallback_excerpt)
        
        entry_lines = [
            '<entry>',
            f'<title>{html.escape(entry_title)}</title>',
            f'<link href="{html.escape(post_url)}" />',
            f'<id>{html.escape(post_url)}</id>',
            f'<updated>{utc_iso(pub_date)}</updated>',
            f'<summary>{html.escape(_resolve_public_excerpt(post, fallback_excerpt))}</summary>',
        ]
        # 摘要模式不再输出全文 content；正文为空时同样退回摘要，与 RSS 保持一致
        if content_mode == "full" and public_html:
            entry_lines.append(f'<content type="html">{html.escape(public_html)}</content>')
        
        # 添加分类信息
        for category in post.categories:
            entry_lines.append(f'<category term="{html.escape(category.slug)}" label="{html.escape(category.name)}" />')
        
        entry_lines.append('</entry>')
        xml_lines.extend(entry_lines)
    
    xml_lines.extend([
        '</feed>'
    ])
    
    return '\n'.join(xml_lines)

