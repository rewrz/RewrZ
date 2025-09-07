from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..crud import format as crud_format
from ..schemas import Format, FormatCreate, FormatUpdate, User

router = APIRouter()

@router.get("/api/v1/formats", response_model=List[Format])
async def get_formats(
    skip: int = 0,
    limit: int = 100,
    db: Session = Depends(get_db)
):
    """获取所有格式列表"""
    formats = crud_format.get_formats(db, skip=skip, limit=limit)
    return formats

@router.get("/api/v1/formats/{format_id}", response_model=Format)
async def get_format(format_id: int, db: Session = Depends(get_db)):
    """根据ID获取格式"""
    db_format = crud_format.get_format(db, format_id=format_id)
    if db_format is None:
        raise HTTPException(status_code=404, detail="Format not found")
    return db_format

@router.get("/api/v1/formats/slug/{slug}", response_model=Format)
async def get_format_by_slug(slug: str, db: Session = Depends(get_db)):
    """根据slug获取格式"""
    db_format = crud_format.get_format_by_slug(db, slug=slug)
    if db_format is None:
        raise HTTPException(status_code=404, detail="Format not found")
    return db_format

@router.post("/api/v1/formats", response_model=Format)
async def create_format(
    format: FormatCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """创建新格式（仅管理员）"""
    return crud_format.create_format(db=db, format=format)

@router.put("/api/v1/formats/{format_id}", response_model=Format)
async def update_format(
    format_id: int,
    format_update: FormatUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """更新格式（仅管理员）"""
    db_format = crud_format.update_format(db, format_id=format_id, format_update=format_update)
    if db_format is None:
        raise HTTPException(status_code=404, detail="Format not found")
    return db_format

@router.delete("/api/v1/formats/{format_id}")
async def delete_format(
    format_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """删除格式（仅管理员）"""
    db_format = crud_format.delete_format(db, format_id=format_id)
    if db_format is None:
        raise HTTPException(status_code=404, detail="Format not found")
    return {"message": "Format deleted successfully"}