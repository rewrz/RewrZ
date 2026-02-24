"""
媒体处理系统配置模块

定义媒体处理相关的默认设置和初始化函数。
支持图像处理、缩略图生成、文件上传等配置。
"""

from sqlalchemy.orm import Session
from ..crud import setting as crud_setting

# 默认媒体处理设置
DEFAULT_MEDIA_SETTINGS = [
    {"key": "media_image_quality", "value": {"value": 85}, "description": "图像压缩质量（1-100）", "category": "media", "type": "integer"},
    {"key": "media_max_image_size", "value": {"value": 2048}, "description": "图像最大尺寸（像素）", "category": "media", "type": "integer"},
    {"key": "media_auto_compress", "value": {"value": True}, "description": "自动压缩上传图像", "category": "media", "type": "boolean"},
    {"key": "media_max_file_size", "value": {"value": 52428800}, "description": "最大文件上传大小（字节）", "category": "media", "type": "integer"},
    {"key": "media_extract_exif", "value": {"value": True}, "description": "提取图像 EXIF 元数据", "category": "media", "type": "boolean"},
    {"key": "media_remove_exif", "value": {"value": False}, "description": "保存时移除 EXIF 数据", "category": "media", "type": "boolean"},
    {"key": "media_allowed_image_formats", "value": {"value": "jpg,jpeg,png,gif,bmp,webp,tiff"}, "description": "允许的图像格式", "category": "media", "type": "string"},
    {"key": "media_allowed_video_formats", "value": {"value": "mp4,avi,mov,wmv,flv,webm,mkv"}, "description": "允许的视频格式", "category": "media", "type": "string"},
    {"key": "media_allowed_audio_formats", "value": {"value": "mp3,wav,flac,aac,ogg,m4a"}, "description": "允许的音频格式", "category": "media", "type": "string"},
    {"key": "media_allowed_document_formats", "value": {"value": "pdf,doc,docx,txt,md"}, "description": "允许的文档格式", "category": "media", "type": "string"},
    {"key": "media_enable_watermark", "value": {"value": False}, "description": "启用图像水印", "category": "media", "type": "boolean"},
    {"key": "media_watermark_text", "value": {"value": "RewrZ"}, "description": "水印文字", "category": "media", "type": "string"},
    {"key": "media_watermark_opacity", "value": {"value": 0.5}, "description": "水印透明度（0.0-1.0）", "category": "media", "type": "float"},
    {"key": "media_progressive_jpeg", "value": {"value": True}, "description": "启用渐进式 JPEG", "category": "media", "type": "boolean"},
    {"key": "media_enable_cdn", "value": {"value": False}, "description": "启用 CDN 加速", "category": "media", "type": "boolean"},
    {"key": "media_cdn_url", "value": {"value": ""}, "description": "CDN 基础 URL", "category": "media", "type": "string"},
    {"key": "media_auto_cleanup", "value": {"value": False}, "description": "自动清理未使用媒体文件", "category": "media", "type": "boolean"},
    {"key": "media_cleanup_days", "value": {"value": 30}, "description": "未使用文件保留天数", "category": "media", "type": "integer"},
    {"key": "thumbnail_enabled", "value": {"value": True}, "description": "启用动态缩略图服务", "category": "media", "type": "boolean"},
    {"key": "thumbnail_cache_dir", "value": {"value": "media_uploads/_variant_cache"}, "description": "缩略图缓存目录", "category": "media", "type": "string"},
    {"key": "thumbnail_allowed_dpr", "value": {"value": "1,2"}, "description": "允许的 DPR 集合", "category": "media", "type": "string"},
    {"key": "thumbnail_allowed_fmt", "value": {"value": "auto,avif,webp,jpg,png"}, "description": "允许的输出格式集合", "category": "media", "type": "string"},
    {"key": "thumbnail_default_fmt", "value": {"value": "auto"}, "description": "默认输出格式策略", "category": "media", "type": "string"},
    {"key": "thumbnail_processor_version", "value": {"value": "v1"}, "description": "图像处理器版本号", "category": "media", "type": "string"},
    {"key": "thumbnail_lock_timeout_ms", "value": {"value": 15000}, "description": "同变体互斥锁超时", "category": "media", "type": "integer"},
    {"key": "thumbnail_negative_cache_ttl_seconds", "value": {"value": 30}, "description": "失败负缓存时长（秒）", "category": "media", "type": "integer"},
    {"key": "thumbnail_generate_timeout_ms", "value": {"value": 4000}, "description": "单次生成超时（毫秒）", "category": "media", "type": "integer"},
    {"key": "thumbnail_source_max_megapixels", "value": {"value": 40}, "description": "原图像素上限（MP）", "category": "media", "type": "integer"},
    {"key": "thumbnail_cleanup_interval_hours", "value": {"value": 168}, "description": "缓存清理周期（小时）", "category": "media", "type": "integer"},
    {"key": "external_image_policy", "value": {"value": "passthrough"}, "description": "外链图片策略", "category": "media", "type": "string"},
    {"key": "external_image_allowlist", "value": {"value": ""}, "description": "外链域名白名单", "category": "media", "type": "string"},
    {"key": "external_image_max_bytes", "value": {"value": 10485760}, "description": "外链图片单文件大小上限（字节）", "category": "media", "type": "integer"},
    {"key": "external_image_timeout_ms", "value": {"value": 3000}, "description": "外链抓取超时（毫秒）", "category": "media", "type": "integer"},
    {"key": "external_image_redirect_limit", "value": {"value": 2}, "description": "外链最大跳转次数", "category": "media", "type": "integer"},
    {"key": "external_image_allowed_mime", "value": {"value": "image/jpeg,image/png,image/webp,image/avif,image/gif"}, "description": "允许的外链 MIME 列表", "category": "media", "type": "string"},
    {"key": "external_image_localize_concurrency", "value": {"value": 2}, "description": "外链本地化并发任务数", "category": "media", "type": "integer"},
    {"key": "external_image_localize_max_retries", "value": {"value": 2}, "description": "外链本地化最大重试次数", "category": "media", "type": "integer"},
]


