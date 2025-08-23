"""
头像管理API模块

提供用户头像的上传、更新、删除功能。
支持自定义头像上传和Gravatar设置管理。
"""

import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Form
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from PIL import Image
from io import BytesIO
from ..core.database import get_db
from ..core.avatar import get_avatar_service
from ..crud import user as crud_user
from ..schemas import UserAvatarUpdate, User
from typing import Optional

router = APIRouter()


@router.post("/api/v1/users/{user_id}/avatar/upload")
async def upload_user_avatar(
    user_id: int,
    avatar_file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    上传用户自定义头像
    
    Args:
        user_id: 用户ID
        avatar_file: 头像文件
    """
    # TODO: 添加用户身份验证和权限检查
    
    # 检查用户是否存在
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 获取头像服务
    avatar_service = get_avatar_service(db)
    
    # 验证文件
    if not avatar_file.filename:
        raise HTTPException(status_code=400, detail="请选择文件")
    
    # 读取文件内容以获取大小
    file_content = await avatar_file.read()
    file_size = len(file_content)
    
    # 验证文件
    is_valid, error_msg = avatar_service.validate_avatar_file(avatar_file.filename, file_size)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)
    
    try:
        # 验证是否为有效图片
        try:
            image = Image.open(BytesIO(file_content))
            image.verify()  # 验证图片完整性
        except Exception:
            raise HTTPException(status_code=400, detail="文件不是有效的图片格式")
        
        # 重新打开图片进行处理（verify后需要重新打开）
        image = Image.open(BytesIO(file_content))
        
        # 自动调整图片大小（最大300x300）
        max_size = (300, 300)
        if image.size[0] > max_size[0] or image.size[1] > max_size[1]:
            image.thumbnail(max_size, Image.Resampling.LANCZOS)
        
        # 确保上传目录存在
        upload_dir = avatar_service.avatar_upload_path
        os.makedirs(upload_dir, exist_ok=True)
        
        # 生成新文件名
        new_filename = avatar_service.generate_avatar_filename(user_id, avatar_file.filename)
        file_path = avatar_service.get_avatar_file_path(new_filename)
        
        # 删除旧头像文件（如果存在）
        if user.avatar_filename:
            old_file_path = avatar_service.get_avatar_file_path(user.avatar_filename)
            if os.path.exists(old_file_path):
                os.remove(old_file_path)
        
        # 保存新图片
        # 转换为RGB模式以确保兼容性
        if image.mode in ('RGBA', 'LA'):
            # 创建白色背景
            background = Image.new('RGB', image.size, (255, 255, 255))
            if image.mode == 'RGBA':
                background.paste(image, mask=image.split()[-1])  # 使用alpha通道作为mask
            else:
                background.paste(image)
            image = background
        elif image.mode != 'RGB':
            image = image.convert('RGB')
        
        # 保存为JPEG格式以减小文件大小
        final_filename = new_filename.rsplit('.', 1)[0] + '.jpg'
        final_file_path = avatar_service.get_avatar_file_path(final_filename)
        image.save(final_file_path, 'JPEG', quality=85, optimize=True)
        
        # 更新用户头像信息
        avatar_url = avatar_service.get_avatar_url_from_filename(final_filename)
        user.avatar_filename = final_filename
        user.avatar_url = avatar_url
        user.use_gravatar = "disabled"  # 使用自定义头像时禁用Gravatar
        
        db.commit()
        db.refresh(user)
        
        return {
            "message": "头像上传成功",
            "avatar_url": avatar_url,
            "filename": final_filename
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"头像上传失败：{str(e)}")


@router.put("/api/v1/users/{user_id}/avatar/settings")
async def update_avatar_settings(
    user_id: int,
    avatar_settings: UserAvatarUpdate,
    db: Session = Depends(get_db)
):
    """
    更新用户头像设置
    
    Args:
        user_id: 用户ID
        avatar_settings: 头像设置
    """
    # TODO: 添加用户身份验证和权限检查
    
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 更新设置
    if avatar_settings.use_gravatar is not None:
        if avatar_settings.use_gravatar not in ["auto", "enabled", "disabled"]:
            raise HTTPException(status_code=400, detail="无效的Gravatar设置")
        user.use_gravatar = avatar_settings.use_gravatar
    
    if avatar_settings.avatar_url is not None:
        user.avatar_url = avatar_settings.avatar_url
    
    db.commit()
    db.refresh(user)
    
    return {"message": "头像设置更新成功"}


@router.delete("/api/v1/users/{user_id}/avatar")
async def delete_user_avatar(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    删除用户自定义头像
    
    Args:
        user_id: 用户ID
    """
    # TODO: 添加用户身份验证和权限检查
    
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    if not user.avatar_filename:
        raise HTTPException(status_code=404, detail="用户没有自定义头像")
    
    # 删除头像文件
    avatar_service = get_avatar_service(db)
    file_path = avatar_service.get_avatar_file_path(user.avatar_filename)
    
    if os.path.exists(file_path):
        os.remove(file_path)
    
    # 清除头像信息
    user.avatar_filename = None
    user.avatar_url = None
    user.use_gravatar = "auto"  # 恢复自动模式
    
    db.commit()
    db.refresh(user)
    
    return {"message": "头像删除成功"}


@router.get("/api/v1/users/{user_id}/avatar")
async def get_user_avatar_info(
    user_id: int,
    db: Session = Depends(get_db)
):
    """
    获取用户头像信息
    
    Args:
        user_id: 用户ID
    """
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    avatar_service = get_avatar_service(db)
    
    # 获取最终头像URL
    final_avatar_url = avatar_service.get_avatar_url(
        email=user.email,
        user_id=user.id
    )
    
    # 获取Gravatar URL（用于预览）
    gravatar_url = avatar_service.get_gravatar_url(user.email) if user.email else ""
    
    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "custom_avatar_url": user.avatar_url,
        "gravatar_url": gravatar_url,
        "final_avatar_url": final_avatar_url,
        "use_gravatar": user.use_gravatar,
        "has_custom_avatar": bool(user.avatar_filename)
    }


@router.get("/media/avatars/{filename}")
async def serve_avatar_file(filename: str):
    """
    提供头像文件访问
    
    Args:
        filename: 头像文件名
    """
    # 安全检查：只允许访问头像目录中的文件
    if '..' in filename or '/' in filename or '\\' in filename:
        raise HTTPException(status_code=400, detail="无效的文件名")
    
    # 获取文件路径
    file_path = os.path.join("media_uploads/avatars", filename)
    
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="头像文件不存在")
    
    # 返回文件
    return FileResponse(
        path=file_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",  # 缓存1天
            "ETag": f'"{filename}"'
        }
    )


@router.get("/api/v1/avatar/preview")
async def preview_gravatar(
    email: str,
    size: int = 80,
    db: Session = Depends(get_db)
):
    """
    预览Gravatar头像
    
    Args:
        email: 邮箱地址
        size: 头像尺寸
    """
    avatar_service = get_avatar_service(db)
    gravatar_url = avatar_service.get_gravatar_url(email, size)
    
    if not gravatar_url:
        raise HTTPException(status_code=400, detail="无法生成Gravatar URL")
    
    return {
        "email": email,
        "gravatar_url": gravatar_url,
        "size": size
    }