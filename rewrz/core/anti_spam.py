"""
反垃圾评论三层防护系统

根据需求规格说明书2.3.2节实现的分层式反垃圾评论系统：
第一层：无感防御（HoneyPot + 时间戳检查）
第二层：内容分析（链接数量检查 + 关键词过滤 + Akismet检查）
第三层：主动验证（验证码确认）
"""

import re
import hashlib
import time
import threading
import asyncio
import hmac
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from sqlalchemy.orm import Session
from ..crud import setting as crud_setting
from .akismet_client import get_akismet_client
from .config import settings


@dataclass
class SpamCheckResult:
    """垃圾检测结果"""
    is_spam: bool
    confidence: float  # 垃圾概率，0-1之间
    reason: str  # 检测原因
    action: str  # 建议动作：allow, moderate, block
    layer: int  # 触发的防护层级


class AntiSpamEngine:
    """反垃圾评论引擎"""
    
    _FORM_TS_PURPOSE = "comment-form-ts-v1"

    def __init__(self, db: Session):
        self.db = db
        self.load_settings()
    
    def load_settings(self):
        """从数据库加载反垃圾设置"""
        self.apply_settings(self.read_settings_from_db())

    def read_settings_from_db(self) -> Dict[str, Any]:
        """读取当前数据库中的反垃圾设置快照"""
        return {
            # 第一层设置
            "honeypot_enabled": self._get_setting_bool("anti_spam_honeypot_enabled", True),
            "time_threshold": self._get_setting_int("anti_spam_time_threshold", 5),  # 最少5秒提交时间
            "form_max_age_seconds": self._get_setting_int("anti_spam_form_max_age_seconds", 3 * 60 * 60),
            # 第二层设置
            "max_links": self._get_setting_int("anti_spam_max_links", 2),  # 最多2个链接
            "keyword_filter_enabled": self._get_setting_bool("anti_spam_keyword_filter", True),
            "akismet_enabled": self._get_setting_bool("anti_spam_akismet_enabled", False),
            "akismet_api_key": self._get_setting_str("anti_spam_akismet_key", ""),
            # 第三层设置
            "captcha_enabled": self._get_setting_bool("anti_spam_captcha_enabled", True),
            "captcha_threshold": self._get_setting_float("anti_spam_captcha_threshold", 0.6),  # 垃圾概率超过60%启用验证码
            # 垃圾关键词列表
            "spam_keywords": self._get_setting_list("anti_spam_keywords", [
                "优惠", "促销", "打折", "免费", "赚钱", "兼职", "代刷", "加QQ", "加微信",
                "viagra", "casino", "poker", "loan", "mortgage", "insurance", "pharmacy"
            ]),
        }

    def apply_settings(self, values: Dict[str, Any]):
        """将设置快照应用到当前实例"""
        for key, value in values.items():
            setattr(self, key, value)
    
    def _get_setting_bool(self, key: str, default: bool) -> bool:
        """获取布尔类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return bool(setting.value["value"])
        return default
    
    def _get_setting_int(self, key: str, default: int) -> int:
        """获取整数类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return int(setting.value["value"])
        return default
    
    def _get_setting_float(self, key: str, default: float) -> float:
        """获取浮点数类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return float(setting.value["value"])
        return default
    
    def _get_setting_str(self, key: str, default: str) -> str:
        """获取字符串类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return str(setting.value["value"])
        return default
    
    def _get_setting_list(self, key: str, default: List[str]) -> List[str]:
        """获取列表类型设置"""
        setting = crud_setting.get_setting(self.db, key)
        if setting and "value" in setting.value:
            return setting.value["value"]
        return default
    
    async def check_comment(self, 
                     content: str, 
                     author_name: str, 
                     author_email: str, 
                     author_url: Optional[str],
                     ip_address: str,
                     user_agent: str,
                     honeypot_field: Optional[str] = None,
                     form_timestamp: Optional[str] = None) -> SpamCheckResult:
        """
        综合检查评论是否为垃圾评论
        
        Args:
            content: 评论内容
            author_name: 作者姓名
            author_email: 作者邮箱
            author_url: 作者网址
            ip_address: IP地址
            user_agent: 用户代理
            honeypot_field: 蜜罐字段值
            form_timestamp: 表单生成时间戳
            
        Returns:
            SpamCheckResult: 检测结果
        """
        
        # 第一层：无感防御
        layer1_result = self.layer1_passive_defense(
            honeypot_field, form_timestamp, ip_address, user_agent
        )
        if layer1_result.is_spam:
            return layer1_result
        
        # 第二层：内容分析
        layer2_result = await self.layer2_content_analysis(
            content, author_name, author_email, author_url, ip_address, user_agent
        )
        if layer2_result.is_spam:
            # 中等风险（0.5~0.8）优先用验证码确认，避免直接静默丢弃或只进待审核；
            # 之前此处直接返回 moderate，导致后面的验证码分支永远不可达，
            # 后台开启验证码也不会生效。
            if (
                self.captcha_enabled
                and layer2_result.action == "moderate"
                and layer2_result.confidence >= self.captcha_threshold
            ):
                return SpamCheckResult(
                    is_spam=False,
                    confidence=layer2_result.confidence,
                    reason="需要验证码确认",
                    action="captcha",
                    layer=3
                )
            return layer2_result

        # 第三层：根据概率决定是否需要验证码
        if layer2_result.confidence >= self.captcha_threshold and self.captcha_enabled:
            return SpamCheckResult(
                is_spam=False,
                confidence=layer2_result.confidence,
                reason="需要验证码确认",
                action="captcha",
                layer=3
            )
        
        # 通过所有检查
        return SpamCheckResult(
            is_spam=False,
            confidence=layer2_result.confidence,
            reason=layer2_result.reason,  # 保留layer2的reason
            action="allow",
            layer=2  # 保留layer2的layer
        )
    
    def layer1_passive_defense(self, 
                              honeypot_field: Optional[str],
                              form_timestamp: Optional[str],
                              ip_address: str,
                              user_agent: str) -> SpamCheckResult:
        """
        第一层：无感防御
        
        包括HoneyPot检查和时间戳检查
        """
        
        # HoneyPot检查
        if self.honeypot_enabled and honeypot_field:
            return SpamCheckResult(
                is_spam=True,
                confidence=1.0,
                reason="触发蜜罐陷阱",
                action="silent_drop",
                layer=1
            )
        
        # 时间戳检查（必须包含签名令牌，兼容旧版纯时间戳）
        if self.time_threshold > 0:
            if not form_timestamp:
                return SpamCheckResult(
                    is_spam=True,
                    confidence=0.95,
                    reason="缺少表单时间戳",
                    action="silent_drop",
                    layer=1
                )

            parsed_timestamp = self.parse_form_timestamp(form_timestamp)
            if parsed_timestamp is None:
                return SpamCheckResult(
                    is_spam=True,
                    confidence=0.95,
                    reason="表单时间戳无效",
                    action="silent_drop",
                    layer=1
                )

            time_diff = time.time() - parsed_timestamp
            if time_diff < self.time_threshold:
                return SpamCheckResult(
                    is_spam=True,
                    confidence=0.9,
                    reason=f"提交时间过短：{time_diff:.1f}秒",
                    action="too_fast",
                    layer=1
                )
            if time_diff > self.form_max_age_seconds:
                return SpamCheckResult(
                    is_spam=True,
                    confidence=0.6,
                    reason="表单令牌已过期",
                    action="expired",
                    layer=1
                )
        
        # 简单的User-Agent检查
        if not user_agent or len(user_agent) < 10:
            return SpamCheckResult(
                is_spam=True,
                confidence=0.8,
                reason="可疑的User-Agent",
                action="moderate",
                layer=1
            )
        
        # 通过第一层检查
        return SpamCheckResult(
            is_spam=False,
            confidence=0.0,
            reason="通过无感防御",
            action="allow",
            layer=1
        )
    
    async def layer2_content_analysis(self,
                               content: str,
                               author_name: str,
                               author_email: str,
                               author_url: Optional[str],
                               ip_address: str,
                               user_agent: str) -> SpamCheckResult:
        """
        第二层：内容分析
        
        包括链接数量检查、关键词过滤和Akismet检查
        """
        spam_score = 0.0
        reasons = []
        
        # 链接数量检查
        url_pattern = r'https?://\S+'
        urls = re.findall(url_pattern, content)
        if len(urls) > self.max_links:
            spam_score += 0.4
            reasons.append(f"包含过多链接：{len(urls)}个")
        
        # 关键词过滤
        if self.keyword_filter_enabled:
            content_lower = content.lower()
            matched_keywords = [kw for kw in self.spam_keywords if kw.lower() in content_lower]
            if matched_keywords:
                spam_score += 0.3 * min(len(matched_keywords), 3)  # 最多加0.9分
                reasons.append(f"包含垃圾关键词：{', '.join(matched_keywords[:3])}")
        
        # 内容质量检查
        if len(content.strip()) < 5:
            spam_score += 0.2
            reasons.append("内容过短")
        
        # 重复字符检查（简化版）
        if self._has_simple_repetitive_content(content):
            spam_score += 0.3
            reasons.append("包含过多重复字符")
        
        # 邮箱格式检查（简化版）
        if not self._is_valid_email_format(author_email):
            spam_score += 0.2
            reasons.append("邮箱格式异常")
        
        # Akismet检查（如果已配置）
        if self.akismet_enabled and self.akismet_api_key:
            akismet_result = await self._check_with_akismet(
                content, author_name, author_email, author_url, ip_address, user_agent
            )
            if akismet_result.get("is_spam", False):
                spam_score += akismet_result.get("confidence", 0.5)
                reasons.append(f"Akismet检测为垃圾评论（置信度: {akismet_result.get('confidence', 0.5):.2f}）")
        
        # 确定最终结果
        is_spam = spam_score >= 0.5  # 降低垃圾阈值，使更多明显垃圾内容被拦截
        action = "block" if spam_score >= 0.8 else ("moderate" if spam_score >= 0.5 else "allow")

        return SpamCheckResult(
            is_spam=is_spam,
            confidence=min(spam_score, 1.0),
            reason="; ".join(reasons) if reasons else "通过内容分析",
            action=action,
            layer=2
        )
    
    def _has_simple_repetitive_content(self, content: str) -> bool:
        """检查是否包含重复内容（简化版，低资源消耗）"""
        if len(content) < 10:
            return False
            
        # 只检查明显的重复字符模式（连续5个相同字符）
        for i in range(len(content) - 4):
            if content[i] == content[i+1] == content[i+2] == content[i+3] == content[i+4]:
                return True
        
        return False
    
    def _is_valid_email_format(self, email: str) -> bool:
        """简化的邮箱格式检查（低资源消耗）"""
        # 简化版本，避免复杂正则表达式
        if not email or '@' not in email:
            return False
        
        parts = email.split('@')
        if len(parts) != 2:
            return False
            
        local, domain = parts
        return len(local) > 0 and len(domain) > 3 and '.' in domain
    
    async def _check_with_akismet(self,
                                 content: str,
                                 author_name: str,
                                 author_email: str,
                                 author_url: str,
                                 ip_address: str,
                                 user_agent: str) -> Dict[str, Any]:
        """
        使用Akismet API检查评论
        
        Args:
            content: 评论内容
            author_name: 作者姓名
            author_email: 作者邮箱
            author_url: 作者网址
            ip_address: IP地址
            user_agent: 用户代理
            
        Returns:
            Dict: Akismet检测结果
        """
        try:
            # 获取站点URL设置
            site_url = self._get_setting_str("site_url", "http://localhost")
            
            # 创建Akismet客户端
            akismet_client = get_akismet_client(self.akismet_api_key, site_url)
            if not akismet_client:
                return {"is_spam": False, "confidence": 0.0}
            
            # 调用Akismet API
            result = await akismet_client.check_comment(
                content=content,
                author_name=author_name,
                author_email=author_email,
                author_url=author_url or "",
                ip_address=ip_address,
                user_agent=user_agent
            )
            
            return result
            
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"Akismet检查出错: {e}")
            # 出错时返回保守结果
            return {"is_spam": False, "confidence": 0.0}
    

    def generate_honeypot_field_name(self) -> str:
        """生成蜜罐字段名称"""
        timestamp = str(int(time.time()))
        return hashlib.md5(f"honeypot_{timestamp}".encode()).hexdigest()[:8]

    def generate_form_timestamp_token(self) -> str:
        """生成签名时间戳令牌，防止客户端伪造提交时间。"""
        timestamp = str(int(time.time()))
        payload = f"{timestamp}:{self._FORM_TS_PURPOSE}".encode("utf-8")
        signature = hmac.new(
            settings.SECRET_KEY.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).hexdigest()
        return f"{timestamp}.{signature}"

    def parse_form_timestamp(self, token: str) -> Optional[float]:
        """
        解析表单时间戳令牌。

        支持格式：
        1. 新版签名令牌：<timestamp>.<hmac_sha256>
        2. 旧版明文时间戳（向后兼容）
        """
        value = str(token or "").strip()
        if not value:
            return None

        # 旧版：纯时间戳（兼容历史页面）
        if re.fullmatch(r"\d+(\.\d+)?", value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        # 新版：签名令牌
        if "." in value:
            ts_part, signature = value.split(".", 1)
            if ts_part.isdigit() and signature:
                payload = f"{ts_part}:{self._FORM_TS_PURPOSE}".encode("utf-8")
                expected = hmac.new(
                    settings.SECRET_KEY.encode("utf-8"),
                    payload,
                    hashlib.sha256,
                ).hexdigest()
                if hmac.compare_digest(signature, expected):
                    return float(ts_part)
                return None

        return None

    def generate_form_token(self) -> str:
        """生成表单令牌"""
        timestamp = str(time.time())
        return hashlib.md5(f"form_token_{timestamp}".encode()).hexdigest()


# 反垃圾设置快照缓存：按数据库维度缓存，避免每次渲染评论表单都重复查库，
# 同时不再把某个请求的 Session 长期挂在全局实例上（原先会导致设置变更后不生效、
# 以及跨请求复用已关闭会话的问题）。
_ANTI_SPAM_SETTINGS_TTL_SECONDS = 15.0
_ANTI_SPAM_SETTINGS_CACHE: Dict[str, Tuple[float, Dict[str, Any]]] = {}
_ANTI_SPAM_SETTINGS_LOCK = threading.Lock()


def _anti_spam_cache_key(db: Session) -> str:
    """按数据库连接串区分缓存，避免不同租户/测试库互相污染。"""
    try:
        return str(db.get_bind().url)
    except Exception:
        return "default"


def clear_anti_spam_settings_cache() -> None:
    """清空反垃圾设置缓存（后台保存设置、初始化默认设置时调用）。"""
    with _ANTI_SPAM_SETTINGS_LOCK:
        _ANTI_SPAM_SETTINGS_CACHE.clear()


def _load_cached_settings(db: Session) -> Dict[str, Any]:
    cache_key = _anti_spam_cache_key(db)
    now_ts = time.monotonic()
    with _ANTI_SPAM_SETTINGS_LOCK:
        cached = _ANTI_SPAM_SETTINGS_CACHE.get(cache_key)
        if cached and now_ts - cached[0] < _ANTI_SPAM_SETTINGS_TTL_SECONDS:
            return dict(cached[1])

    reader = AntiSpamEngine.__new__(AntiSpamEngine)
    reader.db = db
    values = reader.read_settings_from_db()

    with _ANTI_SPAM_SETTINGS_LOCK:
        _ANTI_SPAM_SETTINGS_CACHE[cache_key] = (now_ts, values)
    return dict(values)


def get_anti_spam_engine(db: Session) -> AntiSpamEngine:
    """获取反垃圾引擎实例（使用短 TTL 的设置快照，绑定当前请求的会话）"""
    engine = AntiSpamEngine.__new__(AntiSpamEngine)
    engine.db = db
    engine.apply_settings(_load_cached_settings(db))
    return engine
