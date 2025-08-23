"""
头像服务模块

提供评论用户头像功能，支持：
1. Gravatar 第三方头像服务（基于邮箱MD5）
2. 博主自定义头像上传
3. 默认头像fallback机制

类似WordPress的头像系统实现。
"""

import hashlib
import os
from typing import Optional, Union
from urllib.parse import urlencode
from sqlalchemy.orm import Session
from ..crud import setting as crud_setting
from ..crud import user as crud_user


class AvatarService:
    """头像服务类"""
    
    def __init__(self, db: Session):
        self.db = db
        self.load_settings()
    
    def load_settings(self):
        """从数据库加载头像相关设置"""
        # Gravatar设置
        self.gravatar_enabled = self._get_setting_bool("avatar_gravatar_enabled", True)
        self.gravatar_default = self._get_setting_str("avatar_gravatar_default", "identicon")
        self.gravatar_rating = self._get_setting_str("avatar_gravatar_rating", "g")
        self.gravatar_size = self._get_setting_int("avatar_gravatar_size", 80)
        self.gravatar_base_url = self._get_setting_str("avatar_gravatar_base_url", "https://www.gravatar.com/avatar/")
        
        # 自定义头像设置
        self.custom_avatar_enabled = self._get_setting_bool("avatar_custom_enabled", True)
        self.avatar_upload_path = self._get_setting_str("avatar_upload_path", "media_uploads/avatars/")
        self.avatar_max_size = self._get_setting_int("avatar_max_size", 2 * 1024 * 1024)  # 2MB
        self.avatar_allowed_formats = self._get_setting_list("avatar_allowed_formats", ["jpg", "jpeg", "png", "gif", "webp"])
        
        # 默认头像设置
        self.default_avatar_url = self._get_setting_str("avatar_default_url", "/static/images/default-avatar.png")
        self.show_anonymous_avatars = self._get_setting_bool("avatar_show_anonymous", True)
    
    def _get_setting_bool(self, key: str, default: bool) -> bool:
        """获取布尔类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return bool(setting.value["value"])
        return default
    
    def _get_setting_str(self, key: str, default: str) -> str:
        """获取字符串类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return str(setting.value["value"])
        return default
    
    def _get_setting_int(self, key: str, default: int) -> int:
        """获取整数类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return int(setting.value["value"])
        return default
    
    def _get_setting_list(self, key: str, default: list) -> list:
        """获取列表类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return setting.value["value"]
        return default
    
    def get_gravatar_hash(self, email: str) -> str:
        """
        生成Gravatar哈希值
        
        Args:
            email: 用户邮箱地址
            
        Returns:
            MD5哈希值字符串
        """
        if not email:
            return ""
        
        # 转换为小写并去除空格
        email = email.lower().strip()
        
        # 生成MD5哈希
        return hashlib.md5(email.encode('utf-8')).hexdigest()
    
    def get_gravatar_url(self, email: str, size: Optional[int] = None, 
                        default: Optional[str] = None, rating: Optional[str] = None) -> str:
        """
        生成Gravatar头像URL
        
        Args:
            email: 用户邮箱地址
            size: 头像尺寸（像素），默认使用系统设置
            default: 默认头像类型，默认使用系统设置
            rating: 内容评级，默认使用系统设置
            
        Returns:
            Gravatar头像URL
        """
        if not self.gravatar_enabled or not email:
            return ""
        
        # 使用传入参数或系统默认值
        size = size or self.gravatar_size
        default = default or self.gravatar_default
        rating = rating or self.gravatar_rating
        
        # 生成哈希
        email_hash = self.get_gravatar_hash(email)
        
        # 构建查询参数
        params = {
            's': str(size),
            'd': default,
            'r': rating
        }
        
        # 生成完整URL
        return f"{self.gravatar_base_url}{email_hash}?{urlencode(params)}"
    
    def get_user_custom_avatar_url(self, user_id: int) -> Optional[str]:
        """
        获取用户自定义头像URL
        
        Args:
            user_id: 用户ID
            
        Returns:
            自定义头像URL或None
        """
        if not self.custom_avatar_enabled:
            return None
        
        user = crud_user.get_user(self.db, user_id)
        if not user or not hasattr(user, 'avatar_url') or not user.avatar_url:
            return None
        
        return user.avatar_url
    
    def get_avatar_url(self, email: str, user_id: Optional[int] = None, 
                      size: Optional[int] = None) -> str:
        """
        获取头像URL（统一入口）
        
        优先级：自定义头像 > Gravatar > 默认头像
        
        Args:
            email: 用户邮箱地址
            user_id: 用户ID（可选，用于获取自定义头像）
            size: 头像尺寸
            
        Returns:
            头像URL
        """
        # 1. 优先使用自定义头像（仅限注册用户）
        if user_id and self.custom_avatar_enabled:
            custom_avatar = self.get_user_custom_avatar_url(user_id)
            if custom_avatar:
                return custom_avatar
        
        # 2. 使用Gravatar头像
        if self.gravatar_enabled and email:
            gravatar_url = self.get_gravatar_url(email, size)
            if gravatar_url:
                return gravatar_url
        
        # 3. 返回默认头像
        return self.default_avatar_url
    
    def get_comment_avatar_url(self, author_email: str, author_id: Optional[int] = None, 
                              size: Optional[int] = None) -> str:
        """
        获取评论作者头像URL
        
        Args:
            author_email: 评论作者邮箱
            author_id: 评论作者用户ID（如果是注册用户）
            size: 头像尺寸
            
        Returns:
            头像URL
        """
        if not self.show_anonymous_avatars and not author_id:
            return self.default_avatar_url
        
        return self.get_avatar_url(author_email, author_id, size)
    
    def validate_avatar_file(self, filename: str, file_size: int) -> tuple[bool, str]:
        """
        验证头像文件
        
        Args:
            filename: 文件名
            file_size: 文件大小（字节）
            
        Returns:
            (是否有效, 错误信息)
        """
        # 检查文件大小
        if file_size > self.avatar_max_size:
            max_size_mb = self.avatar_max_size / (1024 * 1024)
            return False, f"文件大小超过限制（最大 {max_size_mb:.1f}MB）"
        
        # 检查文件格式
        if not filename:
            return False, "文件名不能为空"
        
        file_ext = filename.lower().split('.')[-1]
        if file_ext not in self.avatar_allowed_formats:
            allowed = ", ".join(self.avatar_allowed_formats)
            return False, f"不支持的文件格式（支持：{allowed}）"
        
        return True, ""
    
    def generate_avatar_filename(self, user_id: int, original_filename: str) -> str:
        """
        生成头像文件名
        
        Args:
            user_id: 用户ID
            original_filename: 原始文件名
            
        Returns:
            新的文件名
        """
        file_ext = original_filename.lower().split('.')[-1]
        return f"user_{user_id}_avatar.{file_ext}"
    
    def get_avatar_file_path(self, filename: str) -> str:
        """
        获取头像文件的完整路径
        
        Args:
            filename: 头像文件名
            
        Returns:
            完整文件路径
        """
        return os.path.join(self.avatar_upload_path, filename)
    
    def get_avatar_url_from_filename(self, filename: str) -> str:
        """
        从文件名生成头像访问URL
        
        Args:
            filename: 头像文件名
            
        Returns:
            头像访问URL
        """
        return f"/media/avatars/{filename}"


