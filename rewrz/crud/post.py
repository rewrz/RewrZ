"""文章CRUD操作模块

本模块提供文章相关的数据库操作功能，包括创建、读取、更新、删除文章。
支持多重身份内容系统和版本快照功能。
"""
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import select, func
from ..models import Post, Format, Category, Tag
from ..schemas import PostCreate, PostUpdate
from datetime import datetime
from markdown import markdown
from slugify import slugify
from ..core.security import get_password_hash, verify_password

from typing import Optional, List

def get_post(db: Session, post_id: int):
    """根据文章ID获取文章信息，包含关联的格式、分类、标签和评论"""
    from sqlalchemy.orm import selectinload
    from ..models import Comment
    return db.execute(
        select(Post)
        .options(
            joinedload(Post.formats), 
            joinedload(Post.categories), 
            joinedload(Post.tags),
            selectinload(Post.comments).selectinload(Comment.children)  # 加载评论及其子评论
        )
        .filter(Post.id == post_id)
    ).unique().scalar_one_or_none()

def get_post_by_slug(db: Session, slug: str):
    """根据文章别名获取文章信息，包含关联的格式、分类、标签和评论"""
    from sqlalchemy.orm import selectinload
    from ..models import Comment
    return db.execute(
        select(Post)
        .options(
            joinedload(Post.formats), 
            joinedload(Post.categories), 
            joinedload(Post.tags),
            selectinload(Post.comments).selectinload(Comment.children)  # 加载评论及其子评论
        )
        .filter(Post.slug == slug)
    ).unique().scalar_one_or_none()

def get_posts(db: Session, skip: int = 0, limit: int = 100, status: Optional[str] = None, post_type: Optional[str] = None):
    """获取文章列表，支持分页和状态过滤"""
    query = select(Post).options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
    if status:
        # 确保文章状态为 'published' 且 published_at 不为空
        if status == "published":
            query = query.filter(Post.status == status, Post.published_at.isnot(None))
        else:
            query = query.filter(Post.status == status)
    if post_type:
        query = query.filter(Post.post_type == post_type)
    # 默认按发布时间降序排列
    query = query.order_by(Post.published_at.desc())
    return db.execute(query.offset(skip).limit(limit)).unique().scalars().all()


def get_posts_by_type(db: Session, post_type: str, limit: int = 100, skip: int = 0) -> List[Post]:
    """根据文章类型获取文章列表

    Args:
        db: 数据库会话
        post_type: 文章类型（例如 "post" 或 "page"）
        limit: 返回的最大数量
        skip: 跳过的数量

    Returns:
        符合条件的文章列表
    """
    return get_posts(db=db, post_type=post_type, limit=limit, skip=skip)

def get_all_posts(db: Session):
    """获取所有文章（不分页）"""
    query = select(Post).options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags), joinedload(Post.author))
    return db.execute(query).unique().scalars().all()

def count_posts_by_status(db: Session, status: str) -> int:
    """
    根据状态计算文章数量
    """
    return db.execute(select(func.count(Post.id)).filter(Post.status == status)).scalar_one()

def get_posts_by_category(db: Session, category_id: int, skip: int = 0, limit: int = 100):
    """根据分类ID获取文章列表"""
    return db.execute(
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(Post.categories.any(id=category_id))
        .offset(skip)
        .limit(limit)
    ).unique().scalars().all()

def get_posts_by_format(db: Session, format_id: int, skip: int = 0, limit: int = 100):
    """根据格式ID获取文章列表，仅返回已发布的文章"""
    return db.execute(
        select(Post)
        .options(joinedload(Post.formats), joinedload(Post.categories), joinedload(Post.tags))
        .filter(Post.formats.any(id=format_id))
        .filter(Post.status == "published")
        .offset(skip)
        .limit(limit)
    ).unique().scalars().all()

def create_post(db: Session, post: PostCreate, author_id: int, tag_names: Optional[List[str]] = None, format_ids: Optional[List[int]] = None):
    """创建新文章
    
    自动处理：
    - Markdown转换为HTML
    - 自动生成摘要
    - 自动生成唯一别名
    - 密码哈希加密
    """
    # 将Markdown转换为HTML
    content_html = markdown(post.content_markdown)
    # 如果没有提供摘要，则自动生成
    excerpt = post.excerpt if post.excerpt else post.content_markdown[:120]

    # 如果没有提供别名，则从标题生成，并确保唯一性
    if post.slug:
        base_slug = post.slug
    else:
        base_slug = slugify(post.title)
    
    slug = base_slug
    i = 1
    # 检查别名是否已存在，如果存在则添加数字后缀
    while db.execute(select(Post).filter(Post.slug == slug)).scalar_one_or_none():
        slug = f"{base_slug}-{i}"
        i += 1

    db_post = Post(
        title=post.title,
        slug=slug,
        content_markdown=post.content_markdown,
        content_html=content_html,
        excerpt=excerpt,
        featured_image_url=str(post.featured_image_url) if post.featured_image_url else None,
        post_type=post.post_type,
        status=post.status,
        visibility=post.visibility,
        password=get_password_hash(post.password) if post.password else None,
        allow_comments=post.allow_comments,
        version_snapshots=post.version_snapshots,
        author_id=author_id,
        published_at=datetime.now() if post.status == "published" else None
    )

    # 如果指定了分类ID，则关联对应的分类
    if post.category_ids:
        categories = db.execute(select(Category).filter(Category.id.in_(post.category_ids))).scalars().all()
        db_post.categories.extend(categories)

    # 如果指定了标签名称，则创建或获取标签并关联
    if tag_names:
        for tag_name in tag_names:
            tag = db.execute(select(Tag).filter(Tag.name == tag_name)).scalar_one_or_none()
            if not tag:
                tag = Tag(name=tag_name, slug=slugify(tag_name))
                db.add(tag)
                db.flush() # 确保tag有ID
            db_post.tags.append(tag)
    
    # 如果指定了格式ID，则关联对应的格式（多重身份内容系统）
    if format_ids:
        formats = db.execute(select(Format).filter(Format.id.in_(format_ids))).scalars().all()
        db_post.formats.extend(formats)

    db.add(db_post)
    db.commit()
    db.refresh(db_post)
    return db_post