def get_allowed_file_types(db: Session = None) -> list:
    """
    获取允许的文件类型列表
    
    Args:
        db: 数据库会话（可选）
        
    Returns:
        list: 允许的文件类型列表
    """
    # 默认允许的文件类型
    default_types = [
        'image/jpeg', 'image/png', 'image/gif', 'image/webp', 'image/bmp', 'image/tiff',
        'video/mp4', 'video/avi', 'video/quicktime', 'video/x-ms-wmv', 'video/x-flv', 'video/webm',
        'audio/mpeg', 'audio/wav', 'audio/flac', 'audio/aac', 'audio/ogg',
        'application/pdf', 'text/plain', 'text/markdown'
    ]
    
    # 如果提供了数据库会话，尝试从数据库获取配置
    if db:
        try:
            # 获取允许的文件格式配置
            image_formats = crud_setting.get_setting(db, "media_allowed_image_formats")
            video_formats = crud_setting.get_setting(db, "media_allowed_video_formats")
            audio_formats = crud_setting.get_setting(db, "media_allowed_audio_formats")
            document_formats = crud_setting.get_setting(db, "media_allowed_document_formats")
            
            # 解析配置并生成MIME类型列表
            allowed_types = []
            
            if image_formats and image_formats.value:
                formats = image_formats.value.get("value", "").split(",")
                mime_map = {
                    "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
                    "gif": "image/gif", "webp": "image/webp", "bmp": "image/bmp",
                    "tiff": "image/tiff"
                }
                for fmt in formats:
                    fmt = fmt.strip().lower()
                    if fmt in mime_map:
                        allowed_types.append(mime_map[fmt])
            
            if video_formats and video_formats.value:
                formats = video_formats.value.get("value", "").split(",")
                mime_map = {
                    "mp4": "video/mp4", "avi": "video/avi", "mov": "video/quicktime",
                    "wmv": "video/x-ms-wmv", "flv": "video/x-flv", "webm": "video/webm",
                    "mkv": "video/x-matroska"
                }
                for fmt in formats:
                    fmt = fmt.strip().lower()
                    if fmt in mime_map:
                        allowed_types.append(mime_map[fmt])
            
            if audio_formats and audio_formats.value:
                formats = audio_formats.value.get("value", "").split(",")
                mime_map = {
                    "mp3": "audio/mpeg", "wav": "audio/wav", "flac": "audio/flac",
                    "aac": "audio/aac", "ogg": "audio/ogg", "m4a": "audio/mp4"
                }
                for fmt in formats:
                    fmt = fmt.strip().lower()
                    if fmt in mime_map:
                        allowed_types.append(mime_map[fmt])
            
            if document_formats and document_formats.value:
                formats = document_formats.value.get("value", "").split(",")
                mime_map = {
                    "pdf": "application/pdf", "txt": "text/plain", "md": "text/markdown",
                    "doc": "application/msword", "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
                }
                for fmt in formats:
                    fmt = fmt.strip().lower()
                    if fmt in mime_map:
                        allowed_types.append(mime_map[fmt])
            
            if allowed_types:
                return allowed_types
        except Exception as e:
            # 如果数据库访问失败，使用默认配置
            pass
    
    return default_types


def get_max_file_size(db: Session = None) -> int:
    """
    获取最大文件大小限制
    
    Args:
        db: 数据库会话（可选）
        
    Returns:
        int: 最大文件大小（字节）
    """
    # 默认最大文件大小：50MB
    default_size = 50 * 1024 * 1024
    
    # 如果提供了数据库会话，尝试从数据库获取配置
    if db:
        try:
            max_size_setting = crud_setting.get_setting(db, "media_max_file_size")
            if max_size_setting and max_size_setting.value:
                return max_size_setting.value.get("value", default_size)
        except Exception as e:
            # 如果数据库访问失败，使用默认配置
            pass
    
    return default_size