# 全局头像服务实例（延迟初始化）
_avatar_service: Optional[AvatarService] = None

def get_avatar_service(db: Session) -> AvatarService:
    """获取头像服务实例"""
    global _avatar_service
    if _avatar_service is None:
        _avatar_service = AvatarService(db)
    return _avatar_service


# 便捷函数
def get_gravatar_url(email: str, size: int = 80, default: str = "identicon") -> str:
    """
    快速生成Gravatar URL的便捷函数
    
    Args:
        email: 邮箱地址
        size: 头像尺寸
        default: 默认头像类型
        
    Returns:
        Gravatar URL
    """
    if not email:
        return ""
    
    email_hash = hashlib.md5(email.lower().strip().encode('utf-8')).hexdigest()
    params = urlencode({'s': str(size), 'd': default, 'r': 'g'})
    return f"https://www.gravatar.com/avatar/{email_hash}?{params}"


def get_comment_avatar_html(author_email: str, author_name: str, 
                           author_id: Optional[int] = None, size: int = 40, 
                           css_class: str = "avatar") -> str:
    """
    生成评论头像的HTML代码
    
    Args:
        author_email: 作者邮箱
        author_name: 作者姓名
        author_id: 作者用户ID
        size: 头像尺寸
        css_class: CSS类名
        
    Returns:
        头像HTML代码
    """
    avatar_url = get_gravatar_url(author_email, size)
    alt_text = f"{author_name}的头像"
    
    return f'''<img src="{avatar_url}" alt="{alt_text}" class="{css_class}" width="{size}" height="{size}" loading="lazy">'''