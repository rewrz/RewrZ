"""
Avatar management API.
"""

from io import BytesIO
import os

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from PIL import Image
from sqlalchemy.orm import Session

from ..core.avatar import get_avatar_service
from ..core.database import get_db
from ..core.security import get_current_user
from ..crud import user as crud_user
from ..schemas import User, UserAvatarUpdate

router = APIRouter()


def _ensure_avatar_permission(target_user_id: int, current_user: User) -> None:
    if current_user.id != target_user_id:
        raise HTTPException(status_code=403, detail="Not authorized to modify this avatar")


@router.post("/api/v1/users/{user_id}/avatar/upload")
async def upload_user_avatar(
    user_id: int,
    avatar_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_avatar_permission(user_id, current_user)

    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    avatar_service = get_avatar_service(db)

    if not avatar_file.filename:
        raise HTTPException(status_code=400, detail="Please choose a file")

    file_content = await avatar_file.read()
    file_size = len(file_content)
    is_valid, error_msg = avatar_service.validate_avatar_file(avatar_file.filename, file_size)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    try:
        # Validate image integrity first.
        verify_image = Image.open(BytesIO(file_content))
        verify_image.verify()
    except Exception as exc:
        raise HTTPException(status_code=400, detail="File is not a valid image") from exc

    try:
        image = Image.open(BytesIO(file_content))
        image.thumbnail((300, 300), Image.Resampling.LANCZOS)

        os.makedirs(avatar_service.avatar_upload_path, exist_ok=True)

        if user.avatar_filename:
            old_file_path = avatar_service.get_avatar_file_path(user.avatar_filename)
            if os.path.exists(old_file_path):
                os.remove(old_file_path)

        new_filename = avatar_service.generate_avatar_filename(user_id, avatar_file.filename)
        final_filename = f"{new_filename.rsplit('.', 1)[0]}.jpg"
        final_file_path = avatar_service.get_avatar_file_path(final_filename)

        if image.mode in ("RGBA", "LA"):
            background = Image.new("RGB", image.size, (255, 255, 255))
            if image.mode == "RGBA":
                background.paste(image, mask=image.split()[-1])
            else:
                background.paste(image)
            image = background
        elif image.mode != "RGB":
            image = image.convert("RGB")

        image.save(final_file_path, "JPEG", quality=85, optimize=True)

        avatar_url = avatar_service.get_avatar_url_from_filename(final_filename)
        user.avatar_filename = final_filename
        user.avatar_url = avatar_url
        user.use_gravatar = "disabled"
        db.commit()
        db.refresh(user)

        return {
            "message": "Avatar uploaded successfully",
            "avatar_url": avatar_url,
            "filename": final_filename,
        }
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Avatar upload failed: {exc}") from exc


@router.put("/api/v1/users/{user_id}/avatar/settings")
async def update_avatar_settings(
    user_id: int,
    avatar_settings: UserAvatarUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_avatar_permission(user_id, current_user)

    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if avatar_settings.use_gravatar is not None:
        if avatar_settings.use_gravatar not in ["auto", "enabled", "disabled"]:
            raise HTTPException(status_code=400, detail="Invalid gravatar mode")
        user.use_gravatar = avatar_settings.use_gravatar

    if avatar_settings.avatar_url is not None:
        user.avatar_url = avatar_settings.avatar_url

    db.commit()
    db.refresh(user)
    return {"message": "Avatar settings updated successfully"}


@router.delete("/api/v1/users/{user_id}/avatar")
async def delete_user_avatar(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ensure_avatar_permission(user_id, current_user)

    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.avatar_filename:
        raise HTTPException(status_code=404, detail="User does not have a custom avatar")

    avatar_service = get_avatar_service(db)
    file_path = avatar_service.get_avatar_file_path(user.avatar_filename)
    if os.path.exists(file_path):
        os.remove(file_path)

    user.avatar_filename = None
    user.avatar_url = None
    user.use_gravatar = "auto"
    db.commit()
    db.refresh(user)
    return {"message": "Avatar deleted successfully"}


@router.get("/api/v1/users/{user_id}/avatar")
async def get_user_avatar_info(
    user_id: int,
    db: Session = Depends(get_db),
):
    user = crud_user.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    avatar_service = get_avatar_service(db)
    final_avatar_url = avatar_service.get_avatar_url(email=user.email, user_id=user.id)
    gravatar_url = avatar_service.get_gravatar_url(user.email) if user.email else ""

    return {
        "user_id": user.id,
        "username": user.username,
        "email": user.email,
        "custom_avatar_url": user.avatar_url,
        "gravatar_url": gravatar_url,
        "final_avatar_url": final_avatar_url,
        "use_gravatar": user.use_gravatar,
        "has_custom_avatar": bool(user.avatar_filename),
    }


@router.get("/media/avatars/{filename}")
async def serve_avatar_file(
    filename: str,
    db: Session = Depends(get_db),
):
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")

    avatar_service = get_avatar_service(db)
    file_path = avatar_service.get_avatar_file_path(filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="Avatar file not found")

    return FileResponse(
        path=file_path,
        media_type="image/jpeg",
        headers={
            "Cache-Control": "public, max-age=86400",
            "ETag": f'"{filename}"',
        },
    )


@router.get("/api/v1/avatar/preview")
async def preview_gravatar(
    email: str,
    size: int = 80,
    db: Session = Depends(get_db),
):
    avatar_service = get_avatar_service(db)
    gravatar_url = avatar_service.get_gravatar_url(email, size)
    if not gravatar_url:
        raise HTTPException(status_code=400, detail="Could not generate gravatar URL")

    return {
        "email": email,
        "gravatar_url": gravatar_url,
        "size": size,
    }
