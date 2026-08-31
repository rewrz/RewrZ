"""
Jinja2模板过滤器

提供模板中使用的自定义过滤器，包括：
- MD5哈希计算（用于Gravatar）
- 头像URL生成
- 时间格式化等
"""

import hashlib
import re
from html import escape
from datetime import datetime
from typing import Optional
from pathlib import Path
from urllib.parse import urlparse, urlsplit
from jinja2 import Environment
from .license_manager import render_license, LicenseManager
from .donation_system import render_donation_widget
from .blog_enhancements import calculate_reading_time, get_related_posts, get_post_statistics
from .content_utils import (
    get_effective_content_html,
    get_effective_plain_text,
    markdown_to_plain_text,
    html_to_plain_text,
)
from .content_access import strip_hide_blocks
from .micro_text import enhance_micro_html
from .content_intents import choose_primary_intent_slug, to_public_post_segment
from ..core.config import settings # 导入settings
from ..core.database import get_db
from ..core.thumbnail_service import (
    build_variant_url,
    is_local_media_url,
    resolve_media_id_from_url,
)

_STATIC_ROOT = Path(__file__).resolve().parents[1] / "static"


def md5_filter(text: str) -> str:
    """
    MD5哈希过滤器
    
    Args:
        text: 要哈希的文本
        
    Returns:
        MD5哈希值
    """
    if not text:
        return ""
    return hashlib.md5(text.lower().strip().encode('utf-8')).hexdigest()


def gravatar_url_filter(email: str, size: int = 80, default: str = "identicon") -> str:
    """
    生成Gravatar URL的过滤器
    
    Args:
        email: 邮箱地址
        size: 头像尺寸
        default: 默认头像类型
        
    Returns:
        Gravatar URL
    """
    if not email:
        return f"/static/images/default-avatar.png"
    
    email_hash = md5_filter(email)
    return f"https://www.gravatar.com/avatar/{email_hash}?s={size}&d={default}&r=g"


def avatar_url_filter(user_obj, size: int = 80) -> str:
    """
    生成用户头像URL的过滤器
    
    优先级：自定义头像 > Gravatar > 默认头像
    
    Args:
        user_obj: 用户对象
        size: 头像尺寸
        
    Returns:
        头像URL
    """
    # 检查是否有自定义头像
    if hasattr(user_obj, 'avatar_url') and user_obj.avatar_url:
        return user_obj.avatar_url
    
    # 使用Gravatar
    if hasattr(user_obj, 'email') and user_obj.email:
        return gravatar_url_filter(user_obj.email, size)
    
    # 返回默认头像
    return "/static/images/default-avatar.png"


