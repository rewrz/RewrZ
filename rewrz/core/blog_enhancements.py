"""
现代化博客功能增强模块

提供现代化博客常用功能：
1. 阅读时间估算
2. 相关文章推荐
3. 文章统计信息
4. 阅读进度条支持
"""

import re
import math
import hashlib
import time
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func
from ..models.post import Post
from ..models.tag import Tag
from ..models.category import Category
from .database import get_db
from ..crud import setting as setting_crud


class BlogEnhancementEngine:
    """博客功能增强引擎"""
    
    def __init__(self):
        # 中文阅读速度约为 250-300 字/分钟
        # 英文阅读速度约为 200-250 词/分钟
        self.chinese_reading_speed = 275  # 字/分钟
        self.english_reading_speed = 225  # 词/分钟
        # 缓存过期时间（秒）
        self.cache_ttl = 3600  # 1小时
        # 运行时缓存（支持按键自定义TTL）
        self._runtime_cache: Dict[str, Dict[str, Any]] = {}
        # 性能配置缓存，降低每次过滤器调用的数据库访问
        self._perf_config_cache: Dict[str, Any] = {}
        self._perf_config_expires_at = 0.0

    def _cache_get(self, key: str) -> Optional[Any]:
        cached = self._runtime_cache.get(key)
        if not cached:
            return None
        if cached["expires_at"] <= time.time():
            self._runtime_cache.pop(key, None)
            return None
        return cached["value"]

    def _cache_set(self, key: str, value: Any, ttl: int) -> None:
        safe_ttl = max(30, int(ttl))
        self._runtime_cache[key] = {
            "value": value,
            "expires_at": time.time() + safe_ttl,
        }

    def _load_performance_config(self) -> Dict[str, Any]:
        """
        读取性能配置（来自 error_handling_config），并进行短期缓存。
        """
        now = time.time()
        if self._perf_config_cache and now < self._perf_config_expires_at:
            return self._perf_config_cache

        config = {
            "enable_performance_optimization": True,
            "related_posts_cache_strategy": "aggressive",
            "reading_time_cache_duration": 7200,
        }

        db_gen = None
        try:
            db_gen = get_db()
            db = next(db_gen)
            if db is None:
                self._perf_config_cache = config
                self._perf_config_expires_at = now + 60
                return config

            setting = setting_crud.get_setting(db, key="error_handling_config")
            if setting and setting.value:
                saved = setting.value.get("value", {})
                if isinstance(saved, dict):
                    config["enable_performance_optimization"] = bool(saved.get("enable_performance_optimization", True))
                    strategy = saved.get("related_posts_cache_strategy", "aggressive")
                    if strategy in {"aggressive", "moderate", "conservative"}:
                        config["related_posts_cache_strategy"] = strategy
                    try:
                        duration = int(saved.get("reading_time_cache_duration", 7200))
                        config["reading_time_cache_duration"] = max(60, min(duration, 86400))
                    except (TypeError, ValueError):
                        config["reading_time_cache_duration"] = 7200
        except Exception:
            pass
        finally:
            if db_gen is not None:
                try:
                    db_gen.close()
                except Exception:
                    pass

        self._perf_config_cache = config
        self._perf_config_expires_at = now + 60
        return config
    
    def calculate_reading_time(self, content_markdown: str, content_html: str = None) -> Dict[str, Any]:
        """
        计算文章阅读时间（带缓存支持）
        
        Args:
            content_markdown: Markdown格式内容
            content_html: HTML格式内容（可选）
            
        Returns:
            Dict: 包含阅读时间信息的字典
        """
        # 生成内容的哈希值作为缓存键
        content_hash = hashlib.md5(content_markdown.encode('utf-8')).hexdigest()
        cache_key = f"reading_time_{content_hash}"
        performance_config = self._load_performance_config()
        enable_perf_optimization = performance_config.get("enable_performance_optimization", True)
        reading_cache_ttl = performance_config.get("reading_time_cache_duration", self.cache_ttl)
        
        # 尝试从缓存获取结果
        if enable_perf_optimization:
            cached_result = self._cache_get(cache_key)
            if cached_result:
                return cached_result
        
        # 清理markdown内容，移除格式标记
        clean_content = self._clean_markdown_content(content_markdown)
        
        # 统计中文字符数
        chinese_chars = len(re.findall(r'[\u4e00-\u9fff]', clean_content))
        
        # 统计英文单词数
        english_words = len(re.findall(r'\b[a-zA-Z]+\b', clean_content))
        
        # 统计数字
        numbers = len(re.findall(r'\b\d+\b', clean_content))
        
        # 计算阅读时间（分钟）
        chinese_time = chinese_chars / self.chinese_reading_speed
        english_time = english_words / self.english_reading_speed
        total_time = chinese_time + english_time
        
        # 至少1分钟
        if total_time < 1:
            total_time = 1
        
        result = {
            'reading_time_minutes': math.ceil(total_time),
            'word_count': chinese_chars + english_words,
            'chinese_chars': chinese_chars,
            'english_words': english_words,
            'character_count': len(clean_content),
            'estimated_reading_speed': '中等' if total_time <= 5 else ('较慢' if total_time <= 10 else '较长')
        }
        
        # 将结果存入缓存
        if enable_perf_optimization:
            self._cache_set(cache_key, result, reading_cache_ttl)
        
        return result
    
    def _clean_markdown_content(self, content: str) -> str:
        """清理Markdown内容，移除格式标记"""
        if not content:
            return ""
        
        # 移除代码块
        content = re.sub(r'```[\s\S]*?```', '', content)
        content = re.sub(r'`[^`]*`', '', content)
        
        # 移除链接，保留文本
        content = re.sub(r'\[([^\]]*)\]\([^)]*\)', r'\1', content)
        
        # 移除图片
        content = re.sub(r'!\[([^\]]*)\]\([^)]*\)', '', content)
        
        # 移除标题标记
        content = re.sub(r'^#{1,6}\s+', '', content, flags=re.MULTILINE)
        
        # 移除强调标记
        content = re.sub(r'\*\*([^*]*)\*\*', r'\1', content)
        content = re.sub(r'\*([^*]*)\*', r'\1', content)
        content = re.sub(r'__([^_]*)__', r'\1', content)
        content = re.sub(r'_([^_]*)_', r'\1', content)
        
        # 移除列表标记
        content = re.sub(r'^\s*[-*+]\s+', '', content, flags=re.MULTILINE)
        content = re.sub(r'^\s*\d+\.\s+', '', content, flags=re.MULTILINE)
        
        # 移除引用标记
        content = re.sub(r'^>\s+', '', content, flags=re.MULTILINE)
        
        # 移除多余空白
        content = re.sub(r'\s+', ' ', content)
        
        return content.strip()
    
    def get_related_posts(self, 
                         db: Session, 
                         current_post: Post, 
                         limit: int = 5) -> List[Post]:
        """
        获取相关文章推荐（使用缓存友好的算法）
        
        Args:
            db: 数据库会话
            current_post: 当前文章
            limit: 返回文章数量限制
            
        Returns:
            List[Post]: 相关文章列表
        """
        # 生成缓存键
        cache_key = f"related_posts_{current_post.id}_{limit}"
        performance_config = self._load_performance_config()
        enable_perf_optimization = performance_config.get("enable_performance_optimization", True)
        strategy = performance_config.get("related_posts_cache_strategy", "aggressive")
        if not enable_perf_optimization:
            strategy = "conservative"
        strategy_multiplier = {
            "aggressive": 3,
            "moderate": 2,
            "conservative": 1,
        }.get(strategy, 2)
        related_cache_ttl = {
            "aggressive": 7200,
            "moderate": 3600,
            "conservative": 900,
        }.get(strategy, 3600)
        
        # 尝试从缓存获取结果
        if enable_perf_optimization:
            cached_result = self._cache_get(cache_key)
            if cached_result:
                # 从缓存中获取文章ID列表，然后查询完整文章对象
                post_ids = cached_result
                if post_ids:
                    from sqlalchemy import select
                    related_posts = db.execute(
                        select(Post)
                        .filter(Post.id.in_(post_ids))
                        .filter(Post.status == "published")
                    ).scalars().all()
                    # 按缓存中的顺序排序
                    post_map = {post.id: post for post in related_posts}
                    return [post_map[post_id] for post_id in post_ids if post_id in post_map]
                return []
        
        related_posts = []
        
        # 策略1: 基于标签的相关性
        if current_post.tags:
            from sqlalchemy import select
            tag_ids = [tag.id for tag in current_post.tags]
            tag_related = db.execute(
                select(Post)
                .join(Post.tags)
                .filter(
                    and_(
                        Tag.id.in_(tag_ids),
                        Post.id != current_post.id,
                        Post.status == "published"
                    )
                )
                .limit(max(limit * strategy_multiplier, limit))
            ).scalars().all()
            related_posts.extend(tag_related)
        
        # 策略2: 基于分类的相关性
        if current_post.categories and len(related_posts) < limit:
            category_ids = [cat.id for cat in current_post.categories]
            category_related = db.execute(
                select(Post)
                .join(Post.categories)
                .filter(
                    and_(
                        Category.id.in_(category_ids),
                        Post.id != current_post.id,
                        Post.status == "published"
                    )
                )
                .limit(max(limit * strategy_multiplier, limit))
            ).scalars().all()
            
            # 添加不重复的文章
            for post in category_related:
                if post not in related_posts:
                    related_posts.append(post)
        
        # 策略3: 基于格式的相关性
        if current_post.formats and len(related_posts) < limit:
            format_ids = [fmt.id for fmt in current_post.formats]
            from sqlalchemy import select
            from ..models.format import Format
            
            format_related = db.execute(
                select(Post)
                .join(Post.formats)
                .filter(
                    and_(
                        Format.id.in_(format_ids),
                        Post.id != current_post.id,
                        Post.status == "published"
                    )
                )
                .limit(max(limit * strategy_multiplier, limit))
            ).scalars().all()
            
            # 添加不重复的文章
            for post in format_related:
                if post not in related_posts:
                    related_posts.append(post)
        
        # 策略4: 如果相关文章不足，添加最新文章
        if len(related_posts) < limit:
            recent_posts = db.execute(
                select(Post)
                .filter(
                    and_(
                        Post.id != current_post.id,
                        Post.status == "published"
                    )
                )
                .order_by(Post.published_at.desc())
                .limit(max(limit * strategy_multiplier, limit))
            ).scalars().all()
            
            # 添加不重复的文章
            for post in recent_posts:
                if post not in related_posts:
                    related_posts.append(post)
        
        # 按相关性和发布时间排序，并限制数量
        # 优先级：共同标签数 > 共同分类数 > 发布时间
        scored_posts = []
        for post in related_posts:
            score = 0
            
            # 计算标签重叠度
            if current_post.tags and post.tags:
                current_tag_ids = set(tag.id for tag in current_post.tags)
                post_tag_ids = set(tag.id for tag in post.tags)
                tag_overlap = len(current_tag_ids.intersection(post_tag_ids))
                score += tag_overlap * 3  # 标签权重更高
            
            # 计算分类重叠度
            if current_post.categories and post.categories:
                current_cat_ids = set(cat.id for cat in current_post.categories)
                post_cat_ids = set(cat.id for cat in post.categories)
                cat_overlap = len(current_cat_ids.intersection(post_cat_ids))
                score += cat_overlap * 2  # 分类权重中等
            
            # 计算格式重叠度
            if current_post.formats and post.formats:
                current_fmt_ids = set(fmt.id for fmt in current_post.formats)
                post_fmt_ids = set(fmt.id for fmt in post.formats)
                fmt_overlap = len(current_fmt_ids.intersection(post_fmt_ids))
                score += fmt_overlap * 1  # 格式权重较低
            
            scored_posts.append((post, score))
        
        # 按分数降序排序，相同分数按发布时间降序
        scored_posts.sort(key=lambda x: (x[1], x[0].published_at or x[0].created_at), reverse=True)
        
        # 获取前N篇文章
        result_posts = [post for post, score in scored_posts[:limit]]
        
        # 将文章ID列表存入缓存
        post_ids = [post.id for post in result_posts]
        if enable_perf_optimization:
            self._cache_set(cache_key, post_ids, related_cache_ttl)
        
        return result_posts
    
    def get_post_statistics(self, content_markdown: str, post: Post = None) -> Dict[str, Any]:
        """
        获取文章统计信息
        
        Args:
            content_markdown: Markdown内容
            post: 文章对象（可选）
            
        Returns:
            Dict: 统计信息
        """
        reading_info = self.calculate_reading_time(content_markdown)
        clean_content = self._clean_markdown_content(content_markdown)
        
        # 统计段落数
        paragraphs = len([p for p in clean_content.split('\n\n') if p.strip()])
        
        # 统计标题数量
        headers = len(re.findall(r'^#{1,6}\s+', content_markdown, flags=re.MULTILINE))
        
        # 统计链接数量
        links = len(re.findall(r'\[([^\]]*)\]\([^)]*\)', content_markdown))
        
        # 统计图片数量
        images = len(re.findall(r'!\[([^\]]*)\]\([^)]*\)', content_markdown))
        
        # 统计代码块数量
        code_blocks = len(re.findall(r'```[\s\S]*?```', content_markdown))
        inline_code = len(re.findall(r'`[^`]*`', content_markdown))
        
        stats = {
            **reading_info,
            'paragraph_count': paragraphs,
            'header_count': headers,
            'link_count': links,
            'image_count': images,
            'code_block_count': code_blocks,
            'inline_code_count': inline_code
        }
        
        # 如果提供了文章对象，添加额外统计
        if post:
            stats.update({
                'category_count': len(post.categories) if post.categories else 0,
                'tag_count': len(post.tags) if post.tags else 0,
                'format_count': len(post.formats) if post.formats else 0,
                'has_featured_image': bool(post.featured_image_url),
                'allows_comments': post.allow_comments,
                'post_type': post.post_type,
                'license_type': getattr(post, 'license_type', None)
            })
        
        return stats
    
    def get_reading_progress_config(self) -> Dict[str, Any]:
        """
        获取阅读进度条配置
        
        Returns:
            Dict: 阅读进度条配置
        """
        return {
            'enabled': True,
            'height': 3,
            'color': 'linear-gradient(90deg, #667eea, #764ba2)',
            'position': 'top',
            'animation_duration': 100,  # ms
            'performance_optimized': True  # 使用requestAnimationFrame优化性能
        }


# 全局实例
blog_enhancement = BlogEnhancementEngine()


def calculate_reading_time(content_markdown: str, content_html: str = None) -> Dict[str, Any]:
    """计算阅读时间的便捷函数"""
    return blog_enhancement.calculate_reading_time(content_markdown, content_html)


def get_related_posts(db: Session, current_post: Post, limit: int = 5) -> List[Post]:
    """获取相关文章的便捷函数"""
    return blog_enhancement.get_related_posts(db, current_post, limit)


def get_post_statistics(content_markdown: str, post: Post = None) -> Dict[str, Any]:
    """获取文章统计信息的便捷函数"""
    return blog_enhancement.get_post_statistics(content_markdown, post)


def get_reading_progress_config() -> Dict[str, Any]:
    """获取阅读进度条配置的便捷函数"""
    return blog_enhancement.get_reading_progress_config()
