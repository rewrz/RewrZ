from fastapi import APIRouter, Depends, HTTPException, Request, Response, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional, List

from ..core.database import get_db
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..core.config import settings
from ..crud import post as crud_post, category as crud_category, tag as crud_tag, format as crud_format
from ..schemas import Post, PostCreate, PostUpdate, User

router = APIRouter()
templates = get_templates()

# --- 文章管理路由 ---

@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/posts/new", response_class=HTMLResponse)
async def new_post_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示新建文章页面
    """
    categories = crud_category.get_categories(db)
    formats = crud_format.get_formats(db)
    return templates.TemplateResponse("admin/post_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": settings.ADMIN_PATH.rstrip('/'),
        "categories": categories,
        "formats": formats,
        "post": None, # 新建文章时没有post对象
        "post_type": "article" # 明确指定为文章类型
    })

@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/posts/{{post_id}}/edit", response_class=HTMLResponse)
async def edit_post_page(post_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示编辑文章页面
    """
    post = crud_post.get_post(db, post_id=post_id)
    if not post or post.post_type != "post":
        raise HTTPException(status_code=404, detail="Post not found or is not an article")
    
    categories = crud_category.get_categories(db)
    formats = crud_format.get_formats(db)
    
    return templates.TemplateResponse("admin/post_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": settings.ADMIN_PATH.rstrip('/'),
        "post": post,
        "categories": categories,
        "formats": formats,
        "post_type": "article" # 明确指定为文章类型
    })

