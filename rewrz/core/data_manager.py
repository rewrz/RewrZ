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
from datetime import datetime, timezone
from typing import Dict, List, Optional, Any, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..crud import setting as crud_setting
from ..crud import media as crud_media
from ..crud import user as crud_user
from ..models import Post, Category, Tag, Format, Media, User, Comment
from ..schemas import PostCreate, CategoryCreate, TagCreate, FormatCreate, SettingCreate, SettingUpdate
import re
from .template_context import DEFAULT_BASE_SETTINGS

DEFAULT_WP_IMPORT_OPTIONS = {
    "import_post_types": ["post", "page"],
    "import_comments": True,
    "import_views": True,
    "postmeta_whitelist": ["views", "post_views_count"],
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
    
    def __init__(self, db: Session, options: Optional[Dict[str, Any]] = None):
        self.db = db
        self.namespaces = {
            'wp': 'http://wordpress.org/export/1.2/',
            'content': 'http://purl.org/rss/1.0/modules/content/',
            'excerpt': 'http://wordpress.org/export/1.2/excerpt/',
            'dc': 'http://purl.org/dc/elements/1.1/'
        }
        self._author_cache: Dict[str, Optional[User]] = {}
        self.options = self._normalize_import_options(options)

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

        merged["import_comments"] = bool(merged.get("import_comments", True))
        merged["import_views"] = bool(merged.get("import_views", True))
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
            tree = ET.parse(wxr_file_path)
            root = tree.getroot()
            
            # 导入统计
            stats = {
                "posts_imported": 0,
                "categories_imported": 0,
                "tags_imported": 0,
                "comments_imported": 0,
                "views_imported": 0,
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
                "comments_imported": 0,
                "views_imported": 0,
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
    
    def _import_wp_tags(self, root: ET.Element, stats: Dict[str, Any]):
        """导入WordPress标签"""
        tags = root.findall('.//wp:tag', self.namespaces)
        
        for tag_elem in tags:
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
    
    def _import_wp_posts(self, root: ET.Element, stats: Dict[str, Any]):
        """导入WordPress文章"""
        default_user: Optional[User] = None
        items = root.findall('.//item')
        
        for item in items:
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
                    slug = (post_name.text or "").strip() if post_name is not None else ""
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
                        markdown_content = self._html_to_markdown(content_text)
                        if not (markdown_content or "").strip():
                            markdown_content = content_text
                        html_content = ""
                        editor_mode = "markdown"
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

                    new_post = crud_post.create_post(self.db, post_data, author.id)
                    
                    # 关联分类和标签
                    self._associate_wp_taxonomies(item, new_post)

                    # 导入评论
                    if self.options.get("import_comments", True):
                        self._import_wp_comments(item, new_post, stats)

                    # 导入阅读量（postmeta）
                    if self.options.get("import_views", True):
                        views_count = self._extract_wp_views_count(item)
                        if views_count is not None:
                            if self._upsert_post_views_metric(new_post.id, views_count):
                                stats["views_imported"] += 1
                    
                    stats["posts_imported"] += 1
                        
            except Exception as e:
                self.db.rollback()
                stats["errors"].append(f"导入文章失败: {str(e)}")

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
                self.db.commit()
                return

            remaining = next_round

        self.db.commit()

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

    def _upsert_post_views_metric(self, post_id: int, views_count: int) -> bool:
        key = f"post_views_count_{post_id}"
        setting_value = {"value": int(max(0, views_count))}
        existing = crud_setting.get_setting(self.db, key)
        if existing:
            updated = crud_setting.update_setting(
                self.db,
                key,
                SettingUpdate(
                    value=setting_value,
                    description="Imported WordPress post views",
                    category="post_metrics",
                    type="integer",
                ),
            )
            return updated is not None
        created = crud_setting.create_setting(
            self.db,
            SettingCreate(
                key=key,
                value=setting_value,
                description="Imported WordPress post views",
                category="post_metrics",
                type="integer",
            ),
        )
        return created is not None
    
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

        if wp_post_type in {"post", "article"}:
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

            # 关联内容格式（WordPress post_format taxonomy）
            format_items = item.findall('category[@domain="post_format"]')
            format_bound = False
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
            
            self.db.commit()
            
        except Exception as e:
            self.db.rollback()
            print(f"关联分类标签失败: {str(e)}")

    def _map_wp_post_format_slug(self, raw_nicename: str, raw_name: str) -> Optional[str]:
        """将 WordPress post_format 映射为 RewrZ 格式 slug。"""
        normalized = (raw_nicename or "").strip().lower()
        if normalized.startswith("post-format-"):
            normalized = normalized[len("post-format-"):]
        if not normalized:
            normalized = (raw_name or "").strip().lower()

        mapping = {
            "standard": "article",
            "post": "article",
            "article": "article",
            "aside": "micro-post",
            "status": "micro-post",
            "chat": "micro-post",
            "link": "micro-post",
            "quote": "micro-post",
            "image": "photo-album",
            "gallery": "photo-album",
            "video": "video",
            "audio": "poetry-song",
        }
        if normalized in mapping:
            return mapping[normalized]

        # 未知格式保留为自定义格式，避免信息丢失。
        custom_slug = re.sub(r"[^a-z0-9_-]+", "-", normalized).strip("-")
        return custom_slug or None

    def _ensure_post_format(self, format_slug: str, display_name: str) -> Optional[Format]:
        slug = (format_slug or "").strip().lower()
        if not slug:
            return None

        existing = crud_format.get_format_by_slug(self.db, slug)
        if existing:
            return existing

        fallback_name_map = {
            "article": "标准文章",
            "micro-post": "微博",
            "photo-album": "相册",
            "video": "视频",
            "poetry-song": "诗词歌赋",
        }
        resolved_name = (display_name or "").strip() or fallback_name_map.get(slug) or slug
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


def get_wordpress_importer(db: Session, options: Optional[Dict[str, Any]] = None) -> WordPressImporter:
    """获取WordPress导入器实例"""
    return WordPressImporter(db, options=options)


def get_rewrz_importer(db: Session) -> RewrZImporter:
    """获取RewrZ导入器实例"""
    return RewrZImporter(db)