def time_ago_filter(dt: datetime) -> str:
    """
    时间距离现在的过滤器（类似"3小时前"）
    
    Args:
        dt: 时间对象
        
    Returns:
        相对时间字符串
    """
    if not dt:
        return ""
    
    now = datetime.now()
    if dt.tzinfo is not None:
        # 如果dt有时区信息，将now转换为同样的时区
        now = now.replace(tzinfo=dt.tzinfo)
    
    delta = now - dt
    seconds = delta.total_seconds()
    
    if seconds < 60:
        return "刚刚"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        return f"{minutes}分钟前"
    elif seconds < 86400:
        hours = int(seconds // 3600)
        return f"{hours}小时前"
    elif seconds < 2592000:  # 30天
        days = int(seconds // 86400)
        return f"{days}天前"
    else:
        return dt.strftime('%Y年%m月%d日')


def micro_datetime_cn_filter(dt: datetime) -> str:
    """
    微博时间格式过滤器

    规则：
    - 当年：`%m月%d日 %H:%M`
    - 非当年：`%Y年%m月%d日 %H:%M`
    """
    if not dt:
        return ""

    now = datetime.now()
    if dt.tzinfo is not None:
        now = now.replace(tzinfo=dt.tzinfo)

    if dt.year == now.year:
        return dt.strftime("%m月%d日 %H:%M")
    return dt.strftime("%Y年%m月%d日 %H:%M")


def truncate_html_filter(html_content: str, length: int = 100) -> str:
    """
    截断HTML内容的过滤器（保留HTML标签结构）
    
    Args:
        html_content: HTML内容
        length: 截断长度
        
    Returns:
        截断后的HTML
    """
    from bs4 import BeautifulSoup
    
    try:
        soup = BeautifulSoup(html_content, 'html.parser')
        text = soup.get_text()
        
        if len(text) <= length:
            return html_content
        
        # 简单截断
        truncated_text = text[:length] + "..."
        return truncated_text
    except:
        # 如果解析失败，使用简单的文本截断
        if len(html_content) <= length:
            return html_content
        return html_content[:length] + "..."


def extract_image_urls_filter(content_html: str, featured_image_url: Optional[str] = None) -> list:
    """
    从HTML内容中提取图片链接，用于时间轴卡片的九宫格展示

    Args:
        content_html: 文章渲染后的 HTML
        featured_image_url: 特色图片 URL（可选），用于排除重复

    Returns:
        去重后的图片 URL 列表（最多 20 张以防极端情况）
    """
    if not content_html:
        return []

    image_urls = []
    seen = set()
    featured_normalized = (featured_image_url or "").strip()

    for match in re.finditer(r'<img[^>]+src=["\\\']([^"\\\']+)["\\\']', content_html, re.IGNORECASE):
        src = (match.group(1) or "").strip()
        if not src:
            continue
        if featured_normalized and src == featured_normalized:
            continue
        if src in seen:
            continue
        seen.add(src)
        image_urls.append(src)
        if len(image_urls) >= 20:
            break

    return image_urls


_MEDIA_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".svg"}
_MEDIA_VIDEO_EXTENSIONS = {".mp4", ".webm", ".mov", ".m4v", ".mkv", ".avi"}
_MEDIA_AUDIO_EXTENSIONS = {".mp3", ".m4a", ".aac", ".ogg", ".wav", ".flac"}


def _is_local_media_url(url: str) -> bool:
    normalized = str(url or "").strip()
    if not normalized:
        return False
    return normalized.startswith("/media/") or "/media/" in normalized


def _guess_media_kind(url: str) -> Optional[str]:
    normalized = str(url or "").strip()
    if not normalized:
        return None
    try:
        path = (urlparse(normalized).path or "").lower()
    except Exception:
        path = normalized.lower()
    suffix = Path(path).suffix.lower()
    if suffix in _MEDIA_IMAGE_EXTENSIONS:
        return "image"
    if suffix in _MEDIA_VIDEO_EXTENSIONS:
        return "video"
    if suffix in _MEDIA_AUDIO_EXTENSIONS:
        return "audio"
    return None


def extract_media_assets_filter(content_html: str, featured_image_url: Optional[str] = None) -> dict:
    """
    从正文 HTML 中提取本地媒体资源。

    返回结构：
    {
        "images": [...],
        "videos": [...],
        "audio": [...],
    }
    """
    result = {
        "images": [],
        "videos": [],
        "audio": [],
    }
    if not content_html:
        return result

    featured = str(featured_image_url or "").strip()
    if featured:
        result["images"].append(featured)

    seen = {
        "images": {featured} if featured else set(),
        "videos": set(),
        "audio": set(),
    }

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content_html, "html.parser")

        for image_node in soup.find_all("img"):
            src = str(image_node.get("src") or "").strip()
            if not _is_local_media_url(src):
                continue
            if src in seen["images"]:
                continue
            seen["images"].add(src)
            result["images"].append(src)

        for video_node in soup.find_all("video"):
            src = str(video_node.get("src") or "").strip()
            if _is_local_media_url(src) and src not in seen["videos"]:
                seen["videos"].add(src)
                result["videos"].append(src)
            for source_node in video_node.find_all("source"):
                source_src = str(source_node.get("src") or "").strip()
                if not _is_local_media_url(source_src):
                    continue
                if source_src in seen["videos"]:
                    continue
                seen["videos"].add(source_src)
                result["videos"].append(source_src)

        for audio_node in soup.find_all("audio"):
            src = str(audio_node.get("src") or "").strip()
            if _is_local_media_url(src) and src not in seen["audio"]:
                seen["audio"].add(src)
                result["audio"].append(src)
            for source_node in audio_node.find_all("source"):
                source_src = str(source_node.get("src") or "").strip()
                if not _is_local_media_url(source_src):
                    continue
                if source_src in seen["audio"]:
                    continue
                seen["audio"].add(source_src)
                result["audio"].append(source_src)

        for link_node in soup.find_all("a"):
            href = str(link_node.get("href") or "").strip()
            if not _is_local_media_url(href):
                continue
            kind = _guess_media_kind(href)
            if kind == "image":
                if href not in seen["images"]:
                    seen["images"].add(href)
                    result["images"].append(href)
                continue
            if kind == "video":
                if href not in seen["videos"]:
                    seen["videos"].add(href)
                    result["videos"].append(href)
                continue
            if kind == "audio":
                if href not in seen["audio"]:
                    seen["audio"].add(href)
                    result["audio"].append(href)
    except Exception:
        # 保底退化：仅使用现有图片提取逻辑，避免模板崩溃。
        result["images"] = extract_image_urls_filter(content_html, featured_image_url=featured_image_url)
    return result


