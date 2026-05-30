from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.api_keys import ensure_api_key_permission, get_current_external_api_key
from ..core.database import get_db
from ..crud import category as crud_category
from ..crud import media as crud_media
from ..crud import post as crud_post
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..models import Post as PostModel
from ..models.media import Media as MediaModel
from ..schemas import PostCreate, PostUpdate
from . import media as media_api


router = APIRouter(prefix="/api/external/v1", tags=["external"])


def _external_list_response(
    *,
    items: List[Dict[str, Any]],
    page: int,
    per_page: int,
) -> Dict[str, Any]:
    current_page = max(1, int(page))
    current_per_page = max(1, int(per_page))
    return {
        "success": True,
        "items": items,
        "pagination": {
            "page": current_page,
            "per_page": current_per_page,
            "count": len(items),
            "has_next": len(items) == current_per_page,
        },
    }


def _external_data_response(data: Dict[str, Any]) -> Dict[str, Any]:
    return {"success": True, "data": data}


def _external_deleted_response() -> Dict[str, Any]:
    return {"success": True}


def _serialize_post(post_obj: PostModel) -> Dict[str, Any]:
    return {
        "id": int(post_obj.id),
        "title": str(post_obj.title or ""),
        "slug": str(post_obj.slug or ""),
        "excerpt": str(post_obj.excerpt or ""),
        "featured_image_url": str(getattr(post_obj, "featured_image_url", "") or ""),
        "post_type": str(post_obj.post_type or ""),
        "page_template": str(getattr(post_obj, "page_template", "default") or "default"),
        "status": str(post_obj.status or ""),
        "visibility": str(post_obj.visibility or ""),
        "allow_comments": bool(getattr(post_obj, "allow_comments", True)),
        "license_type": str(getattr(post_obj, "license_type", "") or ""),
        "content_markdown": str(getattr(post_obj, "content_markdown", "") or ""),
        "content_html": str(getattr(post_obj, "content_html", "") or ""),
        "author_id": int(getattr(post_obj, "author_id", 0) or 0),
        "created_at": post_obj.created_at.isoformat() if getattr(post_obj, "created_at", None) else None,
        "published_at": post_obj.published_at.isoformat() if getattr(post_obj, "published_at", None) else None,
        "updated_at": post_obj.updated_at.isoformat() if getattr(post_obj, "updated_at", None) else None,
        "categories": [
            {"id": int(item.id), "name": str(item.name or ""), "slug": str(item.slug or "")}
            for item in (getattr(post_obj, "categories", None) or [])
        ],
        "tags": [
            {"id": int(item.id), "name": str(item.name or ""), "slug": str(item.slug or "")}
            for item in (getattr(post_obj, "tags", None) or [])
        ],
        "formats": [
            {"id": int(item.id), "name": str(item.name or ""), "slug": str(item.slug or "")}
            for item in (getattr(post_obj, "formats", None) or [])
        ],
    }


def _serialize_media(media_obj: MediaModel) -> Dict[str, Any]:
    return {
        "id": int(media_obj.id),
        "filename": str(media_obj.filename or ""),
        "title": str(getattr(media_obj, "title", "") or ""),
        "file_type": str(media_obj.file_type or ""),
        "mime_type": str(media_obj.mime_type or ""),
        "folder": str(getattr(media_obj, "folder", "") or ""),
        "url": str(getattr(media_obj, "url", "") or ""),
        "preview_url": str(getattr(media_obj, "preview_url", "") or ""),
        "uploaded_at": media_obj.uploaded_at.isoformat() if getattr(media_obj, "uploaded_at", None) else None,
        "uploaded_by_id": int(getattr(media_obj, "uploaded_by_id", 0) or 0),
    }


def _get_intent_format_id(db: Session, post_type: str, requested_format_ids: Optional[List[int]]) -> Optional[List[int]]:
    normalized_post_type = str(post_type or "").strip().lower()
    if normalized_post_type == "page":
        return None
    if requested_format_ids:
        return requested_format_ids
    article_format = crud_format.get_format_by_slug(db, "article")
    if article_format is None:
        return None
    return [article_format.id]


@router.get("/posts")
async def list_external_posts(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "posts.read")
    skip = (page - 1) * per_page
    posts = crud_post.get_posts(db, skip=skip, limit=per_page, post_type="post")
    return _external_list_response(
        items=[_serialize_post(item) for item in posts],
        page=page,
        per_page=per_page,
    )


