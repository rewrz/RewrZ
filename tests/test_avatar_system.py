"""
头像系统测试

测试头像服务的各项功能：
1. Gravatar URL生成
2. 自定义头像上传
3. 头像显示逻辑
4. 头像设置管理

包含各种头像场景的测试用例。
"""

import pytest
import hashlib
from sqlalchemy.orm import Session
from rewrz.core.avatar import AvatarService, get_gravatar_url, get_comment_avatar_html
from rewrz.core.avatar_config import init_avatar_settings
from tests.conftest import get_db_session


class TestAvatarService:
    """头像服务测试类"""
    
    @pytest.fixture(autouse=True)
    def setup_avatar_service(self, test_db: Session):
        """设置头像服务"""
        # 初始化头像设置
        init_avatar_settings(test_db)
        self.avatar_service = AvatarService(test_db)
        self.db = test_db
    
    def test_gravatar_hash_generation(self):
        """测试Gravatar哈希生成"""
        email = "test@example.com"
        expected_hash = hashlib.md5(email.encode('utf-8')).hexdigest()
        actual_hash = self.avatar_service.get_gravatar_hash(email)
        
        assert actual_hash == expected_hash
    
    def test_gravatar_hash_case_insensitive(self):
        """测试Gravatar哈希大小写不敏感"""
        email1 = "Test@Example.Com"
        email2 = "test@example.com"
        
        hash1 = self.avatar_service.get_gravatar_hash(email1)
        hash2 = self.avatar_service.get_gravatar_hash(email2)
        
        assert hash1 == hash2
    
    def test_gravatar_url_generation(self):
        """测试Gravatar URL生成"""
        email = "test@example.com"
        size = 80
        
        url = self.avatar_service.get_gravatar_url(email, size)
        
        assert "gravatar.com/avatar/" in url
        assert f"s={size}" in url
        assert "d=identicon" in url
        assert "r=g" in url
    
    def test_gravatar_url_with_custom_params(self):
        """测试自定义参数的Gravatar URL生成"""
        email = "test@example.com"
        size = 120
        default = "monsterid"
        rating = "pg"
        
        url = self.avatar_service.get_gravatar_url(email, size, default, rating)
        
        assert f"s={size}" in url
        assert f"d={default}" in url
        assert f"r={rating}" in url
    
    def test_empty_email_gravatar(self):
        """测试空邮箱的Gravatar处理"""
        url = self.avatar_service.get_gravatar_url("")
        assert url == ""
        
        url = self.avatar_service.get_gravatar_url(None)
        assert url == ""
    
    def test_avatar_file_validation_valid(self):
        """测试有效头像文件验证"""
        filename = "test_avatar.jpg"
        file_size = 1024 * 1024  # 1MB
        
        is_valid, error_msg = self.avatar_service.validate_avatar_file(filename, file_size)
        
        assert is_valid == True
        assert error_msg == ""
    
    def test_avatar_file_validation_too_large(self):
        """测试文件过大验证"""
        filename = "test_avatar.jpg"
        file_size = 3 * 1024 * 1024  # 3MB (超过2MB限制)
        
        is_valid, error_msg = self.avatar_service.validate_avatar_file(filename, file_size)
        
        assert is_valid == False
        assert "文件大小超过限制" in error_msg
    
    def test_avatar_file_validation_invalid_format(self):
        """测试无效文件格式验证"""
        filename = "test_avatar.txt"
        file_size = 1024 * 1024
        
        is_valid, error_msg = self.avatar_service.validate_avatar_file(filename, file_size)
        
        assert is_valid == False
        assert "不支持的文件格式" in error_msg
    
    def test_avatar_filename_generation(self):
        """测试头像文件名生成"""
        user_id = 123
        original_filename = "my_photo.jpg"
        
        new_filename = self.avatar_service.generate_avatar_filename(user_id, original_filename)
        
        assert new_filename == "user_123_avatar.jpg"
        assert new_filename.endswith(".jpg")
    
    def test_avatar_url_from_filename(self):
        """测试从文件名生成URL"""
        filename = "user_123_avatar.jpg"
        url = self.avatar_service.get_avatar_url_from_filename(filename)
        
        assert url == "/media/avatars/user_123_avatar.jpg"
    
    def test_comment_avatar_url_anonymous(self):
        """测试匿名评论者头像URL"""
        email = "anonymous@example.com"
        url = self.avatar_service.get_comment_avatar_url(email)
        
        # 应该返回Gravatar URL
        assert "gravatar.com" in url
    
    def test_comment_avatar_url_with_user_id(self):
        """测试注册用户评论头像URL"""
        email = "user@example.com"
        user_id = 1
        
        # 由于没有自定义头像，应该返回Gravatar
        url = self.avatar_service.get_comment_avatar_url(email, user_id)
        assert "gravatar.com" in url or self.avatar_service.default_avatar_url in url
    
    def test_settings_loading(self, test_db: Session):
        """测试设置加载"""
        init_avatar_settings(test_db)
        avatar_service = AvatarService(test_db)
        
        # 验证默认设置已正确加载
        assert avatar_service.gravatar_enabled == True
        assert avatar_service.gravatar_size == 80
        assert avatar_service.custom_avatar_enabled == True
        assert len(avatar_service.avatar_allowed_formats) > 0


