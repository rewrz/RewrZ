"""
数据导入导出管理器

提供完整的数据导入导出功能，包括：
1. RewrZ格式数据导出（JSON格式）
2. WordPress WXR格式导入支持
3. 数据库备份和恢复
4. 媒体文件打包和导入
"""

import os
import json
import xml.etree.ElementTree as ET
import zipfile
import shutil
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import setting as crud_setting
from ..crud import media as crud_media
from ..crud import user as crud_user
from ..models import Post, Category, Tag, Media
from ..schemas import PostCreate, CategoryCreate, TagCreate
import re


class DataExportManager:
    """数据导出管理器"""
    
    def __init__(self, db: Session):
        self.db = db
        
    def export_all_data(self) -> Dict[str, Any]:
        """
        导出所有数据为RewrZ JSON格式
        
        Returns:
            包含所有数据的字典
        """
        export_data = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "blog_info": self._export_blog_info(),
            "posts": self._export_posts(),
            "categories": self._export_categories(),
            "tags": self._export_tags(),
            "media": self._export_media(),
            "settings": self._export_settings()
        }
        
        return export_data
    
    def _export_blog_info(self) -> Dict[str, Any]:
        """导出博客基本信息"""
        site_title = crud_setting.get_setting(self.db, "site_title")
        tagline = crud_setting.get_setting(self.db, "tagline")
        site_url = crud_setting.get_setting(self.db, "site_url")
        
        return {
            "title": site_title.value.get("value") if site_title else "RewrZ Blog",
            "tagline": tagline.value.get("value") if tagline else "A Personal Blog",
            "url": site_url.value.get("value") if site_url else "",
            "export_date": datetime.now().isoformat()
        }
    
    def _export_posts(self) -> List[Dict[str, Any]]:
        """导出所有文章"""
        posts = crud_post.get_all_posts(self.db)
        exported_posts = []
        
        for post in posts:
            post_data = {
                "id": post.id,
                "title": post.title,
                "slug": post.slug,
                "content_markdown": post.content_markdown,
                "content_html": post.content_html,
                "excerpt": post.excerpt,
                "featured_image_url": post.featured_image_url,
                "post_type": post.post_type,
                "status": post.status,
                "visibility": post.visibility,
                "password": post.password,
                "allow_comments": post.allow_comments,
                "license_type": getattr(post, 'license_type', 'cc_by_nc_sa_4'),
                "created_at": post.created_at.isoformat() if post.created_at else None,
                "published_at": post.published_at.isoformat() if post.published_at else None,
                "updated_at": post.updated_at.isoformat() if post.updated_at else None,
                "author": post.author.username if post.author else None,
                "categories": [cat.name for cat in post.categories] if post.categories else [],
                "tags": [tag.name for tag in post.tags] if post.tags else [],
                "formats": [fmt.name for fmt in post.formats] if post.formats else [],
                "version_snapshots": post.version_snapshots or []
            }
            exported_posts.append(post_data)
        
        return exported_posts
    
    def _export_categories(self) -> List[Dict[str, Any]]:
        """导出所有分类"""
        categories = crud_category.get_all_categories(self.db)
        exported_categories = []
        
        for category in categories:
            category_data = {
                "id": category.id,
                "name": category.name,
                "slug": category.slug,
                "parent_id": category.parent_id
            }
            exported_categories.append(category_data)
        
        return exported_categories
    
    def _export_tags(self) -> List[Dict[str, Any]]:
        """导出所有标签"""
        tags = crud_tag.get_all_tags(self.db)
        exported_tags = []
        
        for tag in tags:
            tag_data = {
                "id": tag.id,
                "name": tag.name,
                "slug": tag.slug
            }
            exported_tags.append(tag_data)
        
        return exported_tags
    
    def _export_media(self) -> List[Dict[str, Any]]:
        """导出媒体文件信息"""
        media_items = crud_media.get_all_media(self.db)
        exported_media = []
        
        for media in media_items:
            media_data = {
                "id": media.id,
                "filename": media.filename,
                "original_filename": media.original_filename,
                "filepath": media.filepath,
                "file_type": media.file_type,
                "file_size": media.file_size,
                "mime_type": media.mime_type,
                "title": media.title,
                "alt_text": media.alt_text,
                "description": media.description,
                "metadata": media.metadata,
                "created_at": media.created_at.isoformat() if media.created_at else None,
                "uploaded_by": media.uploaded_by.username if media.uploaded_by else None
            }
            exported_media.append(media_data)
        
        return exported_media
    
    def _export_settings(self) -> List[Dict[str, Any]]:
        """导出系统设置"""
        # 获取所有设置，但排除敏感信息
        settings = crud_setting.get_all_settings(self.db)
        exported_settings = []
        
        # 敏感设置不导出
        sensitive_keys = {'admin_password', 'secret_key', 'jwt_secret', 'database_url'}
        
        for setting in settings:
            if setting.key.lower() not in sensitive_keys:
                setting_data = {
                    "key": setting.key,
                    "value": setting.value,
                    "description": setting.description,
                    "category": setting.category,
                    "type": setting.type
                }
                exported_settings.append(setting_data)
        
        return exported_settings
    
    def create_backup_package(self, export_path: str) -> str:
        """
        创建完整的备份包（包含数据和媒体文件）
        
        Args:
            export_path: 导出路径
            
        Returns:
            备份文件路径
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"rewrz_backup_{timestamp}.zip"
        backup_path = os.path.join(export_path, backup_filename)
        
        # 创建临时目录
        temp_dir = os.path.join(export_path, f"temp_backup_{timestamp}")
        os.makedirs(temp_dir, exist_ok=True)
        
        try:
            # 导出数据到JSON文件
            data = self.export_all_data()
            data_file = os.path.join(temp_dir, "rewrz_data.json")
            with open(data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 复制媒体文件
            media_dir = "media_uploads"
            if os.path.exists(media_dir):
                temp_media_dir = os.path.join(temp_dir, "media")
                shutil.copytree(media_dir, temp_media_dir)
            
            # 创建ZIP文件
            with zipfile.ZipFile(backup_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(temp_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arc_name = os.path.relpath(file_path, temp_dir)
                        zipf.write(file_path, arc_name)
            
        finally:
            # 清理临时目录
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
        
        return backup_path


class WordPressImporter:
    """WordPress WXR文件导入器"""
    
    def __init__(self, db: Session):
        self.db = db
        self.namespaces = {
            'wp': 'http://wordpress.org/export/1.2/',
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'excerpt': 'http://wordpress.org/export/1.2/excerpt/'
        }
    
    def import_from_wxr(self, wxr_file_path: str) -> Dict[str, Any]:
        """
        从WordPress WXR文件导入数据
        
        Args:
            wxr_file_path: WXR文件路径
            
        Returns:
            导入结果统计
        """
        try:
            tree = ET.parse(wxr_file_path)
            root = tree.getroot()
            
            # 导入统计
            stats = {
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "errors": []
            }
            
            # 导入分类
            self._import_wp_categories(root, stats)
            
            # 导入标签
            self._import_wp_tags(root, stats)
            
            # 导入文章
            self._import_wp_posts(root, stats)
            
            return stats
            
        except Exception as e:
            return {
                "error": f"导入失败: {str(e)}",
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "errors": [str(e)]
            }
    
    def _import_wp_categories(self, root: ET.Element, stats: Dict[str, Any]):
        """导入WordPress分类"""
        categories = root.findall('.//wp:category', self.namespaces)
        
        for cat_elem in categories:
            try:
                cat_nicename = cat_elem.find('wp:category_nicename', self.namespaces)
                cat_name = cat_elem.find('wp:cat_name', self.namespaces)
                
                if cat_nicename is not None and cat_name is not None:
                    # 检查分类是否已存在
                    existing_cat = crud_category.get_category_by_slug(self.db, cat_nicename.text)
                    if not existing_cat:
                        category_data = CategoryCreate(
                            name=cat_name.text,
                            slug=cat_nicename.text
                        )
                        crud_category.create_category(self.db, category_data)
                        stats["categories_imported"] += 1
                        
            except Exception as e:
                stats["errors"].append(f"导入分类失败: {str(e)}")
    
    def _import_wp_tags(self, root: ET.Element, stats: Dict[str, Any]):
        """导入WordPress标签"""
        tags = root.findall('.//wp:tag', self.namespaces)
        
        for tag_elem in tags:
            try:
                tag_slug = tag_elem.find('wp:tag_slug', self.namespaces)
                tag_name = tag_elem.find('wp:tag_name', self.namespaces)
                
                if tag_slug is not None and tag_name is not None:
                    # 检查标签是否已存在
                    existing_tag = crud_tag.get_tag_by_slug(self.db, tag_slug.text)
                    if not existing_tag:
                        tag_data = TagCreate(
                            name=tag_name.text,
                            slug=tag_slug.text
                        )
                        crud_tag.create_tag(self.db, tag_data)
                        stats["tags_imported"] += 1
                        
            except Exception as e:
                stats["errors"].append(f"导入标签失败: {str(e)}")
    
    def _import_wp_posts(self, root: ET.Element, stats: Dict[str, Any]):
        """导入WordPress文章"""
        items = root.findall('.//item')
        
        for item in items:
            try:
                # 只导入文章类型
                post_type = item.find('wp:post_type', self.namespaces)
                if post_type is None or post_type.text != 'post':
                    continue
                
                # 只导入已发布的文章
                status = item.find('wp:status', self.namespaces)
                if status is None or status.text != 'publish':
                    continue
                
                title = item.find('title')
                content = item.find('content:encoded', self.namespaces)
                pub_date = item.find('pubDate')
                link = item.find('link')
                
                if title is not None and content is not None:
                    # 从链接中提取slug
                    slug = self._extract_slug_from_url(link.text if link is not None else "")
                    if not slug:
                        slug = self._generate_slug_from_title(title.text)
                    
                    # 检查文章是否已存在
                    existing_post = crud_post.get_post_by_slug(self.db, slug)
                    if existing_post:
                        slug = f"{slug}-imported"
                    
                    # 转换内容格式（简单的HTML到Markdown转换）
                    markdown_content = self._html_to_markdown(content.text)
                    
                    # 创建文章
                    post_data = PostCreate(
                        title=title.text,
                        slug=slug,
                        content_markdown=markdown_content,
                        content_html=content.text,
                        excerpt=self._extract_excerpt(content.text),
                        status="published",
                        visibility="public",
                        allow_comments=True,
                        license_type="cc_by_nc_sa_4",
                        published_at=self._parse_wp_date(pub_date.text if pub_date is not None else None)
                    )
                    
                    # 获取默认用户作为作者
                    default_user = crud_user.get_user_by_id(self.db, 1)  # 假设ID为1的是管理员
                    if default_user:
                        new_post = crud_post.create_post(self.db, post_data, default_user.id)
                        
                        # 关联分类和标签
                        self._associate_wp_taxonomies(item, new_post)
                        
                        stats["posts_imported"] += 1
                        
            except Exception as e:
                stats["errors"].append(f"导入文章失败: {str(e)}")
    
    def _extract_slug_from_url(self, url: str) -> str:
        """从URL中提取slug"""
        if not url:
            return ""
        
        # 移除域名和协议
        path = url.split('/')[-1]
        # 移除文件扩展名
        slug = path.split('.')[0]
        # 清理slug
        slug = re.sub(r'[^\w\-]', '', slug)
        return slug.lower()
    
    def _generate_slug_from_title(self, title: str) -> str:
        """从标题生成slug"""
        if not title:
            return "untitled"
        
        # 转换为小写并替换空格和特殊字符
        slug = re.sub(r'[^\w\s\-]', '', title.lower())
        slug = re.sub(r'[\s\-]+', '-', slug)
        slug = slug.strip('-')
        
        return slug or "untitled"
    
    def _html_to_markdown(self, html_content: str) -> str:
        """简单的HTML到Markdown转换"""
        if not html_content:
            return ""
        
        # 这是一个简化的转换，实际项目中可能需要使用专门的库如html2text
        content = html_content
        
        # 基本的HTML标签转换
        content = re.sub(r'<h1[^>]*>(.*?)</h1>', r'# \1', content, flags=re.DOTALL)
        content = re.sub(r'<h2[^>]*>(.*?)</h2>', r'## \1', content, flags=re.DOTALL)
        content = re.sub(r'<h3[^>]*>(.*?)</h3>', r'### \1', content, flags=re.DOTALL)
        content = re.sub(r'<h4[^>]*>(.*?)</h4>', r'#### \1', content, flags=re.DOTALL)
        content = re.sub(r'<p[^>]*>(.*?)</p>', r'\1\n\n', content, flags=re.DOTALL)
        content = re.sub(r'<br[^>]*/?>', '\n', content)
        content = re.sub(r'<strong[^>]*>(.*?)</strong>', r'**\1**', content, flags=re.DOTALL)
        content = re.sub(r'<b[^>]*>(.*?)</b>', r'**\1**', content, flags=re.DOTALL)
        content = re.sub(r'<em[^>]*>(.*?)</em>', r'*\1*', content, flags=re.DOTALL)
        content = re.sub(r'<i[^>]*>(.*?)</i>', r'*\1*', content, flags=re.DOTALL)
        content = re.sub(r'<a[^>]*href=["\']([^"\']*)["\'][^>]*>(.*?)</a>', r'[\2](\1)', content, flags=re.DOTALL)
        
        # 移除其他HTML标签
        content = re.sub(r'<[^>]+>', '', content)
        
        # 清理多余的空行
        content = re.sub(r'\n\n+', '\n\n', content)
        
        return content.strip()
    
    def _extract_excerpt(self, content: str, max_length: int = 120) -> str:
        """从内容中提取摘要"""
        if not content:
            return ""
        
        # 移除HTML标签
        text = re.sub(r'<[^>]+>', '', content)
        # 移除多余空白
        text = re.sub(r'\s+', ' ', text).strip()
        
        if len(text) <= max_length:
            return text
        
        # 在单词边界截断
        truncated = text[:max_length]
        last_space = truncated.rfind(' ')
        if last_space > 0:
            truncated = truncated[:last_space]
        
        return truncated + "..."
    
    def _parse_wp_date(self, date_str: str) -> Optional[datetime]:
        """解析WordPress日期格式"""
        if not date_str:
            return None
        
        try:
            # WordPress日期格式示例: "Wed, 09 Jun 2021 15:35:35 +0000"
            from email.utils import parsedate_to_datetime
            return parsedate_to_datetime(date_str)
        except:
            return None
    
    def _associate_wp_taxonomies(self, item: ET.Element, post: Post):
        """关联WordPress的分类和标签到文章"""
        try:
            # 关联分类
            categories = item.findall('category[@domain="category"]')
            for cat_elem in categories:
                if cat_elem.text:
                    category = crud_category.get_category_by_name(self.db, cat_elem.text)
                    if category:
                        post.categories.append(category)
            
            # 关联标签
            tags = item.findall('category[@domain="post_tag"]')
            for tag_elem in tags:
                if tag_elem.text:
                    tag = crud_tag.get_tag_by_name(self.db, tag_elem.text)
                    if tag:
                        post.tags.append(tag)
            
            self.db.commit()
            
        except Exception as e:
            print(f"关联分类标签失败: {str(e)}")


class RewrZImporter:
    """RewrZ格式数据导入器"""
    
    def __init__(self, db: Session):
        self.db = db
    
    def import_from_json(self, json_file_path: str) -> Dict[str, Any]:
        """
        从RewrZ JSON文件导入数据
        
        Args:
            json_file_path: JSON文件路径
            
        Returns:
            导入结果统计
        """
        try:
            with open(json_file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            stats = {
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "settings_imported": 0,
                "errors": []
            }
            
            # 导入分类
            if "categories" in data:
                self._import_categories(data["categories"], stats)
            
            # 导入标签
            if "tags" in data:
                self._import_tags(data["tags"], stats)
            
            # 导入设置
            if "settings" in data:
                self._import_settings(data["settings"], stats)
            
            # 导入文章
            if "posts" in data:
                self._import_posts(data["posts"], stats)
            
            return stats
            
        except Exception as e:
            return {
                "error": f"导入失败: {str(e)}",
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "settings_imported": 0,
                "errors": [str(e)]
            }
    
    def _import_categories(self, categories: List[Dict], stats: Dict[str, Any]):
        """导入分类"""
        for cat_data in categories:
            try:
                existing_cat = crud_category.get_category_by_slug(self.db, cat_data["slug"])
                if not existing_cat:
                    category_data = CategoryCreate(
                        name=cat_data["name"],
                        slug=cat_data["slug"]
                    )
                    crud_category.create_category(self.db, category_data)
                    stats["categories_imported"] += 1
            except Exception as e:
                stats["errors"].append(f"导入分类失败: {str(e)}")
    
    def _import_tags(self, tags: List[Dict], stats: Dict[str, Any]):
        """导入标签"""
        for tag_data in tags:
            try:
                existing_tag = crud_tag.get_tag_by_slug(self.db, tag_data["slug"])
                if not existing_tag:
                    tag_create = TagCreate(
                        name=tag_data["name"],
                        slug=tag_data["slug"]
                    )
                    crud_tag.create_tag(self.db, tag_create)
                    stats["tags_imported"] += 1
            except Exception as e:
                stats["errors"].append(f"导入标签失败: {str(e)}")
    
    def _import_settings(self, settings: List[Dict], stats: Dict[str, Any]):
        """导入设置"""
        for setting_data in settings:
            try:
                existing_setting = crud_setting.get_setting(self.db, setting_data["key"])
                if not existing_setting:
                    from ..schemas import SettingCreate
                    setting_create = SettingCreate(
                        key=setting_data["key"],
                        value=setting_data["value"],
                        description=setting_data.get("description", ""),
                        category=setting_data.get("category", "general"),
                        type=setting_data.get("type", "string")
                    )
                    crud_setting.create_setting(self.db, setting_create)
                    stats["settings_imported"] += 1
            except Exception as e:
                stats["errors"].append(f"导入设置失败: {str(e)}")
    
    def _import_posts(self, posts: List[Dict], stats: Dict[str, Any]):
        """导入文章"""
        for post_data in posts:
            try:
                existing_post = crud_post.get_post_by_slug(self.db, post_data["slug"])
                if not existing_post:
                    # 解析日期
                    published_at = None
                    if post_data.get("published_at"):
                        published_at = datetime.fromisoformat(post_data["published_at"].replace('Z', '+00:00'))
                    
                    post_create = PostCreate(
                        title=post_data["title"],
                        slug=post_data["slug"],
                        content_markdown=post_data.get("content_markdown", ""),
                        content_html=post_data.get("content_html", ""),
                        excerpt=post_data.get("excerpt", ""),
                        featured_image_url=post_data.get("featured_image_url"),
                        post_type=post_data.get("post_type", "post"),
                        status=post_data.get("status", "published"),
                        visibility=post_data.get("visibility", "public"),
                        password=post_data.get("password"),
                        allow_comments=post_data.get("allow_comments", True),
                        license_type=post_data.get("license_type", "cc_by_nc_sa_4"),
                        published_at=published_at
                    )
                    
                    # 获取默认用户作为作者
                    default_user = crud_user.get_user_by_id(self.db, 1)
                    if default_user:
                        new_post = crud_post.create_post(self.db, post_create, default_user.id)
                        
                        # 关联分类和标签
                        if post_data.get("categories"):
                            for cat_name in post_data["categories"]:
                                category = crud_category.get_category_by_name(self.db, cat_name)
                                if category:
                                    new_post.categories.append(category)
                        
                        if post_data.get("tags"):
                            for tag_name in post_data["tags"]:
                                tag = crud_tag.get_tag_by_name(self.db, tag_name)
                                if tag:
                                    new_post.tags.append(tag)
                        
                        self.db.commit()
                        stats["posts_imported"] += 1
                        
            except Exception as e:
                stats["errors"].append(f"导入文章失败: {str(e)}")


# 便捷函数
def get_data_export_manager(db: Session) -> DataExportManager:
    """获取数据导出管理器实例"""
    return DataExportManager(db)


def get_wordpress_importer(db: Session) -> WordPressImporter:
    """获取WordPress导入器实例"""
    return WordPressImporter(db)


def get_rewrz_importer(db: Session) -> RewrZImporter:
    """获取RewrZ导入器实例"""
    return RewrZImporter(db)