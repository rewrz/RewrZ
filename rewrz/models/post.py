from sqlalchemy import Column, Index, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Table
from sqlalchemy.orm import relationship
from ..core.time_utils import utc_now_naive
from .base import Base
from .category import Category
from .tag import Tag
from .format import Format # Import the new Format model

# Many-to-many association table for posts and categories
# 后台按分类/标签/格式筛选时走反向列，联合主键最左列 post_id 用不上，单独补索引
post_categories = Table(
    "post_categories",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id"), primary_key=True),
    Index("ix_post_categories_category_id", "category_id"),
)

# Many-to-many association table for posts and tags
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
    Index("ix_post_tags_tag_id", "tag_id"),
)

# Many-to-many association table for posts and formats
post_formats = Table(
    "post_formats",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("format_id", Integer, ForeignKey("formats.id"), primary_key=True),
    Index("ix_post_formats_format_id", "format_id"),
)

class Post(Base):
    __tablename__ = "posts"
    # 公开列表按 type/visibility/status 过滤并按 published_at 倒序；导航页按 type/status
    # 取已发布页面。两个索引覆盖这两类高频查询，避免全表扫描与临时排序。
    __table_args__ = (
        Index("ix_posts_public_listing", "post_type", "visibility", "status", "published_at"),
        Index("ix_posts_page_nav", "post_type", "status", "published_at"),
        # 后台列表按创建时间倒序分页、按状态单独统计，既有复合索引最左列用不上
        Index("ix_posts_status", "status"),
        Index("ix_posts_created_at", "created_at"),
    )

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    content_markdown = Column(Text, nullable=False)
    content_html = Column(Text, nullable=False)
    excerpt = Column(Text, nullable=True)
    featured_image_url = Column(String, nullable=True)
    media_attachment_summary = Column(JSON, nullable=False, default=dict)
    post_type = Column(String, nullable=False, default="post") # 'post'（文章）或 'page'（页面）
    page_template = Column(String, nullable=False, default="default") # 页面模板，仅 page 类型生效
    post_template = Column(String, nullable=False, default="auto") # 文章详情整页模板，仅标准文章生效
    style_preset = Column(String, nullable=False, default="auto") # 格式内样式预设，仅微动态/诗词生效
    status = Column(String, nullable=False, default="draft") # 'published' or 'draft'
    visibility = Column(String, nullable=False, default="public") # 'public', 'private', 'password'
    content_rating = Column(String, nullable=False, default="general") # 'general', 'sensitive', 'nsfw'
    password = Column(String, nullable=True) # Hashed password
    allow_comments = Column(Boolean, default=True)
    license_type = Column(String, default="cc_by_nc_sa_4") # 版权协议类型
    version_snapshots = Column(JSON, default=[])
    created_at = Column(DateTime, default=utc_now_naive)
    published_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive)
    author_id = Column(Integer, ForeignKey("users.id"))

    author = relationship("User")
    categories = relationship("Category", secondary=post_categories, backref="posts")
    tags = relationship("Tag", secondary=post_tags, backref="posts")
    formats = relationship("Format", secondary=post_formats, backref="posts")
    comments = relationship(
        "Comment",
        primaryjoin="and_(Post.id == Comment.post_id, Comment.status == 'approved')",
        order_by="Comment.created_at.asc()",
        lazy="select",  # 列表页不加载评论，详情页显式预加载
        viewonly=True    # 这个关系是只读的，避免在修改时出现问题
    )
