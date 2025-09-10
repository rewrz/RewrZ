"""
全站搜索 API 模块

提供全站搜索功能，支持：
1. 文章内容搜索（标题、内容、摘要）
2. 标签和分类搜索
3. 格式筛选搜索
4. 高级搜索选项
5. 搜索结果排序和分页
"""
import json
from typing import Dict, Any, Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_, func, desc, case
from ..core.database import get_db
from ..core.template_filters import get_templates
from ..crud import post as crud_post
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..crud import setting as crud_setting
from ..core.template_context import build_base_template_context, HOMEPAGE_SETTING_KEYS
from ..models import Post, Category, Tag

router = APIRouter()
templates = get_templates()

@router.get("/search", response_class=HTMLResponse)
async def search_page(
    request: Request, 
    q: Optional[str] = Query(None, description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类筛选"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    format: Optional[str] = Query(None, description="格式筛选"),
    sort: Optional[str] = Query("relevance", description="排序方式"),
    page: int = Query(1, description="页码"),
    per_page: Optional[int] = Query(None, description="每页数量"),
    db: Session = Depends(get_db)
):
    """
    搜索页面
    
    支持全站搜索功能，包括文章、分类、标签等内容的搜索
    """
    # 获取搜索结果数量配置
    if per_page is None:
        search_results_limit_setting = crud_setting.get_setting(db, key="search_results_limit")
        per_page = search_results_limit_setting.value.get("value") if search_results_limit_setting and search_results_limit_setting.value else 15
    results = []
    total_count = 0
    search_info = {
        "query": q or "",
        "category": category,
        "tag": tag,
        "format": format,
        "sort": sort,
        "page": page,
        "per_page": per_page,
        "total_count": 0,
        "total_pages": 0
    }
    
    if q and len(q.strip()) > 0:
        # 执行搜索
        search_result = perform_search(
            db, q.strip(), category, tag, format, sort, page, per_page
        )
        results = search_result["results"]
        total_count = search_result["total_count"]
        search_info["total_count"] = total_count
        search_info["total_pages"] = (total_count + per_page - 1) // per_page
    
    # 获取筛选选项
    categories = crud_category.get_categories(db)
    tags = crud_tag.get_tags(db)
    formats = crud_format.get_formats(db)
    # 准备设置上下文 (包含主页个性化设置，供 base.html 使用)
    homepage_settings = crud_setting.get_settings_by_keys(db, HOMEPAGE_SETTING_KEYS)
    settings_dict = {}
    for key in HOMEPAGE_SETTING_KEYS:
        setting_obj = homepage_settings.get(key)
        if setting_obj and getattr(setting_obj, 'value', None) and 'value' in setting_obj.value:
            settings_dict[key] = setting_obj.value['value']
        else:
            settings_dict[key] = getattr(request.state, key, "")
    
    return templates.TemplateResponse("search_results.html", {
        "request": request,
        "results": results,
        "search_info": search_info,
        "categories": categories,
        "tags": tags,
        "formats": formats,
        "settings": settings_dict,
        **build_base_template_context(request),
    })

@router.get("/api/search")
async def search_api(
    q: str = Query(..., description="搜索关键词"),
    category: Optional[str] = Query(None, description="分类筛选"),
    tag: Optional[str] = Query(None, description="标签筛选"),
    format: Optional[str] = Query(None, description="格式筛选"),
    sort: Optional[str] = Query("relevance", description="排序方式"),
    page: int = Query(1, description="页码"),
    per_page: Optional[int] = Query(None, description="每页数量"),
    db: Session = Depends(get_db)
):
    """
    搜索API接口
    
    返回JSON格式的搜索结果，用于AJAX搜索
    """
    # 获取搜索结果数量配置
    if per_page is None:
        search_results_limit_setting = crud_setting.get_setting(db, key="search_results_limit")
        per_page = search_results_limit_setting.value.get("value") if search_results_limit_setting and search_results_limit_setting.value else 15
    if not q or len(q.strip()) == 0:
        return JSONResponse({
            "results": [],
            "total_count": 0,
            "total_pages": 0,
            "query": "",
            "message": "请输入搜索关键词"
        })
    
    search_result = perform_search(
        db, q.strip(), category, tag, format, sort, page, per_page
    )
    
    # 转换结果为API格式
    api_results = []
    for post in search_result["results"]:
        api_results.append({
            "id": post.id,
            "title": post.title,
            "slug": post.slug,
            "excerpt": post.excerpt,
            "published_at": post.published_at.isoformat() if post.published_at else None,
            "featured_image_url": post.featured_image_url,
            "url": f"/posts/{post.slug}",
            "categories": [{"name": cat.name, "slug": cat.slug} for cat in post.categories],
            "tags": [{"name": tag.name, "slug": tag.slug} for tag in post.tags],
            "formats": [{"name": fmt.name, "slug": fmt.slug} for fmt in post.formats]
        })
    
    return JSONResponse({
        "results": api_results,
        "total_count": search_result["total_count"],
        "total_pages": (search_result["total_count"] + per_page - 1) // per_page,
        "query": q,
        "page": page,
        "per_page": per_page
    })

@router.get("/api/search/suggestions")
async def search_suggestions(
    q: str = Query(..., description="搜索关键词"),
    limit: int = Query(5, description="建议数量"),
    db: Session = Depends(get_db)
):
    """
    搜索建议API
    
    提供搜索关键词的自动完成建议
    """
    if not q or len(q.strip()) < 2:
        return JSONResponse({"suggestions": []})
    
    suggestions = []
    
    # 搜索匹配的文章标题
    posts = db.query(Post).filter(
        and_(
            Post.status == "published",
            Post.title.ilike(f"%{q}%")
        )
    ).limit(limit).all()
    
    for post in posts:
        suggestions.append({
            "type": "post",
            "title": post.title,
            "url": f"/posts/{post.slug}"
        })
    
    # 搜索匹配的分类
    if len(suggestions) < limit:
        categories = db.query(Category).filter(
            Category.name.ilike(f"%{q}%")
        ).limit(limit - len(suggestions)).all()
        
        for category in categories:
            suggestions.append({
                "type": "category",
                "title": f"分类: {category.name}",
                "url": f"/archives/by-category/{category.slug}"
            })
    
    # 搜索匹配的标签
    if len(suggestions) < limit:
        tags = db.query(Tag).filter(
            Tag.name.ilike(f"%{q}%")
        ).limit(limit - len(suggestions)).all()
        
        for tag in tags:
            suggestions.append({
                "type": "tag",
                "title": f"标签: {tag.name}",
                "url": f"/archives/by-tag/{tag.slug}"
            })
    
    return JSONResponse({"suggestions": suggestions})

def perform_search(
    db: Session,
    query: str,
    category_slug: Optional[str] = None,
    tag_slug: Optional[str] = None,
    format_slug: Optional[str] = None,
    sort: str = "relevance",
    page: int = 1,
    per_page: int = 10
) -> Dict[str, Any]:
    """
    执行搜索操作
    
    Args:
        db: 数据库会话
        query: 搜索关键词
        category_slug: 分类筛选
        tag_slug: 标签筛选
        format_slug: 格式筛选
        sort: 排序方式
        page: 页码
        per_page: 每页数量
    
    Returns:
        包含搜索结果和统计信息的字典
    """
    # 构建基础查询
    base_query = db.query(Post).filter(Post.status == "published")
    
    # 添加搜索条件
    search_conditions = []
    
    # 搜索标题、内容、摘要
    search_conditions.append(Post.title.ilike(f"%{query}%"))
    search_conditions.append(Post.content_html.ilike(f"%{query}%"))
    search_conditions.append(Post.excerpt.ilike(f"%{query}%"))
    
    # 应用搜索条件
    base_query = base_query.filter(or_(*search_conditions))
    
    # 分类筛选
    if category_slug:
        category = crud_category.get_category_by_slug(db, slug=category_slug)
        if category:
            base_query = base_query.filter(Post.categories.contains(category))
    
    # 标签筛选
    if tag_slug:
        tag = crud_tag.get_tag_by_slug(db, slug=tag_slug)
        if tag:
            base_query = base_query.filter(Post.tags.contains(tag))
    
    # 格式筛选
    if format_slug:
        format_obj = crud_format.get_format_by_slug(db, slug=format_slug)
        if format_obj:
            base_query = base_query.filter(Post.formats.contains(format_obj))
    
    # 排序
    if sort == "date":
        base_query = base_query.order_by(desc(Post.published_at))
    elif sort == "title":
        base_query = base_query.order_by(Post.title)
    else:  # relevance
        # 简单的相关性排序：标题匹配权重更高
        base_query = base_query.order_by(
            # 标题完全匹配
            case(
                (Post.title.ilike(f"%{query}%"), 1),
                else_=2
            ),
            desc(Post.published_at)
        )
    
    # 计算总数
    total_count = base_query.count()
    
    # 分页
    offset = (page - 1) * per_page
    results = base_query.offset(offset).limit(per_page).all()
    
    return {
        "results": results,
        "total_count": total_count,
        "query": query,
        "page": page,
        "per_page": per_page
    }