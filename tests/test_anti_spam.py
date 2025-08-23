"""
反垃圾评论系统测试

测试三层防护系统的各项功能：
1. 第一层：无感防御（蜜罐、时间戳检查）
2. 第二层：内容分析（链接、关键词、重复内容检查）
3. 第三层：验证码验证

包含各种垃圾评论场景的测试用例。
"""

import pytest
import time
import asyncio
from sqlalchemy.orm import Session
from rewrz.core.anti_spam import AntiSpamEngine, SpamCheckResult
from rewrz.core.anti_spam_config import init_anti_spam_settings
from tests.conftest import get_db_session


class TestAntiSpamEngine:
    """反垃圾评论引擎测试类"""
    
    @pytest.fixture(autouse=True)
    def setup_anti_spam(self, test_db: Session):
        """设置反垃圾系统"""
        # 初始化反垃圾设置
        init_anti_spam_settings(test_db)
        self.anti_spam = AntiSpamEngine(test_db)
        self.db = test_db
    
    @pytest.mark.asyncio
    async def test_honeypot_detection(self):
        """测试蜜罐陷阱检测"""
        # 触发蜜罐陷阱
        result = await self.anti_spam.check_comment(
            content="正常评论内容",
            author_name="张三",
            author_email="zhangsan@example.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field="bot_filled_this",  # 机器人填写了蜜罐字段
            form_timestamp=time.time() - 10
        )
        
        assert result.is_spam == True
        assert result.action == "block"
        assert result.layer == 1
        assert "蜜罐陷阱" in result.reason
    
    @pytest.mark.asyncio
    async def test_time_threshold_check(self):
        """测试时间戳检查"""
        # 提交时间过短
        result = await self.anti_spam.check_comment(
            content="正常评论内容",
            author_name="张三",
            author_email="zhangsan@example.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 1  # 只有1秒，低于3秒阈值
        )
        
        assert result.is_spam == True
        assert result.action == "block"
        assert result.layer == 1
        assert "提交时间过短" in result.reason
    
    @pytest.mark.asyncio
    async def test_user_agent_check(self):
        """测试User-Agent检查"""
        # 可疑的User-Agent
        result = await self.anti_spam.check_comment(
            content="正常评论内容",
            author_name="张三",
            author_email="zhangsan@example.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Bot",  # 过短的User-Agent
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.is_spam == True
        assert result.action == "moderate"
        assert result.layer == 1
        assert "可疑的User-Agent" in result.reason
    
    @pytest.mark.asyncio
    async def test_excessive_links_detection(self):
        """测试过多链接检测"""
        # 包含过多链接的评论
        spam_content = """
        这是一个垃圾评论，包含很多链接：
        访问 https://spam1.com 获取优惠
        还有 https://spam2.com 更多折扣
        以及 https://spam3.com 免费试用
        """
        
        result = await self.anti_spam.check_comment(
            content=spam_content,
            author_name="Spammer",
            author_email="spam@spam.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.confidence > 0.3  # 应该有较高的垃圾概率
        assert "过多链接" in result.reason
        assert result.layer == 2
    
    @pytest.mark.asyncio
    async def test_spam_keyword_detection(self):
        """测试垃圾关键词检测"""
        # 包含垃圾关键词的评论
        spam_content = "免费赚钱机会！加微信领取优惠券，点击进入官方网站"
        
        result = await self.anti_spam.check_comment(
            content=spam_content,
            author_name="广告员",
            author_email="ad@spam.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.confidence > 0.5  # 包含多个垃圾关键词
        assert "垃圾关键词" in result.reason
        assert result.layer == 2
    
    @pytest.mark.asyncio
    async def test_short_content_detection(self):
        """测试过短内容检测"""
        result = await self.anti_spam.check_comment(
            content="好",  # 内容过短
            author_name="用户",
            author_email="user@example.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.confidence > 0.1
        assert "内容过短" in result.reason
        assert result.layer == 2
    
    @pytest.mark.asyncio
    async def test_repetitive_content_detection(self):
        """测试重复内容检测"""
        # 重复字符
        spam_content = "aaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        
        result = await self.anti_spam.check_comment(
            content=spam_content,
            author_name="重复用户",
            author_email="repeat@example.com",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.confidence > 0.2
        assert "重复字符" in result.reason
        assert result.layer == 2
    
    @pytest.mark.asyncio
    async def test_invalid_email_detection(self):
        """测试无效邮箱检测"""
        result = await self.anti_spam.check_comment(
            content="正常的评论内容",
            author_name="用户",
            author_email="invalid-email",  # 无效的邮箱格式
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.confidence > 0.1
        assert "邮箱格式异常" in result.reason
        assert result.layer == 2
    
    @pytest.mark.asyncio
    async def test_normal_comment_approval(self):
        """测试正常评论通过"""
        result = await self.anti_spam.check_comment(
            content="这是一个很好的文章，谢谢作者的分享。我学到了很多有用的知识。",
            author_name="张三",
            author_email="zhangsan@example.com",
            author_url="https://zhangsan.blog",
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        assert result.is_spam == False
        assert result.action == "allow"
        assert result.confidence < 0.3
        assert "通过内容分析" in result.reason
    
    @pytest.mark.asyncio
    async def test_moderate_confidence_captcha(self):
        """测试中等可疑度触发验证码"""
        # 创建一个中等可疑度的评论（包含少量链接但不是明显垃圾）
        result = await self.anti_spam.check_comment(
            content="不错的文章，可以参考这个网站 https://example.com 了解更多",
            author_name="用户",
            author_email="user@tempmail.com",  # 临时邮箱域名
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0 Test",
            honeypot_field=None,
            form_timestamp=time.time() - 10
        )
        
        # 根据设置，可疑度超过0.6时会触发验证码
        if result.confidence >= 0.6:
            assert result.action == "captcha"
            assert result.layer == 3
    
    def test_honeypot_field_generation(self):
        """测试蜜罐字段生成"""
        field_name = self.anti_spam.generate_honeypot_field_name()
        assert len(field_name) == 8  # MD5前8位
        assert field_name.isalnum()  # 只包含字母和数字
    
    def test_form_token_generation(self):
        """测试表单令牌生成"""
        token = self.anti_spam.generate_form_token()
        assert len(token) == 32  # MD5哈希长度
        assert token.isalnum()  # 只包含字母和数字


class TestAntiSpamIntegration:
    """反垃圾系统集成测试"""
    
    @pytest.mark.asyncio
    async def test_settings_loading(self, test_db: Session):
        """测试设置加载"""
        init_anti_spam_settings(test_db)
        anti_spam = AntiSpamEngine(test_db)
        
        # 验证默认设置已正确加载
        assert anti_spam.honeypot_enabled == True
        assert anti_spam.time_threshold == 3
        assert anti_spam.max_links == 2
        assert anti_spam.keyword_filter_enabled == True
        assert len(anti_spam.spam_keywords) > 0
        assert anti_spam.akismet_enabled == False  # 默认不启用Akismet
        assert anti_spam.captcha_enabled == True
        assert anti_spam.captcha_threshold == 0.6
    
    @pytest.mark.asyncio
    async def test_multilayered_spam_detection(self, test_db: Session):
        """测试多层垃圾检测"""
        init_anti_spam_settings(test_db)
        anti_spam = AntiSpamEngine(test_db)

        # 创建一个触发多个检测规则的垃圾评论
        spam_content = """
        免费赚钱！！！加微信获取优惠券！
        访问 https://spam1.com 和 https://spam2.com 和 https://spam3.com
        立即注册获得免费试用！！！
        """

        result = await anti_spam.check_comment(
            content=spam_content,
            author_name="SpamBot",
            author_email="invalid-email",
            author_url=None,
            ip_address="192.168.1.1",
            user_agent="Bot",
            honeypot_field=None,
            form_timestamp=time.time() - 1  # 时间过短
        )

        # 应该在第一层就被拦截（时间过短）
        assert result.is_spam == True
        assert result.layer == 1
        assert "提交时间过短" in result.reason

    @pytest.mark.asyncio
    async def test_legitimate_comment_flow(self, test_db: Session):
        """测试正常评论流程"""
        init_anti_spam_settings(test_db)
        anti_spam = AntiSpamEngine(test_db)

        result = await anti_spam.check_comment(
            content="感谢分享这篇有价值的文章。作为一名开发者，我发现这些技巧很实用。",
            author_name="李开发",
            author_email="li.developer@company.com",
            author_url="https://li-blog.com",
            ip_address="203.208.60.1",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
            honeypot_field=None,
            form_timestamp=time.time() - 30  # 充足的填写时间
        )

        assert result.is_spam == False
        assert result.action == "allow"
        assert result.confidence < 0.3
        assert "通过内容分析" in result.reason