def license_html_filter(license_type: str, author: str, site_url: str = "") -> str:
    """
    生成版权声明HTML的过滤器
    
    Args:
        license_type: 版权类型
        author: 作者名称
        site_url: 网站URL（可选）
        
    Returns:
        版权声明HTML
    """
    return render_license(license_type, author, site_url)


def url_filter(filepath: str) -> str:
    """
    将媒体文件路径转换为可访问的URL
    """
    if not filepath:
        return ""

    try:
        upload_root = Path(settings.MEDIA_UPLOAD_DIR).resolve()
        relative = Path(filepath).resolve().relative_to(upload_root).as_posix()
        return f"/media/{relative}"
    except Exception:
        normalized_path = str(filepath).replace("\\", "/")
        normalized_root = str(settings.MEDIA_UPLOAD_DIR).replace("\\", "/").rstrip("/")
        if normalized_path.startswith(normalized_root):
            return normalized_path.replace(normalized_root, "/media", 1)
        return normalized_path


def get_license_options_filter(selected_license: str = "cc_by_nc_sa_4") -> str:
    """
    生成版权选择下拉框选项的过滤器
    
    Args:
        selected_license: 当前选中的版权类型
        
    Returns:
        HTML选项字符串
    """
    return LicenseManager.get_license_options_html(selected_license)


def donation_widget_filter(db) -> str:
    """
    渲染打赏组件HTML的过滤器
    
    Args:
        db: 数据库会话
        
    Returns:
        打赏组件HTML
    """
    return render_donation_widget(db)

# 新增：Font Awesome 兼容过滤器（将 FA6 风格类名映射为 FA5）
def fa_compat_filter(icon_class: str) -> str:
    """
    将 Font Awesome 6 的风格前缀映射为 Font Awesome 5 的等价类，
    以便在全局统一为 FA5 时保证图标正常显示。
    """
    if not icon_class:
        return ""
    tokens = icon_class.split()
    style_map = {
        'fa-solid': 'fas',
        'fa-regular': 'far',
        'fa-light': 'fal',
        'fa-thin': 'fa',
        'fa-duotone': 'fad',
        'fa-brands': 'fab',
        # 处理 FA6 的 sharp 系列，降级为常规风格
        'fa-sharp': 'fas',
        'fa-sharp-solid': 'fas',
        'fa-sharp-regular': 'far',
        'fa-sharp-light': 'fal',
    }
    normalized = []
    replaced_style = False
    for t in tokens:
        mapped = style_map.get(t, t)
        if mapped in ('fas', 'far', 'fal', 'fad', 'fab'):
            # 保证只保留一个风格前缀，避免重复
            if not replaced_style:
                normalized.append(mapped)
                replaced_style = True
            # 如果已有风格则跳过额外风格标记
            continue
        normalized.append(mapped)
    # 如果没有任何风格类，默认使用 fas
    if not replaced_style:
        normalized.insert(0, 'fas')
    return ' '.join(normalized)


