from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, func
from ..models import Category
from ..schemas import CategoryCreate, CategoryUpdate

def get_category(db: Session, category_id: int):
    return db.execute(select(Category).filter(Category.id == category_id)).scalar_one_or_none()

def get_category_by_slug(db: Session, slug: str):
    return db.execute(select(Category).filter(Category.slug == slug)).scalar_one_or_none()

def get_categories(db: Session, skip: int = 0, limit: int = 100):
    return db.execute(select(Category).options(selectinload(Category.posts)).offset(skip).limit(limit)).scalars().all()

def get_all_categories(db: Session):
    """获取所有分类（不分页）"""
    return db.execute(select(Category).options(selectinload(Category.posts))).scalars().all()

def count_categories(db: Session) -> int:
    """
    计算所有分类的数量
    """
    return db.execute(select(func.count(Category.id))).scalar_one()

def get_category_by_name(db: Session, name: str):
    """根据分类名称获取分类"""
    return db.execute(select(Category).filter(Category.name == name)).scalar_one_or_none()

def create_category(db: Session, category: CategoryCreate):
    db_category = Category(name=category.name, slug=category.slug, parent_id=category.parent_id)
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