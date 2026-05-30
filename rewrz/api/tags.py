from typing import List, Optional

from fastapi import APIRouter, Depends, Form, Header, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from slugify import slugify

from .. import crud, schemas
from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token


router = APIRouter(
    prefix="/api/v1/tags",
    tags=["tags"],
    responses={404: {"description": "Not found"}},
)


class TagBulkAction(BaseModel):
    action: str
    tag_ids: List[int]


@router.post("/")
def create_tag(
    request: Request,
    name: str = Form(...),
    slug: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    if not slug:
        slug = slugify(name)

    tag = schemas.TagCreate(name=name, slug=slug)
    db_tag = crud.tag.create_tag(db=db, tag=tag)
    return {"success": True, "data": db_tag}


@router.get("/", response_model=List[schemas.Tag])
def read_tags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tags = crud.tag.get_tags(db, skip=skip, limit=limit)
    return tags


@router.post("/bulk-action")
def bulk_action_tags(
    request: Request,
    payload: TagBulkAction,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    action = (payload.action or "").strip().lower()
    if action != "delete":
        raise HTTPException(status_code=400, detail="Invalid action")

    tag_ids = []
    seen = set()
    for tag_id in payload.tag_ids or []:
        try:
            value = int(tag_id)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        tag_ids.append(value)

    try:
        result = crud.tag.bulk_delete_tags(db, tag_ids=tag_ids)
    except Exception as exc:
        db.rollback()
        failed = [{"id": tag_id, "reason": str(exc) or "未知错误"} for tag_id in tag_ids]
        return {
            "success": False,
            "action": "delete",
            "requested_count": len(tag_ids),
            "deleted_count": 0,
            "failed_count": len(failed),
            "deleted_ids": [],
            "failed": failed,
        }

    deleted_ids = result["deleted_ids"]
    missing_ids = set(result["missing_ids"])
    blocked_by_posts_ids = set(result["blocked_by_posts_ids"])

    failed = []
    for tag_id in tag_ids:
        if tag_id in missing_ids:
            failed.append({"id": tag_id, "reason": "标签不存在"})
        elif tag_id in blocked_by_posts_ids:
            failed.append({"id": tag_id, "reason": "标签存在文章关联，无法删除"})

    return {
        "success": len(failed) == 0,
        "action": "delete",
        "requested_count": len(tag_ids),
        "deleted_count": len(deleted_ids),
        "failed_count": len(failed),
        "deleted_ids": deleted_ids,
        "failed": failed,
    }


@router.get("/{tag_id}", response_model=schemas.Tag)
def read_tag(tag_id: int, db: Session = Depends(get_db)):
    db_tag = crud.tag.get_tag(db, tag_id=tag_id)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return db_tag


@router.put("/{tag_id}")
def update_tag(
    request: Request,
    tag_id: int,
    name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
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

    if "slug" not in update_data and "name" in update_data:
        update_data["slug"] = slugify(update_data["name"])
    elif "slug" in update_data and not update_data["slug"] and "name" in update_data:
        update_data["slug"] = slugify(update_data["name"])

    tag_update = schemas.TagUpdate(**update_data)
    db_tag = crud.tag.update_tag(db, tag_id=tag_id, tag_update=tag_update)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"success": True, "data": db_tag}


@router.delete("/{tag_id}")
def delete_tag(
    request: Request,
    tag_id: int,
    db: Session = Depends(get_db),
    current_user: schemas.User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    db_tag = crud.tag.delete_tag(db, tag_id=tag_id)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"success": True, "data": db_tag}
