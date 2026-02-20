from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey, JSON, Table
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from .base import Base
from .category import Category
from .tag import Tag
from .format import Format # Import the new Format model

# Many-to-many association table for posts and categories
post_categories = Table(
    "post_categories",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id"), primary_key=True),
)

# Many-to-many association table for posts and tags
post_tags = Table(
    "post_tags",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)

# Many-to-many association table for posts and formats
post_formats = Table(
    "post_formats",
    Base.metadata,
    Column("post_id", Integer, ForeignKey("posts.id"), primary_key=True),
    Column("format_id", Integer, ForeignKey("formats.id"), primary_key=True),
)

class Post(Base):
    __tablename__ = "posts"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String, nullable=False)
    slug = Column(String, unique=True, index=True, nullable=False)
    content_markdown = Column(Text, nullable=False)
    content_html = Column(Text, nullable=False)
    excerpt = Column(Text, nullable=True)
    featured_image_url = Column(String, nullable=True)
    post_type = Column(String, nullable=False, default="article") # 'article' or 'page'
    page_template = Column(String, nullable=False, default="default") # 页面模板，仅 page 类型生效
    status = Column(String, nullable=False, default="draft") # 'published' or 'draft'
    visibility = Column(String, nullable=False, default="public") # 'public', 'private', 'password'
    password = Column(String, nullable=True) # Hashed password
    allow_comments = Column(Boolean, default=True)
    license_type = Column(String, default="cc_by_nc_sa_4") # 版权协议类型
    version_snapshots = Column(JSON, default=[])
    created_at = Column(DateTime, default=func.now())
    published_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, default=func.now(), onupdate=func.now())
    author_id = Column(Integer, ForeignKey("users.id"))

    author = relationship("User")
    categories = relationship("Category", secondary=post_categories, backref="posts")
    tags = relationship("Tag", secondary=post_tags, backref="posts")
    formats = relationship("Format", secondary=post_formats, backref="posts")
    from sqlalchemy.orm import joinedload
    comments = relationship(
        "Comment",
        primaryjoin="and_(Post.id == Comment.post_id, Comment.status == 'approved')",
        order_by="Comment.created_at.asc()",
        lazy="selectin",  # 使用 selectin 加载以优化性能
        viewonly=True    # 这个关系是只读的，避免在修改时出现问题
    )
