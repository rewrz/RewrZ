from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from typing import Optional, List
from fastapi import Form

from ..core.database import get_db
from ..core.security import get_current_user
from ..crud import post as crud_post
from ..crud import format as crud_format # Import crud_format
from ..schemas import Post, PostCreate, PostUpdate, User

router = APIRouter()

@router.get("/admin/posts/new", response_class=HTMLResponse)
async def new_post_page(request: Request, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    from ..core.template_filters import get_templates
    templates = get_templates()
    formats = crud_format.get_formats(db) # Fetch all available formats
    return templates.TemplateResponse("admin/post_form.html", {"request": request, "user": current_user, "formats": formats})

@router.post("/posts/", response_model=Post)
def create_post_api(
    request: Request, # Add request to get session
    post: PostCreate, 
    format_ids: Optional[List[int]] = Form(None), # Add format_ids
    csrf_token: str = Form(...), # Expect CSRF token from form
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    from ..core.security import verify_csrf_token
    verify_csrf_token(request, csrf_token) # Verify CSRF token
    return crud_post.create_post(db=db, post=post, author_id=current_user.id, format_ids=format_ids)

@router.get("/posts/{post_id}", response_model=Post)
def read_post_api(post_id: int, db: Session = Depends(get_db)):
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    return db_post

@router.put("/posts/{post_id}", response_model=Post)
def update_post_api(
    request: Request, # Add request to get session
    post_id: int, 
    post: PostUpdate, 
    format_ids: Optional[List[int]] = Form(None), # Add format_ids
    csrf_token: str = Form(...), # Expect CSRF token from form
    db: Session = Depends(get_db), 
    current_user: User = Depends(get_current_user)
):
    from ..core.security import verify_csrf_token
    verify_csrf_token(request, csrf_token) # Verify CSRF token
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to update this post")
    return crud_post.update_post(db=db, post_id=post_id, post=post, format_ids=format_ids)

@router.delete("/posts/{post_id}", response_model=Post)
def delete_post_api(post_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    db_post = crud_post.get_post(db, post_id=post_id)
    if db_post is None:
        raise HTTPException(status_code=404, detail="Post not found")
    if db_post.author_id != current_user.id:
        raise HTTPException(status_code=403, detail="Not authorized to delete this post")
    return crud_post.delete_post(db=db, post_id=post_id)
