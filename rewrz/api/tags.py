from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.orm import Session
from typing import List, Optional
from .. import crud, schemas
from ..core.database import get_db
from slugify import slugify

router = APIRouter(
    prefix="/api/tags",
    tags=["tags"],
    responses={404: {"description": "Not found"}},
)

@router.post("/")
def create_tag(
    name: str = Form(...),
    slug: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # 如果slug为空，则根据name自动生成
    if not slug:
        slug = slugify(name)
    
    tag = schemas.TagCreate(
        name=name,
        slug=slug
    )
    db_tag = crud.tag.create_tag(db=db, tag=tag)
    return {"success": True, "data": db_tag}

@router.get("/", response_model=List[schemas.Tag])
def read_tags(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    tags = crud.tag.get_tags(db, skip=skip, limit=limit)
    return tags

@router.get("/{tag_id}", response_model=schemas.Tag)
def read_tag(tag_id: int, db: Session = Depends(get_db)):
    db_tag = crud.tag.get_tag(db, tag_id=tag_id)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return db_tag

@router.put("/{tag_id}")
def update_tag(
    tag_id: int,
    name: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    db: Session = Depends(get_db)
):
    # 构建更新数据
    update_data = {}
    if name is not None:
        update_data["name"] = name
    if slug is not None:
        update_data["slug"] = slug
    
    # 如果slug为空且name不为空，则根据name自动生成slug
    if "slug" not in update_data and "name" in update_data:
        update_data["slug"] = slugify(update_data["name"])
    elif "slug" in update_data and not update_data["slug"] and "name" in update_data:
        update_data["slug"] = slugify(update_data["name"])
    
    # 创建TagUpdate对象
    tag_update = schemas.TagUpdate(**update_data)
    db_tag = crud.tag.update_tag(db, tag_id=tag_id, tag_update=tag_update)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"success": True, "data": db_tag}

@router.delete("/{tag_id}")
def delete_tag(tag_id: int, db: Session = Depends(get_db)):
    db_tag = crud.tag.delete_tag(db, tag_id=tag_id)
    if db_tag is None:
        raise HTTPException(status_code=404, detail="Tag not found")
    return {"success": True, "data": db_tag}
