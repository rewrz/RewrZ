"""
评论API模块

提供评论的创建、回复功能，集成反垃圾评论三层防护系统。
包含XSS防护、内容净化、垃圾检测等安全功能。
"""
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status, Request, Form, Query, Header
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..crud import comment as crud_comment
from ..crud import post as crud_post
from ..crud import setting as crud_setting
from ..crud import user as crud_user
from ..schemas import CommentCreate, Comment, User
from ..core.security import get_current_user, verify_csrf_token, decode_access_token, should_use_secure_cookie
from pydantic import BaseModel
from typing import List, Optional
import bleach # 导入bleach用于HTML净化
from markdown import markdown
from ..core.anti_spam import get_anti_spam_engine # 导入反垃圾引擎
from ..core.avatar import get_avatar_service # 导入头像服务
from ..core.template_filters import get_templates # 导入模板函数
from ..core.content_access import extract_hide_block, get_comment_unlock_cookie_name
from ..core.admin_security import check_comment_rate_limit, get_admin_email, get_client_ip
from ..core.notification_email import send_new_comment_notification
from ..core.ip_geo import lookup_ip_locations
from ..core.public_alias import resolve_public_display_name

router = APIRouter()


def _set_comment_unlock_cookie(request: Request, response: HTMLResponse, post_id: int) -> None:
    response.set_cookie(
        key=get_comment_unlock_cookie_name(post_id),
        value="true",
        max_age=30 * 24 * 60 * 60,  # 30天
        samesite="lax",
        secure=should_use_secure_cookie(request),
    )


def _resolve_optional_user(request: Request, db: Session):
    token = (request.cookies.get("access_token") or "").strip()
    if not token:
        return None

    payload = decode_access_token(token)
    if not payload:
        return None

    raw_user_id = payload.get("sub")
    try:
        user_id = int(raw_user_id)
    except (TypeError, ValueError):
        return None

    return crud_user.get_user(db, user_id=user_id)


def _resolve_public_display_name(user_obj) -> str:
    return resolve_public_display_name(
        getattr(user_obj, "display_name", None),
        seed_value=getattr(user_obj, "id", None),
        fallback="已登录用户",
    )

class BulkAction(BaseModel):
    action: str
    comment_ids: List[int]

class AdminReply(BaseModel):
    content: str


class IpGeoLookupRequest(BaseModel):
    ips: List[str]

# 定义评论允许的HTML标签和属性 (需求规格 2.3.1)
ALLOWED_TAGS = ['a', 'strong', 'em', 'code', 'p', 'br']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}