class TestAvatarHelperFunctions:
    """头像辅助函数测试"""
    
    def test_get_gravatar_url_function(self):
        """测试快速Gravatar URL生成函数"""
        email = "test@example.com"
        url = get_gravatar_url(email)
        
        assert "gravatar.com/avatar/" in url
        assert "s=80" in url  # 默认尺寸
        assert "d=identicon" in url  # 默认类型
    
    def test_get_gravatar_url_with_params(self):
        """测试带参数的Gravatar URL生成"""
        email = "test@example.com"
        url = get_gravatar_url(email, size=120, default="monsterid")
        
        assert "s=120" in url
        assert "d=monsterid" in url
    
    def test_get_comment_avatar_html(self):
        """测试评论头像HTML生成"""
        email = "test@example.com"
        name = "测试用户"
        
        html = get_comment_avatar_html(email, name)
        
        assert "<img" in html
        assert "gravatar.com" in html
        assert "测试用户的头像" in html
        assert 'class="avatar"' in html
    
    def test_get_comment_avatar_html_custom_params(self):
        """测试自定义参数的头像HTML生成"""
        email = "test@example.com"
        name = "测试用户"
        size = 60
        css_class = "custom-avatar"
        
        html = get_comment_avatar_html(email, name, size=size, css_class=css_class)
        
        assert f'width="{size}"' in html
        assert f'height="{size}"' in html
        assert f'class="{css_class}"' in html


class TestAvatarIntegration:
    """头像系统集成测试"""
    
    def test_avatar_priority_logic(self, test_db: Session):
        """测试头像优先级逻辑"""
        init_avatar_settings(test_db)
        avatar_service = AvatarService(test_db)
        
        email = "test@example.com"
        
        # 没有用户ID时，应该使用Gravatar
        url1 = avatar_service.get_avatar_url(email)
        assert "gravatar.com" in url1 or avatar_service.default_avatar_url in url1
        
        # 有用户ID但没有自定义头像时，仍使用Gravatar
        url2 = avatar_service.get_avatar_url(email, user_id=999)
        assert "gravatar.com" in url2 or avatar_service.default_avatar_url in url2
    
    def test_avatar_settings_integration(self, test_db: Session):
        """测试头像设置集成"""
        init_avatar_settings(test_db)
        avatar_service = AvatarService(test_db)
        
        # 验证所有设置都已正确初始化
        assert isinstance(avatar_service.gravatar_enabled, bool)
        assert isinstance(avatar_service.gravatar_size, int)
        assert isinstance(avatar_service.avatar_max_size, int)
        assert isinstance(avatar_service.avatar_allowed_formats, list)
        assert avatar_service.gravatar_size > 0
        assert avatar_service.avatar_max_size > 0
    
    def test_disabled_gravatar_fallback(self, test_db: Session):
        """测试Gravatar禁用时的回退机制"""
        init_avatar_settings(test_db)
        avatar_service = AvatarService(test_db)
        
        # 临时禁用Gravatar
        avatar_service.gravatar_enabled = False
        
        email = "test@example.com"
        url = avatar_service.get_avatar_url(email)
        
        # 应该返回默认头像
        assert url == avatar_service.default_avatar_url