"""
头像系统默认配置

用于初始化头像系统的默认设置，包括Gravatar配置、自定义头像设置等。
这些设置可以通过管理后台进行修改。
"""

# 头像系统默认配置
DEFAULT_AVATAR_SETTINGS = [
    # Gravatar设置
    {
        "key": "avatar_gravatar_enabled",
        "value": {"value": True},
        "description": "启用Gravatar头像服务",
        "category": "avatar",
        "type": "boolean"
    },
    {
        "key": "avatar_gravatar_default",
        "value": {"value": "identicon"},
        "description": "Gravatar默认头像类型（identicon/monsterid/wavatar/retro/robohash/blank）",
        "category": "avatar",
        "type": "string"
    },
    {
        "key": "avatar_gravatar_rating",
        "value": {"value": "g"},
        "description": "Gravatar内容评级（g/pg/r/x）",
        "category": "avatar",
        "type": "string"
    },
    {
        "key": "avatar_gravatar_size",
        "value": {"value": 80},
        "description": "Gravatar默认尺寸（像素）",
        "category": "avatar",
        "type": "integer"
    },
    {
        "key": "avatar_gravatar_base_url",
        "value": {"value": "https://www.gravatar.com/avatar/"},
        "description": "Gravatar服务基础URL",
        "category": "avatar",
        "type": "string"
    },
    
    # 自定义头像设置
    {
        "key": "avatar_custom_enabled",
        "value": {"value": True},
        "description": "启用自定义头像上传",
        "category": "avatar",
        "type": "boolean"
    },
    {
        "key": "avatar_upload_path",
        "value": {"value": "media_uploads/avatars/"},
        "description": "头像上传目录路径",
        "category": "avatar",
        "type": "string"
    },
    {
        "key": "avatar_max_size",
        "value": {"value": 2097152},  # 2MB
        "description": "头像文件最大大小（字节）",
        "category": "avatar",
        "type": "integer"
    },
    {
        "key": "avatar_allowed_formats",
        "value": {
            "value": ["jpg", "jpeg", "png", "gif", "webp"]
        },
        "description": "允许的头像文件格式",
        "category": "avatar",
        "type": "array"
    },
    
    # 显示设置
    {
        "key": "avatar_default_url",
        "value": {"value": "/static/images/default-avatar.png"},
        "description": "默认头像URL",
        "category": "avatar",
        "type": "string"
    },
    {
        "key": "avatar_show_anonymous",
        "value": {"value": True},
        "description": "为匿名评论者显示头像",
        "category": "avatar",
        "type": "boolean"
    },
    {
        "key": "avatar_comment_size",
        "value": {"value": 40},
        "description": "评论区头像尺寸（像素）",
        "category": "avatar",
        "type": "integer"
    },
    {
        "key": "avatar_profile_size",
        "value": {"value": 120},
        "description": "用户资料页头像尺寸（像素）",
        "category": "avatar",
        "type": "integer"
    },
    
    # 高级设置
    {
        "key": "avatar_cache_enabled",
        "value": {"value": True},
        "description": "启用头像缓存",
        "category": "avatar",
        "type": "boolean"
    },
    {
        "key": "avatar_cache_duration",
        "value": {"value": 86400},  # 24小时
        "description": "头像缓存时长（秒）",
        "category": "avatar",
        "type": "integer"
    },
    {
        "key": "avatar_lazy_loading",
        "value": {"value": True},
        "description": "启用头像懒加载",
        "category": "avatar",
        "type": "boolean"
    },
    {
        "key": "avatar_auto_resize",
        "value": {"value": True},
        "description": "自动调整上传头像尺寸",
        "category": "avatar",
        "type": "boolean"
    },
    {
        "key": "avatar_compression_quality",
        "value": {"value": 85},
        "description": "头像压缩质量（1-100）",
        "category": "avatar",
        "type": "integer"
    }
]


def init_avatar_settings(db):
    """
    初始化头像设置到数据库
    
    Args:
        db: 数据库会话
    """
    from ..crud import setting as crud_setting
    from ..schemas import SettingCreate
    
    for setting_data in DEFAULT_AVATAR_SETTINGS:
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
            print(f"初始化头像设置: {setting_data['key']}")
        else:
            print(f"头像设置已存在: {setting_data['key']}")