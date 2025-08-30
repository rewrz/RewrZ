"""
评论API模块

提供评论的创建、回复功能，集成反垃圾评论三层防护系统。
包含XSS防护、内容净化、垃圾检测等安全功能。
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from ..core.database import get_db
from ..crud import comment as crud_comment
from ..crud import post as crud_post
from ..crud import setting as crud_setting
from ..schemas import CommentCreate, Comment, User
from ..core.security import get_current_user
from pydantic import BaseModel
from typing import List
import bleach # 导入bleach用于HTML净化
from markdown import markdown
from ..core.config import settings # 反垃圾设置
from ..core.anti_spam import get_anti_spam_engine # 导入反垃圾引擎
from ..core.avatar import get_avatar_service # 导入头像服务
from ..core.template_filters import get_templates # 导入模板函数
import time

router = APIRouter()

class BulkAction(BaseModel):
    action: str
    comment_ids: List[int]

class AdminReply(BaseModel):
    content: str

# 定义评论允许的HTML标签和属性 (需求规格 2.3.1)
ALLOWED_TAGS = ['a', 'strong', 'em', 'code', 'p', 'br']
ALLOWED_ATTRIBUTES = {'a': ['href', 'title']}

@router.post("/api/v1/comments/{post_id}", response_model=Comment)
async def create_comment_api(
    request: Request,
    post_id: int,
    author_name: str = Form(...),
    author_email: str = Form(...),
    content: str = Form(...),
    author_url: str = Form(None),
    parent_id: int = Form(None),
    honeypot_field: str = Form(None, alias="hp_field"),  # 蜜罐字段
    form_timestamp: float = Form(None, alias="ft"),  # 表单时间戳
    captcha_response: str = Form(None, alias="captcha"),  # 验证码响应
    db: Session = Depends(get_db)
):
    """
    创建评论API
    
    集成三层反垃圾防护系统：
    1. 无感防御：蜜罐陷阱 + 时间戳检查
    2. 内容分析：链接数量 + 关键词过滤 + Akismet
    3. 主动验证：验证码确认
    """
    # 检查文章是否存在且允许评论
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if not db_post.allow_comments:
        raise HTTPException(status_code=403, detail="Comments are not allowed on this post.")

    # 反垃圾三层防护系统检查
    anti_spam = get_anti_spam_engine(db)
    
    # 获取客户端信息
    ip_address = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("User-Agent", "")
    
    # 执行垃圾检测
    spam_result = await anti_spam.check_comment(
        content=content,
        author_name=author_name,
        author_email=author_email,
        author_url=author_url,
        ip_address=ip_address,
        user_agent=user_agent,
        honeypot_field=honeypot_field,
        form_timestamp=form_timestamp
    )
    
    # 处理垃圾检测结果
    if spam_result.action == "block":
        # 静默丢弃，返回成功响应但不保存评论
        print(f"垃圾评论被阻止: {spam_result.reason} (IP: {ip_address})")
        return HTMLResponse(
            content="<div class='alert alert-success'>评论提交成功！</div>",
            status_code=200
        )
    
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
        author_name=author_name,
        author_email=author_email,
        author_url=author_url,
        content=sanitized_content,
        ip_address=ip_address,
        user_agent=user_agent,
        status=comment_status  # 根据垃圾检测结果设置状态
    )
    db_comment = crud_comment.create_comment(db=db, comment=comment_create)
    
    # 记录反垃圾检测日志
    print(f"评论创建成功 - ID: {db_comment.id}, 状态: {comment_status}, "
          f"垃圾概率: {spam_result.confidence:.2f}, 原因: {spam_result.reason}")

    # 为HTMX渲染新评论项
    templates = get_templates()
    
    # 获取头像服务并为评论添加头像信息
    avatar_service = get_avatar_service(db)
    comment_avatar_url = avatar_service.get_comment_avatar_url(
        author_email=author_email,
        author_id=None,  # 匿名评论者没有用户ID
        size=40  # 评论区头像尺寸
    )
    
    # 如果需要审核，返回提示信息
    if comment_status == "pending":
        return HTMLResponse(
            content="<div class='alert alert-warning'>评论已提交，正在等待审核。</div>",
            status_code=200
        )
    
    # 返回评论组件，包含头像信息
    return templates.TemplateResponse(
        "components/comment_item.html", 
        {
            "request": request, 
            "comment": db_comment, 
            "post": db_post,
            "avatar_url": comment_avatar_url
        }
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
        raise HTTPException(status_code=404, detail="Post not found")
    
    # 生成防垃圾字段
    anti_spam = get_anti_spam_engine(db)
    honeypot_field_name = anti_spam.generate_honeypot_field_name()
    form_token = anti_spam.generate_form_token()
    form_timestamp = time.time()
    
    return templates.TemplateResponse(
        "components/reply_form.html", 
        {
            "request": request, 
            "post_id": post_id, 
            "parent_id": parent_id, 
            "post": db_post,
            "honeypot_field_name": honeypot_field_name,
            "form_token": form_token,
            "form_timestamp": form_timestamp
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
        raise HTTPException(status_code=404, detail="Post not found")
    
    if not db_post.allow_comments:
        return HTMLResponse(
            content="<div class='alert alert-info'>此文章不允许评论。</div>",
            status_code=200
        )
    
    # 生成防垃圾字段
    anti_spam = get_anti_spam_engine(db)
    honeypot_field_name = anti_spam.generate_honeypot_field_name()
    form_token = anti_spam.generate_form_token()
    form_timestamp = time.time()
    
    return templates.TemplateResponse(
        "components/comment_form.html", 
        {
            "request": request, 
            "post_id": post_id, 
            "post": db_post,
            "honeypot_field_name": honeypot_field_name,
            "form_token": form_token,
            "form_timestamp": form_timestamp,
            "captcha_enabled": anti_spam.captcha_enabled
        }
    )

@router.post("/api/comments/{comment_id}/approve", status_code=status.HTTP_200_OK)
async def approve_comment_api(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批准评论
    """
    db_comment = crud_comment.update_comment_status(db, comment_id=comment_id, status="approved")
    if db_comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"success": True, "message": "Comment approved successfully"}