def _resolve_thumb_media_id(source, db) -> Optional[int]:
    if source is None:
        return None
    try:
        if isinstance(source, int):
            return int(source)
        raw_text = str(source).strip()
        if not raw_text:
            return None
        if raw_text.isdigit():
            return int(raw_text)
        if not db:
            return None
        return resolve_media_id_from_url(db, raw_text)
    except Exception:
        return None


def thumb_url_filter(source, preset: str = "post_cover", db=None, dpr: int = 1, fmt: str = "auto") -> str:
    if source is None:
        return ""

    raw_text = str(source).strip()
    if not raw_text:
        return ""

    media_id = _resolve_thumb_media_id(source, db)
    if media_id is None:
        return raw_text

    try:
        return build_variant_url(media_id=media_id, preset=str(preset or "post_cover"), dpr=int(dpr), fmt=str(fmt or "auto"))
    except Exception:
        return raw_text


def thumb_srcset_filter(source, preset: str = "post_cover", db=None, dprs="1,2", fmt: str = "auto") -> str:
    media_id = _resolve_thumb_media_id(source, db)
    if media_id is None:
        return ""

    if isinstance(dprs, (list, tuple, set)):
        dpr_values = list(dprs)
    else:
        dpr_values = str(dprs or "1,2").split(",")

    entries = []
    seen = set()
    for item in dpr_values:
        try:
            dpr_value = int(str(item).strip())
        except (TypeError, ValueError):
            continue
        if dpr_value in seen:
            continue
        seen.add(dpr_value)
        if dpr_value < 1:
            continue
        url = thumb_url_filter(media_id, preset=preset, db=db, dpr=dpr_value, fmt=fmt)
        if not url:
            continue
        entries.append(f"{url} {dpr_value}x")
    return ", ".join(entries)


def responsive_image_filter(image_url: str, alt_text: str = "", 
                           css_classes: str = "", sizes: str = "", db=None, preset: str = "post_cover") -> str:
    """
    生成响应式图像 HTML 的过滤器
    
    Args:
        image_url: 图像 URL
        alt_text: 替代文本
        css_classes: CSS 类名
        sizes: sizes 属性值
        db: 数据库会话
        
    Returns:
        响应式图像 HTML
    """
    raw_url = str(image_url or "").strip()
    if not raw_url:
        return ""

    src_url = raw_url
    srcset_attr = ""
    if db and (is_local_media_url(raw_url) or str(raw_url).isdigit()):
        src_url = thumb_url_filter(raw_url, preset=preset, db=db, dpr=1, fmt="auto")
        srcset_attr = thumb_srcset_filter(raw_url, preset=preset, db=db, dprs="1,2", fmt="auto")

    safe_alt = escape(str(alt_text or ""), quote=True)
    safe_class = escape(str(css_classes or ""), quote=True)
    safe_sizes = escape(str(sizes or "(max-width: 768px) 100vw, 1200px"), quote=True)
    safe_src = escape(str(src_url or raw_url), quote=True)

    if srcset_attr:
        safe_srcset = escape(srcset_attr, quote=True)
        return (
            f'<img src="{safe_src}" alt="{safe_alt}" class="{safe_class}" '
            f'loading="lazy" decoding="async" srcset="{safe_srcset}" sizes="{safe_sizes}">'
        )

    return f'<img src="{safe_src}" alt="{safe_alt}" class="{safe_class}" loading="lazy" decoding="async">'


def date_filter(value, format_string: str = "%Y-%m-%d") -> str:
    if value == 'now':
        value = datetime.now()
    
    if isinstance(value, datetime):
        return value.strftime(format_string)
    
    return str(value)


def compact_number_cn_filter(value) -> str:
    """
    中文数字缩写过滤器（用于浏览量等计数展示）

    规则：
    - < 1万：原值
    - >= 1万：按"万"缩写
    - >= 1亿：按"亿"缩写
    """
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "0"

    is_negative = number < 0
    abs_number = abs(number)

    if abs_number < 10000:
        text = str(int(abs_number))
    elif abs_number < 100000000:
        text = f"{abs_number / 10000:.1f}".rstrip("0").rstrip(".") + "万"
    else:
        text = f"{abs_number / 100000000:.1f}".rstrip("0").rstrip(".") + "亿"

    return f"-{text}" if is_negative else text