def update_post(db: Session, post_id: int, post: PostUpdate, tag_names: Optional[List[str]] = None, format_ids: Optional[List[int]] = None):
    """更新文章信息
    
    自动处理：
    - 版本快照保存
    - Markdown转换
    - 别名更新
    - 发布时间管理
    """
    db_post = db.execute(select(Post).filter(Post.id == post_id)).scalar_one_or_none()
    if db_post:
        # 保存旧内容作为版本快照
        old_content = db_post.content_markdown
        if old_content:
            db_post.version_snapshots.insert(0, {"timestamp": datetime.now().isoformat(), "content": old_content})
            if len(db_post.version_snapshots) > 5:
                db_post.version_snapshots.pop()

        update_data = post.model_dump(exclude_unset=True)
        
        # 单独处理密码哈希
        if 'password' in update_data and update_data['password']:
            # 仅在密码实际发生变化时才进行哈希
            new_password = update_data['password']
            # 检查新密码是否与当前密码不同（明文 vs 哈希值）
            if not db_post.password or not verify_password(new_password, db_post.password):
                print(f"Hashing password: {new_password}")
                hashed_password = get_password_hash(new_password)
                print(f"Hashed password: {hashed_password}")
                db_post.password = hashed_password
            del update_data['password']  # 从更新数据中移除，避免重复设置

        # 确保featured_image_url字段被处理
        if hasattr(post, 'featured_image_url') and post.featured_image_url is not None:
            db_post.featured_image_url = post.featured_image_url
        elif hasattr(post, 'featured_image_url') and post.featured_image_url is None:
            db_post.featured_image_url = None

        for key, value in update_data.items():
            if key == "content_markdown":
                db_post.content_markdown = value # 添加这一行来更新 content_markdown
                db_post.content_html = markdown(value)
            elif key == "title": # 如果标题发生变化，更新别名并确保唯一性
                base_slug = slugify(value)
                slug = base_slug
                i = 1
                # 检查别名是否已存在，如果存在则添加数字后缀
                while db.execute(select(Post).filter(Post.slug == slug)).scalar_one_or_none():
                    slug = f"{base_slug}-{i}"
                    i += 1
                db_post.slug = slug
            elif key == "excerpt" and not value and db_post.content_markdown: # 如果内容变化且摘要为空，则自动生成摘要
                db_post.excerpt = db_post.content_markdown[:120]
            # 跳过featured_image_url，因为它已经在上面处理过了
            elif key != "featured_image_url":
                setattr(db_post, key, value)
        
        # 如果状态变为已发布，更新发布时间
        if post.status == "published" and db_post.published_at is None:
            db_post.published_at = datetime.now()
        elif post.status != "published" and db_post.published_at is not None:
            db_post.published_at = None # 或者保持不变，取决于具体取消发布的需求

        if post.category_ids:
            db_post.categories.clear()
            categories = db.execute(select(Category).filter(Category.id.in_(post.category_ids))).scalars().all()
            db_post.categories.extend(categories)

        # 更新标签
        if tag_names is not None:
            db_post.tags.clear()
            for tag_name in tag_names:
                tag = db.execute(select(Tag).filter(Tag.name == tag_name)).scalar_one_or_none()
                if not tag:
                    tag = Tag(name=tag_name, slug=slugify(tag_name))
                    db.add(tag)
                    db.flush()
                db_post.tags.append(tag)

        # 更新内容格式
        if format_ids is not None:
            db_post.formats.clear()
            formats = db.execute(select(Format).filter(Format.id.in_(format_ids))).scalars().all()
            db_post.formats.extend(formats)

        # 确保 updated_at 设置为当前时间
        import time
        time.sleep(0.001)  # 添加小延迟以确保 updated_at 与之前的时间不同
        db_post.updated_at = datetime.now()
        db.commit()
        db.refresh(db_post)
    return db_post

def delete_post(db: Session, post_id: int):
    """删除文章
    
    Args:
        db: 数据库会话
        post_id: 文章ID
        
    Returns:
        被删除的文章对象
    """
    db_post = db.execute(select(Post).filter(Post.id == post_id)).scalar_one_or_none()
    if db_post:
        db.delete(db_post)
        db.commit()
    return db_post
