"""
数据导入导出API模块

提供数据导入导出功能的HTTP接口，包括：
1. 数据导出（JSON格式）
2. 备份包创建和下载
3. WordPress WXR文件导入
4. RewrZ JSON文件导入
"""

import os
import json
import tempfile
from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile, Form
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..core.data_manager import (
    get_data_export_manager, 
    get_wordpress_importer, 
    get_rewrz_importer
)
from ..schemas import User
from datetime import datetime

router = APIRouter()
templates = get_templates()


async def data_management_page(
    request: Request,
    db: Session,
    current_user: User
):
    """
    数据管理页面
    
    显示数据导入导出的管理界面
    """
    return templates.TemplateResponse("admin/data_management.html", {
        "request": request,
        "user": current_user,
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })


@router.get("/api/export/json")
async def export_data_json(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导出数据为JSON格式
    
    返回包含所有博客数据的JSON文件
    """
    try:
        export_manager = get_data_export_manager(db)
        data = export_manager.export_all_data()
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rewrz_export_{timestamp}.json"
        
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.json', 
            delete=False,
            encoding='utf-8'
        )
        
        try:
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()
            
            return FileResponse(
                path=temp_file.name,
                filename=filename,
                media_type='application/json',
                background=lambda: os.unlink(temp_file.name)  # 下载后删除临时文件
            )
            
        except Exception as e:
            if not temp_file.closed:
                temp_file.close()
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise e
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/api/export/backup")
async def export_backup_package(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建并下载完整备份包
    
    包含数据文件和媒体文件的ZIP包
    """
    try:
        export_manager = get_data_export_manager(db)
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 创建备份包
            backup_path = export_manager.create_backup_package(temp_dir)
            
            if not os.path.exists(backup_path):
                raise HTTPException(status_code=500, detail="备份包创建失败")
            
            return FileResponse(
                path=backup_path,
                filename=os.path.basename(backup_path),
                media_type='application/zip',
                background=lambda: _cleanup_temp_files(temp_dir)
            )
            
        except Exception as e:
            _cleanup_temp_files(temp_dir)
            raise e
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"备份失败: {str(e)}")


@router.post("/api/import/wordpress")
async def import_wordpress_data(
    wxr_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导入WordPress WXR文件
    
    支持WordPress标准导出格式
    """
    if not wxr_file.filename.endswith('.xml'):
        raise HTTPException(status_code=400, detail="请上传XML格式的WXR文件")
    
    # 检查文件大小（限制50MB）
    max_size = 50 * 1024 * 1024  # 50MB
    content = await wxr_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大50MB）")
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.xml',
        delete=False
    )
    
    try:
        temp_file.write(content)
        temp_file.close()
        
        # 执行导入
        importer = get_wordpress_importer(db)
        result = importer.import_from_wxr(temp_file.name)
        
        return JSONResponse({
            "success": True,
            "message": "WordPress数据导入完成",
            "stats": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}"
        }, status_code=500)
        
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


@router.post("/api/import/rewrz")
async def import_rewrz_data(
    json_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导入RewrZ JSON文件
    
    支持RewrZ标准导出格式
    """
    if not json_file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="请上传JSON格式的数据文件")
    
    # 检查文件大小（限制10MB）
    max_size = 10 * 1024 * 1024  # 10MB
    content = await json_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大10MB）")
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.json',
        delete=False
    )
    
    try:
        temp_file.write(content)
        temp_file.close()
        
        # 执行导入
        importer = get_rewrz_importer(db)
        result = importer.import_from_json(temp_file.name)
        
        return JSONResponse({
            "success": True,
            "message": "RewrZ数据导入完成",
            "stats": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}"
        }, status_code=500)
        
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


@router.post("/api/import/backup")
async def import_backup_package(
    backup_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导入完整备份包
    
    支持RewrZ备份ZIP文件
    """
    if not backup_file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="请上传ZIP格式的备份文件")
    
    # 检查文件大小（限制100MB）
    max_size = 100 * 1024 * 1024  # 100MB
    content = await backup_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大100MB）")
    
    import zipfile
    import shutil
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存上传的ZIP文件
        zip_path = os.path.join(temp_dir, backup_file.filename)
        with open(zip_path, 'wb') as f:
            f.write(content)
        
        # 解压ZIP文件
        extract_dir = os.path.join(temp_dir, "extracted")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # 查找数据文件
        data_file = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.json') and 'rewrz' in file.lower():
                    data_file = os.path.join(root, file)
                    break
            if data_file:
                break
        
        if not data_file:
            raise HTTPException(status_code=400, detail="备份包中未找到有效的数据文件")
        
        # 导入数据
        importer = get_rewrz_importer(db)
        result = importer.import_from_json(data_file)
        
        # 恢复媒体文件
        media_restored = 0
        media_dir = os.path.join(extract_dir, "media")
        if os.path.exists(media_dir):
            target_media_dir = "media_uploads"
            if not os.path.exists(target_media_dir):
                os.makedirs(target_media_dir)
            
            for root, dirs, files in os.walk(media_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, media_dir)
                    dst_path = os.path.join(target_media_dir, rel_path)
                    
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    
                    if not os.path.exists(dst_path):
                        shutil.copy2(src_path, dst_path)
                        media_restored += 1
        
        result["media_restored"] = media_restored
        
        return JSONResponse({
            "success": True,
            "message": "备份包导入完成",
            "stats": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}"
        }, status_code=500)
        
    finally:
        _cleanup_temp_files(temp_dir)


@router.get("/api/data/stats")
async def get_data_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取数据统计信息
    
    用于显示当前博客的数据概况
    """
    try:
        from ..crud import post as crud_post
        from ..crud import category as crud_category
        from ..crud import tag as crud_tag
        from ..crud import media as crud_media
        from ..crud import setting as crud_setting
        
        # 统计数据
        posts_count = len(crud_post.get_all_posts(db))
        categories_count = len(crud_category.get_all_categories(db))
        tags_count = len(crud_tag.get_all_tags(db))
        media_count = len(crud_media.get_all_media(db))
        settings_count = len(crud_setting.get_all_settings(db))
        
        # 计算媒体文件总大小
        import os
        media_items = crud_media.get_all_media(db)
        total_media_size = 0
        for item in media_items:
            # 获取实际文件大小
            if os.path.exists(item.filepath):
                total_media_size += os.path.getsize(item.filepath)
            # 如果文件不存在，尝试从文件名推断路径
            elif os.path.exists(os.path.join("media_uploads", item.filepath)):
                total_media_size += os.path.getsize(os.path.join("media_uploads", item.filepath))
            # 如果还是找不到文件，则跳过
        
        # 格式化文件大小
        def format_file_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
        
        return JSONResponse({
            "posts": posts_count,
            "categories": categories_count,
            "tags": tags_count,
            "media_files": media_count,
            "settings": settings_count,
            "total_media_size": format_file_size(total_media_size),
            "total_media_size_bytes": total_media_size
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


def _cleanup_temp_files(temp_dir: str):
    """清理临时文件和目录"""
    try:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"清理临时文件失败: {str(e)}")
