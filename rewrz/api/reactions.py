from typing import Optional
import secrets

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.database import get_db
from ..core.security import should_use_secure_cookie
from ..crud import reaction as crud_reaction
from ..models import Comment, Post

router = APIRouter()

VISITOR_TOKEN_COOKIE = "rewrz_visitor_token"
VISITOR_TOKEN_MAX_AGE = 365 * 24 * 60 * 60


class LikePayload(BaseModel):
    target_type: str
    target_id: int
    liked: Optional[bool] = None


class ReactPayload(BaseModel):
    target_type: str
    target_id: int
    reaction_type: Optional[str] = None


def _ensure_visitor_token(request: Request) -> tuple[str, bool]:
    existing = (request.cookies.get(VISITOR_TOKEN_COOKIE) or "").strip()
    if existing:
        return existing, False
    return secrets.token_urlsafe(24), True


def _attach_visitor_cookie(request: Request, response: JSONResponse, token: str) -> None:
    response.set_cookie(
        key=VISITOR_TOKEN_COOKIE,
        value=token,
        max_age=VISITOR_TOKEN_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=should_use_secure_cookie(request),
    )


def _validate_target_exists(db: Session, target_type: str, target_id: int) -> None:
    normalized_type = (target_type or "").strip().lower()
    if normalized_type == "post":
        exists = db.execute(
            select(Post.id).where(
                Post.id == int(target_id),
                Post.status == "published",
                Post.published_at.isnot(None),
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="内容不存在")
        return
    if normalized_type == "comment":
        exists = db.execute(
            select(Comment.id).where(
                Comment.id == int(target_id),
                Comment.status == "approved",
            )
        ).scalar_one_or_none()
        if exists is None:
            raise HTTPException(status_code=404, detail="评论不存在")
        return
    raise HTTPException(status_code=400, detail="无效的目标类型")


@router.get("/api/v1/reactions/summary")
@router.get("/api/reactions/summary")
async def get_reaction_summary(
    request: Request,
    target_type: str = Query(...),
    target_id: int = Query(..., ge=1),
    db: Session = Depends(get_db),
):
    _validate_target_exists(db, target_type, target_id)
    token, should_set_cookie = _ensure_visitor_token(request)
    try:
        summary = crud_reaction.get_reaction_summary(
            db,
            target_type=target_type,
            target_id=target_id,
            visitor_token=token,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = JSONResponse({"success": True, "summary": summary})
    if should_set_cookie:
        _attach_visitor_cookie(request, response, token)
    return response


@router.post("/api/v1/reactions/like")
@router.post("/api/reactions/like")
async def set_like(
    request: Request,
    payload: LikePayload,
    db: Session = Depends(get_db),
):
    _validate_target_exists(db, payload.target_type, payload.target_id)
    token, should_set_cookie = _ensure_visitor_token(request)
    try:
        liked, summary = crud_reaction.set_like_state(
            db,
            target_type=payload.target_type,
            target_id=payload.target_id,
            visitor_token=token,
            like_active=payload.liked,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = JSONResponse({"success": True, "liked": liked, "summary": summary})
    if should_set_cookie:
        _attach_visitor_cookie(request, response, token)
    return response


@router.post("/api/v1/reactions/react")
@router.post("/api/reactions/react")
async def set_reaction(
    request: Request,
    payload: ReactPayload,
    db: Session = Depends(get_db),
):
    _validate_target_exists(db, payload.target_type, payload.target_id)
    token, should_set_cookie = _ensure_visitor_token(request)
    try:
        reaction_type, summary = crud_reaction.set_reaction_state(
            db,
            target_type=payload.target_type,
            target_id=payload.target_id,
            visitor_token=token,
            reaction_type=payload.reaction_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = JSONResponse({"success": True, "reaction_type": reaction_type, "summary": summary})
    if should_set_cookie:
        _attach_visitor_cookie(request, response, token)
    return response