def is_file_type_allowed(file_type: str, db: Session = None) -> bool:
    """
    检查文件类型是否被允许
    
    Args:
        file_type: 文件MIME类型
        db: 数据库会话（可选）
        
    Returns:
        bool: 文件类型是否被允许
    """
    allowed_types = get_allowed_file_types(db)
    return file_type in allowed_types


def format_file_size(size_bytes: int) -> str:
    """
    格式化文件大小为人类可读的格式
    
    Args:
        size_bytes: 文件大小（字节）
        
    Returns:
        str: 格式化后的文件大小
    """
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 1)
    return f"{s} {size_names[i]}"


def init_media_settings(db):
    """
    初始化媒体设置到数据库
    
    Args:
        db: 数据库会话
    """
    from ..crud import setting as crud_setting
    from ..schemas import SettingCreate
    
    for setting_data in DEFAULT_MEDIA_SETTINGS:
        # 检查设置是否已存在
        existing_setting = crud_setting.get_setting(db, setting_data["key"])
        if not existing_setting:
            # 创建新设置
            setting_create = SettingCreate(
                key=setting_data["key"],
                value=setting_data["value"],
                description=setting_data["description"],
                category=setting_data["category"],
                type=setting_data["type"]
            )
            crud_setting.create_setting(db, setting_create)
            print(f"初始化媒体设置: {setting_data['key']}")
        else:
            print(f"媒体设置已存在: {setting_data['key']}")


def get_media_settings_schema():
    """
    获取媒体设置的配置模式，用于管理界面
    
    Returns:
        Dict: 设置配置模式
    """
    return {
        "图像基础处理": {
            "media_image_quality": {"type": "range", "min": 1, "max": 100, "step": 1, "label": "原图压缩质量"},
            "media_max_image_size": {"type": "number", "min": 500, "max": 12000, "label": "原图最大尺寸（像素）"},
            "media_auto_compress": {"type": "checkbox", "label": "上传后自动压缩原图"},
            "media_extract_exif": {"type": "checkbox", "label": "提取 EXIF 元数据"},
            "media_remove_exif": {"type": "checkbox", "label": "写盘时移除 EXIF"},
            "media_progressive_jpeg": {"type": "checkbox", "label": "启用渐进式 JPEG"},
        },
        "动态缩略图引擎": {
            "thumbnail_enabled": {"type": "checkbox", "label": "启用动态缩略图服务"},
            "thumbnail_cache_dir": {"type": "text", "label": "缓存目录"},
            "thumbnail_allowed_dpr": {"type": "text", "label": "允许的 DPR"},
            "thumbnail_allowed_fmt": {"type": "text", "label": "允许的输出格式集合"},
            "thumbnail_default_fmt": {"type": "select", "label": "默认输出格式", "options": {"auto": "auto", "avif": "avif", "webp": "webp", "jpg": "jpg", "png": "png"}},
            "thumbnail_processor_version": {"type": "text", "label": "处理器版本"},
            "thumbnail_lock_timeout_ms": {"type": "number", "label": "生成锁超时（毫秒）"},
            "thumbnail_negative_cache_ttl_seconds": {"type": "number", "label": "失败负缓存时长（秒）"},
            "thumbnail_generate_timeout_ms": {"type": "number", "label": "单次生成超时（毫秒）"},
            "thumbnail_source_max_megapixels": {"type": "number", "label": "原图像素上限（MP）"},
            "thumbnail_cleanup_interval_hours": {"type": "number", "label": "缓存清理周期（小时）"},
        },
        "外链图片策略": {
            "external_image_policy": {
                "type": "select",
                "label": "外链策略",
                "options": {"passthrough": "passthrough", "localize_async": "localize_async", "block": "block"},
            },
            "external_image_allowlist": {"type": "text", "label": "域名白名单"},
            "external_image_max_bytes": {"type": "number", "label": "单文件大小上限（字节）"},
            "external_image_timeout_ms": {"type": "number", "label": "抓取超时（毫秒）"},
            "external_image_redirect_limit": {"type": "number", "label": "最大重定向次数"},
            "external_image_allowed_mime": {"type": "text", "label": "允许 MIME 列表"},
            "external_image_localize_concurrency": {"type": "number", "label": "本地化并发"},
            "external_image_localize_max_retries": {"type": "number", "label": "本地化最大重试"},
        },
        "上传限制与格式": {
            "media_max_file_size": {
                "type": "select",
                "label": "最大文件上传大小",
                "options": {
                    "10485760": "10MB",
                    "26214400": "25MB",
                    "52428800": "50MB",
                    "104857600": "100MB",
                    "209715200": "200MB",
                },
            },
            "media_allowed_image_formats": {"type": "text", "label": "允许的图像格式"},
            "media_allowed_video_formats": {"type": "text", "label": "允许的视频格式"},
            "media_allowed_audio_formats": {"type": "text", "label": "允许的音频格式"},
            "media_allowed_document_formats": {"type": "text", "label": "允许的文档格式"},
        },
    }
