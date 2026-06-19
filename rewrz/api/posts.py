from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form, Header, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import json

from ..core.admin_path import get_admin_path
from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..core.config import settings
from ..core.page_templates import DEFAULT_PAGE_TEMPLATE, get_page_template_options, normalize_page_template
from ..crud import post as crud_post, category as crud_category, format as crud_format, setting as crud_setting
from ..schemas import Post, PostCreate, PostUpdate, User, PostBatchUpdate, FormatCreate
from ..core.content_intents import INTENT_SLUGS, INTENT_NAME_MAP, to_public_post_segment
from ..core.content_utils import render_markdown_html
from ..core.micro_text import enhance_micro_html, extract_micro_tags, strip_micro_tags
from . import media as media_api

router = APIRouter()
templates = get_templates()
ADMIN_PATH = get_admin_path()


def _get_content_primary_mode(db: Session) -> str:
    setting = crud_setting.get_setting(db, "content_primary_mode")
    if setting and isinstance(setting.value, dict):
        mode = str(setting.value.get("value", "")).strip().lower()
        if mode in {"markdown", "html"}:
            return mode
    return "markdown"


def _get_or_create_intent_formats(db: Session):
    formats = []
    for slug in INTENT_SLUGS:
        fmt = crud_format.get_format_by_slug(db, slug=slug)
        if fmt is None:
            fmt = crud_format.create_format(
                db,
                FormatCreate(name=INTENT_NAME_MAP.get(slug, slug), slug=slug),
            )
        formats.append(fmt)
    return formats


def _resolve_selected_format_ids(format_id: Optional[int]) -> Optional[List[int]]:
    if isinstance(format_id, int) and format_id > 0:
        return [format_id]
    return None


def _resolve_selected_intent_slug(db: Session, format_id: Optional[int], fallback_slug: str = "article") -> str:
    fallback = str(fallback_slug or "article").strip().lower() or "article"
    if isinstance(format_id, int) and format_id > 0:
        fmt = crud_format.get_format(db, format_id)
        if fmt and getattr(fmt, "slug", None):
            return str(fmt.slug).strip().lower() or fallback
    return fallback


def _resolve_post_primary_intent_slug(post_obj) -> str:
    if not post_obj or not getattr(post_obj, "formats", None):
        return "article"
    slugs = [
        str(getattr(fmt, "slug", "") or "").strip().lower()
        for fmt in (post_obj.formats or [])
    ]
    if "micro" in slugs:
        return "micro"
    if "poem" in slugs:
        return "poem"
    return "article"


def _normalize_category_ids_for_intent(category_ids: Optional[List[int]], intent_slug: str) -> List[int]:
    normalized_intent = str(intent_slug or "article").strip().lower() or "article"
    if normalized_intent in {"micro", "poem"}:
        return []
    cleaned = sorted({
        int(item) for item in (category_ids or [])
        if isinstance(item, int) and item > 0
    })
    return cleaned


def _build_micro_quick_title(content: str) -> str:
    return ""


def _build_micro_quick_slug(content: str) -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S')


