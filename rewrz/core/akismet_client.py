"""
Akismet API客户端

提供与Akismet垃圾评论检测服务的集成功能。
支持评论垃圾检测、提交误判反馈等功能。

Akismet API 文档: https://akismet.com/development/api/
"""

import asyncio
import aiohttp
import logging
from typing import Dict, Optional, Union
from urllib.parse import urlencode

logger = logging.getLogger(__name__)


class AkismetClient:
    """Akismet API客户端"""
    
    def __init__(self, api_key: str, blog_url: str):
        """
        初始化Akismet客户端
        
        Args:
            api_key: Akismet API密钥
            blog_url: 博客网站URL
        """
        self.api_key = api_key
        self.blog_url = blog_url
        self.base_url = f"https://{api_key}.rest.akismet.com/1.1"
        
    async def verify_key(self) -> bool:
        """
        验证API密钥是否有效
        
        Returns:
            bool: 密钥是否有效
        """
        url = "https://rest.akismet.com/1.1/verify-key"
        data = {
            'key': self.api_key,
            'blog': self.blog_url
        }
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.text()
                    return result.strip() == 'valid'
        except Exception as e:
            logger.error(f"验证Akismet密钥失败: {e}")
            return False
    
    async def check_comment(self,
                           content: str,
                           author_name: str = "",
                           author_email: str = "",
                           author_url: str = "",
                           ip_address: str = "",
                           user_agent: str = "",
                           referrer: str = "",
                           comment_type: str = "comment") -> Dict[str, Union[bool, float]]:
        """
        检查评论是否为垃圾评论
        
        Args:
            content: 评论内容
            author_name: 作者姓名
            author_email: 作者邮箱
            author_url: 作者网址
            ip_address: IP地址
            user_agent: 用户代理
            referrer: 引用页面
            comment_type: 评论类型（comment, trackback, pingback等）
            
        Returns:
            Dict: 包含检测结果的字典
                - is_spam: 是否为垃圾评论
                - confidence: 置信度（0-1）
                - pro_tip: 专业版提示（如果有）
        """
        if not self.api_key or not self.blog_url:
            logger.warning("Akismet API密钥或博客URL未配置")
            return {"is_spam": False, "confidence": 0.0}
        
        url = f"{self.base_url}/comment-check"
        data = {
            'blog': self.blog_url,
            'user_ip': ip_address,
            'user_agent': user_agent,
            'referrer': referrer,
            'comment_type': comment_type,
            'comment_author': author_name,
            'comment_author_email': author_email,
            'comment_author_url': author_url,
            'comment_content': content,
        }
        
        # 移除空值
        data = {k: v for k, v in data.items() if v}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.text()
                    headers = response.headers
                    
                    # 解析响应
                    is_spam = result.strip() == 'true'
                    
                    # 获取置信度（专业版功能）
                    confidence = 0.0
                    pro_tip = None
                    
                    if 'X-akismet-pro-tip' in headers:
                        pro_tip = headers['X-akismet-pro-tip']
                        
                    if 'X-akismet-debug-help' in headers:
                        logger.debug(f"Akismet调试信息: {headers['X-akismet-debug-help']}")
                    
                    # 如果是垃圾评论，置信度设为高
                    if is_spam:
                        confidence = 0.8  # 基础置信度
                        if pro_tip == 'discard':
                            confidence = 0.95  # 建议直接丢弃的垃圾评论
                    
                    return {
                        "is_spam": is_spam,
                        "confidence": confidence,
                        "pro_tip": pro_tip
                    }
                    
        except Exception as e:
            logger.error(f"Akismet检查失败: {e}")
            # 发生错误时，返回保守结果
            return {"is_spam": False, "confidence": 0.0}
    
    async def submit_spam(self,
                         content: str,
                         author_name: str = "",
                         author_email: str = "",
                         author_url: str = "",
                         ip_address: str = "",
                         user_agent: str = "",
                         referrer: str = "",
                         comment_type: str = "comment") -> bool:
        """
        提交垃圾评论给Akismet（用于训练）
        
        Args:
            content: 评论内容
            author_name: 作者姓名
            author_email: 作者邮箱
            author_url: 作者网址
            ip_address: IP地址
            user_agent: 用户代理
            referrer: 引用页面
            comment_type: 评论类型
            
        Returns:
            bool: 提交是否成功
        """
        if not self.api_key or not self.blog_url:
            return False
            
        url = f"{self.base_url}/submit-spam"
        data = {
            'blog': self.blog_url,
            'user_ip': ip_address,
            'user_agent': user_agent,
            'referrer': referrer,
            'comment_type': comment_type,
            'comment_author': author_name,
            'comment_author_email': author_email,
            'comment_author_url': author_url,
            'comment_content': content,
        }
        
        # 移除空值
        data = {k: v for k, v in data.items() if v}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.text()
                    return result.strip() == 'Thanks for making the web a better place.'
        except Exception as e:
            logger.error(f"提交垃圾评论失败: {e}")
            return False
    
    async def submit_ham(self,
                        content: str,
                        author_name: str = "",
                        author_email: str = "",
                        author_url: str = "",
                        ip_address: str = "",
                        user_agent: str = "",
                        referrer: str = "",
                        comment_type: str = "comment") -> bool:
        """
        提交误判的正常评论给Akismet（用于训练）
        
        Args:
            content: 评论内容
            author_name: 作者姓名
            author_email: 作者邮箱
            author_url: 作者网址
            ip_address: IP地址
            user_agent: 用户代理
            referrer: 引用页面
            comment_type: 评论类型
            
        Returns:
            bool: 提交是否成功
        """
        if not self.api_key or not self.blog_url:
            return False
            
        url = f"{self.base_url}/submit-ham"
        data = {
            'blog': self.blog_url,
            'user_ip': ip_address,
            'user_agent': user_agent,
            'referrer': referrer,
            'comment_type': comment_type,
            'comment_author': author_name,
            'comment_author_email': author_email,
            'comment_author_url': author_url,
            'comment_content': content,
        }
        
        # 移除空值
        data = {k: v for k, v in data.items() if v}
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, data=data) as response:
                    result = await response.text()
                    return result.strip() == 'Thanks for making the web a better place.'
        except Exception as e:
            logger.error(f"提交正常评论失败: {e}")
            return False


def get_akismet_client(api_key: str, blog_url: str) -> Optional[AkismetClient]:
    """
    获取Akismet客户端实例
    
    Args:
        api_key: API密钥
        blog_url: 博客URL
        
    Returns:
        AkismetClient: 客户端实例，如果参数无效则返回None
    """
    if not api_key or not blog_url:
        return None
    
    return AkismetClient(api_key, blog_url)