def post_content_html_filter(post_obj, db=None) -> str:
    if not post_obj:
        return ""
    html_content = get_effective_content_html(
        getattr(post_obj, "content_markdown", ""),
        getattr(post_obj, "content_html", ""),
    )
    format_slugs = [
        str(getattr(fmt, "slug", "") or "").strip().lower()
        for fmt in getattr(post_obj, "formats", []) or []
    ]
    if "micro" in format_slugs:
        return enhance_micro_html(html_content, db)
    return html_content


def post_public_content_html_filter(post_obj, db=None) -> str:
    if not post_obj:
        return ""
    raw_markdown = getattr(post_obj, "content_markdown", "") or ""
    raw_html = getattr(post_obj, "content_html", "") or ""
    sanitized_markdown = strip_hide_blocks(raw_markdown)
    if sanitized_markdown != raw_markdown:
        html_content = get_effective_content_html(sanitized_markdown, "")
    else:
        html_content = get_effective_content_html(raw_markdown, raw_html)

    format_slugs = [
        str(getattr(fmt, "slug", "") or "").strip().lower()
        for fmt in getattr(post_obj, "formats", []) or []
    ]
    if "micro" in format_slugs:
        return enhance_micro_html(html_content, db)
    return html_content


def post_preview_text_filter(post_obj, length: int = 200) -> str:
    if not post_obj:
        return ""
    plain_text = get_effective_plain_text(
        getattr(post_obj, "content_markdown", ""),
        getattr(post_obj, "content_html", ""),
    )
    if len(plain_text) <= length:
        return plain_text
    return f"{plain_text[:length]}..."


def post_plain_text_filter(post_obj) -> str:
    if not post_obj:
        return ""
    return get_effective_plain_text(
        getattr(post_obj, "content_markdown", ""),
        getattr(post_obj, "content_html", ""),
    )


def post_public_plain_text_filter(post_obj) -> str:
    if not post_obj:
        return ""
    raw_markdown = getattr(post_obj, "content_markdown", "") or ""
    raw_html = getattr(post_obj, "content_html", "") or ""
    sanitized_markdown = strip_hide_blocks(raw_markdown)
    if sanitized_markdown != raw_markdown:
        return get_effective_plain_text(sanitized_markdown, "")
    return get_effective_plain_text(raw_markdown, raw_html)


def post_summary_text_filter(post_obj, length: int = 200) -> str:
    if not post_obj:
        return ""
    manual_excerpt = str(getattr(post_obj, "excerpt", "") or "").strip()
    if manual_excerpt:
        normalized_excerpt = html_to_plain_text(manual_excerpt) if "<" in manual_excerpt and ">" in manual_excerpt else manual_excerpt
        if len(normalized_excerpt) <= length:
            return normalized_excerpt
        return f"{normalized_excerpt[:length]}..."

    plain_text = post_public_plain_text_filter(post_obj)
    if len(plain_text) <= length:
        return plain_text
    return f"{plain_text[:length]}..."


def strip_media_nodes_filter(content_html: str) -> str:
    """
    剔除正文中的媒体标签，保留文本与基础格式标签。
    用于微博聚合页：正文仅展示文字格式，媒体由九宫格单独承载。
    """
    if not content_html:
        return ""

    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(content_html, "html.parser")
        media_tags = ["img", "video", "audio", "iframe", "figure", "picture", "source", "embed", "object"]
        for media_node in soup.find_all(media_tags):
            media_node.decompose()

        # 清理正文中仅用于媒体占位的本地媒体链接，避免与下方播放器重复。
        for link_node in soup.find_all("a"):
            href = str(link_node.get("href") or "").strip()
            if not _is_local_media_url(href):
                continue
            if _guess_media_kind(href) is None:
                continue
            link_node.decompose()

        # 清理剔除媒体后留下的空段落，减少无意义留白
        for paragraph in soup.find_all("p"):
            if not paragraph.get_text(strip=True) and not paragraph.find(True):
                paragraph.decompose()

        return str(soup)
    except Exception:
        return content_html