def _parse_micro_media_items(raw_media_items: Optional[str], limit: int = 9) -> List[Dict[str, str]]:
    raw = (raw_media_items or "").strip()
    if not raw:
        return []

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="媒体数据格式无效") from exc

    if not isinstance(payload, list):
        raise HTTPException(status_code=400, detail="媒体数据格式无效")

    parsed_items: List[Dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url", "")).strip()
        file_type = str(item.get("file_type", "")).strip().lower()
        name = str(item.get("name", "")).strip()[:80]
        if not url.startswith("/media/"):
            continue
        if file_type not in {"image", "video", "audio"}:
            continue
        parsed_items.append(
            {
                "url": url,
                "file_type": file_type,
                "name": name,
            }
        )
        if len(parsed_items) >= limit:
            break
    return parsed_items


def _merge_micro_content_with_media(content: str, media_items: List[Dict[str, str]]) -> tuple[str, Optional[str]]:
    normalized_content = (content or "").strip()
    if not media_items:
        return normalized_content, None

    media_lines: List[str] = []
    featured_image_url: Optional[str] = None
    for index, media_item in enumerate(media_items, start=1):
        media_url = media_item.get("url", "")
        media_type = media_item.get("file_type", "")
        media_name = media_item.get("name", "") or f"附件{index}"
        if media_type == "image":
            media_lines.append(f"![动态配图{index}]({media_url})")
            if featured_image_url is None:
                featured_image_url = media_url
            continue
        if media_type == "video":
            media_lines.append(f"[视频：{media_name}]({media_url})")
            continue
        if media_type == "audio":
            media_lines.append(f"[音频：{media_name}]({media_url})")

    if not media_lines:
        return normalized_content, featured_image_url

    if normalized_content:
        merged_content = f"{normalized_content}\n\n" + "\n\n".join(media_lines)
    else:
        merged_content = "\n\n".join(media_lines)
    return merged_content, featured_image_url

# --- 文章管理路由 ---


@router.post("/api/v1/posts/quick/media", response_model=dict)
@router.post("/api/posts/quick/media", response_model=dict)
async def upload_public_quick_micro_media(
    request: Request,
    files: List[UploadFile] = File(...),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    前台快捷发布媒体上传接口。

    仅允许登录用户上传图片/视频/音频，且不暴露后台管理路径。
    """
    verify_csrf_token(request, csrf_token)

    selected_files = [item for item in files if item is not None]
    if not selected_files:
        raise HTTPException(status_code=400, detail="请选择要上传的媒体文件")
    if len(selected_files) > 9:
        raise HTTPException(status_code=400, detail="单次最多上传 9 个文件")

    uploaded_items: List[Dict[str, Any]] = []
    for media_file in selected_files:
        mime_type = str(getattr(media_file, "content_type", "") or "").strip().lower()
        if not mime_type.startswith(("image/", "video/", "audio/")):
            raise HTTPException(status_code=400, detail="仅支持图片、视频或音频文件")

        uploaded_media = await media_api.upload_media(
            request=request,
            file=media_file,
            title=None,
            alt_text=None,
            description=None,
            target_folder="micro",
            deduplicate=False,
            auto_process=True,
            db=db,
            current_user=current_user,
            csrf_token=csrf_token,
        )

        media_url = str(getattr(uploaded_media, "url", "") or "").strip()
        if not media_url:
            continue

        uploaded_items.append(
            {
                "id": int(getattr(uploaded_media, "id", 0) or 0),
                "url": media_url,
                "file_type": str(getattr(uploaded_media, "file_type", "") or "").strip().lower(),
                "name": str(getattr(uploaded_media, "filename", "") or "media"),
                "preview_url": str(getattr(uploaded_media, "preview_url", "") or media_url),
            }
        )

    return {
        "success": True,
        "items": uploaded_items,
    }


@router.post("/api/v1/posts/quick", response_model=dict)
@router.post("/api/posts/quick", response_model=dict)
async def create_public_quick_micro_post(
    request: Request,
    content: str = Form(""),
    media_items: Optional[str] = Form(None),
    visibility: str = Form("public"),
    password: Optional[str] = Form(None),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    前台快捷发布接口。

    设计约束：
    - 仅允许 post_type=post
    - 仅允许内容意图为 micro
    """
    verify_csrf_token(request, csrf_token)

    normalized_content = (content or "").strip()
    normalized_visibility = str(visibility or "public").strip().lower() or "public"
    normalized_password = (password or "").strip() or None
    parsed_media_items = _parse_micro_media_items(media_items)
    if not normalized_content and not parsed_media_items:
        raise HTTPException(status_code=400, detail="动态内容或媒体至少填写一项")
    if len(normalized_content) > 2000:
        raise HTTPException(status_code=400, detail="动态内容最多 2000 字")
    if normalized_visibility not in {"public", "private", "password"}:
        raise HTTPException(status_code=400, detail="动态可见性无效")
    if normalized_visibility == "password" and not normalized_password:
        raise HTTPException(status_code=400, detail="密码保护动态必须设置访问密码")
    if normalized_visibility != "password":
        normalized_password = None
    body_content = strip_micro_tags(normalized_content)
    merged_content, featured_image_url = _merge_micro_content_with_media(body_content, parsed_media_items)

    intent_formats = {fmt.slug: fmt for fmt in _get_or_create_intent_formats(db)}
    micro_format = intent_formats.get("micro")
    if micro_format is None:
        raise HTTPException(status_code=500, detail="未找到微博格式配置")

    post_create_data = PostCreate(
        title=_build_micro_quick_title(normalized_content),
        slug=_build_micro_quick_slug(normalized_content),
        content_markdown=merged_content,
        excerpt=None,
        featured_image_url=featured_image_url,
        post_type="post",
        status="published",
        visibility=normalized_visibility,
        password=normalized_password,
        allow_comments=True,
        category_ids=[],
        format_ids=[micro_format.id],
        license_type="cc_by_nc_sa_4",
    )
    parsed_tags = extract_micro_tags(normalized_content)
    created = crud_post.create_post(
        db=db,
        post=post_create_data,
        author_id=current_user.id,
        tag_names=parsed_tags,
        format_ids=[micro_format.id],
    )

    created_time = getattr(created, "published_at", None) or getattr(created, "created_at", None)
    return {
        "success": True,
        "id": created.id,
        "post_url": f"/{to_public_post_segment('micro')}/{created.slug}",
        "published_at": created_time.isoformat() if created_time else "",
        "media_count": len(parsed_media_items),
    }


@router.post("/api/v1/posts/quick/preview", response_model=dict)
@router.post("/api/posts/quick/preview", response_model=dict)
async def preview_public_quick_micro_post(
    request: Request,
    content: str = Form(""),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    前台快捷发布预览接口（仅渲染，不入库）。
    """
    verify_csrf_token(request, csrf_token)
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return {"success": True, "html": ""}
    if len(normalized_content) > 2000:
        raise HTTPException(status_code=400, detail="动态内容最多 2000 字")
    preview_source = strip_micro_tags(normalized_content)
    return {
        "success": True,
        "html": enhance_micro_html(render_markdown_html(preview_source), db),
    }

@router.get(f"{ADMIN_PATH}/posts/new", response_class=HTMLResponse)
async def new_post_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示新建文章页面
    """
    categories = crud_category.get_categories(db)
    formats = _get_or_create_intent_formats(db)
    content_primary_mode = _get_content_primary_mode(db)
    return templates.TemplateResponse("admin/post_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": ADMIN_PATH,
        "categories": categories,
        "formats": formats,
        "content_primary_mode": content_primary_mode,
        "post": None, # 新建文章时没有post对象
        "post_type": "post", # 明确指定为文章类型
        "media_upload_dir_name": settings.MEDIA_UPLOAD_DIR # 传递媒体上传目录名称
    })

@router.get(f"{ADMIN_PATH}/posts/{{post_id}}/edit", response_class=HTMLResponse)
async def edit_post_page(post_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示编辑文章页面
    """
    post = crud_post.get_post(db, post_id=post_id)
    if not post or post.post_type != "post":
        raise HTTPException(status_code=404, detail="Post not found or is not an article")
    
    categories = crud_category.get_categories(db)
    formats = _get_or_create_intent_formats(db)
    content_primary_mode = _get_content_primary_mode(db)
    
    return templates.TemplateResponse("admin/post_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": ADMIN_PATH,
        "post": post,
        "categories": categories,
        "formats": formats,
        "content_primary_mode": content_primary_mode,
        "post_type": "post", # 明确指定为文章类型
        "media_upload_dir_name": settings.MEDIA_UPLOAD_DIR # 传递媒体上传目录名称
    })

@router.post(f"{ADMIN_PATH}/posts/new")
async def create_post_api(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    editor_mode: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    featured_image_url: Optional[str] = Form(None),
    status: str = Form("draft"),
    visibility: str = Form("public"),
    password: Optional[str] = Form(None),
    allow_comments: bool = Form(True),
    category_ids: Optional[List[int]] = Form(None),
    tags: Optional[str] = Form(None), # 接收逗号分隔的标签字符串
    format_id: Optional[int] = Form(None),
    license_type: str = Form("cc_by_nc_sa_4"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建新文章的API端点
    """
    verify_csrf_token(request, csrf_token)
    normalized_password = (password or "").strip() or None
    if visibility == "password" and not normalized_password:
        raise HTTPException(status_code=400, detail="密码保护内容必须设置访问密码")
    
    selected_intent_slug = _resolve_selected_intent_slug(db, format_id, fallback_slug="article")
    normalized_category_ids = _normalize_category_ids_for_intent(category_ids, selected_intent_slug)

    post_create_data = PostCreate(
        title=title,
        content_markdown=content,
        content_html=content_html,
        editor_mode=editor_mode or _get_content_primary_mode(db),
        slug=slug,
        excerpt=excerpt,
        featured_image_url=featured_image_url,
        status=status,
        visibility=visibility,
        password=normalized_password,
        allow_comments=allow_comments,
        category_ids=normalized_category_ids,
        license_type=license_type,
        post_type="post" # 确保文章类型为 'post'
    )
    
    # 处理标签
    tag_names = [name.strip() for name in tags.split(',') if name.strip()] if tags else []
    
    resolved_format_ids = _resolve_selected_format_ids(format_id)

    db_post = crud_post.create_post(
        db=db, 
        post=post_create_data, 
        author_id=current_user.id,
        tag_names=tag_names, # 传递标签名称列表
        format_ids=resolved_format_ids # 仅传递单个主类型ID
    )
    
    # 返回HTMX响应，重定向到文章列表或编辑页面
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{ADMIN_PATH}/posts"
    return response

@router.put(f"{ADMIN_PATH}/posts/{{post_id}}")
@router.post(f"{ADMIN_PATH}/posts/{{post_id}}")
async def update_post_api(
    request: Request,
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    editor_mode: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    featured_image_url: Optional[str] = Form(None),
    status: str = Form("draft"),
    visibility: str = Form("public"),
    password: Optional[str] = Form(None),
    allow_comments: bool = Form(True),
    category_ids: Optional[List[int]] = Form(None),
    tags: Optional[str] = Form(None), # 接收逗号分隔的标签字符串
    format_id: Optional[int] = Form(None),
    license_type: str = Form("cc_by_nc_sa_4"),
    method_override: Optional[str] = Form(None, alias="_method"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新文章的API端点
    """
    verify_csrf_token(request, csrf_token)
    if request.method.upper() == "POST":
        normalized_method_override = str(method_override or "").strip().upper()
        if normalized_method_override not in {"", "PUT"}:
            raise HTTPException(status_code=405, detail="文章编辑仅支持 PUT 覆写提交")
    
    db_post = crud_post.get_post(db, post_id=post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 确保文章类型不被修改
    if db_post.post_type != "post":
        raise HTTPException(status_code=400, detail="Cannot update non-article type via this endpoint")
    normalized_password = (password or "").strip() or None
    if visibility == "password" and not normalized_password and not db_post.password:
        raise HTTPException(status_code=400, detail="密码保护内容必须设置访问密码")

    fallback_intent_slug = _resolve_post_primary_intent_slug(db_post)
    selected_intent_slug = _resolve_selected_intent_slug(db, format_id, fallback_slug=fallback_intent_slug)
    normalized_category_ids = _normalize_category_ids_for_intent(category_ids, selected_intent_slug)

    post_update_data = PostUpdate(
        title=title,
        content_markdown=content,
        content_html=content_html,
        editor_mode=editor_mode or _get_content_primary_mode(db),
        slug=slug,
        excerpt=excerpt,
        featured_image_url=featured_image_url,
        status=status,
        visibility=visibility,
        password=normalized_password,
        allow_comments=allow_comments,
        category_ids=normalized_category_ids,
        license_type=license_type,
        post_type="post" # 确保文章类型不被修改
    )
    
    # 处理标签
    tag_names = [name.strip() for name in tags.split(',') if name.strip()] if tags else []

    resolved_format_ids = _resolve_selected_format_ids(format_id)

    updated_post = crud_post.update_post(
        db=db, 
        post_id=post_id, 
        post=post_update_data, 
        format_ids=resolved_format_ids,
        tag_names=tag_names
    )
    
    # 返回HTMX响应，重定向到文章列表或编辑页面
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{ADMIN_PATH}/posts"
    return response

@router.delete(f"{ADMIN_PATH}/api/v1/posts/{{post_id}}")
async def delete_post_api(post_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    删除文章的API端点
    """
    db_post = crud_post.get_post(db, post_id=post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")

    crud_post.delete_post(db, post_id=post_id)
    return {"success": True, "message": "文章删除成功"}

@router.post(f"{ADMIN_PATH}/api/v1/posts/batch-publish", response_model=dict)
async def batch_publish_posts(
    request: Request,
    post_batch_update: PostBatchUpdate, # 使用新的Pydantic模型
    csrf_token: str = Header(..., alias="X-CSRF-Token"), # 从请求头获取CSRF令牌
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量发布文章的API端点
    """
    verify_csrf_token(request, csrf_token) # 验证CSRF令牌
    try:
        requested_ids = sorted({
            post_id for post_id in post_batch_update.post_ids
            if isinstance(post_id, int) and post_id > 0
        })
        published_count = crud_post.bulk_update_posts_status_by_ids(
            db=db,
            post_ids=requested_ids,
            status="published",
            author_id=current_user.id,
        )
        skipped_count = max(len(requested_ids) - published_count, 0)
        return {
            "success": True,
            "message": f"成功发布 {published_count} 篇文章",
            "requested_count": len(requested_ids),
            "published_count": published_count,
            "skipped_count": skipped_count,
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"success": False, "error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"批量发布失败: {str(e)}"})

@router.post(f"{ADMIN_PATH}/api/v1/posts/batch-draft", response_model=dict)
async def batch_draft_posts(
    request: Request,
    post_batch_update: PostBatchUpdate, # 使用新的Pydantic模型
    csrf_token: str = Header(..., alias="X-CSRF-Token"), # 从请求头获取CSRF令牌
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量将文章移至草稿的API端点
    """
    verify_csrf_token(request, csrf_token) # 验证CSRF令牌
    try:
        requested_ids = sorted({
            post_id for post_id in post_batch_update.post_ids
            if isinstance(post_id, int) and post_id > 0
        })
        drafted_count = crud_post.bulk_update_posts_status_by_ids(
            db=db,
            post_ids=requested_ids,
            status="draft",
            author_id=current_user.id,
        )
        skipped_count = max(len(requested_ids) - drafted_count, 0)
        return {
            "success": True,
            "message": f"成功将 {drafted_count} 篇文章移至草稿",
            "requested_count": len(requested_ids),
            "drafted_count": drafted_count,
            "skipped_count": skipped_count,
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"success": False, "error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"批量移至草稿失败: {str(e)}"})

@router.post(f"{ADMIN_PATH}/api/v1/posts/batch-delete", response_model=dict)
async def batch_delete_posts(
    request: Request,
    post_batch_update: PostBatchUpdate, # 使用新的Pydantic模型
    csrf_token: str = Header(..., alias="X-CSRF-Token"), # 从请求头获取CSRF令牌
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量删除文章的API端点
    """
    verify_csrf_token(request, csrf_token) # 验证CSRF令牌
    try:
        requested_ids = list({
            post_id for post_id in post_batch_update.post_ids
            if isinstance(post_id, int) and post_id > 0
        })
        deleted_count = crud_post.delete_posts_by_ids(
            db=db,
            post_ids=requested_ids,
            author_id=current_user.id,
        )
        skipped_count = max(len(requested_ids) - deleted_count, 0)
        return {
            "success": True,
            "message": f"成功删除 {deleted_count} 篇文章",
            "requested_count": len(requested_ids),
            "deleted_count": deleted_count,
            "skipped_count": skipped_count,
        }
    except HTTPException as e:
        return JSONResponse(status_code=e.status_code, content={"success": False, "error": e.detail})
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": f"批量删除失败: {str(e)}"})

# --- 页面管理路由 ---

@router.get(f"{ADMIN_PATH}/pages/new", response_class=HTMLResponse)
async def new_page_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示新建页面页面
    """
    from ..core.template_filters import get_license_options_filter
    content_primary_mode = _get_content_primary_mode(db)
    return templates.TemplateResponse("admin/page_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": ADMIN_PATH,
        "post": None,  # 新建页面时没有post对象
        "page_template_options": get_page_template_options(),
        "content_primary_mode": content_primary_mode,
        "license_options": get_license_options_filter
    })

@router.get(f"{ADMIN_PATH}/pages/{{page_id}}/edit", response_class=HTMLResponse)
async def edit_page_page(page_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示编辑页面页面
    """
    page = crud_post.get_post(db, post_id=page_id)
    if not page or page.post_type != "page":
        raise HTTPException(status_code=404, detail="Page not found or is not a page type")
    
    from ..core.template_filters import get_license_options_filter
    content_primary_mode = _get_content_primary_mode(db)
    return templates.TemplateResponse("admin/page_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": ADMIN_PATH,
        "post": page,
        "page_template_options": get_page_template_options(),
        "content_primary_mode": content_primary_mode,
        "license_options": get_license_options_filter
    })

@router.post(f"{ADMIN_PATH}/pages/new")
async def create_page_api(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    editor_mode: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    featured_image_url: Optional[str] = Form(None),
    page_template: str = Form(DEFAULT_PAGE_TEMPLATE),
    status: str = Form("draft"),
    visibility: str = Form("public"),
    password: Optional[str] = Form(None),
    allow_comments: bool = Form(True),
    license_type: str = Form("cc_by_nc_sa_4"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建新页面的API端点
    """
    verify_csrf_token(request, csrf_token)
    normalized_password = (password or "").strip() or None
    if visibility == "password" and not normalized_password:
        raise HTTPException(status_code=400, detail="密码保护内容必须设置访问密码")
    
    page_create_data = PostCreate(
        title=title,
        content_markdown=content,
        content_html=content_html,
        editor_mode=editor_mode or _get_content_primary_mode(db),
        slug=slug,
        excerpt=excerpt,
        featured_image_url=featured_image_url,
        page_template=normalize_page_template(page_template),
        status=status,
        visibility=visibility,
        password=normalized_password,
        allow_comments=allow_comments,
        license_type=license_type,
        post_type="page" # 确保文章类型为 'page'
    )
    
    db_page = crud_post.create_post(
        db=db, 
        post=page_create_data, 
        author_id=current_user.id
    )
    
    # 返回HTMX响应，重定向到页面列表
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{ADMIN_PATH}/pages"
    return response

@router.put(f"{ADMIN_PATH}/pages/{{page_id}}")
@router.post(f"{ADMIN_PATH}/pages/{{page_id}}")
async def update_page_api(
    request: Request,
    page_id: int,
    title: str = Form(...),
    content: str = Form(...),
    content_html: Optional[str] = Form(None),
    editor_mode: Optional[str] = Form(None),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    featured_image_url: Optional[str] = Form(None),
    page_template: str = Form(DEFAULT_PAGE_TEMPLATE),
    status: str = Form("draft"),
    visibility: str = Form("public"),
    password: Optional[str] = Form(None),
    allow_comments: bool = Form(True),
    license_type: str = Form("cc_by_nc_sa_4"),
    method_override: Optional[str] = Form(None, alias="_method"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新页面的API端点
    """
    verify_csrf_token(request, csrf_token)
    if request.method.upper() == "POST":
        normalized_method_override = str(method_override or "").strip().upper()
        if normalized_method_override not in {"", "PUT"}:
            raise HTTPException(status_code=405, detail="页面编辑仅支持 PUT 覆写提交")
    
    db_page = crud_post.get_post(db, post_id=page_id)
    if not db_page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # 确保文章类型不被修改
    if db_page.post_type != "page":
        raise HTTPException(status_code=400, detail="Cannot update non-page type via this endpoint")
    normalized_password = (password or "").strip() or None
    if visibility == "password" and not normalized_password and not db_page.password:
        raise HTTPException(status_code=400, detail="密码保护内容必须设置访问密码")

    page_update_data = PostUpdate(
        title=title,
        content_markdown=content,
        content_html=content_html,
        editor_mode=editor_mode or _get_content_primary_mode(db),
        slug=slug,
        excerpt=excerpt,
        featured_image_url=featured_image_url,
        page_template=normalize_page_template(page_template),
        status=status,
        visibility=visibility,
        password=normalized_password,
        allow_comments=allow_comments,
        license_type=license_type,
        post_type="page" # 确保文章类型不被修改
    )
    
    updated_page = crud_post.update_post(
        db=db, 
        post_id=page_id, 
        post=page_update_data
    )
    
    # 返回HTMX响应，重定向到页面列表
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{ADMIN_PATH}/pages"
    return response

@router.delete(f"{ADMIN_PATH}/api/v1/pages/{{page_id}}")
async def delete_page_api(page_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    删除页面的API端点
    """
    db_page = crud_post.get_post(db, post_id=page_id)
    if not db_page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    if db_page.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this page")

    crud_post.delete_post(db, post_id=page_id)
    return {"success": True, "message": "页面删除成功"}