@router.get("/posts/{post_id}")
async def get_external_post(
    post_id: int,
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "posts.read")
    post_obj = crud_post.get_post(db, post_id)
    if post_obj is None or str(post_obj.post_type or "") != "post":
        raise HTTPException(status_code=404, detail="文章不存在")
    return _external_data_response(_serialize_post(post_obj))


@router.post("/posts")
async def create_external_post(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "posts.write")

    status_value = str(payload.get("status", "draft") or "draft").strip().lower()
    if status_value == "published":
        ensure_api_key_permission(api_key, "posts.publish")

    format_ids = payload.get("format_ids") if isinstance(payload.get("format_ids"), list) else None
    post_create = PostCreate(
        title=str(payload.get("title", "") or "").strip(),
        slug=payload.get("slug"),
        content_markdown=str(payload.get("content_markdown", "") or ""),
        content_html=payload.get("content_html"),
        editor_mode=payload.get("editor_mode"),
        excerpt=payload.get("excerpt"),
        featured_image_url=payload.get("featured_image_url"),
        post_type="post",
        status=status_value,
        visibility=str(payload.get("visibility", "public") or "public"),
        password=payload.get("password"),
        allow_comments=bool(payload.get("allow_comments", True)),
        category_ids=payload.get("category_ids"),
        tag_ids=payload.get("tag_ids"),
        format_ids=_get_intent_format_id(db, "post", format_ids),
        license_type=str(payload.get("license_type", "cc_by_nc_sa_4") or "cc_by_nc_sa_4"),
    )
    created = crud_post.create_post(
        db=db,
        post=post_create,
        author_id=int(getattr(api_key, "created_by_user_id", 0) or 0),
        format_ids=post_create.format_ids,
    )
    return _external_data_response(_serialize_post(created))


@router.patch("/posts/{post_id}")
async def update_external_post(
    post_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "posts.write")
    post_obj = crud_post.get_post(db, post_id)
    if post_obj is None or str(post_obj.post_type or "") != "post":
        raise HTTPException(status_code=404, detail="文章不存在")

    next_status = payload.get("status")
    if next_status is not None and str(next_status).strip().lower() == "published":
        ensure_api_key_permission(api_key, "posts.publish")

    update_data = PostUpdate(
        title=payload.get("title"),
        slug=payload.get("slug"),
        content_markdown=payload.get("content_markdown"),
        content_html=payload.get("content_html"),
        editor_mode=payload.get("editor_mode"),
        excerpt=payload.get("excerpt"),
        featured_image_url=payload.get("featured_image_url"),
        post_type="post",
        status=payload.get("status", post_obj.status),
        visibility=payload.get("visibility", post_obj.visibility),
        password=payload.get("password"),
        allow_comments=payload.get("allow_comments", post_obj.allow_comments),
        category_ids=payload.get("category_ids"),
        tag_ids=payload.get("tag_ids"),
        format_ids=payload.get("format_ids"),
        license_type=payload.get("license_type", post_obj.license_type),
    )
    updated = crud_post.update_post(db, post_id, update_data, format_ids=payload.get("format_ids"))
    return _external_data_response(_serialize_post(updated))


@router.delete("/posts/{post_id}")
async def delete_external_post(
    post_id: int,
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "posts.delete")
    post_obj = crud_post.get_post(db, post_id)
    if post_obj is None or str(post_obj.post_type or "") != "post":
        raise HTTPException(status_code=404, detail="文章不存在")
    crud_post.delete_post(db, post_id)
    return _external_deleted_response()


@router.get("/pages")
async def list_external_pages(
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "pages.read")
    skip = (page - 1) * per_page
    posts = crud_post.get_posts(db, skip=skip, limit=per_page, post_type="page")
    return _external_list_response(
        items=[_serialize_post(item) for item in posts],
        page=page,
        per_page=per_page,
    )


@router.get("/pages/{page_id}")
async def get_external_page(
    page_id: int,
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "pages.read")
    page_obj = crud_post.get_post(db, page_id)
    if page_obj is None or str(page_obj.post_type or "") != "page":
        raise HTTPException(status_code=404, detail="页面不存在")
    return _external_data_response(_serialize_post(page_obj))