@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/posts/new")
async def create_post_api(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    category_id: Optional[int] = Form(None),
    tags: Optional[str] = Form(None), # 接收逗号分隔的标签字符串
    format_ids: Optional[List[int]] = Form(None),
    license_type: str = Form("cc_by_nc_sa_4"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建新文章的API端点
    """
    verify_csrf_token(request, csrf_token)
    
    post_create_data = PostCreate(
        title=title,
        content=content,
        slug=slug,
        excerpt=excerpt,
        status=status,
        category_id=category_id,
        license_type=license_type,
        post_type="article" # 确保文章类型为 'article'
    )
    
    # 处理标签
    tag_names = [name.strip() for name in tags.split(',') if name.strip()] if tags else []
    
    db_post = crud_post.create_post(
        db=db, 
        post=post_create_data, 
        author_id=current_user.id, 
        format_ids=format_ids,
        tag_names=tag_names
    )
    
    # 返回HTMX响应，重定向到文章列表或编辑页面
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{settings.ADMIN_PATH.rstrip('/')}/posts"
    return response

@router.put(f"{settings.ADMIN_PATH.rstrip('/')}/posts/{{post_id}}")
async def update_post_api(
    request: Request,
    post_id: int,
    title: str = Form(...),
    content: str = Form(...),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    category_id: Optional[int] = Form(None),
    tags: Optional[str] = Form(None), # 接收逗号分隔的标签字符串
    format_ids: Optional[List[int]] = Form(None),
    license_type: str = Form("cc_by_nc_sa_4"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新文章的API端点
    """
    verify_csrf_token(request, csrf_token)
    
    db_post = crud_post.get_post(db, post_id=post_id)
    if not db_post:
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 确保文章类型不被修改
    if db_post.post_type != "post":
        raise HTTPException(status_code=400, detail="Cannot update non-article type via this endpoint")

    post_update_data = PostUpdate(
        title=title,
        content=content,
        slug=slug,
        excerpt=excerpt,
        status=status,
        category_id=category_id,
        license_type=license_type,
        post_type="post" # 确保文章类型不被修改
    )
    
    # 处理标签
    tag_names = [name.strip() for name in tags.split(',') if name.strip()] if tags else []

    updated_post = crud_post.update_post(
        db=db, 
        post_id=post_id, 
        post=post_update_data, 
        format_ids=format_ids,
        tag_names=tag_names
    )
    
    # 返回HTMX响应，重定向到文章列表或编辑页面
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{settings.ADMIN_PATH.rstrip('/')}/posts"
    return response

@router.delete(f"{settings.ADMIN_PATH.rstrip('/')}/api/posts/{{post_id}}")
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

# --- 页面管理路由 ---

@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/pages/new", response_class=HTMLResponse)
async def new_page_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示新建页面页面
    """
    categories = crud_category.get_categories(db)
    formats = crud_format.get_formats(db)
    return templates.TemplateResponse("admin/post_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": settings.ADMIN_PATH.rstrip('/'),
        "categories": categories,
        "formats": formats,
        "post": None, # 新建页面时没有post对象
        "post_type": "page" # 明确指定为页面类型
    })

@router.get(f"{settings.ADMIN_PATH.rstrip('/')}/pages/{{page_id}}/edit", response_class=HTMLResponse)
async def edit_page_page(page_id: int, request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    显示编辑页面页面
    """
    page = crud_post.get_post(db, post_id=page_id)
    if not page or page.post_type != "page":
        raise HTTPException(status_code=404, detail="Page not found or is not a page type")
    
    categories = crud_category.get_categories(db)
    formats = crud_format.get_formats(db)
    
    return templates.TemplateResponse("admin/post_form.html", {
        "request": request,
        "user": current_user,
        "admin_path": settings.ADMIN_PATH.rstrip('/'),
        "post": page,
        "categories": categories,
        "formats": formats,
        "post_type": "page" # 明确指定为页面类型
    })

@router.post(f"{settings.ADMIN_PATH.rstrip('/')}/pages/new")
async def create_page_api(
    request: Request,
    title: str = Form(...),
    content: str = Form(...),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    category_id: Optional[int] = Form(None),
    tags: Optional[str] = Form(None), # 接收逗号分隔的标签字符串
    format_ids: Optional[List[int]] = Form(None),
    license_type: str = Form("cc_by_nc_sa_4"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建新页面的API端点
    """
    verify_csrf_token(request, csrf_token)
    
    page_create_data = PostCreate(
        title=title,
        content=content,
        slug=slug,
        excerpt=excerpt,
        status=status,
        category_id=category_id,
        license_type=license_type,
        post_type="page" # 确保文章类型为 'page'
    )
    
    # 处理标签
    tag_names = [name.strip() for name in tags.split(',') if name.strip()] if tags else []
    
    db_page = crud_post.create_post(
        db=db, 
        post=page_create_data, 
        author_id=current_user.id, 
        format_ids=format_ids,
        tag_names=tag_names
    )
    
    # 返回HTMX响应，重定向到页面列表
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{settings.ADMIN_PATH.rstrip('/')}/pages"
    return response

@router.put(f"{settings.ADMIN_PATH.rstrip('/')}/pages/{{page_id}}")
async def update_page_api(
    request: Request,
    page_id: int,
    title: str = Form(...),
    content: str = Form(...),
    slug: Optional[str] = Form(None),
    excerpt: Optional[str] = Form(None),
    status: str = Form("draft"),
    category_id: Optional[int] = Form(None),
    tags: Optional[str] = Form(None), # 接收逗号分隔的标签字符串
    format_ids: Optional[List[int]] = Form(None),
    license_type: str = Form("cc_by_nc_sa_4"),
    csrf_token: str = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    更新页面的API端点
    """
    verify_csrf_token(request, csrf_token)
    
    db_page = crud_post.get_post(db, post_id=page_id)
    if not db_page:
        raise HTTPException(status_code=404, detail="Page not found")
    
    # 确保文章类型不被修改
    if db_page.post_type != "page":
        raise HTTPException(status_code=400, detail="Cannot update non-page type via this endpoint")

    page_update_data = PostUpdate(
        title=title,
        content=content,
        slug=slug,
        excerpt=excerpt,
        status=status,
        category_id=category_id,
        license_type=license_type,
        post_type="page" # 确保文章类型不被修改
    )
    
    # 处理标签
    tag_names = [name.strip() for name in tags.split(',') if name.strip()] if tags else []

    updated_page = crud_post.update_post(
        db=db, 
        post_id=page_id, 
        post=page_update_data, 
        format_ids=format_ids,
        tag_names=tag_names
    )
    
    # 返回HTMX响应，重定向到页面列表
    response = Response(status_code=200)
    response.headers["HX-Redirect"] = f"{settings.ADMIN_PATH.rstrip('/')}/pages"
    return response

@router.delete(f"{settings.ADMIN_PATH.rstrip('/')}/api/pages/{{page_id}}")
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