@router.post("/api/v1/comments/{post_id:int}", response_class=HTMLResponse)
@router.post("/api/comments/{post_id:int}", response_class=HTMLResponse)
async def create_comment_api(
    request: Request,
    background_tasks: BackgroundTasks,
    post_id: int,
    author_name: Optional[str] = Form(None),
    author_email: Optional[str] = Form(None),
    content: str = Form(...),
    author_url: str = Form(None),
    parent_id: int = Form(None),
    honeypot_field: str = Form(None, alias="hp_field"),  # 蜜罐字段
    form_timestamp: str = Form(None, alias="ft"),  # 表单时间戳令牌
    captcha_response: str = Form(None, alias="captcha"),  # 验证码响应
    csrf_token: str = Form(...),
    db: Session = Depends(get_db)
):
    """
    创建评论API
    
    集成三层反垃圾防护系统：
    1. 无感防御：蜜罐陷阱 + 时间戳检查
    2. 内容分析：链接数量 + 关键词过滤 + Akismet
    3. 主动验证：验证码确认
    """
    verify_csrf_token(request, csrf_token)

    # 检查文章是否存在且允许评论
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    if not db_post.allow_comments:
        raise HTTPException(status_code=403, detail="当前内容未开启评论")

    logged_in_user = _resolve_optional_user(request, db)
    logged_in_public_name = _resolve_public_display_name(logged_in_user) if logged_in_user else ""
    resolved_author_name = (author_name or "").strip()
    resolved_author_email = (author_email or "").strip()
    resolved_author_url = (author_url or "").strip() or None

    if logged_in_user is not None:
        resolved_author_name = _resolve_public_display_name(logged_in_user)
        resolved_author_email = (
            (getattr(logged_in_user, "email", None) or "").strip()
            or resolved_author_email
        )
        if not resolved_author_url:
            profile_website = (getattr(logged_in_user, "website", None) or "").strip()
            resolved_author_url = profile_website or None

    if not resolved_author_name:
        raise HTTPException(status_code=400, detail="请填写昵称")
    if not resolved_author_email:
        raise HTTPException(status_code=400, detail="请填写邮箱")

    # 获取客户端信息
    ip_address = get_client_ip(request)
    user_agent = request.headers.get("User-Agent", "")

    # 评论提交 API 速率限制（按IP）
    allowed, retry_after = check_comment_rate_limit(db, ip_address)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="评论提交过于频繁，请稍后再试",
            headers={"Retry-After": str(retry_after)},
        )

    # 反垃圾三层防护系统检查
    anti_spam = get_anti_spam_engine(db)
    
    # 执行垃圾检测
    spam_result = await anti_spam.check_comment(
        content=content,
        author_name=resolved_author_name,
        author_email=resolved_author_email,
        author_url=resolved_author_url,
        ip_address=ip_address,
        user_agent=user_agent,
        honeypot_field=honeypot_field,
        form_timestamp=form_timestamp
    )
    
    # 处理垃圾检测结果
    if spam_result.action in {"silent_drop", "block"}:
        # 静默丢弃：返回成功响应但不保存评论，也不写入解锁Cookie
        print(f"垃圾评论被阻止: {spam_result.reason} (IP: {ip_address})")
        return HTMLResponse(
            content=(
                "<div class='rounded-xl border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700 "
                "dark:border-emerald-800/60 dark:bg-emerald-900/20 dark:text-emerald-300'>评论提交成功。</div>"
            ),
            status_code=200
        )

    if spam_result.action == "too_fast":
        raise HTTPException(status_code=429, detail="提交过快，请稍后重试")

    if spam_result.action == "expired":
        raise HTTPException(status_code=400, detail="表单已过期，请刷新页面后重试")
    
    elif spam_result.action == "captcha":
        # 需要验证码确认
        if not captcha_response or captcha_response != request.session.get('captcha'):
            raise HTTPException(
                status_code=400, 
                detail="验证码错误，请重新输入"
            )
        
    # 决定评论状态
    if spam_result.action == "moderate" or spam_result.confidence > 0.3:
        comment_status = "pending"  # 需要审核
    else:
        comment_status = "approved"  # 直接通过

    # 净化评论内容 (需求规格 3.2.1 - XSS防护)
    # 先进行Markdown转换，然后使用bleach进行严格的白名单过滤
    sanitized_content = bleach.clean(
        markdown(content), 
        tags=ALLOWED_TAGS, 
        attributes=ALLOWED_ATTRIBUTES,
        strip=True  # 移除不允许的标签而不是转义
    )

    comment_create = CommentCreate(
        post_id=post_id,
        parent_id=parent_id if parent_id else None,
        author_name=resolved_author_name,
        author_email=resolved_author_email,
        author_url=resolved_author_url,
        content=sanitized_content,
        ip_address=ip_address,
        user_agent=user_agent,
        status=comment_status  # 根据垃圾检测结果设置状态
    )
    db_comment = crud_comment.create_comment(db=db, comment=comment_create)

    # 新评论异步通知管理员
    admin_email = get_admin_email(db)
    if admin_email:
        review_url = f"{request.url.scheme}://{request.url.netloc}{request.state.admin_path}/comments?status=pending"
        comment_preview = " ".join((content or "").strip().split())[:160]
        background_tasks.add_task(
            send_new_comment_notification,
            admin_email,
            db_post.title or "(untitled)",
            resolved_author_name,
            resolved_author_email,
            comment_preview,
            review_url,
            db=db,
        )
    
    # 记录反垃圾检测日志
    print(f"评论创建成功 - ID: {db_comment.id}, 状态: {comment_status}, "
          f"垃圾概率: {spam_result.confidence:.2f}, 原因: {spam_result.reason}")

    # 为HTMX渲染新评论项
    templates = get_templates()
    
    # 获取头像服务并为评论添加头像信息
    avatar_service = get_avatar_service(db)
    comment_avatar_url = avatar_service.get_comment_avatar_url(
        author_email=resolved_author_email,
        author_id=None,  # 匿名评论者没有用户ID
        size=40  # 评论区头像尺寸
    )
    
    # 如果需要审核，返回提示信息
    if comment_status == "pending":
        pending_response = HTMLResponse(
            content=(
                "<div class='rounded-xl border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700 "
                "dark:border-amber-800/60 dark:bg-amber-900/20 dark:text-amber-300'>评论已提交，正在等待审核。</div>"
            ),
            status_code=200
        )
        _set_comment_unlock_cookie(request, pending_response, post_id)
        return pending_response
    
    # 返回评论组件，包含头像信息
    approved_response = templates.TemplateResponse(
        "components/comment_item.html", 
        {
            "request": request, 
            "comment": db_comment, 
            "post": db_post,
            "avatar_url": comment_avatar_url
        }
    )
    _set_comment_unlock_cookie(request, approved_response, post_id)
    return approved_response


