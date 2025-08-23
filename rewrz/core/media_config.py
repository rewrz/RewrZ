"""
媒体处理系统配置模块

定义媒体处理相关的默认设置和初始化函数。
支持图像处理、缩略图生成、文件上传等配置。
"""

from sqlalchemy.orm import Session
from ..crud import setting as crud_setting

# 默认媒体处理设置
DEFAULT_MEDIA_SETTINGS = [
    # 图像处理设置
    {
        "key": "media_image_quality",
        "value": {"value": 85},
        "description": "图像压缩质量（1-100）",
        "category": "media",
        "type": "integer"
    },
    {
        "key": "media_max_image_size",
        "value": {"value": 2048},
        "description": "图像最大尺寸（像素）",
        "category": "media",
        "type": "integer"
    },
    {
        "key": "media_enable_webp",
        "value": {"value": True},
        "description": "启用WebP格式转换",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_auto_compress",
        "value": {"value": True},
        "description": "自动压缩上传的图像",
        "category": "media",
        "type": "boolean"
    },
    
    # 缩略图设置
    {
        "key": "media_generate_thumbnails",
        "value": {"value": True},
        "description": "自动生成缩略图",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_thumbnail_quality",
        "value": {"value": 80},
        "description": "缩略图压缩质量（1-100）",
        "category": "media",
        "type": "integer"
    },
    
    # 上传设置
    {
        "key": "media_upload_path",
        "value": {"value": "media_uploads/"},
        "description": "媒体文件上传路径",
        "category": "media",
        "type": "string"
    },
    {
        "key": "media_max_file_size",
        "value": {"value": 52428800},  # 50MB
        "description": "最大文件上传大小（字节）",
        "category": "media",
        "type": "integer"
    },
    
    # 安全设置
    {
        "key": "media_extract_exif",
        "value": {"value": True},
        "description": "提取图像EXIF元数据",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_remove_exif",
        "value": {"value": False},
        "description": "保存时移除EXIF数据（隐私保护）",
        "category": "media",
        "type": "boolean"
    },
    
    # 文件格式配置
    {
        "key": "media_allowed_image_formats",
        "value": {"value": "jpg,jpeg,png,gif,bmp,webp,tiff"},
        "description": "允许的图像文件格式（逗号分隔）",
        "category": "media",
        "type": "string"
    },
    {
        "key": "media_allowed_video_formats",
        "value": {"value": "mp4,avi,mov,wmv,flv,webm,mkv"},
        "description": "允许的视频文件格式（逗号分隔）",
        "category": "media",
        "type": "string"
    },
    {
        "key": "media_allowed_audio_formats",
        "value": {"value": "mp3,wav,flac,aac,ogg,m4a"},
        "description": "允许的音频文件格式（逗号分隔）",
        "category": "media",
        "type": "string"
    },
    {
        "key": "media_allowed_document_formats",
        "value": {"value": "pdf,doc,docx,txt,md"},
        "description": "允许的文档文件格式（逗号分隔）",
        "category": "media",
        "type": "string"
    },
    
    # 优化设置
    {
        "key": "media_enable_responsive",
        "value": {"value": True},
        "description": "启用响应式图片生成",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_progressive_jpeg",
        "value": {"value": True},
        "description": "启用渐进式JPEG",
        "category": "media",
        "type": "boolean"
    },
    
    # 缓存和存储设置
    {
        "key": "media_enable_cdn",
        "value": {"value": False},
        "description": "启用CDN加速",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_cdn_url",
        "value": {"value": ""},
        "description": "CDN基础URL",
        "category": "media",
        "type": "string"
    },
    
    # 批量处理设置
    {
        "key": "media_batch_process_limit",
        "value": {"value": 10},
        "description": "批量处理文件数量限制",
        "category": "media",
        "type": "integer"
    },
    {
        "key": "media_parallel_processing",
        "value": {"value": True},
        "description": "启用并行处理",
        "category": "media",
        "type": "boolean"
    },
    
    # 图像水印设置
    {
        "key": "media_enable_watermark",
        "value": {"value": False},
        "description": "启用图像水印",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_watermark_text",
        "value": {"value": "RewrZ"},
        "description": "水印文字",
        "category": "media",
        "type": "string"
    },
    {
        "key": "media_watermark_opacity",
        "value": {"value": 0.5},
        "description": "水印透明度（0.0-1.0）",
        "category": "media",
        "type": "float"
    },
    
    # 存储清理设置
    {
        "key": "media_auto_cleanup",
        "value": {"value": False},
        "description": "自动清理未使用的媒体文件",
        "category": "media",
        "type": "boolean"
    },
    {
        "key": "media_cleanup_days",
        "value": {"value": 30},
        "description": "未使用文件保留天数",
        "category": "media",
        "type": "integer"
    }
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
        "图像处理": {
            "media_image_quality": {
                "type": "range",
                "min": 1,
                "max": 100,
                "step": 1,
                "label": "图像压缩质量"
            },
            "media_max_image_size": {
                "type": "number",
                "min": 500,
                "max": 5000,
                "label": "图像最大尺寸（像素）"
            },
            "media_enable_webp": {
                "type": "checkbox",
                "label": "启用WebP格式转换"
            },
            "media_auto_compress": {
                "type": "checkbox",
                "label": "自动压缩上传图像"
            }
        },
        "缩略图设置": {
            "media_generate_thumbnails": {
                "type": "checkbox",
                "label": "自动生成缩略图"
            },
            "media_thumbnail_quality": {
                "type": "range",
                "min": 50,
                "max": 100,
                "step": 5,
                "label": "缩略图压缩质量"
            }
        },
        "上传限制": {
            "media_max_file_size": {
                "type": "select",
                "options": {
                    "10485760": "10MB",
                    "26214400": "25MB",
                    "52428800": "50MB",
                    "104857600": "100MB",
                    "209715200": "200MB"
                },
                "label": "最大文件上传大小"
            }
        },
        "安全设置": {
            "media_extract_exif": {
                "type": "checkbox",
                "label": "提取EXIF元数据"
            },
            "media_remove_exif": {
                "type": "checkbox",
                "label": "移除EXIF数据（隐私保护）"
            }
        },
        "文件格式配置": {
            "media_allowed_image_formats": {
                "type": "text",
                "label": "允许的图像格式",
                "placeholder": "jpg,jpeg,png,gif,bmp,webp,tiff",
                "help": "用逗号分隔，不包含点号"
            },
            "media_allowed_video_formats": {
                "type": "text",
                "label": "允许的视频格式",
                "placeholder": "mp4,avi,mov,wmv,flv,webm,mkv",
                "help": "用逗号分隔，不包含点号"
            },
            "media_allowed_audio_formats": {
                "type": "text",
                "label": "允许的音频格式",
                "placeholder": "mp3,wav,flac,aac,ogg,m4a",
                "help": "用逗号分隔，不包含点号"
            },
            "media_allowed_document_formats": {
                "type": "text",
                "label": "允许的文档格式",
                "placeholder": "pdf,doc,docx,txt,md",
                "help": "用逗号分隔，不包含点号"
            }
        },
        "高级功能": {
            "media_enable_watermark": {
                "type": "checkbox",
                "label": "启用图像水印"
            },
            "media_watermark_text": {
                "type": "text",
                "label": "水印文字",
                "dependency": "media_enable_watermark"
            },
            "media_watermark_opacity": {
                "type": "range",
                "min": 0.1,
                "max": 1.0,
                "step": 0.1,
                "label": "水印透明度",
                "dependency": "media_enable_watermark"
            }
        }
    }