@router.delete("/api/comments/{comment_id}", status_code=status.HTTP_200_OK)
async def delete_comment_api(
    comment_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除评论
    """
    db_comment = crud_comment.delete_comment(db, comment_id=comment_id)
    if db_comment is None:
        raise HTTPException(status_code=404, detail="Comment not found")
    return {"success": True, "message": "Comment deleted successfully"}

@router.post("/api/v1/admin/comments/{comment_id}/moderate")
async def moderate_comment(
    comment_id: int,
    action: str = Form(...),  # approve, reject, spam
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    管理员审核评论
    
    Args:
        comment_id: 评论ID
        action: 审核动作 (approve/reject/spam)
    """
    if action not in ["approve", "reject", "spam"]:
        raise HTTPException(status_code=400, detail="Invalid action")
    
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
        raise HTTPException(status_code=404, detail="Comment not found")
    
    return {"message": f"Comment {action}d successfully", "comment_id": comment_id}

@router.post("/api/comments/bulk-action", status_code=status.HTTP_200_OK)
async def bulk_action_api(
    bulk_action: BulkAction,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    批量操作评论
    """
    if bulk_action.action == "approve":
        crud_comment.bulk_update_comment_status(db, comment_ids=bulk_action.comment_ids, status="approved")
        message = "Comments approved successfully"
    elif bulk_action.action == "delete":
        crud_comment.bulk_delete_comments(db, comment_ids=bulk_action.comment_ids)
        message = "Comments deleted successfully"
    else:
        raise HTTPException(status_code=400, detail="Invalid action")
        
    return {"success": True, "message": message}

@router.post("/api/comments/{comment_id}/reply", response_model=Comment, status_code=status.HTTP_201_CREATED)
async def admin_reply_to_comment(
    comment_id: int,
    reply: AdminReply,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    管理员回复评论
    """
    # 获取被回复的评论
    original_comment = crud_comment.get_comment(db, comment_id=comment_id)
    if not original_comment:
        raise HTTPException(status_code=404, detail="Comment not found")
    
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
        author_name=current_user.username,  # 使用管理员用户名
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
    # TODO: 实现获取待审核评论的CRUD函数
    
    return {"message": "Pending comments endpoint - to be implemented"}
