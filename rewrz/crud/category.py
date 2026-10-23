from sqlalchemy.orm import Session
from sqlalchemy import select, func
from ..models import Category, Post
from ..models.post import post_categories
from ..schemas import CategoryCreate, CategoryUpdate
from ..core.time_utils import utc_now_naive

def get_category(db: Session, category_id: int):
    return db.execute(select(Category).filter(Category.id == category_id)).scalar_one_or_none()

def get_category_by_slug(db: Session, slug: str):
    return db.execute(select(Category).filter(Category.slug == slug)).scalar_one_or_none()

def get_categories(db: Session, skip: int = 0, limit: int = 100):
    return db.execute(select(Category).offset(skip).limit(limit)).scalars().all()

def get_all_categories(db: Session):
    """获取所有分类（不分页）"""
    return db.execute(select(Category)).scalars().all()


def get_published_post_category_counts(db: Session) -> dict[int, int]:
    """按分类聚合已发布文章数量，避免加载分类下的全部文章。"""
    rows = db.execute(
        select(post_categories.c.category_id, func.count(Post.id))
        .join(Post, Post.id == post_categories.c.post_id)
        .where(
            Post.status == "published",
            Post.post_type == "post",
            Post.visibility == "public",
            Post.published_at.isnot(None),
            Post.published_at <= utc_now_naive(),
        )
        .group_by(post_categories.c.category_id)
    ).all()
    return {int(category_id): int(count) for category_id, count in rows if category_id is not None}

def count_categories(db: Session) -> int:
    """
    计算所有分类的数量
    """
    return db.execute(select(func.count(Category.id))).scalar_one()

def get_category_by_name(db: Session, name: str):
    """根据分类名称获取分类"""
    return db.execute(select(Category).filter(Category.name == name)).scalar_one_or_none()

def create_category(db: Session, category: CategoryCreate):
    db_category = Category(
        name=category.name, 
        slug=category.slug, 
        parent_id=category.parent_id,
        description=category.description
    )
    db.add(db_category)
    db.commit()
    db.refresh(db_category)
    return db_category

def update_category(db: Session, category_id: int, category_update: CategoryUpdate):
    db_category = db.execute(select(Category).filter(Category.id == category_id)).scalar_one_or_none()
    if db_category:
        for key, value in category_update.model_dump(exclude_unset=True).items():
            setattr(db_category, key, value)
        db.commit()
        db.refresh(db_category)
    return db_category

def delete_category(db: Session, category_id: int):
    db_category = db.execute(select(Category).filter(Category.id == category_id)).scalar_one_or_none()
    if db_category:
        db.delete(db_category)
        db.commit()
    return db_category


def bulk_delete_categories(db: Session, category_ids: list[int]):
    """批量删除分类（单事务提交），并返回可用于前端提示的删除结果。"""
    if not category_ids:
        return {
            "deleted_ids": [],
            "missing_ids": [],
            "blocked_by_posts_ids": [],
            "blocked_by_children_ids": [],
        }

    existing_ids = set(
        db.execute(select(Category.id).filter(Category.id.in_(category_ids))).scalars().all()
    )
    if not existing_ids:
        return {
            "deleted_ids": [],
            "missing_ids": category_ids,
            "blocked_by_posts_ids": [],
            "blocked_by_children_ids": [],
        }

    blocked_by_posts_ids = set(
        db.execute(
            select(post_categories.c.category_id)
            .filter(post_categories.c.category_id.in_(existing_ids))
            .distinct()
        ).scalars().all()
    )
    blocked_by_children_ids = set(
        db.execute(
            select(Category.parent_id)
            .filter(
                Category.parent_id.in_(existing_ids),
                ~Category.id.in_(existing_ids),
            )
            .distinct()
        ).scalars().all()
    )

    blocked_ids = blocked_by_posts_ids | blocked_by_children_ids
    deletable_ids = [category_id for category_id in category_ids if category_id in existing_ids and category_id not in blocked_ids]

    if deletable_ids:
        db.query(Category).filter(Category.id.in_(deletable_ids)).delete(synchronize_session=False)
        db.commit()

    missing_ids = [category_id for category_id in category_ids if category_id not in existing_ids]
    return {
        "deleted_ids": deletable_ids,
        "missing_ids": missing_ids,
        "blocked_by_posts_ids": [category_id for category_id in category_ids if category_id in blocked_by_posts_ids],
        "blocked_by_children_ids": [category_id for category_id in category_ids if category_id in blocked_by_children_ids],
    }
