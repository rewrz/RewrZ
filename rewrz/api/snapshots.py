"""
版本快照API模块

提供文章版本快照的管理功能，包括：
1. 获取文章的历史快照列表
2. 恢复到指定快照版本
3. 快照比较功能
4. 快照清理功能
"""
from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any, Optional
from datetime import datetime
import difflib
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..crud import post as crud_post
from ..schemas import User, Post
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = get_templates()

@router.get("/api/v1/posts/{post_id}/snapshots", response_class=HTMLResponse)
async def get_post_snapshots(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取文章的版本快照列表
    
    返回文章的历史快照，按时间倒序排列。
    用于在编辑界面显示版本历史。
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限（只有作者或管理员可以查看快照）
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限访问此文章的快照")
    
    # 获取快照列表
    snapshots = db_post.version_snapshots or []
    
    # 为快照添加额外信息
    processed_snapshots = []
    for i, snapshot in enumerate(snapshots):
        processed_snapshot = {
            'index': i,
            'timestamp': snapshot.get('timestamp'),
            'content': snapshot.get('content', ''),
            'content_preview': snapshot.get('content', '')[:100] + '...' if len(snapshot.get('content', '')) > 100 else snapshot.get('content', ''),
            'formatted_time': _format_timestamp(snapshot.get('timestamp')),
            'relative_time': _get_relative_time(snapshot.get('timestamp')),
            'word_count': len(snapshot.get('content', '').split())
        }
        processed_snapshots.append(processed_snapshot)
    
    # 渲染模板
    return templates.TemplateResponse("admin/post_snapshots.html", {
        "request": request,
        "user": current_user,
        "post": db_post,
        "snapshots": processed_snapshots,
        "current_content": db_post.content_markdown
    })

@router.get("/api/v1/posts/{post_id}/snapshots/json")
async def get_post_snapshots_json(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取文章快照的JSON数据
    
    用于AJAX请求获取快照数据
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限访问此文章的快照")
    
    snapshots = db_post.version_snapshots or []
    
    # 处理快照数据
    processed_snapshots = []
    for i, snapshot in enumerate(snapshots):
        processed_snapshots.append({
            'index': i,
            'timestamp': snapshot.get('timestamp'),
            'content': snapshot.get('content', ''),
            'formatted_time': _format_timestamp(snapshot.get('timestamp')),
            'relative_time': _get_relative_time(snapshot.get('timestamp')),
            'word_count': len(snapshot.get('content', '').split())
        })
    
    return {
        'snapshots': processed_snapshots,
        'current_content': db_post.content_markdown,
        'post_id': post_id
    }

@router.get("/api/v1/posts/{post_id}/snapshots/{snapshot_index}")
async def get_snapshot_content(
    post_id: int,
    snapshot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取指定快照的详细内容
    
    用于预览或比较快照内容
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限访问此文章的快照")
    
    snapshots = db_post.version_snapshots or []
    
    # 检查快照索引是否有效
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")
    
    snapshot = snapshots[snapshot_index]
    
    return {
        'index': snapshot_index,
        'timestamp': snapshot.get('timestamp'),
        'content': snapshot.get('content', ''),
        'formatted_time': _format_timestamp(snapshot.get('timestamp')),
        'relative_time': _get_relative_time(snapshot.get('timestamp')),
        'word_count': len(snapshot.get('content', '').split()),
        'current_content': db_post.content_markdown
    }

@router.post("/api/v1/posts/{post_id}/snapshots/{snapshot_index}/restore")
async def restore_snapshot(
    post_id: int,
    snapshot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    恢复到指定的快照版本
    
    将文章内容恢复到选定的历史快照，并创建新的快照保存当前内容
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限修改此文章")
    
    snapshots = db_post.version_snapshots or []
    
    # 检查快照索引是否有效
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")
    
    # 获取要恢复的快照内容
    target_snapshot = snapshots[snapshot_index]
    target_content = target_snapshot.get('content', '')
    
    if not target_content:
        raise HTTPException(status_code=400, detail="快照内容为空")
    
    # 保存当前内容作为新快照（在恢复之前）
    current_content = db_post.content_markdown
    current_snapshot = {
        "timestamp": datetime.now().isoformat(),
        "content": current_content,
        "restore_point": True  # 标记这是恢复操作前的保存点
    }
    
    # 将当前内容插入到快照列表最前面
    new_snapshots = [current_snapshot] + snapshots
    if len(new_snapshots) > 5:
        new_snapshots = new_snapshots[:5]
    
    # 恢复文章内容
    from ..schemas import PostUpdate
    post_update = PostUpdate(
        content_markdown=target_content,
        version_snapshots=new_snapshots
    )
    
    # 更新文章
    updated_post = crud_post.update_post(db, post_id, post_update)
    
    return {
        'success': True,
        'message': '文章已恢复到指定快照版本',
        'restored_to': _format_timestamp(target_snapshot.get('timestamp')),
        'new_content': target_content
    }

@router.get("/api/v1/posts/{post_id}/snapshots/{snapshot_index}/compare")
async def compare_snapshot(
    post_id: int,
    snapshot_index: int,
    compare_with: str = "current",  # "current" 或 "previous"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    比较快照与当前内容或其他快照的差异
    
    返回详细的文本差异信息，用于版本比较
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限访问此文章的快照")
    
    snapshots = db_post.version_snapshots or []
    
    # 检查快照索引是否有效
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")
    
    snapshot_content = snapshots[snapshot_index].get('content', '')
    
    # 确定比较对象
    if compare_with == "current":
        compare_content = db_post.content_markdown
        compare_label = "当前版本"
    elif compare_with == "previous" and snapshot_index < len(snapshots) - 1:
        compare_content = snapshots[snapshot_index + 1].get('content', '')
        compare_label = f"快照 {snapshot_index + 1}"
    else:
        raise HTTPException(status_code=400, detail="无效的比较对象")
    
    # 生成差异
    diff = _generate_diff(snapshot_content, compare_content)
    
    return {
        'snapshot_index': snapshot_index,
        'snapshot_timestamp': snapshots[snapshot_index].get('timestamp'),
        'compare_with': compare_with,
        'compare_label': compare_label,
        'diff': diff,
        'summary': _get_diff_summary(diff)
    }

@router.delete("/api/v1/posts/{post_id}/snapshots/{snapshot_index}")
async def delete_snapshot(
    post_id: int,
    snapshot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    删除指定的快照
    
    手动删除不需要的历史快照
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限修改此文章")
    
    snapshots = db_post.version_snapshots or []
    
    # 检查快照索引是否有效
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")
    
    # 删除指定快照
    new_snapshots = snapshots[:snapshot_index] + snapshots[snapshot_index + 1:]
    
    # 更新文章
    from ..schemas import PostUpdate
    post_update = PostUpdate(version_snapshots=new_snapshots)
    crud_post.update_post(db, post_id, post_update)
    
    return {
        'success': True,
        'message': '快照已删除',
        'remaining_snapshots': len(new_snapshots)
    }

@router.post("/api/v1/posts/{post_id}/snapshots/cleanup")
async def cleanup_snapshots(
    post_id: int,
    keep_count: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    清理旧快照
    
    只保留最新的N个快照，删除更旧的快照
    """
    # 获取文章信息
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    
    # 检查权限
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="没有权限修改此文章")
    
    if keep_count < 1:
        raise HTTPException(status_code=400, detail="至少需要保留1个快照")
    
    snapshots = db_post.version_snapshots or []
    
    if len(snapshots) <= keep_count:
        return {
            'success': True,
            'message': '无需清理',
            'kept_snapshots': len(snapshots)
        }
    
    # 保留最新的快照
    new_snapshots = snapshots[:keep_count]
    deleted_count = len(snapshots) - keep_count
    
    # 更新文章
    from ..schemas import PostUpdate
    post_update = PostUpdate(version_snapshots=new_snapshots)
    crud_post.update_post(db, post_id, post_update)
    
    return {
        'success': True,
        'message': f'已清理 {deleted_count} 个旧快照',
        'kept_snapshots': len(new_snapshots),
        'deleted_snapshots': deleted_count
    }

# 辅助函数

def _format_timestamp(timestamp_str: str) -> str:
    """格式化时间戳为可读格式"""
    if not timestamp_str:
        return "未知时间"
    
    try:
        # 解析ISO格式时间戳
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return dt.strftime('%Y年%m月%d日 %H:%M:%S')
    except (ValueError, AttributeError):
        return timestamp_str

def _get_relative_time(timestamp_str: str) -> str:
    """获取相对时间描述"""
    if not timestamp_str:
        return "未知时间"
    
    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        now = datetime.now()
        
        # 计算时间差
        if dt.tzinfo:
            # 如果时间戳带时区信息，需要转换为本地时间
            import pytz
            local_tz = pytz.timezone('Asia/Shanghai')  # 或使用系统时区
            dt = dt.astimezone(local_tz).replace(tzinfo=None)
        
        diff = now - dt
        
        if diff.days > 0:
            return f"{diff.days}天前"
        elif diff.seconds > 3600:
            hours = diff.seconds // 3600
            return f"{hours}小时前"
        elif diff.seconds > 60:
            minutes = diff.seconds // 60
            return f"{minutes}分钟前"
        else:
            return "刚刚"
    except (ValueError, AttributeError):
        return "未知时间"

def _generate_diff(old_content: str, new_content: str) -> List[Dict[str, Any]]:
    """生成内容差异"""
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    
    diff_lines = []
    for line in difflib.unified_diff(old_lines, new_lines, n=3):
        line_type = "context"
        if line.startswith("+++") or line.startswith("---"):
            line_type = "header"
        elif line.startswith("@@"):
            line_type = "range"
        elif line.startswith("+"):
            line_type = "addition"
        elif line.startswith("-"):
            line_type = "deletion"
        
        diff_lines.append({
            "type": line_type,
            "content": line.rstrip('\n'),
            "line_number": None  # 可以后续添加行号支持
        })
    
    return diff_lines

def _get_diff_summary(diff_lines: List[Dict[str, Any]]) -> Dict[str, int]:
    """获取差异摘要"""
    additions = sum(1 for line in diff_lines if line["type"] == "addition")
    deletions = sum(1 for line in diff_lines if line["type"] == "deletion")
    
    return {
        "additions": additions,
        "deletions": deletions,
        "total_changes": additions + deletions
    }