@router.post("/api/v1/reveal/{post_id}", response_class=HTMLResponse)
async def reveal_hidden_content(
    post_id: int,
    request: Request,
    index: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    评论后可见内容揭示接口

    仅当访客已拥有当前文章评论 Cookie 时，返回 [hide] 块渲染结果。
    """
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")

    unlock_cookie_name = get_comment_unlock_cookie_name(post_id)
    if request.cookies.get(unlock_cookie_name) != "true":
        return HTMLResponse(
            content="<div class='text-sm text-red-600'>请先发表评论后再查看隐藏内容。</div>",
            status_code=403,
        )

    hidden_markdown = extract_hide_block(db_post.content_markdown, index)
    if hidden_markdown is None:
        raise HTTPException(status_code=404, detail="Hidden block not found")

    return HTMLResponse(
        content=(
            '<div class="my-4 rounded-lg border border-green-300 bg-green-50 p-4">'
            f"{markdown(hidden_markdown)}"
            "</div>"
        ),
        status_code=200,
    )

@router.get("/api/v1/comments/reply_form/{post_id}/{parent_id}", response_class=HTMLResponse)
async def get_reply_form(request: Request, post_id: int, parent_id: int, db: Session = Depends(get_db)):
    """
    获取回复表单
    
    生成包含防垃圾字段的回复表单
    """
    templates = get_templates()
    
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 生成防垃圾字段
    anti_spam = get_anti_spam_engine(db)
    form_timestamp_token = anti_spam.generate_form_timestamp_token()
    parent_comment = crud_comment.get_comment(db, comment_id=parent_id)
    if parent_comment is None:
        raise HTTPException(status_code=404, detail="父评论不存在")
    logged_in_user = _resolve_optional_user(request, db)
    logged_in_public_name = _resolve_public_display_name(logged_in_user) if logged_in_user else ""
    
    return templates.TemplateResponse(
        "components/reply_form.html", 
        {
            "request": request, 
            "post_id": post_id, 
            "parent_id": parent_id, 
            "post": db_post,
            "parent_author_name": parent_comment.author_name,
            "form_timestamp_token": form_timestamp_token,
            "captcha_enabled": anti_spam.captcha_enabled,
            "logged_in_user": logged_in_user,
            "logged_in_public_name": logged_in_public_name,
        }
    )

@router.get("/api/v1/comments/form/{post_id}", response_class=HTMLResponse)
async def get_comment_form(request: Request, post_id: int, db: Session = Depends(get_db)):
    """
    获取评论表单
    
    生成包含反垃圾防护字段的评论表单
    """
    templates = get_templates()
    
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    if not db_post.allow_comments:
        return HTMLResponse(
            content=(
                "<div class='rounded-xl border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-700 "
                "dark:border-sky-800/60 dark:bg-sky-900/20 dark:text-sky-300'>当前内容未开启评论。</div>"
            ),
            status_code=200
        )
    
    # 生成防垃圾字段
    anti_spam = get_anti_spam_engine(db)
    form_timestamp_token = anti_spam.generate_form_timestamp_token()
    logged_in_user = _resolve_optional_user(request, db)
    logged_in_public_name = _resolve_public_display_name(logged_in_user) if logged_in_user else ""
    
    return templates.TemplateResponse(
        "components/comment_form.html", 
        {
            "request": request, 
            "post_id": post_id, 
            "post": db_post,
            "form_timestamp_token": form_timestamp_token,
            "captcha_enabled": anti_spam.captcha_enabled,
            "logged_in_user": logged_in_user,
            "logged_in_public_name": logged_in_public_name,
        }
    )


@router.get("/api/v1/comments/embed/{post_id}", response_class=HTMLResponse)
async def get_inline_comment_embed(request: Request, post_id: int, db: Session = Depends(get_db)):
    """
    获取微博聚合页内嵌评论区域（可折叠展开）
    """
    templates = get_templates()
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")

    if db_post.status != "published" or db_post.published_at is None:
        raise HTTPException(status_code=404, detail="文章不存在")

    anti_spam = get_anti_spam_engine(db)
    form_timestamp_token = anti_spam.generate_form_timestamp_token()
    approved_comments = list(db_post.comments or [])
    root_comments = [item for item in approved_comments if item.parent_id is None]
    logged_in_user = _resolve_optional_user(request, db)
    logged_in_public_name = _resolve_public_display_name(logged_in_user) if logged_in_user else ""

    return templates.TemplateResponse(
        "components/micro_comments_embed.html",
        {
            "request": request,
            "post": db_post,
            "total_comments": len(approved_comments),
            "root_comments": root_comments,
            "form_timestamp_token": form_timestamp_token,
            "captcha_enabled": anti_spam.captcha_enabled,
            "logged_in_user": logged_in_user,
            "logged_in_public_name": logged_in_public_name,
        },
    )

@router.post("/api/v1/comments/{comment_id}/approve", status_code=status.HTTP_200_OK)
@router.post("/api/comments/{comment_id}/approve", status_code=status.HTTP_200_OK)
async def approve_comment_api(
    request: Request,
    comment_id: int,
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批准评论
    """
    verify_csrf_token(request, csrf_token)
    db_comment = crud_comment.update_comment_status(db, comment_id=comment_id, status="approved")
    if db_comment is None:
        raise HTTPException(status_code=404, detail="评论不存在")
    return {"success": True, "message": "评论已批准"}

@router.delete("/api/v1/comments/{comment_id}", status_code=status.HTTP_200_OK)
@router.delete("/api/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_comment_api(
    request: Request,
    comment_id: int,
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除评论
    """
    verify_csrf_token(request, csrf_token)
    db_comment = crud_comment.delete_comment(db, comment_id=comment_id)
    if db_comment is None:
        raise HTTPException(status_code=404, detail="评论不存在")
    return {"success": True, "message": "评论已删除"}

@router.post("/api/v1/admin/comments/{comment_id}/moderate")
async def moderate_comment(
    request: Request,
    comment_id: int,
    action: str = Form(...),  # approve, reject, spam
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    管理员审核评论
    
    Args:
        comment_id: 评论ID
        action: 审核动作 (approve/reject/spam)
    """
    verify_csrf_token(request, csrf_token)
    if action not in ["approve", "reject", "spam"]:
        raise HTTPException(status_code=400, detail="无效的操作类型")
    
    # 设置评论状态
    status_map = {
        "approve": "approved",
        "reject": "rejected", 
        "spam": "spam"
    }
    
    db_comment = crud_comment.update_comment_status(
        db, comment_id=comment_id, status=status_map[action]
    )
    
    if db_comment is None:
        raise HTTPException(status_code=404, detail="评论不存在")
    
    return {"message": f"评论操作成功：{action}", "comment_id": comment_id}

@router.post("/api/v1/comments/bulk-action", status_code=status.HTTP_200_OK)
@router.post("/api/comments/bulk-action", status_code=status.HTTP_200_OK)
async def bulk_action_api(
    request: Request,
    bulk_action: BulkAction,
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量操作评论
    """
    verify_csrf_token(request, csrf_token)
    comment_ids = sorted({
        comment_id for comment_id in (bulk_action.comment_ids or [])
        if isinstance(comment_id, int) and comment_id > 0
    })
    if not comment_ids:
        raise HTTPException(status_code=400, detail="未提供有效的评论ID")

    if bulk_action.action == "approve":
        affected = crud_comment.bulk_update_comment_status(db, comment_ids=comment_ids, status="approved")
        message = f"批量批准成功（{affected} 条）"
    elif bulk_action.action == "pending":
        affected = crud_comment.bulk_update_comment_status(db, comment_ids=comment_ids, status="pending")
        message = f"批量移至待审核成功（{affected} 条）"
    elif bulk_action.action == "spam":
        affected = crud_comment.bulk_update_comment_status(db, comment_ids=comment_ids, status="spam")
        message = f"批量标记垃圾评论成功（{affected} 条）"
    elif bulk_action.action == "delete":
        affected = crud_comment.bulk_delete_comments(db, comment_ids=comment_ids)
        message = f"批量删除成功（{affected} 条）"
    else:
        raise HTTPException(status_code=400, detail="无效的批量操作类型")
        
    return {"success": True, "message": message, "affected": affected}


@router.post("/api/v1/admin/comments/ip-geo", status_code=status.HTTP_200_OK)
@router.post("/api/admin/comments/ip-geo", status_code=status.HTTP_200_OK)
async def lookup_comment_ip_geo(
    request: Request,
    payload: IpGeoLookupRequest,
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    批量查询评论IP地理位置信息（用于后台列表参考展示）
    """
    verify_csrf_token(request, csrf_token)
    ips = payload.ips if payload and payload.ips else []
    return {"success": True, "locations": lookup_ip_locations(ips)}

@router.post("/api/v1/comments/{comment_id}/reply", response_model=Comment, status_code=status.HTTP_201_CREATED)
@router.post("/api/comments/{comment_id}/reply", response_model=Comment, status_code=status.HTTP_201_CREATED)
async def admin_reply_to_comment(
    request: Request,
    comment_id: int,
    reply: AdminReply,
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    管理员回复评论
    """
    verify_csrf_token(request, csrf_token)
    # 获取被回复的评论
    original_comment = crud_comment.get_comment(db, comment_id=comment_id)
    if not original_comment:
        raise HTTPException(status_code=404, detail="评论不存在")
    
    # 从数据库获取网站设置
    site_url_setting = crud_setting.get_setting(db, "site_url")
    admin_email_setting = crud_setting.get_setting(db, "admin_email")
    
    site_url = None
    admin_email = ""
    
    if site_url_setting and site_url_setting.value:
        site_url_value = site_url_setting.value.get("value")
        # 确保 site_url_value 是字符串并且不为空
        if isinstance(site_url_value, str) and site_url_value.strip():
            site_url = site_url_value.strip()
    
    if admin_email_setting and admin_email_setting.value:
        admin_email_value = admin_email_setting.value.get("value")
        # 确保 admin_email_value 是字符串并且不为空
        if isinstance(admin_email_value, str) and admin_email_value.strip():
            admin_email = admin_email_value.strip()
    
    # 创建回复评论
    reply_comment = CommentCreate(
        post_id=original_comment.post_id,
        parent_id=comment_id,
        author_name=_resolve_public_display_name(current_user),  # 使用对外显示名，避免暴露登录名
        author_email=admin_email,  # 使用管理员邮箱
        author_url=site_url,    # 使用网站地址
        content=reply.content,
        status="approved",  # 管理员回复默认批准
        is_admin_reply=True
    )
    
    db_reply = crud_comment.create_comment(db=db, comment=reply_comment)
    return db_reply

@router.get("/api/v1/admin/comments/pending")
async def get_pending_comments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取待审核的评论列表
    """
    pending_comments = crud_comment.get_comments(
        db=db,
        status="pending",
        sort_by_latest=True,
        limit=100,
    )
    return {
        "count": len(pending_comments),
        "comments": pending_comments,
    }
