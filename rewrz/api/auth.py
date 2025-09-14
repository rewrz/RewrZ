from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session
from datetime import timedelta
from ..core.database import get_db
from ..core.security import verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES, get_current_user
from ..core.config import settings
from ..crud import user as crud_user
from ..schemas import User

router = APIRouter()

# 登录端点已移至main.py中的动态路由注册系统以确保安全性
# @router.post("/token")
# async def login_for_access_token(response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
# 登录函数实现已移至main.py中的动态路由注册系统
# async def login_for_access_token_impl(response: Response, form_data: OAuth2PasswordRequestForm, db: Session):
#     user = crud_user.get_user_by_username(db, username=form_data.username)
#     if not user or not verify_password(form_data.password, user.hashed_password):
#         raise HTTPException(
#             status_code=status.HTTP_401_UNAUTHORIZED,
#             detail="Incorrect username or password",
#             headers={"WWW-Authenticate": "Bearer"},
#         )
#     access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
#     access_token = create_access_token(
#         data={"sub": str(user.id)}, expires_delta=access_token_expires
#     )
#     response.set_cookie(key="access_token", value=access_token, httponly=True, expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite='Lax')
#     admin_path = settings.ADMIN_PATH.rstrip('/')
#     response.headers["HX-Redirect"] = f"{admin_path}/dashboard"
#     return {"message": "Login successful"}

# 登录功能实现（供动态路由调用）
async def login_for_access_token_impl(response: Response, form_data: OAuth2PasswordRequestForm, db: Session):
    """
    登录函数实现，供动态路由调用
    """
    user = crud_user.get_user_by_username(db, username=form_data.username)
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.id)}, expires_delta=access_token_expires
    )
    response.set_cookie(key="access_token", value=access_token, httponly=True, expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60, samesite='Lax')
    admin_path = settings.ADMIN_PATH.rstrip('/')
    response.headers["HX-Redirect"] = f"{admin_path}/dashboard"
    # 返回空内容，只设置头部信息
    return {"message": "Login successful"}

@router.get("/users/me/", response_model=User)
async def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user

# 后台登录和仪表盘路由已完全移至 main.py 中的动态路由注册系统
# 这样可以根据 ADMIN_PATH 配置动态生成路由，提高安全性