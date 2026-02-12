from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from slugify import slugify

from .. import crud, schemas
from ..core.database import get_db


router = APIRouter(
    prefix="/api/v1/categories",
    tags=["categories"],
    responses={404: {"description": "Not found"}},
)
legacy_router = APIRouter(
    prefix="/api/categories",
    tags=["categories"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
@legacy_router.post("/")
def create_category(
    name: str = Form(...),
    slug: Optional[str] = Form(None),
    parent_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not slug:
        slug = slugify(name)

    category = schemas.CategoryCreate(
        name=name,
        slug=slug,
        parent_id=parent_id,
        description=description,
    )
    db_category = crud.category.create_category(db=db, category=category)
    return {"success": True, "data": db_category}


@router.get("/", response_model=List[schemas.Category])
@legacy_router.get("/", response_model=List[schemas.Category])
def read_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    categories = crud.category.get_categories(db, skip=skip, limit=limit)
    return categories


@router.get("/{category_id}", response_model=schemas.Category)
@legacy_router.get("/{category_id}", response_model=schemas.Category)
def read_category(category_id: int, db: Session = Depends(get_db)):
    db_category = crud.category.get_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return db_category


@router.put("/{category_id}")
@legacy_router.put("/{category_id}")
def update_category(
    category_id: int,
    name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    parent_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    update_data = {}
    if name is not None:
        update_data["name"] = name
    if slug is not None:
        update_data["slug"] = slug
    if parent_id is not None:
        update_data["parent_id"] = parent_id
    if description is not None:
        update_data["description"] = description

    if "slug" not in update_data and "name" in update_data:
        update_data["slug"] = slugify(update_data["name"])
    elif "slug" in update_data and not update_data["slug"] and "name" in update_data:
        update_data["slug"] = slugify(update_data["name"])

    category_update = schemas.CategoryUpdate(**update_data)
    db_category = crud.category.update_category(db, category_id=category_id, category_update=category_update)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True, "data": db_category}


@router.delete("/{category_id}")
@legacy_router.delete("/{category_id}")
def delete_category(category_id: int, db: Session = Depends(get_db)):
    db_category = crud.category.delete_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True, "data": db_category}