def reading_time_filter(content_value: str) -> str:
    """
    计算阅读时间的过滤器
    
    Args:
        content_value: Markdown或HTML内容
        
    Returns:
        阅读时间字符串
    """
    if not content_value:
        return "1 分钟"

    source_text = markdown_to_plain_text(content_value)
    if not source_text and "<" in content_value and ">" in content_value:
        source_text = html_to_plain_text(content_value)
    if not source_text:
        source_text = content_value

    reading_info = calculate_reading_time(source_text)
    minutes = reading_info['reading_time_minutes']
    
    if minutes == 1:
        return "1 分钟"
    else:
        return f"{minutes} 分钟"


def reading_stats_filter(content_value: str, post_obj=None) -> dict:
    """
    获取文章统计信息的过滤器
    
    Args:
        content_value: Markdown或HTML内容
        post_obj: 文章对象（可选）
        
    Returns:
        统计信息字典
    """
    effective_content = content_value or ""
    if not effective_content and post_obj is not None:
        effective_content = getattr(post_obj, "content_markdown", "") or getattr(post_obj, "content_html", "")
    if not effective_content:
        return {}

    source_text = markdown_to_plain_text(effective_content)
    if not source_text and "<" in effective_content and ">" in effective_content:
        source_text = html_to_plain_text(effective_content)
    if not source_text:
        source_text = effective_content
    return get_post_statistics(source_text, post_obj)


def related_posts_filter(current_post, db, limit: int = 5) -> list:
    """
    获取相关文章的过滤器
    
    Args:
        current_post: 当前文章对象
        db: 数据库会话
        limit: 返回数量限制
        
    Returns:
        相关文章列表
    """
    if not current_post:
        return []

    db_gen = None
    effective_db = db
    if effective_db is None:
        db_gen = get_db()
        effective_db = next(db_gen)

    try:
        return get_related_posts(effective_db, current_post, limit)
    except Exception as e:
        print(f"获取相关文章失败: {e}")
        return []
    finally:
        if db_gen is not None:
            try:
                db_gen.close()
            except Exception:
                pass


def post_url_filter(post) -> str:
    """
    生成文章URL的过滤器
    
    Args:
        post: 文章对象，需要包含slug和formats属性
        
    Returns:
        文章URL字符串，格式为 /{format_slug}/{post_slug}
    """
    if not post or not hasattr(post, 'slug'):
        return "#"
    
    available_slugs = []
    if hasattr(post, 'formats') and post.formats:
        available_slugs = [fmt.slug for fmt in post.formats if getattr(fmt, "slug", None)]

    primary_intent = choose_primary_intent_slug(available_slugs)
    path_segment = to_public_post_segment(primary_intent)
    return f"/{path_segment}/{post.slug}"


def static_asset(request, path: str) -> str:
    """
    生成带文件时间戳的静态资源链接，避免浏览器继续使用旧缓存。

    链接统一收口为根相对路径（不含协议与域名端口），
    这样即使反代入口的域名、端口或 Host 头发生变化，
    也不会生成跨域绝对地址导致静态资源被浏览器拦截。

    Args:
        request: 当前请求对象
        path: 相对 static 目录的资源路径

    Returns:
        附带版本参数的静态资源根相对路径
    """
    resolved_path = urlsplit(str(request.url_for("static", path=path))).path
    root_path = str(request.scope.get("root_path") or "")
    asset_url = f"{root_path}{resolved_path}"

    asset_path = _STATIC_ROOT / Path(path)
    if not asset_path.is_file():
        return asset_url

    version = int(asset_path.stat().st_mtime_ns)
    separator = "&" if "?" in asset_url else "?"
    return f"{asset_url}{separator}v={version}"


