"""
反垃圾评论系统默认配置

用于初始化反垃圾评论系统的默认设置，包括三层防护的各项参数。
这些设置可以通过管理后台进行修改。
"""

# 反垃圾评论默认配置
DEFAULT_ANTI_SPAM_SETTINGS = [
    # 第一层：无感防御设置
    {
        "key": "anti_spam_honeypot_enabled",
        "value": {"value": True},
        "description": "启用蜜罐陷阱检测",
        "category": "anti_spam",
        "type": "boolean"
    },
    {
        "key": "anti_spam_time_threshold", 
        "value": {"value": 5},
        "description": "最小提交时间阈值（秒）",
        "category": "anti_spam",
        "type": "integer"
    },
    
    # 第二层：内容分析设置
    {
        "key": "anti_spam_max_links",
        "value": {"value": 2},
        "description": "评论中允许的最大链接数量",
        "category": "anti_spam", 
        "type": "integer"
    },
    {
        "key": "anti_spam_keyword_filter",
        "value": {"value": True},
        "description": "启用关键词过滤",
        "category": "anti_spam",
        "type": "boolean"
    },
    {
        "key": "anti_spam_keywords",
        "value": {
            "value": [
                # 中文垃圾关键词
                "优惠", "促销", "打折", "免费", "赚钱", "兼职", "代刷", 
                "加QQ", "加微信", "联系电话", "咨询热线", "官方网站",
                "点击进入", "立即注册", "马上咨询", "专业代理",
                
                # 英文垃圾关键词
                "viagra", "cialis", "casino", "poker", "loan", "mortgage", 
                "insurance", "pharmacy", "discount", "sale", "buy now",
                "click here", "free trial", "earn money", "work from home",
                "weight loss", "diet pills", "enlargement", "replica"
            ]
        },
        "description": "垃圾评论关键词列表",
        "category": "anti_spam",
        "type": "array"
    },
    {
        "key": "anti_spam_akismet_enabled",
        "value": {"value": False},
        "description": "启用Akismet垃圾检测服务",
        "category": "anti_spam",
        "type": "boolean"
    },
    {
        "key": "anti_spam_akismet_key",
        "value": {"value": ""},
        "description": "Akismet API密钥",
        "category": "anti_spam",
        "type": "string"
    },
    
    # 第三层：验证码设置
    {
        "key": "anti_spam_captcha_enabled",
        "value": {"value": True},
        "description": "启用验证码验证",
        "category": "anti_spam",
        "type": "boolean"
    },
    {
        "key": "anti_spam_captcha_threshold",
        "value": {"value": 0.6},
        "description": "触发验证码的垃圾概率阈值",
        "category": "anti_spam",
        "type": "float"
    },
    
    # 高级设置
    {
        "key": "anti_spam_ip_whitelist",
        "value": {
            "value": ["127.0.0.1", "::1"]
        },
        "description": "IP地址白名单",
        "category": "anti_spam",
        "type": "array"
    },
    {
        "key": "anti_spam_ip_blacklist",
        "value": {
            "value": []
        },
        "description": "IP地址黑名单",
        "category": "anti_spam",
        "type": "array"
    },
    {
        "key": "anti_spam_auto_approve_threshold",
        "value": {"value": 0.1},
        "description": "自动通过的最大垃圾概率阈值",
        "category": "anti_spam",
        "type": "float"
    },
    {
        "key": "anti_spam_auto_reject_threshold",
        "value": {"value": 0.8},
        "description": "自动拒绝的最小垃圾概率阈值",
        "category": "anti_spam",
        "type": "float"
    },
    
    # 日志和统计设置
    {
        "key": "anti_spam_log_enabled",
        "value": {"value": True},
        "description": "启用反垃圾日志记录",
        "category": "anti_spam",
        "type": "boolean"
    },
    {
        "key": "anti_spam_stats_enabled",
        "value": {"value": True},
        "description": "启用反垃圾统计",
        "category": "anti_spam",
        "type": "boolean"
    }
]


def init_anti_spam_settings(db):
    """
    初始化反垃圾设置到数据库
    
    Args:
        db: 数据库会话
    """
    from ..crud import setting as crud_setting
    from ..schemas import SettingCreate
    
    for setting_data in DEFAULT_ANTI_SPAM_SETTINGS:
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
            print(f"初始化反垃圾设置: {setting_data['key']}")
        else:
            print(f"反垃圾设置已存在: {setting_data['key']}")
