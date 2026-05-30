from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slugify import slugify

from .. import crud, schemas
from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token


router = APIRouter(
    prefix="/api/v1/categories",
    tags=["categories"],
    responses={404: {"description": "Not found"}},
)


class CategoryBulkAction(BaseModel):
    action: str
    category_ids: List[int]


@router.post("/")
def create_category(
    request: Request,
    name: str = Form(...),
    slug: Optional[str] = Form(None),
    parent_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
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
def read_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    categories = crud.category.get_categories(db, skip=skip, limit=limit)
    return categories


@router.post("/bulk-action")
def bulk_action_categories(
    request: Request,
    payload: CategoryBulkAction,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    action = (payload.action or "").strip().lower()
    if action != "delete":
        raise HTTPException(status_code=400, detail="Invalid action")

    category_ids = []
    seen = set()
    for category_id in payload.category_ids or []:
        try:
            value = int(category_id)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        category_ids.append(value)

    try:
        result = crud.category.bulk_delete_categories(db, category_ids=category_ids)
    except Exception as exc:
        db.rollback()
        failed = [{"id": category_id, "reason": str(exc) or "未知错误"} for category_id in category_ids]
        return {
            "success": False,
            "action": "delete",
            "requested_count": len(category_ids),
            "deleted_count": 0,
            "failed_count": len(failed),
            "deleted_ids": [],
            "failed": failed,
        }

    deleted_ids = result["deleted_ids"]
    missing_ids = set(result["missing_ids"])
    blocked_by_posts_ids = set(result["blocked_by_posts_ids"])
    blocked_by_children_ids = set(result["blocked_by_children_ids"])

    failed = []
    for category_id in category_ids:
        if category_id in missing_ids:
            failed.append({"id": category_id, "reason": "分类不存在"})
        elif category_id in blocked_by_posts_ids:
            failed.append({"id": category_id, "reason": "分类下存在文章关联，无法删除"})
        elif category_id in blocked_by_children_ids:
            failed.append({"id": category_id, "reason": "分类存在子分类关联，无法删除"})

    return {
        "success": len(failed) == 0,
        "action": "delete",
        "requested_count": len(category_ids),
        "deleted_count": len(deleted_ids),
        "failed_count": len(failed),
        "deleted_ids": deleted_ids,
        "failed": failed,
    }


@router.get("/{category_id}", response_model=schemas.Category)
def read_category(category_id: int, db: Session = Depends(get_db)):
    db_category = crud.category.get_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return db_category


@router.put("/{category_id}")
def update_category(
    request: Request,
    category_id: int,
    name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    parent_id: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
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
def delete_category(
    request: Request,
    category_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    db_category = crud.category.delete_category(db, category_id=category_id)
    if db_category is None:
        raise HTTPException(status_code=404, detail="Category not found")
    return {"success": True, "data": db_category}