def register_template_filters(app):
    """
    注册所有模板过滤器到FastAPI应用
    
    Args:
        app: FastAPI应用实例
    """
    # 获取Jinja2环境
    from fastapi.templating import Jinja2Templates
    templates = Jinja2Templates(directory="rewrz/templates")
    
    # 注册过滤器
    templates.env.filters['md5'] = md5_filter
    templates.env.filters['gravatar_url'] = gravatar_url_filter
    templates.env.filters['avatar_url'] = avatar_url_filter
    templates.env.filters['time_ago'] = time_ago_filter
    templates.env.filters['micro_datetime_cn'] = micro_datetime_cn_filter
    templates.env.filters['truncate_html'] = truncate_html_filter
    templates.env.filters['extract_image_urls'] = extract_image_urls_filter
    templates.env.filters['extract_media_assets'] = extract_media_assets_filter
    templates.env.filters['date'] = date_filter
    templates.env.filters['compact_number_cn'] = compact_number_cn_filter
    templates.env.filters['license_html'] = license_html_filter
    templates.env.filters['license_options'] = get_license_options_filter
    templates.env.filters['donation_widget'] = donation_widget_filter
    templates.env.filters['responsive_image'] = responsive_image_filter
    templates.env.filters['thumb_url'] = thumb_url_filter
    templates.env.filters['thumb_srcset'] = thumb_srcset_filter
    templates.env.filters['url'] = url_filter # 注册url过滤器
    templates.env.filters['fa_compat'] = fa_compat_filter # 注册Font Awesome兼容过滤器
    templates.env.filters['post_content_html'] = post_content_html_filter
    templates.env.filters['post_public_content_html'] = post_public_content_html_filter
    templates.env.filters['post_preview_text'] = post_preview_text_filter
    templates.env.filters['post_plain_text'] = post_plain_text_filter
    templates.env.filters['post_public_plain_text'] = post_public_plain_text_filter
    templates.env.filters['post_summary_text'] = post_summary_text_filter
    templates.env.filters['strip_media_nodes'] = strip_media_nodes_filter
    templates.env.globals['static_asset'] = static_asset
    
    return templates


# 全局模板实例
_templates = None

def get_templates():
    """获取配置好过滤器的模板实例"""
    global _templates
    if _templates is None:
        from fastapi.templating import Jinja2Templates
        _templates = Jinja2Templates(directory="rewrz/templates")
        
        # 注册过滤器
        _templates.env.filters['md5'] = md5_filter
        _templates.env.filters['gravatar_url'] = gravatar_url_filter
        _templates.env.filters['avatar_url'] = avatar_url_filter
        _templates.env.filters['time_ago'] = time_ago_filter
        _templates.env.filters['micro_datetime_cn'] = micro_datetime_cn_filter
        _templates.env.filters['truncate_html'] = truncate_html_filter
        _templates.env.filters['extract_image_urls'] = extract_image_urls_filter
        _templates.env.filters['extract_media_assets'] = extract_media_assets_filter
        _templates.env.filters['date'] = date_filter
        _templates.env.filters['compact_number_cn'] = compact_number_cn_filter
        _templates.env.filters['license_html'] = license_html_filter
        _templates.env.filters['license_options'] = get_license_options_filter
        _templates.env.filters['donation_widget'] = donation_widget_filter
        _templates.env.filters['responsive_image'] = responsive_image_filter
        _templates.env.filters['thumb_url'] = thumb_url_filter
        _templates.env.filters['thumb_srcset'] = thumb_srcset_filter
        _templates.env.filters['url'] = url_filter # 注册url过滤器
        # 新增的现代化博客功能过滤器
        _templates.env.filters['reading_time'] = reading_time_filter
        _templates.env.filters['reading_stats'] = reading_stats_filter
        _templates.env.filters['related_posts'] = related_posts_filter
        _templates.env.filters['fa_compat'] = fa_compat_filter # 注册Font Awesome兼容过滤器
        _templates.env.filters['post_url'] = post_url_filter # 注册文章URL生成过滤器
        _templates.env.filters['post_content_html'] = post_content_html_filter
        _templates.env.filters['post_public_content_html'] = post_public_content_html_filter
        _templates.env.filters['post_preview_text'] = post_preview_text_filter
        _templates.env.filters['post_plain_text'] = post_plain_text_filter
        _templates.env.filters['post_public_plain_text'] = post_public_plain_text_filter
        _templates.env.filters['post_summary_text'] = post_summary_text_filter
        _templates.env.filters['strip_media_nodes'] = strip_media_nodes_filter
        _templates.env.globals['static_asset'] = static_asset

    return _templates
