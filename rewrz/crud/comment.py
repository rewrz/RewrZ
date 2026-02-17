"""评论CRUD操作模块

本模块提供评论相关的数据库操作功能，包括创建、读取、更新、删除评论。
支持嵌套评论和状态管理。
"""
from sqlalchemy.orm import Session
from sqlalchemy import select, func, delete, update
from ..models import Comment
from ..schemas import CommentCreate
from datetime import datetime
from typing import Iterable, List


_BULK_CHUNK_SIZE = 500


def _normalize_comment_ids(comment_ids: Iterable[int]) -> List[int]:
    return sorted({comment_id for comment_id in (comment_ids or []) if isinstance(comment_id, int) and comment_id > 0})


def _iter_chunks(items: List[int], chunk_size: int = _BULK_CHUNK_SIZE):
    for idx in range(0, len(items), chunk_size):
        yield items[idx: idx + chunk_size]

def get_comment(db: Session, comment_id: int):
    """根据评论id获取评论信息"""
    return db.execute(select(Comment).filter(Comment.id == comment_id)).scalar_one_or_none()

def get_comments_for_post(db: Session, post_id: int, skip: int = 0, limit: int = 100):
    """获取指定文章的评论列表，支持分页"""
    return db.execute(select(Comment).filter(Comment.post_id == post_id).offset(skip).limit(limit)).scalars().all()

def get_comments(db: Session, skip: int = 0, limit: int = 100, sort_by_latest: bool = False, status: str = None):
    """获取评论列表，支持分页、排序和状态筛选
    
    Args:
        db: 数据库会话
        skip: 跳过的记录数
        limit: 返回的记录数上限
        sort_by_latest: 是否按最新时间排序
        status: 评论状态 ('approved', 'pending', 'spam')
        
    Returns:
        评论对象列表
    """
    query = select(Comment)
    
    if status:
        query = query.filter(Comment.status == status)
        
    if sort_by_latest:
        query = query.order_by(Comment.created_at.desc())
    
    return db.execute(query.offset(skip).limit(limit)).scalars().all()

def count_comments(db: Session) -> int:
    """
    计算所有评论的数量
    """
    return db.execute(select(func.count(Comment.id))).scalar_one()

def count_comments_by_status(db: Session, status: str) -> int:
    """
    根据状态计算评论数量
    """
    return db.execute(select(func.count(Comment.id)).filter(Comment.status == status)).scalar_one()

def create_comment(db: Session, comment: CommentCreate, ip_address: str = "", user_agent: str = ""):
    """创建新评论
    
    Args:
        db: 数据库会话
        comment: 评论创建数据
        ip_address: 用户IP地址（用于反垃圾检测）
        user_agent: 用户代理字符串
        
    Returns:
        创建的评论对象
    """
    # 将HttpUrl转换为字符串
    author_url_str = str(comment.author_url) if comment.author_url else None
    
    resolved_ip = ip_address or comment.ip_address or ""
    resolved_user_agent = user_agent or comment.user_agent or ""

    db_comment = Comment(
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        author_name=comment.author_name,
        author_email=comment.author_email,
        author_url=author_url_str,
        content=comment.content,
        ip_address=resolved_ip,
        user_agent=resolved_user_agent,
        status=comment.status,  # 使用传入的状态
        created_at=datetime.now()
    )
    db.add(db_comment)
    db.commit()
    db.refresh(db_comment)
    return db_comment

def update_comment_status(db: Session, comment_id: int, status: str):
    """更新评论状态（待审核、已通过、已拒绝、垃圾评论）"""
    db_comment = db.execute(select(Comment).filter(Comment.id == comment_id)).scalar_one_or_none()
    if db_comment:
        db_comment.status = status
        db.commit()
        db.refresh(db_comment)
    return db_comment

def delete_comment(db: Session, comment_id: int):
    """删除评论
    
    Args:
        db: 数据库会话
        comment_id: 评论ID
        
    Returns:
        被删除的评论对象
    """
    db_comment = db.execute(select(Comment).filter(Comment.id == comment_id)).scalar_one_or_none()
    if db_comment:
        db.delete(db_comment)
        db.commit()
    return db_comment

def bulk_update_comment_status(db: Session, comment_ids: list[int], status: str) -> int:
    """批量更新评论状态（分块执行，避免超大IN参数导致性能和兼容性问题）"""
    normalized_ids = _normalize_comment_ids(comment_ids)
    if not normalized_ids:
        return 0

    affected = 0
    for chunk in _iter_chunks(normalized_ids):
        result = db.execute(
            update(Comment)
            .where(Comment.id.in_(chunk))
            .values(status=status)
        )
        affected += int(result.rowcount or 0)
    db.commit()
    return affected

def bulk_delete_comments(db: Session, comment_ids: list[int]) -> int:
    """批量删除评论（分块执行，避免超大IN参数导致性能和兼容性问题）"""
    normalized_ids = _normalize_comment_ids(comment_ids)
    if not normalized_ids:
        return 0

    affected = 0
    for chunk in _iter_chunks(normalized_ids):
        result = db.execute(delete(Comment).where(Comment.id.in_(chunk)))
        affected += int(result.rowcount or 0)
    db.commit()
    return affected
