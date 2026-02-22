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
import mimetypes
import hashlib
import xml.etree.ElementTree as ET
import zipfile
import shutil
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple, Callable
from urllib.parse import ParseResult, unquote, urljoin, urlparse
from urllib.request import Request as UrlRequest, urlopen
from sqlalchemy.orm import Session
from sqlalchemy import select
from bs4 import BeautifulSoup, Comment, NavigableString as BsNavigableString, Tag as BsTag
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..crud import setting as crud_setting
from ..crud import media as crud_media
from ..crud import user as crud_user
from ..models import Post, Category, Tag, Format, Media, User, Comment, Setting
from ..schemas import PostCreate, CategoryCreate, TagCreate, FormatCreate, SettingCreate
from .cache import clear_cache, cache_key_for_setting, cache
import re
from .template_context import DEFAULT_BASE_SETTINGS
from .content_intents import INTENT_NAME_MAP, normalize_intent_slug

DEFAULT_WP_IMPORT_OPTIONS = {
    "import_post_types": ["post", "page"],
    "import_comments": True,
    "import_views": True,
    "download_remote_media": False,
    "remote_media_path_strategy": "latest_month",
    "postmeta_whitelist": ["views", "post_views_count"],
    "post_type_format_map": {},
    "markdown_strategy": "html_to_markdown",
}


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
            "title": site_title.value.get("value") if site_title else DEFAULT_BASE_SETTINGS["site_title"],
            "tagline": tagline.value.get("value") if tagline else DEFAULT_BASE_SETTINGS["tagline"],
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
                "editor_mode": "html" if (post.content_html or "").strip() and not (post.content_markdown or "").strip() else "markdown",
                "excerpt": post.excerpt,
                "featured_image_url": post.featured_image_url,
                "post_type": post.post_type,
                "page_template": getattr(post, "page_template", "default"),
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
            # 兼容不同版本的媒体模型字段
            original_filename = getattr(media, "original_filename", None) or getattr(media, "filename", "")
            created_at = getattr(media, "created_at", None) or getattr(media, "uploaded_at", None)
            metadata_value = getattr(media, "metadata", None)
            if not isinstance(metadata_value, (dict, list, str, int, float, bool, type(None))):
                metadata_value = None

            file_size = getattr(media, "file_size", None)
            if file_size is None:
                filepath = getattr(media, "filepath", None)
                if filepath:
                    size_candidates = [
                        filepath,
                        os.path.join("media_uploads", filepath),
                    ]
                    for candidate in size_candidates:
                        if os.path.exists(candidate):
                            try:
                                file_size = os.path.getsize(candidate)
                            except OSError:
                                file_size = None
                            break

            media_data = {
                "id": getattr(media, "id", None),
                "filename": getattr(media, "filename", ""),
                "original_filename": original_filename,
                "filepath": getattr(media, "filepath", ""),
                "file_type": getattr(media, "file_type", ""),
                "file_size": file_size,
                "mime_type": getattr(media, "mime_type", ""),
                "title": getattr(media, "title", None),
                "alt_text": getattr(media, "alt_text", None),
                "description": getattr(media, "description", None),
                "metadata": metadata_value,
                "created_at": created_at.isoformat() if created_at else None,
                "uploaded_by": media.uploaded_by.username if getattr(media, "uploaded_by", None) else None
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
    
    def __init__(
        self,
        db: Session,
        options: Optional[Dict[str, Any]] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.db = db
        self.namespaces = {
            'wp': 'http://wordpress.org/export/1.2/',
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }
        self._author_cache: Dict[str, Optional[User]] = {}
        self.options = self._normalize_import_options(options)
        self.progress_callback = progress_callback
        self._deferred_setting_cache_keys: set[str] = set()
        self._attachment_url_map: Dict[int, str] = {}
        self._site_base_url: str = ""
        self._downloaded_media_url_map: Dict[str, str] = {}
        self._downloaded_media_count: int = 0

    def _report_progress(
        self,
        stage: str,
        message: str,
        current: Optional[int] = None,
        total: Optional[int] = None,
        extra: Optional[Dict[str, Any]] = None,
    ) -> None:
        if not self.progress_callback:
            return
        payload: Dict[str, Any] = {
            "stage": stage,
            "message": message,
        }
        if current is not None:
            payload["current"] = int(current)
        if total is not None:
            payload["total"] = int(total)
        if extra:
            payload.update(extra)
        try:
            self.progress_callback(payload)
        except Exception:
            # 进度回调失败不影响导入主流程
            pass

    def _normalize_import_options(self, options: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        merged = dict(DEFAULT_WP_IMPORT_OPTIONS)
        if isinstance(options, dict):
            merged.update(options)

        raw_types = merged.get("import_post_types", ["post", "page"])
        if isinstance(raw_types, str):
            raw_types = [part.strip() for part in raw_types.split(",")]
        import_post_types = [str(t).strip().lower() for t in raw_types if str(t).strip()]
        if not import_post_types:
            import_post_types = ["post", "page"]
        merged["import_post_types"] = sorted(set(import_post_types))

        raw_meta_keys = merged.get("postmeta_whitelist", ["views", "post_views_count"])
        if isinstance(raw_meta_keys, str):
            raw_meta_keys = [part.strip() for part in raw_meta_keys.split(",")]
        postmeta_whitelist = [str(k).strip() for k in raw_meta_keys if str(k).strip()]
        if not postmeta_whitelist:
            postmeta_whitelist = ["views", "post_views_count"]
        merged["postmeta_whitelist"] = sorted(set(postmeta_whitelist))

        merged["post_type_format_map"] = self._normalize_post_type_format_map(
            merged.get("post_type_format_map", {})
        )
        merged["import_comments"] = bool(merged.get("import_comments", True))
        merged["import_views"] = bool(merged.get("import_views", True))
        merged["download_remote_media"] = bool(merged.get("download_remote_media", False))
        strategy = str(merged.get("remote_media_path_strategy", "latest_month")).strip().lower() or "latest_month"
        if strategy not in {"latest_month", "preserve_relative_path"}:
            strategy = "latest_month"
        merged["remote_media_path_strategy"] = strategy
        merged["markdown_strategy"] = str(merged.get("markdown_strategy", "html_to_markdown")).strip() or "html_to_markdown"
        return merged
    
    def import_from_wxr(self, wxr_file_path: str) -> Dict[str, Any]:
        """
        从WordPress WXR文件导入数据
        
        Args:
            wxr_file_path: WXR文件路径
            
        Returns:
            导入结果统计
        """
        try:
            self._report_progress("prepare", "正在解析 WordPress 导出文件...")
            tree = ET.parse(wxr_file_path)
            root = tree.getroot()
            self._site_base_url = (
                (root.findtext("./channel/link") or "").strip()
                if root is not None
                else ""
            )
            self._attachment_url_map = self._build_wp_attachment_map(root)
            self._downloaded_media_url_map = {}
            self._downloaded_media_count = 0
            category_nodes = root.findall('.//wp:category', self.namespaces)
            tag_nodes = root.findall('.//wp:tag', self.namespaces)
            item_nodes = root.findall('.//item')
            
            # 导入统计
            stats = {
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "comments_imported": 0,
                "views_imported": 0,
                "media_downloaded": 0,
                "errors": []
            }
            
            self._report_progress(
                "prepare",
                "文件解析完成，开始导入数据。",
                extra={
                    "categories_total": len(category_nodes),
                    "tags_total": len(tag_nodes),
                    "items_total": len(item_nodes),
                    "attachments_total": len(self._attachment_url_map),
                },
            )

            # 导入分类
            self._import_wp_categories(root, stats, total=len(category_nodes))
            
            # 导入标签
            self._import_wp_tags(root, stats, total=len(tag_nodes))
            
            # 导入文章
            self._import_wp_posts(root, stats, total=len(item_nodes))
            stats["media_downloaded"] = self._downloaded_media_count
            self._clear_deferred_setting_cache()

            self._report_progress("completed", "WordPress 数据导入完成。", current=1, total=1, extra={"stats": stats})
            
            return stats
            
        except Exception as e:
            self._report_progress("failed", f"导入失败: {str(e)}")
            return {
                "error": f"导入失败: {str(e)}",
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "comments_imported": 0,
                "views_imported": 0,
                "media_downloaded": self._downloaded_media_count,
                "errors": [str(e)]
            }
    
    def _import_wp_categories(self, root: ET.Element, stats: Dict[str, Any], total: Optional[int] = None):
        """导入WordPress分类"""
        categories = root.findall('.//wp:category', self.namespaces)
        total_count = total if total is not None else len(categories)
        self._report_progress("categories", "正在导入分类...", current=0, total=total_count)

        for index, cat_elem in enumerate(categories, start=1):
            try:
                cat_nicename = cat_elem.find('wp:category_nicename', self.namespaces)
                cat_name = cat_elem.find('wp:cat_name', self.namespaces)
                
                if cat_nicename is not None and cat_name is not None:
                    slug = (cat_nicename.text or "").strip()
                    name = (cat_name.text or "").strip()
                    if not slug or not name:
                        continue
                    # 检查分类是否已存在
                    existing_cat = crud_category.get_category_by_slug(self.db, slug)
                    existing_cat_by_name = crud_category.get_category_by_name(self.db, name)
                    if not existing_cat and not existing_cat_by_name:
                        category_data = CategoryCreate(
                            name=name,
                            slug=slug
                        )
                        crud_category.create_category(self.db, category_data)
                        stats["categories_imported"] += 1
                        
            except Exception as e:
                self.db.rollback()
                stats["errors"].append(f"导入分类失败: {str(e)}")
            finally:
                self._report_progress(
                    "categories",
                    f"正在导入分类 ({index}/{total_count})",
                    current=index,
                    total=total_count,
                    extra={"categories_imported": stats["categories_imported"]},
                )
    
    def _import_wp_tags(self, root: ET.Element, stats: Dict[str, Any], total: Optional[int] = None):
        """导入WordPress标签"""
        tags = root.findall('.//wp:tag', self.namespaces)
        total_count = total if total is not None else len(tags)
        self._report_progress("tags", "正在导入标签...", current=0, total=total_count)

        for index, tag_elem in enumerate(tags, start=1):
            try:
                tag_slug = tag_elem.find('wp:tag_slug', self.namespaces)
                tag_name = tag_elem.find('wp:tag_name', self.namespaces)
                
                if tag_slug is not None and tag_name is not None:
                    slug = (tag_slug.text or "").strip()
                    name = (tag_name.text or "").strip()
                    if not slug or not name:
                        continue
                    # 检查标签是否已存在
                    existing_tag = crud_tag.get_tag_by_slug(self.db, slug)
                    existing_tag_by_name = crud_tag.get_tag_by_name(self.db, name)
                    if not existing_tag and not existing_tag_by_name:
                        tag_data = TagCreate(
                            name=name,
                            slug=slug
                        )
                        crud_tag.create_tag(self.db, tag_data)
                        stats["tags_imported"] += 1
                        
            except Exception as e:
                self.db.rollback()
                stats["errors"].append(f"导入标签失败: {str(e)}")
            finally:
                self._report_progress(
                    "tags",
                    f"正在导入标签 ({index}/{total_count})",
                    current=index,
                    total=total_count,
                    extra={"tags_imported": stats["tags_imported"]},
                )
    
    def _import_wp_posts(self, root: ET.Element, stats: Dict[str, Any], total: Optional[int] = None):
        """导入WordPress文章"""
        default_user: Optional[User] = None
        items = root.findall('.//item')
        total_count = total if total is not None else len(items)
        self._report_progress("posts", "正在导入文章...", current=0, total=total_count)

        for index, item in enumerate(items, start=1):
            try:
                # 按白名单导入指定 post_type，附件/修订等系统类型会被跳过。
                post_type = item.find('wp:post_type', self.namespaces)
                raw_post_type = (post_type.text or "").strip().lower() if post_type is not None else "post"
                if not raw_post_type:
                    raw_post_type = "post"

                if raw_post_type not in self.options.get("import_post_types", ["post", "page"]):
                    continue

                mapped_post_type = self._map_wp_post_type(raw_post_type)
                if mapped_post_type is None:
                    continue
                
                status = item.find('wp:status', self.namespaces)
                wp_status = (status.text or "").strip().lower() if status is not None else "publish"
                # 跳过已删除/继承项
                if wp_status in {"trash", "inherit"}:
                    continue
                
                title = item.find('title')
                content = item.find('content:encoded', self.namespaces)
                excerpt = item.find('excerpt:encoded', self.namespaces)
                description = item.find('description')
                pub_date = item.find('pubDate')
                link = item.find('link')
                creator = item.find('dc:creator', self.namespaces)
                post_name = item.find('wp:post_name', self.namespaces)
                comment_status = item.find('wp:comment_status', self.namespaces)
                post_password = item.find('wp:post_password', self.namespaces)
                post_date = item.find('wp:post_date', self.namespaces)
                post_date_gmt = item.find('wp:post_date_gmt', self.namespaces)
                post_modified = item.find('wp:post_modified', self.namespaces)
                post_modified_gmt = item.find('wp:post_modified_gmt', self.namespaces)
                
                if title is not None:
                    content_text = content.text if (content is not None and content.text is not None) else ""
                    # 优先使用WordPress保存的post_name作为slug，保持原始链接一致。
                    slug = self._normalize_imported_slug((post_name.text or "").strip()) if post_name is not None else ""
                    if not slug:
                        slug = self._extract_slug_from_url(link.text if link is not None else "")
                    if not slug:
                        slug = self._generate_slug_from_title(title.text)
                    
                    # 检查文章是否已存在
                    existing_post = crud_post.get_post_by_slug(self.db, slug)
                    if existing_post:
                        slug = f"{slug}-imported"
                    
                    markdown_strategy = self.options.get("markdown_strategy")
                    if markdown_strategy == "raw_html":
                        markdown_content = ""
                        html_content = content_text
                        editor_mode = "html"
                    else:
                        markdown_content = self._html_to_markdown(
                            content_text,
                            source_link=(link.text if link is not None else ""),
                        )
                        if not (markdown_content or "").strip():
                            markdown_content = content_text
                        html_content = ""
                        editor_mode = "markdown"
                    featured_image_url = self._extract_wp_featured_image_url(
                        item,
                        content_text,
                        source_link=(link.text if link is not None else ""),
                    )
                    raw_excerpt = (excerpt.text or "").strip() if excerpt is not None else ""
                    description_text = (description.text or "").strip() if description is not None else ""
                    excerpt_text = raw_excerpt if raw_excerpt else (description_text if description_text else self._extract_excerpt(content_text))

                    raw_password = (post_password.text or "").strip() if post_password is not None else ""
                    mapped_status, mapped_visibility = self._map_wp_post_status_and_visibility(
                        wp_status=wp_status,
                        post_password=raw_password,
                    )
                    allow_comments = (
                        (comment_status.text or "").strip().lower() == "open"
                        if comment_status is not None
                        else True
                    )
                    created_at = self._first_non_none_datetime(
                        self._parse_wp_datetime_text(post_date_gmt.text if post_date_gmt is not None else None, assume_utc=True),
                        self._parse_wp_datetime_text(post_date.text if post_date is not None else None),
                        self._parse_wp_date(pub_date.text if pub_date is not None else None),
                    )
                    updated_at = self._first_non_none_datetime(
                        self._parse_wp_datetime_text(post_modified_gmt.text if post_modified_gmt is not None else None, assume_utc=True),
                        self._parse_wp_datetime_text(post_modified.text if post_modified is not None else None),
                        created_at,
                    )
                    published_at = created_at if mapped_status == "published" else None
                    
                    # 创建文章
                    post_data = PostCreate(
                        title=title.text or "",
                        slug=slug,
                        content_markdown=markdown_content,
                        content_html=html_content,
                        editor_mode=editor_mode,
                        excerpt=excerpt_text,
                        featured_image_url=featured_image_url,
                        post_type=mapped_post_type,
                        status=mapped_status,
                        visibility=mapped_visibility,
                        password=raw_password or None,
                        allow_comments=allow_comments,
                        license_type="cc_by_nc_sa_4",
                        created_at=created_at,
                        updated_at=updated_at,
                        published_at=published_at,
                    )
                    
                    # 获取默认用户作为作者
                    if default_user is None:
                        default_user = self._resolve_default_user()

                    creator_name = (creator.text or "").strip() if creator is not None else ""
                    author = self._resolve_post_author(creator_name, default_user)
                    if author is None:
                        stats["errors"].append(f"导入文章失败: 未找到可用作者账户（creator={creator_name or 'N/A'}）")
                        continue

                    if self.options.get("download_remote_media", False):
                        media_reference_datetime = published_at or created_at or updated_at
                        markdown_content, html_content, featured_image_url = self._localize_post_media_references(
                            markdown_content=markdown_content,
                            html_content=html_content,
                            featured_image_url=featured_image_url,
                            source_link=(link.text if link is not None else ""),
                            uploaded_by_id=author.id,
                            reference_datetime=media_reference_datetime,
                        )
                        post_data.content_markdown = markdown_content
                        post_data.content_html = html_content
                        post_data.featured_image_url = featured_image_url

                    new_post = crud_post.create_post(self.db, post_data, author.id, auto_commit=False)
                    
                    # 关联分类和标签
                    self._associate_wp_taxonomies(item, new_post, raw_post_type=raw_post_type)

                    # 导入评论
                    if self.options.get("import_comments", True):
                        self._import_wp_comments(item, new_post, stats)

                    # 导入阅读量（postmeta）
                    imported_views_key = None
                    if self.options.get("import_views", True):
                        views_count = self._extract_wp_views_count(item)
                        if views_count is not None:
                            if self._upsert_post_views_metric(new_post.id, views_count, auto_commit=False):
                                stats["views_imported"] += 1
                                imported_views_key = f"post_views_count_{new_post.id}"

                    self.db.commit()
                    if imported_views_key:
                        self._deferred_setting_cache_keys.add(imported_views_key)
                    stats["posts_imported"] += 1
                        
            except Exception as e:
                self.db.rollback()
                stats["errors"].append(f"导入文章失败: {str(e)}")
            finally:
                self._report_progress(
                    "posts",
                    f"正在导入文章 ({index}/{total_count})",
                    current=index,
                    total=total_count,
                    extra={
                        "posts_imported": stats["posts_imported"],
                        "comments_imported": stats["comments_imported"],
                        "views_imported": stats["views_imported"],
                        "media_downloaded": self._downloaded_media_count,
                        "errors_count": len(stats["errors"]),
                    },
                )

    def _import_wp_comments(self, item: ET.Element, post: Post, stats: Dict[str, Any]):
        """导入WordPress评论（包含父子回复关系）。"""
        comment_items = item.findall('wp:comment', self.namespaces)
        if not comment_items:
            return

        pending_comments = []
        for comment_elem in comment_items:
            content_elem = comment_elem.find('wp:comment_content', self.namespaces)
            content = (content_elem.text or "").strip() if content_elem is not None else ""
            if not content:
                continue

            wp_comment_id = self._safe_int(
                (comment_elem.find('wp:comment_id', self.namespaces).text if comment_elem.find('wp:comment_id', self.namespaces) is not None else None)
            )
            wp_parent_id = self._safe_int(
                (comment_elem.find('wp:comment_parent', self.namespaces).text if comment_elem.find('wp:comment_parent', self.namespaces) is not None else None),
                default=0,
            )
            author_name = (
                (comment_elem.find('wp:comment_author', self.namespaces).text or "").strip()
                if comment_elem.find('wp:comment_author', self.namespaces) is not None
                else ""
            ) or "Anonymous"
            author_email = (
                (comment_elem.find('wp:comment_author_email', self.namespaces).text or "").strip()
                if comment_elem.find('wp:comment_author_email', self.namespaces) is not None
                else ""
            ) or "unknown@example.com"
            author_url = (
                (comment_elem.find('wp:comment_author_url', self.namespaces).text or "").strip()
                if comment_elem.find('wp:comment_author_url', self.namespaces) is not None
                else ""
            ) or None
            ip_address = (
                (comment_elem.find('wp:comment_author_IP', self.namespaces).text or "").strip()
                if comment_elem.find('wp:comment_author_IP', self.namespaces) is not None
                else ""
            ) or None
            user_agent = (
                (comment_elem.find('wp:comment_agent', self.namespaces).text or "").strip()
                if comment_elem.find('wp:comment_agent', self.namespaces) is not None
                else ""
            ) or None

            approved_text = (
                (comment_elem.find('wp:comment_approved', self.namespaces).text or "").strip().lower()
                if comment_elem.find('wp:comment_approved', self.namespaces) is not None
                else "0"
            )
            status = self._map_wp_comment_status(approved_text)

            created_at = self._first_non_none_datetime(
                self._parse_wp_datetime_text(
                    comment_elem.find('wp:comment_date_gmt', self.namespaces).text
                    if comment_elem.find('wp:comment_date_gmt', self.namespaces) is not None
                    else None,
                    assume_utc=True,
                ),
                self._parse_wp_datetime_text(
                    comment_elem.find('wp:comment_date', self.namespaces).text
                    if comment_elem.find('wp:comment_date', self.namespaces) is not None
                    else None
                ),
            ) or datetime.utcnow()

            pending_comments.append(
                {
                    "wp_id": wp_comment_id,
                    "wp_parent_id": wp_parent_id,
                    "author_name": author_name,
                    "author_email": author_email,
                    "author_url": author_url,
                    "content": content,
                    "ip_address": ip_address,
                    "user_agent": user_agent,
                    "status": status,
                    "created_at": created_at,
                }
            )

        wp_to_local: Dict[int, int] = {}
        remaining = pending_comments

        # 父评论优先落库，无法匹配的回复在最后降级为顶级评论导入。
        while remaining:
            progressed = False
            next_round = []
            for comment_data in remaining:
                parent_wp_id = comment_data["wp_parent_id"] or 0
                if parent_wp_id and parent_wp_id not in wp_to_local:
                    next_round.append(comment_data)
                    continue

                db_comment = Comment(
                    post_id=post.id,
                    parent_id=wp_to_local.get(parent_wp_id) if parent_wp_id else None,
                    author_name=comment_data["author_name"],
                    author_email=comment_data["author_email"],
                    author_url=comment_data["author_url"],
                    content=comment_data["content"],
                    ip_address=comment_data["ip_address"],
                    user_agent=comment_data["user_agent"],
                    status=comment_data["status"],
                    is_admin_reply=False,
                    created_at=comment_data["created_at"],
                )
                self.db.add(db_comment)
                self.db.flush()
                if comment_data["wp_id"]:
                    wp_to_local[comment_data["wp_id"]] = db_comment.id
                stats["comments_imported"] += 1
                progressed = True

            if not progressed:
                for comment_data in next_round:
                    db_comment = Comment(
                        post_id=post.id,
                        parent_id=None,
                        author_name=comment_data["author_name"],
                        author_email=comment_data["author_email"],
                        author_url=comment_data["author_url"],
                        content=comment_data["content"],
                        ip_address=comment_data["ip_address"],
                        user_agent=comment_data["user_agent"],
                        status=comment_data["status"],
                        is_admin_reply=False,
                        created_at=comment_data["created_at"],
                    )
                    self.db.add(db_comment)
                    self.db.flush()
                    stats["comments_imported"] += 1
                return

            remaining = next_round

        self.db.flush()

    def _map_wp_comment_status(self, approved_text: str) -> str:
        if approved_text in {"1", "approve", "approved"}:
            return "approved"
        if approved_text in {"spam", "trash"}:
            return "spam"
        return "pending"

    def _extract_wp_views_count(self, item: ET.Element) -> Optional[int]:
        """提取WordPress postmeta中的阅读量（views/post_views_count）。"""
        max_views: Optional[int] = None
        whitelist = set(self.options.get("postmeta_whitelist", ["views", "post_views_count"]))
        postmeta_items = item.findall('wp:postmeta', self.namespaces)
        for meta in postmeta_items:
            key_elem = meta.find('wp:meta_key', self.namespaces)
            value_elem = meta.find('wp:meta_value', self.namespaces)
            key = (key_elem.text or "").strip() if key_elem is not None else ""
            raw_value = (value_elem.text or "").strip() if value_elem is not None else ""
            if key not in whitelist:
                continue
            value = self._safe_int(raw_value, default=0)
            if value is None:
                continue
            if max_views is None or value > max_views:
                max_views = value
        return max_views

    def _upsert_post_views_metric(self, post_id: int, views_count: int, *, auto_commit: bool = True) -> bool:
        key = f"post_views_count_{post_id}"
        setting_value = {"value": int(max(0, views_count))}
        existing = self.db.execute(select(Setting).filter(Setting.key == key)).scalar_one_or_none()
        if existing:
            existing.value = setting_value
            existing.description = "Imported WordPress post views"
            existing.category = "post_metrics"
            existing.type = "integer"
        else:
            self.db.add(Setting(
                key=key,
                value=setting_value,
                description="Imported WordPress post views",
                category="post_metrics",
                type="integer",
            ))

        if auto_commit:
            self.db.commit()
            clear_cache(cache_key_for_setting(key))
        return True

    def _clear_deferred_setting_cache(self) -> None:
        if not self._deferred_setting_cache_keys:
            return
        for setting_key in self._deferred_setting_cache_keys:
            cache.pop(cache_key_for_setting(setting_key), None)
        self._deferred_setting_cache_keys.clear()
    
    def _normalize_imported_slug(self, raw_slug: str) -> str:
        """规范化导入得到的 slug，兼容 URL 编码与 Unicode。"""
        candidate = (raw_slug or "").strip()
        if not candidate:
            return ""

        parsed = self._safe_urlparse(candidate)
        if parsed and (parsed.scheme or parsed.netloc):
            candidate = (parsed.path or "").strip()

        candidate = candidate.split("?", 1)[0].split("#", 1)[0].strip()
        if "/" in candidate:
            candidate = candidate.rsplit("/", 1)[-1]

        for _ in range(2):
            decoded = unquote(candidate)
            if decoded == candidate:
                break
            candidate = decoded

        candidate = candidate.replace("+", " ")
        candidate = re.sub(r"\s+", "-", candidate, flags=re.UNICODE)
        candidate = re.sub(r"[^\w\-]+", "-", candidate, flags=re.UNICODE)
        candidate = re.sub(r"-{2,}", "-", candidate).strip("-_")

        return candidate.lower()

    def _extract_slug_from_url(self, url: str) -> str:
        """从URL中提取slug"""
        if not url:
            return ""

        parsed = self._safe_urlparse(url)
        if parsed is None:
            return ""
        path = (parsed.path or "").strip()
        if not path:
            return ""

        path_tail = path.rsplit("/", 1)[-1]
        stem, ext = os.path.splitext(path_tail)
        slug_source = stem if ext else path_tail
        return self._normalize_imported_slug(slug_source)

    def _safe_urlparse(self, raw_url: str) -> Optional[ParseResult]:
        """安全解析 URL，避免异常输入导致导入中断。"""
        try:
            return urlparse((raw_url or "").strip())
        except ValueError:
            return None
    
    def _generate_slug_from_title(self, title: str) -> str:
        """从标题生成slug"""
        if not title:
            return "untitled"

        slug = self._normalize_imported_slug(title)
        return slug or "untitled"

    def _build_wp_attachment_map(self, root: ET.Element) -> Dict[int, str]:
        """构建 WordPress 附件 ID -> URL 的映射，用于恢复特色图。"""
        mapping: Dict[int, str] = {}
        if root is None:
            return mapping

        for item in root.findall(".//item"):
            post_type = (item.findtext("wp:post_type", default="", namespaces=self.namespaces) or "").strip().lower()
            if post_type != "attachment":
                continue

            post_id = self._safe_int(
                item.findtext("wp:post_id", default="", namespaces=self.namespaces),
                default=None,
            )
            raw_url = (
                item.findtext("wp:attachment_url", default="", namespaces=self.namespaces)
                or item.findtext("link", default="")
                or ""
            ).strip()
            if post_id is None or not raw_url:
                continue
            normalized = self._normalize_media_url(raw_url)
            if normalized:
                mapping[int(post_id)] = normalized

        return mapping

    def _extract_wp_postmeta_values(self, item: ET.Element, target_key: str) -> List[str]:
        values: List[str] = []
        if item is None or not target_key:
            return values

        for meta in item.findall("wp:postmeta", self.namespaces):
            key_elem = meta.find("wp:meta_key", self.namespaces)
            value_elem = meta.find("wp:meta_value", self.namespaces)
            key_text = (key_elem.text or "").strip() if key_elem is not None else ""
            if key_text != target_key:
                continue
            raw_value = (value_elem.text or "").strip() if value_elem is not None else ""
            if raw_value:
                values.append(raw_value)
        return values

    def _normalize_media_url(self, raw_url: str, source_link: str = "") -> str:
        url = (raw_url or "").strip()
        if not url:
            return ""
        if url.startswith("//"):
            return f"https:{url}"
        if url.startswith("http://") or url.startswith("https://"):
            return url

        base = (source_link or self._site_base_url or "").strip()
        if base:
            return urljoin(base, url)
        return url

    def _extract_first_image_url_from_html(self, html_content: str, source_link: str = "") -> Optional[str]:
        if not (html_content or "").strip():
            return None
        soup = BeautifulSoup(html_content, "html.parser")
        img = soup.find("img")
        if not isinstance(img, BsTag):
            return None
        raw_src = (
            img.get("src")
            or img.get("data-src")
            or img.get("data-original")
            or img.get("data-lazy-src")
            or ""
        ).strip()
        if not raw_src:
            return None
        normalized = self._normalize_media_url(raw_src, source_link=source_link)
        return normalized or None

    def _extract_wp_featured_image_url(self, item: ET.Element, html_content: str, source_link: str = "") -> Optional[str]:
        """提取特色图：_thumbnail_id -> post_theme_color_meta.image_url -> 正文首图。"""
        if item is None:
            return self._extract_first_image_url_from_html(html_content, source_link=source_link)

        # 1) _thumbnail_id => attachment_url
        thumbnail_ids = self._extract_wp_postmeta_values(item, "_thumbnail_id")
        for raw_id in thumbnail_ids:
            attachment_id = self._safe_int(raw_id, default=None)
            if attachment_id is None:
                continue
            attachment_url = self._attachment_url_map.get(int(attachment_id))
            if attachment_url:
                return attachment_url

        # 2) 常见主题字段（序列化串中含 image_url）
        theme_meta_values = self._extract_wp_postmeta_values(item, "post_theme_color_meta")
        for raw_meta in theme_meta_values:
            match = re.search(r'image_url";s:\d+:"([^"]+)"', raw_meta)
            if match:
                extracted = self._normalize_media_url(match.group(1), source_link=source_link)
                if extracted:
                    return extracted

        # 3) 兜底正文首图
        return self._extract_first_image_url_from_html(html_content, source_link=source_link)

    def _get_media_upload_root(self) -> str:
        return os.path.abspath("media_uploads")

    def _sanitize_path_segment(self, value: str, fallback: str = "file") -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1F]+', "-", str(value or "").strip())
        cleaned = cleaned.replace("..", "-")
        cleaned = re.sub(r"\s+", "-", cleaned)
        cleaned = re.sub(r"-{2,}", "-", cleaned)
        cleaned = cleaned.strip(" .-")
        if not cleaned:
            return fallback
        return cleaned[:128]

    def _extract_preserved_relative_dir_parts(self, source_url: str) -> List[str]:
        parsed = self._safe_urlparse(source_url)
        if parsed is None:
            return []
        raw_parts = [part for part in (parsed.path or "").split("/") if part]
        if len(raw_parts) <= 1:
            return []

        dir_parts = raw_parts[:-1]
        sliced = None

        # 优先按原路径中的 年/月 结构保留（例如 25/03 或 2025/03）。
        for idx in range(len(dir_parts) - 1):
            year_seg = str(dir_parts[idx] or "").strip()
            month_seg = str(dir_parts[idx + 1] or "").strip()
            if (
                re.fullmatch(r"\d{2}(\d{2})?", year_seg)
                and re.fullmatch(r"(0?[1-9]|1[0-2])", month_seg)
            ):
                sliced = dir_parts[idx:]
                break

        # 若路径中没有明显的 年/月 段，交给外层回退到文章发布时间生成目录。
        if sliced is None:
            return []

        normalized_parts: List[str] = []
        for part in sliced:
            segment = self._sanitize_path_segment(part, fallback="")
            if segment:
                normalized_parts.append(segment)
        return normalized_parts

    def _is_remote_http_url(self, url: str) -> bool:
        parsed = self._safe_urlparse(url)
        if parsed is None:
            return False
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    def _looks_like_media_candidate(self, url: str, mime_type: str = "") -> bool:
        if not url:
            return False
        mime = (mime_type or "").split(";", 1)[0].strip().lower()
        if mime.startswith(("image/", "video/", "audio/")):
            return True

        parsed = self._safe_urlparse(url)
        if parsed is None:
            return False
        path = (parsed.path or "").lower()
        if "/wp-content/uploads/" in path:
            return True

        ext = os.path.splitext(path)[1].lower()
        media_exts = {
            ".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif",
            ".mp4", ".m4v", ".mov", ".webm", ".avi", ".mkv",
            ".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        }
        return ext in media_exts

    def _guess_extension_from_mime(self, mime_type: str) -> str:
        mime = (mime_type or "").split(";", 1)[0].strip().lower()
        if not mime:
            return ""
        ext = mimetypes.guess_extension(mime) or ""
        if ext == ".jpe":
            return ".jpg"
        return ext.lower()

    def _guess_file_type(self, mime_type: str, url_or_path: str = "") -> str:
        mime = (mime_type or "").split(";", 1)[0].strip().lower()
        if mime.startswith("image/"):
            return "image"
        if mime.startswith("video/"):
            return "video"
        if mime.startswith("audio/"):
            return "audio"
        if mime:
            return "document"
        ext = os.path.splitext((url_or_path or "").lower())[1]
        if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".avif"}:
            return "image"
        if ext in {".mp4", ".m4v", ".mov", ".webm", ".avi", ".mkv"}:
            return "video"
        if ext in {".mp3", ".wav", ".ogg", ".m4a", ".flac", ".aac"}:
            return "audio"
        return "document"

    def _fetch_remote_media_bytes(self, url: str, timeout_seconds: int, max_bytes: int) -> Tuple[bytes, str]:
        request = UrlRequest(
            url,
            headers={"User-Agent": "RewrZ-WordPressImporter/1.0"},
        )
        with urlopen(request, timeout=max(1, timeout_seconds)) as response:
            content_type = (response.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
            chunks: List[bytes] = []
            total = 0
            while True:
                chunk = response.read(65536)
                if not chunk:
                    break
                total += len(chunk)
                if total > max_bytes:
                    raise ValueError(f"远程媒体文件过大（>{max_bytes} bytes）")
                chunks.append(chunk)
        return b"".join(chunks), content_type

    def _persist_downloaded_media(
        self,
        source_url: str,
        payload: bytes,
        mime_type: str,
        uploaded_by_id: int,
        reference_datetime: Optional[datetime] = None,
    ) -> str:
        upload_root = os.path.abspath(self._get_media_upload_root())
        strategy = str(self.options.get("remote_media_path_strategy", "latest_month") or "latest_month").strip().lower()
        if strategy not in {"latest_month", "preserve_relative_path"}:
            strategy = "latest_month"

        parsed = self._safe_urlparse(source_url)
        raw_path = (parsed.path or "") if parsed is not None else ""
        original_name = os.path.basename(unquote(raw_path)).strip()
        stem, ext = os.path.splitext(original_name)
        ext = ext.lower()
        if not ext:
            ext = self._guess_extension_from_mime(mime_type)
        if not ext:
            ext = ".bin"
        stem = self._sanitize_path_segment(stem or "wp-media", fallback="wp-media")
        year_month = self._resolve_media_year_month(reference_datetime)

        digest = hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]
        if strategy == "preserve_relative_path":
            relative_parts = self._extract_preserved_relative_dir_parts(source_url)
            if not relative_parts:
                relative_parts = [year_month[0], year_month[1]]
            filename = f"{stem}{ext}"
        else:
            relative_parts = [year_month[0], year_month[1]]
            filename = f"{stem}-{digest}{ext}"

        target_dir = os.path.join(upload_root, *relative_parts) if relative_parts else upload_root
        os.makedirs(target_dir, exist_ok=True)
        filepath = os.path.join(target_dir, filename)

        if os.path.exists(filepath):
            try:
                with open(filepath, "rb") as existing_handle:
                    existing_payload = existing_handle.read()
            except Exception:
                existing_payload = None
            if existing_payload is not None and existing_payload != payload:
                filepath = os.path.join(target_dir, f"{stem}-{digest}{ext}")

        file_already_exists = os.path.exists(filepath)
        if not file_already_exists:
            with open(filepath, "wb") as handle:
                handle.write(payload)
            self._downloaded_media_count += 1

        existing_media = crud_media.get_media_by_filepath(self.db, filepath)
        if existing_media is None:
            media_filename = original_name or os.path.basename(filepath)
            title = os.path.splitext(media_filename)[0] if media_filename else stem
            relative_dir = os.path.dirname(os.path.relpath(filepath, upload_root)).replace("\\", "/")
            folder = "" if relative_dir in {"", "."} else relative_dir
            file_hash = hashlib.sha256(payload).hexdigest()
            db_media = Media(
                filename=media_filename,
                filepath=filepath,
                folder=folder,
                file_type=self._guess_file_type(mime_type, source_url),
                mime_type=mime_type or (mimetypes.guess_type(filename)[0] or "application/octet-stream"),
                file_hash=file_hash,
                file_size=len(payload),
                title=title[:255] if title else stem,
                alt_text="",
                description=f"Imported from WordPress: {source_url}",
                uploaded_by_id=uploaded_by_id,
            )
            self.db.add(db_media)
            self.db.flush()

        relative_path = os.path.relpath(filepath, upload_root).replace("\\", "/")
        return f"/media/{relative_path}"

    def _resolve_media_year_month(self, reference_datetime: Optional[datetime]) -> Tuple[str, str]:
        chosen = reference_datetime or datetime.utcnow()
        if chosen.tzinfo is not None:
            chosen = chosen.astimezone(timezone.utc).replace(tzinfo=None)
        return chosen.strftime("%Y"), chosen.strftime("%m")

    def _build_media_download_cache_key(self, normalized_url: str, reference_datetime: Optional[datetime]) -> str:
        strategy = str(self.options.get("remote_media_path_strategy", "latest_month") or "latest_month").strip().lower()
        if strategy not in {"latest_month", "preserve_relative_path"}:
            strategy = "latest_month"
        if strategy == "preserve_relative_path":
            if self._extract_preserved_relative_dir_parts(normalized_url):
                return normalized_url
        year, month = self._resolve_media_year_month(reference_datetime)
        return f"{normalized_url}|{year}/{month}"

    def _download_media_and_get_local_url(
        self,
        url: str,
        source_link: str,
        uploaded_by_id: int,
        reference_datetime: Optional[datetime] = None,
    ) -> str:
        normalized = self._normalize_media_url(url, source_link=source_link)
        if not normalized:
            return url
        if not self._is_remote_http_url(normalized):
            return normalized
        if not self._looks_like_media_candidate(normalized):
            return normalized
        cache_key = self._build_media_download_cache_key(normalized, reference_datetime)
        if cache_key in self._downloaded_media_url_map:
            return self._downloaded_media_url_map[cache_key]

        timeout_seconds = int(self.options.get("media_download_timeout_seconds", 20) or 20)
        max_megabytes = int(self.options.get("media_download_max_mb", 30) or 30)
        max_bytes = max(1, max_megabytes) * 1024 * 1024

        try:
            payload, mime_type = self._fetch_remote_media_bytes(
                normalized,
                timeout_seconds=timeout_seconds,
                max_bytes=max_bytes,
            )
            if not payload:
                return normalized
            if not self._looks_like_media_candidate(normalized, mime_type=mime_type):
                return normalized
            local_url = self._persist_downloaded_media(
                source_url=normalized,
                payload=payload,
                mime_type=mime_type,
                uploaded_by_id=uploaded_by_id,
                reference_datetime=reference_datetime,
            )
            self._downloaded_media_url_map[cache_key] = local_url
            return local_url
        except Exception:
            return normalized

    def _split_trailing_url_punctuation(self, url: str) -> Tuple[str, str]:
        if not url:
            return "", ""
        trailing_chars = ".,;:!?)]}>。，；：！？）】》"
        core = url
        suffix = ""
        while core and core[-1] in trailing_chars:
            suffix = core[-1] + suffix
            core = core[:-1]
        return core, suffix

    def _localize_media_urls_in_text(
        self,
        text: str,
        source_link: str,
        uploaded_by_id: int,
        reference_datetime: Optional[datetime] = None,
    ) -> str:
        if not text:
            return text

        pattern = re.compile(r"https?://[^\s<>'\"]+")
        matches = sorted(set(pattern.findall(text)), key=len, reverse=True)
        if not matches:
            return text

        updated = text
        for matched in matches:
            core, suffix = self._split_trailing_url_punctuation(matched)
            if not core:
                continue
            local_url = self._download_media_and_get_local_url(
                core,
                source_link=source_link,
                uploaded_by_id=uploaded_by_id,
                reference_datetime=reference_datetime,
            )
            if local_url and local_url != core:
                updated = updated.replace(matched, f"{local_url}{suffix}")

        return updated

    def _localize_media_urls_in_html(
        self,
        html_content: str,
        source_link: str,
        uploaded_by_id: int,
        reference_datetime: Optional[datetime] = None,
    ) -> str:
        if not html_content:
            return html_content

        soup = BeautifulSoup(html_content, "html.parser")
        changed = False
        for node in soup.find_all(True):
            tag_name = (node.name or "").lower()
            attrs: List[str] = []
            if tag_name in {"img", "source", "video", "audio", "iframe"}:
                attrs = ["src", "poster"]
            elif tag_name == "a":
                attrs = ["href"]
            if not attrs:
                continue

            for attr_name in attrs:
                raw_value = (node.get(attr_name) or "").strip()
                if not raw_value:
                    continue
                normalized = self._normalize_media_url(raw_value, source_link=source_link)
                local_url = self._download_media_and_get_local_url(
                    normalized,
                    source_link=source_link,
                    uploaded_by_id=uploaded_by_id,
                    reference_datetime=reference_datetime,
                )
                if local_url != raw_value:
                    node[attr_name] = local_url
                    changed = True

        return str(soup) if changed else html_content

    def _localize_post_media_references(
        self,
        markdown_content: str,
        html_content: str,
        featured_image_url: Optional[str],
        source_link: str,
        uploaded_by_id: int,
        reference_datetime: Optional[datetime] = None,
    ) -> Tuple[str, str, Optional[str]]:
        localized_markdown = self._localize_media_urls_in_text(
            markdown_content,
            source_link=source_link,
            uploaded_by_id=uploaded_by_id,
            reference_datetime=reference_datetime,
        ) if markdown_content else markdown_content

        localized_html = self._localize_media_urls_in_html(
            html_content,
            source_link=source_link,
            uploaded_by_id=uploaded_by_id,
            reference_datetime=reference_datetime,
        ) if html_content else html_content

        localized_featured = featured_image_url
        if featured_image_url:
            normalized_featured = self._normalize_media_url(featured_image_url, source_link=source_link)
            localized_featured = self._download_media_and_get_local_url(
                normalized_featured,
                source_link=source_link,
                uploaded_by_id=uploaded_by_id,
                reference_datetime=reference_datetime,
            )

        return localized_markdown, localized_html, localized_featured
    
    def _strip_wp_block_comments(self, raw_html: str) -> str:
        """去掉 Gutenberg 的注释型区块标记。"""
        if not raw_html:
            return ""
        cleaned = re.sub(r"<!--\s*/?wp:[\s\S]*?-->", "", raw_html, flags=re.IGNORECASE)
        return cleaned.strip()

    def _rewrite_wp_shortcodes(self, raw_html: str) -> str:
        """处理常见短代码，避免导入后丢语义。"""
        if not raw_html:
            return ""
        content = raw_html

        # [dm href='...']text[/dm] -> 链接
        content = re.sub(
            r"\[dm\s+href=['\"]([^'\"]+)['\"]\](.*?)\[/dm\]",
            r'<a href="\1">\2</a>',
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # [caption ...]...[/caption] -> 保留内部内容（一般含图片）
        content = re.sub(
            r"\[caption[^\]]*\](.*?)\[/caption\]",
            r"\1",
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # [embed]url[/embed] -> 普通链接
        content = re.sub(
            r"\[embed\](.*?)\[/embed\]",
            r'<a href="\1">\1</a>',
            content,
            flags=re.IGNORECASE | re.DOTALL,
        )
        # [audio src="..."] [video src="..."]
        content = re.sub(
            r"\[audio[^\]]*src=['\"]([^'\"]+)['\"][^\]]*\]",
            r'<audio src="\1"></audio>',
            content,
            flags=re.IGNORECASE,
        )
        content = re.sub(
            r"\[video[^\]]*src=['\"]([^'\"]+)['\"][^\]]*\]",
            r'<video src="\1"></video>',
            content,
            flags=re.IGNORECASE,
        )
        return content

    def _clean_markdown_text(self, text: str) -> str:
        cleaned = (text or "").replace("\xa0", " ")
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"[ \t]*\n[ \t]*", "\n", cleaned)
        return cleaned

    def _inline_node_to_markdown(self, node: Any, source_link: str = "") -> str:
        if isinstance(node, Comment):
            return ""
        if isinstance(node, BsNavigableString):
            return self._clean_markdown_text(str(node))
        if not isinstance(node, BsTag):
            return ""

        name = (node.name or "").lower()
        if name in {"script", "style", "noscript"}:
            return ""
        if name == "br":
            return "\n"
        if name in {"strong", "b"}:
            return f"**{self._inline_children_to_markdown(node, source_link=source_link).strip()}**"
        if name in {"em", "i"}:
            return f"*{self._inline_children_to_markdown(node, source_link=source_link).strip()}*"
        if name == "code" and node.parent and node.parent.name != "pre":
            return f"`{node.get_text(strip=True)}`"
        if name == "a":
            href = self._normalize_media_url((node.get("href") or "").strip(), source_link=source_link)
            text = self._inline_children_to_markdown(node, source_link=source_link).strip() or href
            if href:
                return f"[{text}]({href})"
            return text
        if name == "img":
            src = self._normalize_media_url((node.get("src") or node.get("data-src") or "").strip(), source_link=source_link)
            if not src:
                return ""
            alt = (node.get("alt") or "").strip()
            return f"![{alt}]({src})"

        return self._inline_children_to_markdown(node, source_link=source_link)

    def _inline_children_to_markdown(self, parent: BsTag, source_link: str = "") -> str:
        parts = [self._inline_node_to_markdown(child, source_link=source_link) for child in parent.children]
        return self._clean_markdown_text("".join(parts))

    def _list_to_markdown(self, list_node: BsTag, depth: int = 0, source_link: str = "") -> str:
        ordered = (list_node.name or "").lower() == "ol"
        lines: List[str] = []
        index = 1

        for li in list_node.find_all("li", recursive=False):
            if not isinstance(li, BsTag):
                continue
            direct_text_parts: List[str] = []
            nested_lists: List[BsTag] = []
            for child in li.children:
                if isinstance(child, BsTag) and (child.name or "").lower() in {"ul", "ol"}:
                    nested_lists.append(child)
                else:
                    rendered = self._inline_node_to_markdown(child, source_link=source_link).strip()
                    if rendered:
                        direct_text_parts.append(rendered)

            indent = "  " * depth
            bullet = f"{index}. " if ordered else "- "
            item_text = self._clean_markdown_text(" ".join(direct_text_parts)).strip()
            lines.append(f"{indent}{bullet}{item_text}".rstrip())

            for nested in nested_lists:
                nested_md = self._list_to_markdown(nested, depth=depth + 1, source_link=source_link).rstrip()
                if nested_md:
                    lines.append(nested_md)

            if ordered:
                index += 1

        return "\n".join(lines).strip()

    def _table_to_markdown(self, table_node: BsTag, source_link: str = "") -> str:
        rows = table_node.find_all("tr")
        if not rows:
            return ""

        header_cells = rows[0].find_all(["th", "td"])
        headers = [
            (self._inline_children_to_markdown(cell, source_link=source_link).strip() or "-")
            for cell in header_cells
        ]
        if not headers:
            return ""

        lines = [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join(["---"] * len(headers)) + " |",
        ]

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if not cells:
                continue
            values = [
                self._inline_children_to_markdown(cell, source_link=source_link).strip()
                for cell in cells[:len(headers)]
            ]
            if len(values) < len(headers):
                values.extend([""] * (len(headers) - len(values)))
            lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines).strip()

    def _block_node_to_markdown(self, node: Any, source_link: str = "") -> str:
        if isinstance(node, Comment):
            return ""
        if isinstance(node, BsNavigableString):
            text = self._clean_markdown_text(str(node)).strip()
            return f"{text}\n\n" if text else ""
        if not isinstance(node, BsTag):
            return ""

        name = (node.name or "").lower()
        if name in {"script", "style", "noscript"}:
            return ""
        if name in {"h1", "h2", "h3", "h4", "h5", "h6"}:
            level = int(name[1])
            text = self._inline_children_to_markdown(node, source_link=source_link).strip()
            return f"{'#' * level} {text}\n\n" if text else ""
        if name in {"p", "div", "section", "article"}:
            text = self._inline_children_to_markdown(node, source_link=source_link).strip()
            return f"{text}\n\n" if text else ""
        if name in {"ul", "ol"}:
            text = self._list_to_markdown(node, depth=0, source_link=source_link)
            return f"{text}\n\n" if text else ""
        if name == "blockquote":
            inner_parts = [self._block_node_to_markdown(child, source_link=source_link) for child in node.children]
            inner = "\n".join(part.strip() for part in inner_parts if part and part.strip()).strip()
            if not inner:
                inner = self._inline_children_to_markdown(node, source_link=source_link).strip()
            if not inner:
                return ""
            quoted = []
            for line in inner.splitlines():
                quoted.append(f"> {line}" if line.strip() else ">")
            return "\n".join(quoted).strip() + "\n\n"
        if name == "pre":
            code_tag = node.find("code")
            code_text = (code_tag.get_text("\n", strip=False) if code_tag else node.get_text("\n", strip=False)).strip("\n")
            language = ""
            class_values = []
            if code_tag and code_tag.get("class"):
                class_values = code_tag.get("class") or []
            elif node.get("class"):
                class_values = node.get("class") or []
            for cls_name in class_values:
                if cls_name.startswith("language-"):
                    language = cls_name.split("language-", 1)[1].strip()
                    break
            return f"```{language}\n{code_text}\n```\n\n"
        if name == "code":
            return f"`{node.get_text(strip=True)}`\n\n"
        if name == "hr":
            return "---\n\n"
        if name == "img":
            inline = self._inline_node_to_markdown(node, source_link=source_link).strip()
            return f"{inline}\n\n" if inline else ""
        if name in {"video", "audio", "iframe"}:
            media_src = (
                (node.get("src") or "").strip()
                or ((node.find("source") or {}).get("src") if node.find("source") else "")
            )
            media_src = self._normalize_media_url(media_src, source_link=source_link)
            if not media_src:
                return ""
            label = "视频" if name == "video" else ("音频" if name == "audio" else "嵌入内容")
            return f"[{label}]({media_src})\n\n"
        if name == "figure":
            image_markdown = ""
            figure_img = node.find("img")
            if isinstance(figure_img, BsTag):
                image_markdown = self._inline_node_to_markdown(figure_img, source_link=source_link).strip()
            caption_node = node.find("figcaption")
            caption = (
                self._inline_children_to_markdown(caption_node, source_link=source_link).strip()
                if isinstance(caption_node, BsTag)
                else ""
            )
            result_parts: List[str] = []
            if image_markdown:
                result_parts.append(image_markdown)
            if caption:
                result_parts.append(f"*{caption}*")
            if result_parts:
                return "\n".join(result_parts).strip() + "\n\n"
            return ""
        if name == "table":
            table_md = self._table_to_markdown(node, source_link=source_link)
            return f"{table_md}\n\n" if table_md else ""

        # 默认兜底：先尝试块级递归，再尝试行内文本。
        child_blocks = [self._block_node_to_markdown(child, source_link=source_link) for child in node.children]
        merged_blocks = "\n".join(part.strip() for part in child_blocks if part and part.strip()).strip()
        if merged_blocks:
            return merged_blocks + "\n\n"
        inline = self._inline_children_to_markdown(node, source_link=source_link).strip()
        return f"{inline}\n\n" if inline else ""

    def _html_to_markdown(self, html_content: str, source_link: str = "") -> str:
        """增强版 HTML -> Markdown 转换（兼容 Gutenberg 与常见媒体块）。"""
        if not html_content:
            return ""

        prepared = self._rewrite_wp_shortcodes(self._strip_wp_block_comments(html_content))
        if not prepared.strip():
            return ""

        soup = BeautifulSoup(prepared, "html.parser")
        for tag in soup.find_all(["script", "style", "noscript"]):
            tag.decompose()
        for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
            comment.extract()

        container = soup.body if soup.body else soup
        chunks: List[str] = []
        for child in container.children:
            rendered = self._block_node_to_markdown(child, source_link=source_link)
            if rendered and rendered.strip():
                chunks.append(rendered.strip())

        if not chunks:
            fallback = self._inline_children_to_markdown(container, source_link=source_link).strip()
            return fallback

        markdown = "\n\n".join(chunks)
        markdown = re.sub(r"\n{3,}", "\n\n", markdown).strip()
        return markdown
    
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
            return self._normalize_datetime(parsedate_to_datetime(date_str))
        except:
            return None

    def _parse_wp_datetime_text(self, date_str: Optional[str], assume_utc: bool = False) -> Optional[datetime]:
        """解析 WordPress wp:post_date/wp:post_modified 格式。"""
        if not date_str:
            return None

        normalized = date_str.strip()
        if not normalized or normalized.startswith("0000-00-00"):
            return None

        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
            try:
                parsed = datetime.strptime(normalized, fmt)
                if assume_utc:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return self._normalize_datetime(parsed)
            except ValueError:
                continue
        return None

    def _safe_int(self, value: Optional[str], default: Optional[int] = None) -> Optional[int]:
        if value is None:
            return default
        text = str(value).strip()
        if not text:
            return default
        try:
            return int(text)
        except (ValueError, TypeError):
            return default

    def _normalize_datetime(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _first_non_none_datetime(self, *values: Optional[datetime]) -> Optional[datetime]:
        for value in values:
            if value is not None:
                return value
        return None

    def _map_wp_post_status_and_visibility(self, wp_status: str, post_password: str) -> Tuple[str, str]:
        visibility = "public"
        if post_password:
            visibility = "password"
        if wp_status == "private":
            visibility = "private"

        if wp_status in {"publish", "private"}:
            status = "published"
        elif wp_status in {"draft", "pending", "future", "auto-draft"}:
            status = "draft"
        else:
            status = "draft"

        return status, visibility

    def _map_wp_post_type(self, wp_post_type: str) -> Optional[str]:
        """将 WordPress post_type 映射到 RewrZ post_type。

        - post/article -> post
        - page -> page
        - 常见系统类型（attachment/revision/nav_menu_item 等）跳过
        - 其余自定义类型按 post 导入（由白名单控制是否导入）
        """
        if not wp_post_type:
            return None

        if wp_post_type == "post":
            return "post"
        if wp_post_type == "page":
            return "page"

        ignored_post_types = {
            "attachment",
            "revision",
            "nav_menu_item",
            "custom_css",
            "customize_changeset",
            "oembed_cache",
            "user_request",
            "wp_block",
            "wp_navigation",
            "wp_template",
            "wp_template_part",
        }
        if wp_post_type in ignored_post_types:
            return None

        # 自定义 post_type 统一按文章导入，避免内容丢失。
        return "post"
    
    def _associate_wp_taxonomies(self, item: ET.Element, post: Post, raw_post_type: str = ""):
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

            format_bound = False
            # 优先使用 post_type -> format 映射，便于将自定义类型（如 shuoshuo）导入到指定格式。
            mapped_from_type = self._map_wp_post_type_to_format_slug(raw_post_type)
            if mapped_from_type:
                mapped_format = self._ensure_post_format(mapped_from_type, "")
                if mapped_format and mapped_format not in post.formats:
                    post.formats.append(mapped_format)
                    format_bound = True

            # 未配置自定义映射时，回退到 WordPress post_format taxonomy。
            if not format_bound:
                format_items = item.findall('category[@domain="post_format"]')
                for format_elem in format_items:
                    raw_nicename = (format_elem.get("nicename") or "").strip().lower()
                    raw_name = (format_elem.text or "").strip()
                    mapped_slug = self._map_wp_post_format_slug(raw_nicename, raw_name)
                    if not mapped_slug:
                        continue
                    format_obj = self._ensure_post_format(mapped_slug, raw_name)
                    if format_obj and format_obj not in post.formats:
                        post.formats.append(format_obj)
                        format_bound = True

            # 若 WordPress 未显式给出 post_format，则默认绑定标准文章格式。
            if not format_bound and not post.formats:
                default_format = self._ensure_post_format("article", "标准文章")
                if default_format and default_format not in post.formats:
                    post.formats.append(default_format)
            
        except Exception as e:
            self.db.rollback()
            raise RuntimeError(f"关联分类标签失败: {str(e)}")

    def _map_wp_post_format_slug(self, raw_nicename: str, raw_name: str) -> Optional[str]:
        """将 WordPress post_format 映射为 RewrZ 内容类型 slug。"""
        normalized = (raw_nicename or "").strip().lower()
        if normalized.startswith("post-format-"):
            normalized = normalized[len("post-format-"):]
        if not normalized:
            normalized = (raw_name or "").strip().lower()

        mapping = {
            "standard": "article",
            "post": "article",
            "article": "article",
            "aside": "micro",
            "status": "micro",
            "chat": "micro",
            "link": "micro",
            "quote": "micro",
            # 媒体形态不再决定内容类型，统一归到 article。
            "image": "article",
            "gallery": "article",
            "video": "article",
            "audio": "poem",
        }
        if normalized in mapping:
            return mapping[normalized]

        return "article"

    def _normalize_post_type_format_map(self, raw_map: Any) -> Dict[str, str]:
        normalized: Dict[str, str] = {}
        items: List[Tuple[str, str]] = []
        if isinstance(raw_map, dict):
            items = [(str(k), str(v)) for k, v in raw_map.items()]
        elif isinstance(raw_map, str):
            # 支持 "shuoshuo:micro,news:article" 简写格式。
            for token in re.split(r"[,;\n]+", raw_map):
                part = token.strip()
                if not part or ":" not in part:
                    continue
                left, right = part.split(":", 1)
                items.append((left, right))

        for raw_key, raw_value in items:
            wp_type = re.sub(r"[^a-z0-9_-]+", "", raw_key.strip().lower())
            format_slug = self._normalize_rewrz_format_slug(raw_value)
            if not wp_type or not format_slug:
                continue
            normalized[wp_type] = format_slug
        return dict(sorted(normalized.items()))

    def _normalize_rewrz_format_slug(self, raw_value: Any) -> Optional[str]:
        raw_text = str(raw_value or "").strip().lower()
        if not raw_text:
            return None
        alias_map = {
            "post": "article",
            "standard": "article",
            "article": "article",
            "weibo": "micro",
            "micro": "micro",
            "micro_post": "micro",
            "status": "micro",
            "aside": "micro",
            "poetry": "poem",
            "song": "poem",
            "audio": "poem",
            "微博": "micro",
            "标准文章": "article",
            "文章": "article",
            "诗词歌赋": "poem",
        }
        mapped = alias_map.get(raw_text, raw_text)
        slug = re.sub(r"[^a-z0-9_-]+", "-", mapped).strip("-")
        return normalize_intent_slug(slug)

    def _map_wp_post_type_to_format_slug(self, wp_post_type: str) -> Optional[str]:
        normalized_type = (wp_post_type or "").strip().lower()
        if not normalized_type:
            return None
        mapping = self.options.get("post_type_format_map") or {}
        if not isinstance(mapping, dict):
            return None
        raw_target = mapping.get(normalized_type)
        if raw_target is None:
            return None
        return self._normalize_rewrz_format_slug(raw_target)

    def _ensure_post_format(self, format_slug: str, display_name: str) -> Optional[Format]:
        slug = normalize_intent_slug(format_slug)
        if not slug:
            return None

        existing = crud_format.get_format_by_slug(self.db, slug)
        if existing:
            return existing

        resolved_name = (display_name or "").strip() or INTENT_NAME_MAP.get(slug, slug)
        existing_by_name = self.db.execute(select(Format).filter(Format.name == resolved_name)).scalar_one_or_none()
        if existing_by_name:
            return existing_by_name

        try:
            created = crud_format.create_format(
                self.db,
                FormatCreate(name=resolved_name, slug=slug),
            )
            return created
        except Exception:
            self.db.rollback()
            return crud_format.get_format_by_slug(self.db, slug)

    def _resolve_default_user(self) -> Optional[User]:
        """优先使用ID=1用户，不存在时回退到首个用户。"""
        user = crud_user.get_user(self.db, 1)
        if user:
            return user
        return self.db.execute(select(User).order_by(User.id.asc()).limit(1)).scalar_one_or_none()

    def _resolve_post_author(self, creator_name: str, default_user: Optional[User]) -> Optional[User]:
        if creator_name:
            if creator_name in self._author_cache:
                cached = self._author_cache[creator_name]
                return cached or default_user
            user = crud_user.get_user_by_username(self.db, creator_name)
            self._author_cache[creator_name] = user
            if user:
                return user
        return default_user


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
                "comments_imported": 0,
                "views_imported": 0,
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
                "comments_imported": 0,
                "views_imported": 0,
                "errors": [str(e)]
            }
    
    def _import_categories(self, categories: List[Dict], stats: Dict[str, Any]):
        """导入分类"""
        for cat_data in categories:
            try:
                slug = (cat_data.get("slug") or "").strip()
                name = (cat_data.get("name") or "").strip()
                if not slug or not name:
                    continue

                existing_cat = crud_category.get_category_by_slug(self.db, slug)
                existing_cat_by_name = crud_category.get_category_by_name(self.db, name)
                if not existing_cat and not existing_cat_by_name:
                    category_data = CategoryCreate(
                        name=name,
                        slug=slug
                    )
                    crud_category.create_category(self.db, category_data)
                    stats["categories_imported"] += 1
            except Exception as e:
                self.db.rollback()
                stats["errors"].append(f"导入分类失败: {str(e)}")
    
    def _import_tags(self, tags: List[Dict], stats: Dict[str, Any]):
        """导入标签"""
        for tag_data in tags:
            try:
                slug = (tag_data.get("slug") or "").strip()
                name = (tag_data.get("name") or "").strip()
                if not slug or not name:
                    continue

                existing_tag = crud_tag.get_tag_by_slug(self.db, slug)
                existing_tag_by_name = crud_tag.get_tag_by_name(self.db, name)
                if not existing_tag and not existing_tag_by_name:
                    tag_create = TagCreate(
                        name=name,
                        slug=slug
                    )
                    crud_tag.create_tag(self.db, tag_create)
                    stats["tags_imported"] += 1
            except Exception as e:
                self.db.rollback()
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
                self.db.rollback()
                stats["errors"].append(f"导入设置失败: {str(e)}")
    
    def _import_posts(self, posts: List[Dict], stats: Dict[str, Any]):
        """导入文章"""
        default_user: Optional[User] = None
        for post_data in posts:
            try:
                existing_post = crud_post.get_post_by_slug(self.db, post_data["slug"])
                if not existing_post:
                    # 解析日期
                    created_at = self._parse_iso_datetime(post_data.get("created_at"))
                    published_at = self._parse_iso_datetime(post_data.get("published_at"))
                    updated_at = self._parse_iso_datetime(post_data.get("updated_at"))
                    raw_markdown = post_data.get("content_markdown", "")
                    raw_html = post_data.get("content_html")
                    editor_mode = "markdown"
                    if (raw_html or "").strip() and not (raw_markdown or "").strip():
                        editor_mode = "html"
                    
                    post_create = PostCreate(
                        title=post_data["title"],
                        slug=post_data["slug"],
                        content_markdown=raw_markdown,
                        content_html=raw_html,
                        editor_mode=post_data.get("editor_mode") or editor_mode,
                        excerpt=post_data.get("excerpt", ""),
                        featured_image_url=post_data.get("featured_image_url"),
                        post_type=post_data.get("post_type", "post"),
                        page_template=post_data.get("page_template", "default"),
                        status=post_data.get("status", "published"),
                        visibility=post_data.get("visibility", "public"),
                        password=post_data.get("password"),
                        allow_comments=post_data.get("allow_comments", True),
                        license_type=post_data.get("license_type", "cc_by_nc_sa_4"),
                        created_at=created_at,
                        published_at=published_at,
                        updated_at=updated_at,
                    )
                    
                    # 获取默认用户作为作者
                    if default_user is None:
                        default_user = self._resolve_default_user()
                        if not default_user:
                            stats["errors"].append("导入文章失败: 未找到可用作者账户，请先创建管理员用户后重试")
                            return
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
                self.db.rollback()
                stats["errors"].append(f"导入文章失败: {str(e)}")

    def _parse_iso_datetime(self, date_str: Optional[str]) -> Optional[datetime]:
        if not date_str:
            return None
        try:
            parsed = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            return self._normalize_datetime(parsed)
        except Exception:
            return None

    def _normalize_datetime(self, dt: Optional[datetime]) -> Optional[datetime]:
        if dt is None:
            return None
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    def _resolve_default_user(self) -> Optional[User]:
        """优先使用ID=1用户，不存在时回退到首个用户。"""
        user = crud_user.get_user(self.db, 1)
        if user:
            return user
        return self.db.execute(select(User).order_by(User.id.asc()).limit(1)).scalar_one_or_none()


# 便捷函数
def get_data_export_manager(db: Session) -> DataExportManager:
    """获取数据导出管理器实例"""
    return DataExportManager(db)


def get_wordpress_importer(
    db: Session,
    options: Optional[Dict[str, Any]] = None,
    progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> WordPressImporter:
    """获取WordPress导入器实例"""
    return WordPressImporter(db, options=options, progress_callback=progress_callback)


def get_rewrz_importer(db: Session) -> RewrZImporter:
    """获取RewrZ导入器实例"""
    return RewrZImporter(db)



