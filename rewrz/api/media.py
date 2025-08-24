"""
媒体管理API模块

提供媒体文件的上传、管理、处理功能。
集成图像处理、缩略图生成、元数据提取等增强功能。
"""
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import shutil
import os
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..crud import media as crud_media
from ..schemas import Media, MediaCreate, MediaUpdate, User
from ..core.config import settings
from ..core.media_processor import get_media_processor  # 导入媒体处理器

router = APIRouter()

# 确保媒体上传目录存在
os.makedirs(settings.MEDIA_UPLOAD_DIR, exist_ok=True)
os.makedirs("media_uploads/thumbnails", exist_ok=True)  # 缩略图目录

@router.get("/admin/media", response_class=HTMLResponse)
async def media_library_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    媒体库管理页面
    
    显示所有上传的媒体文件，支持搜索、筛选、批量操作
    """
    templates = get_templates()
    media_items = crud_media.get_all_media(db=db) # 从请求状态获取数据库会话
    return templates.TemplateResponse("admin/media.html", {"request": request, "user": current_user, "media_items": media_items})

@router.post("/media/upload", response_model=Media)
async def upload_media(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    auto_process: bool = Form(True),  # 是否自动处理图像
    generate_thumbnails: bool = Form(True),  # 是否生成缩略图
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    上传媒体文件
    
    支持图像自动处理、缩略图生成、元数据提取等功能
    """
    # 获取媒体处理器
    media_processor = get_media_processor(db)
    
    # 验证文件
    file_content = await file.read()
    file_size = len(file_content)
    
    is_valid, error_msg = media_processor.validate_upload_file(
        file.filename, file_size, file.content_type
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 生成唯一文件名
    filename = f"{os.urandom(8).hex()}_{file.filename}"
    filepath = os.path.join(settings.MEDIA_UPLOAD_DIR, filename)
    
    # 保存原始文件
    try:
        with open(filepath, "wb") as buffer:
            buffer.write(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")
    
    # 获取文件信息
    file_info = media_processor.get_file_info(filepath)
    
    # 处理图像文件
    processed_info = {}
    thumbnails = {}
    
    if file_info['file_type'] == 'image' and auto_process:
        try:
            # 提取图像元数据
            image_metadata = media_processor.extract_image_metadata(filepath)
            processed_info['metadata'] = image_metadata
            
            # 优化原始图像
            if media_processor.auto_compress:
                optimization_result = media_processor.optimize_image(filepath)
                processed_info['optimization'] = optimization_result
            
            # 生成缩略图
            if generate_thumbnails:
                thumbnail_dir = os.path.join(settings.MEDIA_UPLOAD_DIR, "thumbnails")
                thumbnails = media_processor.generate_thumbnails(filepath, thumbnail_dir)
                processed_info['thumbnails'] = thumbnails
            
            # 生成WebP版本
            if media_processor.enable_webp:
                webp_path = media_processor.generate_webp_version(filepath, settings.MEDIA_UPLOAD_DIR)
                if webp_path:
                    processed_info['webp_version'] = webp_path
            
        except Exception as e:
            print(f"图像处理失败: {e}")
            processed_info['processing_error'] = str(e)

    # 确定文件类型和MIME类型
    mime_type = file.content_type or file_info.get('mime_type', 'application/octet-stream')
    file_type = file_info['file_type']
    
    # 创建媒体数据库记录
    media_create = MediaCreate(
        filename=file.filename,
        filepath=filepath,
        file_type=file_type,
        mime_type=mime_type,
        title=title or Path(file.filename).stem,
        alt_text=alt_text,
        description=description
    )
    
    # 保存到数据库
    db_media = crud_media.create_media(
        db=db, 
        media=media_create, 
        uploaded_by_id=current_user.id
    )
    
    # 返回包含处理信息的响应
    response_data = db_media.__dict__.copy()
    if processed_info:
        response_data['processing_info'] = processed_info
    
    return response_data

@router.get("/media/{media_id}", response_model=Media)
def get_media_item(media_id: int, db: Session = Depends(get_db)):
    """
    获取媒体文件详情
    
    包含文件信息、处理状态、缩略图等完整信息
    """
    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    return db_media

@router.put("/media/{media_id}", response_model=Media)
def update_media_item(
    media_id: int,
    media_update: MediaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新媒体文件信息
    
    允许更新标题、替代文本、描述等元数据
    """
    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限修改此媒体文件")
    return crud_media.update_media(db=db, media_id=media_id, media_update=media_update)

@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_item(media_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    删除媒体文件
    
    同时删除原文件、缩略图和WebP版本
    """
    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限删除此媒体文件")
    
    # 删除主文件
    if os.path.exists(db_media.filepath):
        os.remove(db_media.filepath)
    
    # 删除相关的缩略图和处理文件
    file_stem = Path(db_media.filepath).stem
    
    # 删除缩略图
    thumbnail_dir = os.path.join(settings.MEDIA_UPLOAD_DIR, "thumbnails")
    if os.path.exists(thumbnail_dir):
        for thumbnail_file in os.listdir(thumbnail_dir):
            if thumbnail_file.startswith(file_stem):
                thumbnail_path = os.path.join(thumbnail_dir, thumbnail_file)
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
    
    # 删除WebP版本
    webp_path = os.path.join(settings.MEDIA_UPLOAD_DIR, f"{file_stem}.webp")
    if os.path.exists(webp_path):
        os.remove(webp_path)
    
    # 从数据库删除记录
    crud_media.delete_media(db=db, media_id=media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from sqlalchemy.orm import Session
from typing import List, Optional
from pathlib import Path
import shutil
import os
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..crud import media as crud_media
from ..schemas import Media, MediaCreate, MediaUpdate, User
from ..core.config import settings
from ..core.media_processor import get_media_processor  # 导入媒体处理器

router = APIRouter()

# 确保媒体上传目录存在
os.makedirs(settings.MEDIA_UPLOAD_DIR, exist_ok=True)
os.makedirs("media_uploads/thumbnails", exist_ok=True)  # 缩略图目录

@router.get("/admin/media", response_class=HTMLResponse)
async def media_library_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    媒体库管理页面
    
    显示所有上传的媒体文件，支持搜索、筛选、批量操作
    """
    templates = get_templates()
    media_items = crud_media.get_all_media(db=db) # 从请求状态获取数据库会话
    return templates.TemplateResponse("admin/media.html", {"request": request, "user": current_user, "media_items": media_items})

@router.post("/media/upload", response_model=Media)
async def upload_media(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    auto_process: bool = Form(True),  # 是否自动处理图像
    generate_thumbnails: bool = Form(True),  # 是否生成缩略图
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    上传媒体文件
    
    支持图像自动处理、缩略图生成、元数据提取等功能
    """
    # 获取媒体处理器
    media_processor = get_media_processor(db)
    
    # 验证文件
    file_content = await file.read()
    file_size = len(file_content)
    
    is_valid, error_msg = media_processor.validate_upload_file(
        file.filename, file_size, file.content_type
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    # 生成唯一文件名
    filename = f"{os.urandom(8).hex()}_{file.filename}"
    filepath = os.path.join(settings.MEDIA_UPLOAD_DIR, filename)
    
    # 保存原始文件
    try:
        with open(filepath, "wb") as buffer:
            buffer.write(file_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"文件保存失败：{str(e)}")
    
    # 获取文件信息
    file_info = media_processor.get_file_info(filepath)
    
    # 处理图像文件
    processed_info = {}
    thumbnails = {}
    
    if file_info['file_type'] == 'image' and auto_process:
        try:
            # 提取图像元数据
            image_metadata = media_processor.extract_image_metadata(filepath)
            processed_info['metadata'] = image_metadata
            
            # 优化原始图像
            if media_processor.auto_compress:
                optimization_result = media_processor.optimize_image(filepath)
                processed_info['optimization'] = optimization_result
            
            # 生成缩略图
            if generate_thumbnails:
                thumbnail_dir = os.path.join(settings.MEDIA_UPLOAD_DIR, "thumbnails")
                thumbnails = media_processor.generate_thumbnails(filepath, thumbnail_dir)
                processed_info['thumbnails'] = thumbnails
            
            # 生成WebP版本
            if media_processor.enable_webp:
                webp_path = media_processor.generate_webp_version(filepath, settings.MEDIA_UPLOAD_DIR)
                if webp_path:
                    processed_info['webp_version'] = webp_path
            
        except Exception as e:
            print(f"图像处理失败: {e}")
            processed_info['processing_error'] = str(e)

    # 确定文件类型和MIME类型
    mime_type = file.content_type or file_info.get('mime_type', 'application/octet-stream')
    file_type = file_info['file_type']
    
    # 创建媒体数据库记录
    media_create = MediaCreate(
        filename=file.filename,
        filepath=filepath,
        file_type=file_type,
        mime_type=mime_type,
        title=title or Path(file.filename).stem,
        alt_text=alt_text,
        description=description
    )
    
    # 保存到数据库
    db_media = crud_media.create_media(
        db=db, 
        media=media_create, 
        uploaded_by_id=current_user.id
    )
    
    # 返回包含处理信息的响应
    response_data = db_media.__dict__.copy()
    if processed_info:
        response_data['processing_info'] = processed_info
    
    return response_data

@router.get("/media/{media_id}", response_model=Media)
def get_media_item(media_id: int, db: Session = Depends(get_db)):
    """
    获取媒体文件详情
    
    包含文件信息、处理状态、缩略图等完整信息
    """
    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    return db_media

@router.put("/media/{media_id}", response_model=Media)
def update_media_item(
    media_id: int,
    media_update: MediaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新媒体文件信息
    
    允许更新标题、替代文本、描述等元数据
    """
    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限修改此媒体文件")
    return crud_media.update_media(db=db, media_id=media_id, media_update=media_update)

@router.delete("/media/{media_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_item(media_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    删除媒体文件
    
    同时删除原文件、缩略图和WebP版本
    """
    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="媒体文件不存在")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="无权限删除此媒体文件")
    
    # 删除主文件
    if os.path.exists(db_media.filepath):
        os.remove(db_media.filepath)
    
    # 删除相关的缩略图和处理文件
    file_stem = Path(db_media.filepath).stem
    
    # 删除缩略图
    thumbnail_dir = os.path.join(settings.MEDIA_UPLOAD_DIR, "thumbnails")
    if os.path.exists(thumbnail_dir):
        for thumbnail_file in os.listdir(thumbnail_dir):
            if thumbnail_file.startswith(file_stem):
                thumbnail_path = os.path.join(thumbnail_dir, thumbnail_file)
                if os.path.exists(thumbnail_path):
                    os.remove(thumbnail_path)
    
    # 删除WebP版本
    webp_path = os.path.join(settings.MEDIA_UPLOAD_DIR, f"{file_stem}.webp")
    if os.path.exists(webp_path):
        os.remove(webp_path)
    
    # 从数据库删除记录
    crud_media.delete_media(db=db, media_id=media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
