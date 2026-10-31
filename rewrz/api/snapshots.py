"""
版本快照API模块

提供文章与页面的版本快照管理功能，包括：
1. 获取历史快照列表
2. 恢复到指定快照版本
3. 快照比较功能
4. 快照删除与清理功能

快照结构：{timestamp, editor_mode, content_markdown, content_html, restore_point}
"""
from fastapi import APIRouter, Body, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from datetime import datetime
import difflib

from ..core.database import get_db
from ..core.security import get_current_user, is_admin_user
from ..core.template_filters import get_templates
from ..core.time_utils import as_utc, format_site_time, utc_now, utc_now_naive
from ..core.content_utils import (
    detect_stored_editor_mode,
    get_effective_content_html,
    get_effective_plain_text,
)
from ..crud import post as crud_post
from ..crud.post import SNAPSHOT_LIMIT
from ..schemas import User, Post, PostUpdate

router = APIRouter()
templates = get_templates()


@router.get("/api/v1/posts/{post_id}/snapshots", response_class=HTMLResponse)
def get_post_snapshots(
    post_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取文章的版本快照列表，按时间倒序排列。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = [_serialize_snapshot(index, item) for index, item in enumerate(db_post.version_snapshots or [])]
    current_text = get_effective_plain_text(db_post.content_markdown, db_post.content_html)

    return templates.TemplateResponse(request, "admin/post_snapshots.html", {
        "request": request,
        "user": current_user,
        "post": db_post,
        "snapshots": snapshots,
        "current_content": current_text,
    })


@router.get("/api/v1/posts/{post_id}/snapshots/json")
def get_post_snapshots_json(
    post_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """供编辑页快照弹窗使用的 JSON 数据。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = [_serialize_snapshot(index, item) for index, item in enumerate(db_post.version_snapshots or [])]

    return {
        'snapshots': snapshots,
        'current_markdown': db_post.content_markdown or "",
        'current_html': get_effective_content_html(db_post.content_markdown, db_post.content_html),
        'current_editor_mode': detect_stored_editor_mode(db_post.content_markdown, db_post.content_html),
        'current_content': get_effective_plain_text(db_post.content_markdown, db_post.content_html),
        'snapshot_limit': SNAPSHOT_LIMIT,
        'post_id': post_id,
    }


@router.get("/api/v1/posts/{post_id}/snapshots/{snapshot_index}")
def get_snapshot_content(
    post_id: int,
    snapshot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """获取指定快照的详细内容，用于预览或比较。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = db_post.version_snapshots or []
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")

    return _serialize_snapshot(snapshot_index, snapshots[snapshot_index])


@router.post("/api/v1/posts/{post_id}/snapshots/{snapshot_index}/restore")
def restore_snapshot(
    post_id: int,
    snapshot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """恢复到指定快照版本，并把当前正文保存为新的恢复点。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = list(db_post.version_snapshots or [])
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")

    target_snapshot = snapshots[snapshot_index]
    target_mode, target_markdown, target_html = _snapshot_fields(target_snapshot)
    if not (target_markdown.strip() or target_html.strip()):
        raise HTTPException(status_code=400, detail="快照内容为空")

    current_snapshot = {
        "timestamp": utc_now_naive().isoformat(),
        "editor_mode": detect_stored_editor_mode(db_post.content_markdown, db_post.content_html),
        "content_markdown": db_post.content_markdown or "",
        "content_html": db_post.content_html or "",
        "restore_point": True,
    }
    new_snapshots = ([current_snapshot] + snapshots)[:SNAPSHOT_LIMIT]

    # 显式传入 version_snapshots，避免 update_post 再追加一条重复快照
    post_update = PostUpdate(
        editor_mode=target_mode,
        content_markdown=target_markdown,
        content_html=target_html,
        version_snapshots=new_snapshots,
    )
    crud_post.update_post(db, post_id, post_update)

    return {
        'success': True,
        'message': '文章已恢复到指定快照版本',
        'restored_to': _format_timestamp(target_snapshot.get('timestamp')),
        'editor_mode': target_mode,
        'new_content': target_markdown,
        'new_html': target_html,
    }


@router.get("/api/v1/posts/{post_id}/snapshots/{snapshot_index}/compare")
def compare_snapshot(
    post_id: int,
    snapshot_index: int,
    compare_with: str = "current",  # "current" 或 "previous"
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """比较快照与当前内容或更早快照的差异，统一按纯文本对比。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = db_post.version_snapshots or []
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")

    snapshot = snapshots[snapshot_index]
    snapshot_text = get_effective_plain_text(
        snapshot.get('content_markdown', ''),
        snapshot.get('content_html', ''),
    )

    if compare_with == "current":
        compare_text = get_effective_plain_text(db_post.content_markdown, db_post.content_html)
        compare_label = "当前版本"
    elif compare_with == "previous" and snapshot_index < len(snapshots) - 1:
        previous = snapshots[snapshot_index + 1]
        compare_text = get_effective_plain_text(
            previous.get('content_markdown', ''),
            previous.get('content_html', ''),
        )
        compare_label = f"快照 {snapshot_index + 2}"
    else:
        raise HTTPException(status_code=400, detail="无效的比较对象")

    diff = _generate_diff(snapshot_text, compare_text)

    return {
        'snapshot_index': snapshot_index,
        'snapshot_timestamp': snapshot.get('timestamp'),
        'compare_with': compare_with,
        'compare_label': compare_label,
        'diff': diff,
        'summary': _get_diff_summary(diff)
    }


@router.delete("/api/v1/posts/{post_id}/snapshots/{snapshot_index}")
def delete_snapshot(
    post_id: int,
    snapshot_index: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """删除指定的历史快照。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = list(db_post.version_snapshots or [])
    if snapshot_index < 0 or snapshot_index >= len(snapshots):
        raise HTTPException(status_code=404, detail="快照不存在")

    new_snapshots = snapshots[:snapshot_index] + snapshots[snapshot_index + 1:]
    crud_post.update_post(db, post_id, PostUpdate(version_snapshots=new_snapshots))

    return {
        'success': True,
        'message': '快照已删除',
        'remaining_snapshots': len(new_snapshots)
    }


@router.post("/api/v1/posts/{post_id}/snapshots/batch-delete")
def batch_delete_snapshots(
    post_id: int,
    indices: List[int] = Body(..., embed=True),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """批量删除指定的历史快照。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    snapshots = list(db_post.version_snapshots or [])
    valid_indices = {index for index in indices if 0 <= index < len(snapshots)}
    if not valid_indices:
        raise HTTPException(status_code=400, detail="请选择要删除的快照")

    new_snapshots = [item for index, item in enumerate(snapshots) if index not in valid_indices]
    crud_post.update_post(db, post_id, PostUpdate(version_snapshots=new_snapshots))

    return {
        'success': True,
        'message': f'已删除 {len(snapshots) - len(new_snapshots)} 个快照',
        'deleted_count': len(snapshots) - len(new_snapshots),
        'remaining_snapshots': len(new_snapshots)
    }


@router.post("/api/v1/posts/{post_id}/snapshots/cleanup")
def cleanup_snapshots(
    post_id: int,
    keep_count: int = 3,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """只保留最新的 N 个快照。"""
    db_post = _load_post_or_404(db, post_id)
    _ensure_snapshot_permission(db_post, current_user)

    if keep_count < 1:
        raise HTTPException(status_code=400, detail="至少需要保留1个快照")

    snapshots = list(db_post.version_snapshots or [])
    if len(snapshots) <= keep_count:
        return {
            'success': True,
            'message': '无需清理',
            'kept_snapshots': len(snapshots)
        }

    new_snapshots = snapshots[:keep_count]
    deleted_count = len(snapshots) - keep_count
    crud_post.update_post(db, post_id, PostUpdate(version_snapshots=new_snapshots))

    return {
        'success': True,
        'message': f'已清理 {deleted_count} 个旧快照',
        'kept_snapshots': len(new_snapshots),
        'deleted_snapshots': deleted_count
    }


# 辅助函数

def _load_post_or_404(db: Session, post_id: int) -> Post:
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="文章不存在")
    return db_post


def _ensure_snapshot_permission(db_post: Post, current_user: User) -> None:
    """作者本人或管理员可以操作快照。"""
    if db_post.author_id == getattr(current_user, "id", None):
        return
    if is_admin_user(current_user):
        return
    raise HTTPException(status_code=403, detail="没有权限操作此文章的快照")


def _snapshot_fields(snapshot: Dict[str, Any]) -> tuple[str, str, str]:
    """返回 (editor_mode, content_markdown, content_html)。"""
    content_markdown = str(snapshot.get("content_markdown") or "")
    content_html = str(snapshot.get("content_html") or "")
    editor_mode = str(snapshot.get("editor_mode") or "").strip().lower()
    if editor_mode not in {"markdown", "html"}:
        editor_mode = detect_stored_editor_mode(content_markdown, content_html)
    return editor_mode, content_markdown, content_html


def _serialize_snapshot(index: int, snapshot: Dict[str, Any]) -> Dict[str, Any]:
    editor_mode, content_markdown, content_html = _snapshot_fields(snapshot)
    effective_html = get_effective_content_html(content_markdown, content_html)
    plain_text = get_effective_plain_text(content_markdown, content_html)
    preview = plain_text[:100] + ('...' if len(plain_text) > 100 else '')
    return {
        'index': index,
        'timestamp': snapshot.get('timestamp'),
        'editor_mode': editor_mode,
        'content_markdown': content_markdown,
        'content_html': effective_html,
        'content': plain_text,
        'content_preview': preview,
        'formatted_time': _format_timestamp(snapshot.get('timestamp')),
        'relative_time': _get_relative_time(snapshot.get('timestamp')),
        'word_count': len(plain_text.split()),
        'restore_point': bool(snapshot.get('restore_point')),
    }


def _format_timestamp(timestamp_str: str) -> str:
    """格式化时间戳为可读格式"""
    if not timestamp_str:
        return "未知时间"

    try:
        # 解析ISO格式时间戳
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        return format_site_time(dt, '%Y年%m月%d日 %H:%M:%S')
    except (ValueError, AttributeError):
        return timestamp_str


def _get_relative_time(timestamp_str: str) -> str:
    """获取相对时间描述"""
    if not timestamp_str:
        return "未知时间"

    try:
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # 数据库时间戳统一按 UTC 解释，差值计算也用 UTC，避免服务器本地时区干扰
        diff = utc_now() - as_utc(dt)

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