@router.post("/pages")
async def create_external_page(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "pages.write")
    status_value = str(payload.get("status", "draft") or "draft").strip().lower()
    if status_value == "published":
        ensure_api_key_permission(api_key, "pages.publish")

    page_create = PostCreate(
        title=str(payload.get("title", "") or "").strip(),
        slug=payload.get("slug"),
        content_markdown=str(payload.get("content_markdown", "") or ""),
        content_html=payload.get("content_html"),
        editor_mode=payload.get("editor_mode"),
        excerpt=payload.get("excerpt"),
        featured_image_url=payload.get("featured_image_url"),
        post_type="page",
        page_template=str(payload.get("page_template", "default") or "default"),
        status=status_value,
        visibility=str(payload.get("visibility", "public") or "public"),
        password=payload.get("password"),
        allow_comments=bool(payload.get("allow_comments", True)),
        license_type=str(payload.get("license_type", "cc_by_nc_sa_4") or "cc_by_nc_sa_4"),
    )
    created = crud_post.create_post(
        db=db,
        post=page_create,
        author_id=int(getattr(api_key, "created_by_user_id", 0) or 0),
    )
    return _external_data_response(_serialize_post(created))


@router.patch("/pages/{page_id}")
async def update_external_page(
    page_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "pages.write")
    page_obj = crud_post.get_post(db, page_id)
    if page_obj is None or str(page_obj.post_type or "") != "page":
        raise HTTPException(status_code=404, detail="页面不存在")

    next_status = payload.get("status")
    if next_status is not None and str(next_status).strip().lower() == "published":
        ensure_api_key_permission(api_key, "pages.publish")

    update_data = PostUpdate(
        title=payload.get("title"),
        slug=payload.get("slug"),
        content_markdown=payload.get("content_markdown"),
        content_html=payload.get("content_html"),
        editor_mode=payload.get("editor_mode"),
        excerpt=payload.get("excerpt"),
        featured_image_url=payload.get("featured_image_url"),
        page_template=payload.get("page_template", page_obj.page_template),
        post_type="page",
        status=payload.get("status", page_obj.status),
        visibility=payload.get("visibility", page_obj.visibility),
        password=payload.get("password"),
        allow_comments=payload.get("allow_comments", page_obj.allow_comments),
        license_type=payload.get("license_type", page_obj.license_type),
    )
    updated = crud_post.update_post(db, page_id, update_data)
    return _external_data_response(_serialize_post(updated))


@router.delete("/pages/{page_id}")
async def delete_external_page(
    page_id: int,
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "pages.delete")
    page_obj = crud_post.get_post(db, page_id)
    if page_obj is None or str(page_obj.post_type or "") != "page":
        raise HTTPException(status_code=404, detail="页面不存在")
    crud_post.delete_post(db, page_id)
    return _external_deleted_response()


@router.get("/categories")
async def list_external_categories(
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "categories.read")
    categories = crud_category.get_categories(db)
    return _external_list_response(
        items=[
            {"id": int(item.id), "name": str(item.name or ""), "slug": str(item.slug or ""), "description": str(item.description or "")}
            for item in categories
        ],
        page=1,
        per_page=max(len(categories), 1),
    )


@router.get("/tags")
async def list_external_tags(
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "tags.read")
    tags = crud_tag.get_tags(db)
    return _external_list_response(
        items=[
            {"id": int(item.id), "name": str(item.name or ""), "slug": str(item.slug or "")}
            for item in tags
        ],
        page=1,
        per_page=max(len(tags), 1),
    )


@router.post("/media")
async def upload_external_media(
    file: UploadFile = File(...),
    title: Optional[str] = Form(None),
    alt_text: Optional[str] = Form(None),
    description: Optional[str] = Form(None),
    target_folder: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    api_key=Depends(get_current_external_api_key),
):
    ensure_api_key_permission(api_key, "media.write")
    uploaded = await media_api.upload_media_for_external_api(
        file=file,
        title=title,
        alt_text=alt_text,
        description=description,
        target_folder=target_folder,
        db=db,
        uploaded_by_user_id=int(getattr(api_key, "created_by_user_id", 0) or 0),
    )
    return _external_data_response(_serialize_media(uploaded))
