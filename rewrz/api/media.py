from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..core.config import settings
from ..core.database import get_db
from ..core.media_processor import get_media_processor
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..crud import media as crud_media
from ..models.media import Media as MediaModel
from ..schemas import Media, MediaCreate, MediaUpdate, User

router = APIRouter()
templates = get_templates()

class MediaBulkDeleteRequest(BaseModel):
    media_ids: List[int] = Field(default_factory=list)


UPLOAD_ROOT = Path(settings.MEDIA_UPLOAD_DIR).resolve()
os.makedirs(UPLOAD_ROOT, exist_ok=True)


def _media_url_from_filepath(filepath: str) -> str:
    if not filepath:
        return ""
    try:
        relative_path = Path(filepath).resolve().relative_to(UPLOAD_ROOT).as_posix()
    except Exception:
        return ""
    return f"/media/{relative_path}"


def _attach_media_url(media_obj: MediaModel) -> MediaModel:
    media_obj.url = _media_url_from_filepath(media_obj.filepath)
    return media_obj


def _safe_unlink(path: Path) -> None:
    try:
        if path.exists() and path.is_file():
            path.unlink()
    except OSError:
        pass


def _delete_media_files(db_media: MediaModel) -> None:
    original_path = Path(db_media.filepath)
    _safe_unlink(original_path)

    # Thumbnail files are generated under the same month directory: /YYYY/MM/thumbnails/
    thumbnails_dir = original_path.parent / "thumbnails"
    if thumbnails_dir.exists():
        for thumb_file in thumbnails_dir.glob(f"{original_path.stem}_*"):
            _safe_unlink(thumb_file)

    _safe_unlink(original_path.with_suffix(".webp"))


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/media", response_class=HTMLResponse)
async def media_library_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    media_items = crud_media.get_all_media(db=db)
    for item in media_items:
        _attach_media_url(item)

    return templates.TemplateResponse(
        "admin/media.html",
        {
            "request": request,
            "user": current_user,
            "media_items": media_items,
        },
    )


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media", response_model=List[Media])
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media", response_model=List[Media])
async def get_media_items_api(
    request: Request,
    page: int = 1,
    limit: int = 12,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    skip = (page - 1) * limit
    media_items = crud_media.get_all_media(db=db, skip=skip, limit=limit, search=search)
    for item in media_items:
        _attach_media_url(item)
    return media_items


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/media/upload", response_model=Media)
async def upload_media(
    request: Request,
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    auto_process: bool = Form(True),
    generate_thumbnails: bool = Form(True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    media_processor = get_media_processor(db)

    original_name = Path(file.filename or "upload.bin").name
    file_content = await file.read()
    file_size = len(file_content)

    is_valid, error_msg = media_processor.validate_upload_file(
        original_name,
        file_size,
        file.content_type,
    )
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_msg)

    now = datetime.now()
    sub_dir = Path(now.strftime("%Y")) / now.strftime("%m")
    target_dir = UPLOAD_ROOT / sub_dir
    target_dir.mkdir(parents=True, exist_ok=True)

    unique_name = f"{os.urandom(8).hex()}_{original_name}"
    filepath = target_dir / unique_name

    try:
        filepath.write_bytes(file_content)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to save file: {exc}") from exc

    file_info = media_processor.get_file_info(str(filepath))

    if file_info.get("file_type") == "image" and auto_process:
        try:
            media_processor.extract_image_metadata(str(filepath))
            if media_processor.auto_compress:
                media_processor.optimize_image(str(filepath))
            if generate_thumbnails:
                thumb_dir = target_dir / "thumbnails"
                thumb_dir.mkdir(parents=True, exist_ok=True)
                media_processor.generate_thumbnails(str(filepath), str(thumb_dir))
            if media_processor.enable_webp:
                media_processor.generate_webp_version(str(filepath), str(target_dir))
        except Exception:
            # Processing failures should not block upload persistence.
            pass

    media_create = MediaCreate(
        filename=original_name,
        filepath=str(filepath),
        file_type=file_info.get("file_type", "other"),
        mime_type=file.content_type or file_info.get("mime_type") or "application/octet-stream",
        title=title or Path(original_name).stem,
        alt_text=alt_text,
        description=description,
    )

    db_media = crud_media.create_media(db=db, media=media_create, uploaded_by_id=current_user.id)
    _attach_media_url(db_media)
    return db_media


@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}", response_model=Media)
@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}", response_model=Media)
def get_media_item(
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_media = db.execute(
        select(MediaModel)
        .filter(MediaModel.id == media_id)
        .options(joinedload(MediaModel.uploaded_by))
    ).scalar_one_or_none()

    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")

    _attach_media_url(db_media)
    return db_media


@router.put(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}", response_model=Media)
@router.put(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}", response_model=Media)
def update_media_item(
    request: Request,
    media_id: int,
    media_update: MediaUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)

    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this media file")

    updated_media = crud_media.update_media(db=db, media_id=media_id, media_update=media_update)
    _attach_media_url(updated_media)
    return updated_media


@router.delete(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/{{media_id}}", status_code=status.HTTP_204_NO_CONTENT)
@router.delete(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/{{media_id}}", status_code=status.HTTP_204_NO_CONTENT)
def delete_media_item(
    request: Request,
    media_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)

    db_media = crud_media.get_media(db, media_id=media_id)
    if db_media is None:
        raise HTTPException(status_code=404, detail="Media file not found")
    if db_media.uploaded_by_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this media file")

    _delete_media_files(db_media)
    crud_media.delete_media(db=db, media_id=media_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/v1/media/bulk-delete")
@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/api/media/bulk-delete")
def bulk_delete_media_items(
    request: Request,
    payload: MediaBulkDeleteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    media_ids = list(dict.fromkeys(payload.media_ids or []))
    if not media_ids:
        raise HTTPException(status_code=400, detail="No media IDs provided")

    deleted_ids: List[int] = []
    skipped: List[dict] = []

    for media_id in media_ids:
        db_media = crud_media.get_media(db, media_id=media_id)
        if db_media is None:
            skipped.append({"id": media_id, "reason": "not_found"})
            continue
        if db_media.uploaded_by_id != current_user.id:
            skipped.append({"id": media_id, "reason": "forbidden"})
            continue

        _delete_media_files(db_media)
        crud_media.delete_media(db=db, media_id=media_id)
        deleted_ids.append(media_id)

    return {
        "requested_count": len(media_ids),
        "deleted_count": len(deleted_ids),
        "deleted_ids": deleted_ids,
        "skipped": skipped,
    }
