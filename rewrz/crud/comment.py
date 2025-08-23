"""评论CRUD操作模块

本模块提供评论相关的数据库操作功能，包括创建、读取、更新、删除评论。
支持嵌套评论和状态管理。
"""
from sqlalchemy.orm import Session
from sqlalchemy import select
from ..models import Comment
from ..schemas import CommentCreate
from datetime import datetime

def get_comment(db: Session, comment_id: int):
    """根据评论id获取评论信息"""
    return db.execute(select(Comment).filter(Comment.id == comment_id)).scalar_one_or_none()

def get_comments_for_post(db: Session, post_id: int, skip: int = 0, limit: int = 100):
    """获取指定文章的评论列表，支持分页"""
    return db.execute(select(Comment).filter(Comment.post_id == post_id).offset(skip).limit(limit)).scalars().all()

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
    db_comment = Comment(
        post_id=comment.post_id,
        parent_id=comment.parent_id,
        author_name=comment.author_name,
        author_email=comment.author_email,
        author_url=comment.author_url,
        content=comment.content,
        ip_address=ip_address,
        user_agent=user_agent,
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
