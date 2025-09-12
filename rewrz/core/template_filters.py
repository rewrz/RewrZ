"""
Jinja2模板过滤器

提供模板中使用的自定义过滤器，包括：
- MD5哈希计算（用于Gravatar）
- 头像URL生成
- 时间格式化等
"""

import hashlib
from datetime import datetime
from typing import Optional
from jinja2 import Environment
from .license_manager import render_license, LicenseManager
from .donation_system import render_donation_widget
from .blog_enhancements import calculate_reading_time, get_related_posts, get_post_statistics
from ..core.config import settings # 导入settings


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
    return filepath.replace(settings.MEDIA_UPLOAD_DIR, '/media')


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


def responsive_image_filter(image_url: str, alt_text: str = "", 
                           css_classes: str = "", sizes: str = "", db=None) -> str:
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
    if not image_url:
        return ""
    
    # 如果有数据库会话，使用媒体处理器
    if db:
        try:
            from .media_processor import get_media_processor
            media_processor = get_media_processor(db)
            return media_processor.get_responsive_image_html(image_url, alt_text, css_classes, sizes)
        except Exception as e:
            print(f"使用媒体处理器生成响应式图像失败: {e}")
    
    # 退回简单的 img 标签
    return f'<img src="{image_url}" alt="{alt_text}" class="{css_classes}" loading="lazy">'


def date_filter(value, format_string: str = "%Y-%m-%d") -> str:
    if value == 'now':
        value = datetime.now()
    
    if isinstance(value, datetime):
        return value.strftime(format_string)
    
    return str(value)


def reading_time_filter(content_markdown: str) -> str:
    """
    计算阅读时间的过滤器
    
    Args:
        content_markdown: Markdown内容
        
    Returns:
        阅读时间字符串
    """
    if not content_markdown:
        return "1 分钟"
    
    reading_info = calculate_reading_time(content_markdown)
    minutes = reading_info['reading_time_minutes']
    
    if minutes == 1:
        return "1 分钟"
    else:
        return f"{minutes} 分钟"


def reading_stats_filter(content_markdown: str, post_obj=None) -> dict:
    """
    获取文章统计信息的过滤器
    
    Args:
        content_markdown: Markdown内容
        post_obj: 文章对象（可选）
        
    Returns:
        统计信息字典
    """
    if not content_markdown:
        return {}
    
    return get_post_statistics(content_markdown, post_obj)


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
    if not current_post or not db:
        return []
    
    try:
        return get_related_posts(db, current_post, limit)
    except Exception as e:
        print(f"获取相关文章失败: {e}")
        return []


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
    templates.env.filters['truncate_html'] = truncate_html_filter
    templates.env.filters['date'] = date_filter
    templates.env.filters['license_html'] = license_html_filter
    templates.env.filters['license_options'] = get_license_options_filter
    templates.env.filters['donation_widget'] = donation_widget_filter
    templates.env.filters['responsive_image'] = responsive_image_filter
    templates.env.filters['url'] = url_filter # 注册url过滤器
    templates.env.filters['fa_compat'] = fa_compat_filter # 注册Font Awesome兼容过滤器
    
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
        _templates.env.filters['truncate_html'] = truncate_html_filter
        _templates.env.filters['date'] = date_filter
        _templates.env.filters['license_html'] = license_html_filter
        _templates.env.filters['license_options'] = get_license_options_filter
        _templates.env.filters['donation_widget'] = donation_widget_filter
        _templates.env.filters['responsive_image'] = responsive_image_filter
        _templates.env.filters['url'] = url_filter # 注册url过滤器
        # 新增的现代化博客功能过滤器
        _templates.env.filters['reading_time'] = reading_time_filter
        _templates.env.filters['reading_stats'] = reading_stats_filter
        _templates.env.filters['related_posts'] = related_posts_filter
        _templates.env.filters['fa_compat'] = fa_compat_filter # 注册Font Awesome兼容过滤器
    
    return _templates
