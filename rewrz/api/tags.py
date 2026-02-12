from typing import List, Optional

from fastapi import APIRouter, Depends, Form, HTTPException
from sqlalchemy.orm import Session
from slugify import slugify

from .. import crud, schemas
from ..core.database import get_db


router = APIRouter(
    prefix="/api/v1/tags",
    tags=["tags"],
    responses={404: {"description": "Not found"}},
)
legacy_router = APIRouter(
    prefix="/api/tags",
    tags=["tags"],
    responses={404: {"description": "Not found"}},
)


@router.post("/")
@legacy_router.post("/")
def create_tag(
    name: str = Form(...),
    slug: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
    if not slug:
        slug = slugify(name)

    tag = schemas.TagCreate(name=name, slug=slug)
    db_tag = crud.tag.create_tag(db=db, tag=tag)
    return {"success": True, "data": db_tag}


@router.get("/", response_model=List[schemas.Tag])
@legacy_router.get("/", response_model=List[schemas.Tag])
def read_tags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tags = crud.tag.get_tags(db, skip=skip, limit=limit)
    return tags


@router.get("/{tag_id}", response_model=schemas.Tag)
@legacy_router.get("/{tag_id}", response_model=schemas.Tag)
def read_tag(tag_id: int, db: Session = Depends(get_db)):
    db_tag = crud.tag.get_tag(db, tag_id=tag_id)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return db_tag


@router.put("/{tag_id}")
@legacy_router.put("/{tag_id}")
def update_tag(
    tag_id: int,
    name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    db: Session = Depends(get_db),
):
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
@legacy_router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    db_tag = crud.tag.delete_tag(db, tag_id=tag_id)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"success": True, "data": db_tag}
