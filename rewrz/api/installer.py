"""
安装向导 API 模块

提供 RewrZ 博客系统的 Web 安装向导功能，包括：
1. 环境检查和验证
2. 数据库初始化和迁移
3. 管理员账户创建
4. 基础站点配置
5. 初始内容和设置
6. 安装完成确认
"""
import secrets
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..core.database import get_db, create_all_tables
from ..core.security import get_password_hash, verify_csrf_token, generate_csrf_token
from ..core.template_filters import get_templates
from ..models import Post, User
from ..crud import user as crud_user
from ..crud import setting as crud_setting
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..crud import post as crud_post
from ..schemas import (
    UserCreate,
    SettingCreate,
    CategoryCreate,
    TagCreate,
    FormatCreate,
    PostCreate,
)
from ..core.config import get_env_file_path, settings
from ..core.default_content import (
    DEFAULT_CATEGORIES,
    DEFAULT_TAGS,
    SAMPLE_POST,
    get_default_formats,
)
from typing import Dict, Any

router = APIRouter()
templates = get_templates()


def _is_installer_locked() -> bool:
    """统一安装状态判定，避免未完成安装时被残留文件误锁死。"""
    return bool(settings.installation_complete)


def _ensure_installer_csrf_token(request: Request) -> str:
    """确保安装向导使用会话内一致的 CSRF 令牌。"""
    csrf_token = ""
    try:
        csrf_token = str(request.session.get("csrf_token") or "").strip()
    except Exception:
        csrf_token = ""
    if not csrf_token:
        csrf_token = generate_csrf_token()
        try:
            request.session["csrf_token"] = csrf_token
        except Exception:
            pass
    return csrf_token


def _open_installer_session(request: Request) -> Session:
    """按安装向导中选定的数据库路径打开独立会话。"""
    import sqlalchemy as sa
    from sqlalchemy.orm import sessionmaker

    database_path = request.session.get("database_path", "./data/rewrz.db")
    new_engine = sa.create_engine(
        f"sqlite:///{database_path}", connect_args={"check_same_thread": False}
    )
    return sessionmaker(autocommit=False, autoflush=False, bind=new_engine)()


def _get_or_create_category(db: Session, payload: Dict[str, Any]):
    """按 slug/name 幂等创建分类，返回（分类对象，是否为新建）。"""
    existing = crud_category.get_category_by_slug(db, payload["slug"])
    if existing is None:
        existing = crud_category.get_category_by_name(db, payload["name"])
    if existing is not None:
        return existing, False
    return crud_category.create_category(db, CategoryCreate(**payload)), True


def _get_or_create_tag(db: Session, payload: Dict[str, Any]):
    """按 slug/name 幂等创建标签，返回（标签对象，是否为新建）。"""
    existing = crud_tag.get_tag_by_slug(db, payload["slug"])
    if existing is None:
        existing = crud_tag.get_tag_by_name(db, payload["name"])
    if existing is not None:
        return existing, False
    return crud_tag.create_tag(db, TagCreate(**payload)), True


def _ensure_default_formats(db: Session) -> int:
    """补齐 `content_intents` 定义的默认内容类型，返回新建数量。"""
    created = 0
    for payload in get_default_formats():
        if crud_format.get_format_by_slug(db, payload["slug"]) is not None:
            continue
        crud_format.create_format(db, FormatCreate(**payload))
        created += 1
    return created


def _stamp_alembic_head(database_url: str) -> None:
    """把新库标记为 Alembic 最新版本。

    安装阶段由 `create_all` 直接建表，若不标记 head，
    后续 `alembic upgrade head` 会重复执行建表迁移而失败。
    """
    from alembic import command
    from alembic.config import Config

    config = Config(str(Path(__file__).resolve().parents[2] / "alembic.ini"))
    # 安装阶段 .env 尚未生成，应用配置中的 DATABASE_URL 为空，
    # alembic/env.py 会回落到这里的 sqlalchemy.url。
    config.set_main_option("sqlalchemy.url", database_url)
    command.stamp(config, "head")


@router.get("/installer", response_class=HTMLResponse)
async def installer_page(request: Request):
    """
    安装向导首页
    
    检查系统是否已安装，如果已安装则重定向到管理后台
    """
    if _is_installer_locked():
        return RedirectResponse(url="/")
    
    # 初始化 CSRF 令牌（绑定到会话）
    csrf_token = _ensure_installer_csrf_token(request)
    
    return templates.TemplateResponse("installer/welcome.html", {
        "request": request,
        "csrf_token": csrf_token
    })

@router.get("/installer/check-environment")
async def check_environment(request: Request):
    """
    检查安装环境
    
    验证系统环境是否满足安装要求
    """
    checks = {
        "python_version": False,
        "write_permissions": False,
        "media_directory": False,
        "database_path": False,
        "dependencies": False
    }
    
    errors = []
    warnings = []
    
    # 检查Python版本 (需要3.10+)
    import sys
    if sys.version_info >= (3, 10):
        checks["python_version"] = True
    else:
        errors.append(f"Python版本过低: 当前版本 {sys.version_info.major}.{sys.version_info.minor}，需要 3.10+")
    
    # 检查写权限
    try:
        test_file = Path(".test_write")
        test_file.write_text("test")
        test_file.unlink()
        checks["write_permissions"] = True
    except Exception as e:
        errors.append(f"当前目录缺少写权限: {str(e)}")
    
    # 检查媒体目录
    try:
        media_dir = Path("media_uploads")
        media_dir.mkdir(exist_ok=True)
        test_media_file = media_dir / ".test_write"
        test_media_file.write_text("test")
        test_media_file.unlink()
        checks["media_directory"] = True
    except Exception as e:
        errors.append(f"媒体目录创建或写入失败: {str(e)}")
    
    # 检查数据库路径
    try:
        data_dir = Path("data")
        data_dir.mkdir(exist_ok=True)
        checks["database_path"] = True
    except Exception as e:
        errors.append(f"数据目录创建失败: {str(e)}")
    
    # 检查关键依赖库
    try:
        import fastapi
        import sqlalchemy
        import jinja2
        checks["dependencies"] = True
    except ImportError as e:
        errors.append(f"缺少关键依赖库: {str(e)}")
    
    if _is_installer_locked():
        errors.append("系统已经安装，如需重新安装请删除 .env 文件")
    
    can_proceed = len(errors) == 0 and all(checks.values())
    
    return JSONResponse({
        "success": can_proceed,
        "checks": checks,
        "errors": errors,
        "warnings": warnings
    })

@router.get("/installer/step/{step_number}")
async def get_install_step(step_number: float, request: Request):
    """
    获取安装步骤页面
    
    根据步骤编号返回相应的安装步骤模板
    """
    if _is_installer_locked():
        return JSONResponse({"error": "系统已安装"}, status_code=400)
    
    csrf_token = _ensure_installer_csrf_token(request)
    
    step_templates = {
        1.0: "installer/step1_environment.html",
        2.0: "installer/step2_database.html", 
        3.0: "installer/step3_admin.html",
        4.0: "installer/step4_site_config.html",
        4.5: "installer/step4_5_admin_path.html",  # 新增后台路径配置步骤
        5.0: "installer/step5_initial_content.html",
        6.0: "installer/step6_complete.html"
    }
    
    if step_number not in step_templates:
        raise HTTPException(status_code=404, detail="安装步骤不存在")

    context: Dict[str, Any] = {
        "request": request,
        "csrf_token": csrf_token,
        "step_number": step_number
    }

    # 初始内容步骤的预览数据来自后端同一份定义，避免与创建逻辑漂移
    if step_number == 5.0:
        context["default_content"] = {
            "categories": [dict(item) for item in DEFAULT_CATEGORIES],
            "tags": [dict(item) for item in DEFAULT_TAGS],
            "formats": [dict(item) for item in get_default_formats()],
        }

    return templates.TemplateResponse(step_templates[step_number], context)

@router.post("/installer/initialize-database")
async def initialize_database(
    request: Request,
    database_path: str = Form("./data/rewrz.db"),
    csrf_token: str = Form(...),
):
    """
    初始化数据库
    
    创建数据库表结构和运行初始迁移
    """
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)

        # 保存数据库路径到会话中，供后续步骤使用
        request.session["database_path"] = database_path
        
        # 创建数据目录（如果不存在）
        from pathlib import Path
        db_path = Path(database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 更新数据库URL并重新创建引擎
        from ..core.database import engine, SessionLocal, Base
        import sqlalchemy as sa
        
        # 重新创建引擎使用用户指定的数据库路径
        new_database_url = f"sqlite:///{database_path}"
        new_engine = sa.create_engine(new_database_url, connect_args={"check_same_thread": False})
        
        # 创建数据库表
        Base.metadata.create_all(bind=new_engine)

        # 新库已包含最新结构，直接标记为 Alembic head
        _stamp_alembic_head(new_database_url)

        return JSONResponse({
            "success": True,
            "message": "数据库初始化成功"
        })
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"数据库初始化失败: {str(e)}"
        }, status_code=500)

@router.post("/installer/create-admin")
async def create_admin_user(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    display_name: str = Form(None),
    csrf_token: str = Form(...),
):
    """
    创建管理员账户
    
    创建首个管理员账户，并设置为超级管理员角色
    """
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)
        
        db = _open_installer_session(request)

        try:
            # 检查用户名是否已存在
            existing_user = crud_user.get_user_by_username(db, username=username)
            if existing_user:
                return JSONResponse({
                    "success": False,
                    "error": "用户名已存在"
                }, status_code=400)
            
            # 检查邮箱是否已存在
            existing_email = crud_user.get_user_by_email(db, email=email)
            if existing_email:
                return JSONResponse({
                    "success": False,
                    "error": "邮箱已存在"
                }, status_code=400)
            
            # 创建管理员用户
            user_data = UserCreate(
                username=username,
                email=email,
                password=password,
                display_name=display_name or username
            )
            
            admin_user = crud_user.create_user(db=db, user=user_data)
            
            # 设置为超级管理员
            admin_user.role = "super_admin"
            db.commit()

            # 记录管理员 ID，供初始内容步骤作为示例文章作者
            request.session["admin_user_id"] = admin_user.id

            return JSONResponse({
                "success": True,
                "message": "管理员账户创建成功",
                "user_id": admin_user.id
            })
        finally:
            db.close()
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"创建管理员账户失败: {str(e)}"
        }, status_code=500)

@router.post("/installer/configure-site")
async def configure_site(
    request: Request,
    site_title: str = Form(...),
    tagline: str = Form(None),
    site_url: str = Form(None),
    timezone: str = Form("Asia/Shanghai"),
    language: str = Form("zh-CN"),
    csrf_token: str = Form(...),
):
    """
    配置站点基础信息
    
    设置站点标题、号口、URL等基础信息
    """
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)
        
        db = _open_installer_session(request)

        try:
            # 基础站点设置
            settings_data = [
                {
                    "key": "site_title",
                    "value": {"value": site_title},
                    "description": "站点标题",
                    "category": "basic",
                    "type": "text"
                },
                {
                    "key": "tagline", 
                    "value": {"value": tagline or ""},
                    "description": "站点副标题",
                    "category": "basic",
                    "type": "text"
                },
                {
                    "key": "site_url",
                    "value": {"value": site_url or ""},
                    "description": "站点URL地址",
                    "category": "basic", 
                    "type": "text"
                },
                {
                    "key": "timezone",
                    "value": {"value": timezone},
                    "description": "时区设置",
                    "category": "basic",
                    "type": "select"
                },
                {
                    "key": "language",
                    "value": {"value": language},
                    "description": "语言设置",
                    "category": "basic",
                    "type": "select"
                }
            ]
            
            # 保存设置
            for setting_data in settings_data:
                setting = SettingCreate(**setting_data)
                crud_setting.create_setting(db, setting)
            
            return JSONResponse({
                "success": True,
                "message": "站点配置保存成功"
            })
        finally:
            db.close()
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"站点配置失败: {str(e)}"
        }, status_code=500)

@router.post("/installer/create-initial-content")
async def create_initial_content(
    request: Request,
    create_default_content: bool = Form(False),
    create_sample_content: bool = Form(False),
    csrf_token: str = Form(...),
):
    """
    创建初始内容

    - create_default_content：创建默认分类、标签与内容类型
    - create_sample_content：创建一篇示例文章

    数量统计只统计本次真正新建的记录，重复提交同一库时计数为 0。
    """
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)

        created = {
            "categories": 0,
            "tags": 0,
            "formats": 0,
            "sample_post": False,
        }

        if not create_default_content and not create_sample_content:
            return JSONResponse({
                "success": True,
                "message": "未勾选任何初始内容，已跳过",
                "created": created
            })

        db = _open_installer_session(request)

        try:
            category_ids = []
            tag_ids = []

            if create_default_content:
                for payload in DEFAULT_CATEGORIES:
                    category, is_new = _get_or_create_category(db, payload)
                    category_ids.append(category.id)
                    created["categories"] += int(is_new)

                for payload in DEFAULT_TAGS:
                    tag, is_new = _get_or_create_tag(db, payload)
                    tag_ids.append(tag.id)
                    created["tags"] += int(is_new)

            # 内容类型是内容意图（article/micro/poem），只要创建内容就必须可用
            if create_default_content or create_sample_content:
                created["formats"] += _ensure_default_formats(db)

            if create_sample_content:
                # 示例文章按 slug 幂等，重复提交不重复创建
                existing_sample = db.execute(
                    select(Post).filter(Post.slug == SAMPLE_POST["slug"])
                ).scalar_one_or_none()

                if existing_sample is None:
                    # 示例文章需要归属，未勾选默认内容时补齐首个默认分类与标签
                    if not category_ids:
                        category, is_new = _get_or_create_category(db, DEFAULT_CATEGORIES[0])
                        category_ids.append(category.id)
                        created["categories"] += int(is_new)
                    if not tag_ids:
                        tag, is_new = _get_or_create_tag(db, DEFAULT_TAGS[0])
                        tag_ids.append(tag.id)
                        created["tags"] += int(is_new)

                    # 作者优先取管理员创建步骤记录的 ID，兜底用首个后台用户
                    author_id = request.session.get("admin_user_id")
                    if author_id is None:
                        first_user = db.execute(
                            select(User).order_by(User.id)
                        ).scalars().first()
                        author_id = first_user.id if first_user else None

                    article_format = crud_format.get_format_by_slug(db, "article")
                    crud_post.create_post(
                        db,
                        PostCreate(
                            title=SAMPLE_POST["title"],
                            slug=SAMPLE_POST["slug"],
                            content_markdown=SAMPLE_POST["content_markdown"],
                            excerpt=SAMPLE_POST["excerpt"],
                            post_type="post",
                            status="published",
                            category_ids=[category_ids[0]],
                            tag_ids=[tag_ids[0]],
                        ),
                        author_id=author_id,
                        format_ids=[article_format.id],
                    )
                    created["sample_post"] = True

            return JSONResponse({
                "success": True,
                "message": "初始内容创建成功",
                "created": created
            })
        finally:
            db.close()

    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"创建初始内容失败: {str(e)}"
        }, status_code=500)

@router.post("/installer/configure-admin-path")
async def configure_admin_path(
    request: Request,
    path_template: str = Form(...),
    brand_name: str = Form("rewrz"),
    short_prefix: str = Form("ra"),
    custom_path: str = Form(None),
    random_length: int = Form(8),
    csrf_token: str = Form(...)
):
    """
    配置后台路径
    
    根据用户选择的模板和参数生成后台路径
    """
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)
        
        # 导入后台路径生成器
        from ..core.admin_path_generator import generate_admin_path, validate_admin_path
        
        # 生成后台路径
        try:
            admin_path = generate_admin_path(
                template=path_template,
                brand=brand_name,
                prefix=short_prefix,
                custom_path=custom_path,
                random_length=random_length
            )
        except ValueError as e:
            return JSONResponse({
                "success": False,
                "error": f"路径生成失败: {str(e)}"
            }, status_code=400)
        
        # 验证路径
        is_valid, error_message = validate_admin_path(admin_path)
        if not is_valid:
            return JSONResponse({
                "success": False,
                "error": f"路径验证失败: {error_message}"
            }, status_code=400)
        
        # 保存配置到会话（安装完成时使用）
        request.session["admin_path_config"] = {
            "admin_path": admin_path,
            "template": path_template,
            "brand_name": brand_name,
            "short_prefix": short_prefix,
            "custom_path": custom_path,
            "random_length": random_length
        }
        
        return JSONResponse({
            "success": True,
            "message": "后台路径配置成功！",
            "admin_path": admin_path
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"配置后台路径失败: {str(e)}"
        }, status_code=500)

@router.post("/installer/finalize")
async def finalize_installation(
    request: Request,
    csrf_token: str = Form(...)
):
    """
    完成安装
    
    创建 .env 文件并完成最终配置
    """
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)
        
        if _is_installer_locked():
            return JSONResponse({
                "success": False,
                "error": "系统已经安装"
            }, status_code=400)
        
        env_path = Path(get_env_file_path())
        previous_env_content = None
        previous_env_existed = env_path.exists()
        if previous_env_existed:
            previous_env_content = env_path.read_text(encoding="utf-8")
        
        # 获取数据库路径配置（从会话中获取用户自定义的路径）
        database_path = request.session.get("database_path", "./data/rewrz.db")
        
        # 生成安全密钥
        secret_key = secrets.token_hex(32)
        
        # 获取后台路径配置（从会话中或使用默认值）
        admin_path_config = request.session.get("admin_path_config")
        if admin_path_config:
            admin_path = admin_path_config["admin_path"]
        else:
            # 如果没有配置，使用默认的随机路径
            admin_path = "/admin_" + secrets.token_hex(8)
        
        # 创建 .env 文件
        env_content = f'''# RewrZ 博客系统配置文件
# 由安装向导自动生成，请勿手动修改

# 安全密钥（用于加密和签名）
SECRET_KEY="{secret_key}"

# 数据库连接地址
DATABASE_URL="sqlite:///{database_path}"

# 管理后台路径（随机生成以提高安全性）
ADMIN_PATH="{admin_path}"

# 媒体上传目录
MEDIA_UPLOAD_DIR="media_uploads"

# 会话过期时间（分钟）
ACCESS_TOKEN_EXPIRE_MINUTES=43200

# 日志级别
LOG_LEVEL="INFO"

# 安装完成标记
INSTALLATION_COMPLETE="true"
'''
        
        # 写入 .env 文件
        env_path.write_text(env_content, encoding="utf-8")
        
        # 关键修复：立即重新加载配置和数据库连接
        from ..core.config import settings
        from ..core.database import db_manager
        
        # 重新加载配置
        config_reloaded = settings.reload_config()
        
        # 重新初始化数据库连接
        db_initialized = db_manager.initialize()
        
        if not db_initialized:
            raise RuntimeError("配置文件创建成功，但数据库连接初始化失败")
        
        # 使用新的数据库连接保存安装状态
        db = db_manager.get_session()
        if not db:
            raise RuntimeError("无法获取数据库会话")
        
        try:
            # 更新安装状态设置
            install_status_setting = SettingCreate(
                key="installation_complete",
                value={"value": True},
                description="安装完成标记",
                category="system",
                type="boolean"
            )
            crud_setting.create_setting(db, install_status_setting)
            
            # 记录安装时间
            install_time_setting = SettingCreate(
                key="installation_time",
                value={"value": str(datetime.now())},
                description="安装完成时间",
                category="system",
                type="datetime"
            )
            crud_setting.create_setting(db, install_time_setting)
        finally:
            db.close()
        
        return JSONResponse({
            "success": True,
            "message": "RewrZ 博客系统安装完成！配置已自动重载，可以立即使用。",
            "admin_path": admin_path,  # 返回后台路径供用户查看
            "redirect_url": f"{admin_path}/login",
            "auto_reloaded": True  # 标记配置已自动重载
        })
        
    except Exception as e:
        if 'env_path' in locals():
            try:
                if previous_env_existed and previous_env_content is not None:
                    env_path.write_text(previous_env_content, encoding="utf-8")
                elif env_path.exists():
                    env_path.unlink()
            except OSError:
                pass
            try:
                settings.reload_config()
            except Exception:
                pass
        return JSONResponse({
            "success": False,
            "error": f"完成安装失败: {str(e)}"
        }, status_code=500)

# 旧的简单安装端点（保留兼容性）
@router.post("/installer/setup")
async def run_installer(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...),
    site_title: str = Form(...),
    csrf_token: str = Form(...)
):
    """
    简单安装流程（兼容旧模板）
    
    一步完成基础安装，包括创建管理员和基础配置
    """
    env_created = False
    try:
        # 验证 CSRF 令牌
        verify_csrf_token(request, csrf_token)

        # 检查是否已安装
        if _is_installer_locked():
            raise HTTPException(status_code=400, detail="系统已经安装")

        # 1. 创建 .env 文件
        secret_key = secrets.token_hex(32)
        admin_path = "/admin_" + secrets.token_hex(8)  # 生成随机后台路径
        database_path = "./data/rewrz.db"  # 默认数据库路径
        env_content = f'''
SECRET_KEY="{secret_key}"
DATABASE_URL="sqlite:///{database_path}"
ADMIN_PATH="{admin_path}"
MEDIA_UPLOAD_DIR="media_uploads"
'''
        env_path = Path(get_env_file_path())
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(env_content.strip())
        env_created = True

        # 2. 初始化数据库
        # 创建数据目录（如果不存在）
        from pathlib import Path
        db_path = Path(database_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 重新创建引擎使用指定的数据库路径
        from ..core.database import engine, SessionLocal, Base
        import sqlalchemy as sa
        new_database_url = f"sqlite:///{database_path}"
        new_engine = sa.create_engine(new_database_url, connect_args={"check_same_thread": False})
        Base.metadata.create_all(bind=new_engine)

        # 获取数据库会话
        from sqlalchemy.orm import sessionmaker
        NewSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
        db = NewSessionLocal()
        
        try:
            # 3. 创建管理员用户
            db_user = crud_user.get_user_by_username(db, username=username)
            if db_user:
                raise HTTPException(status_code=400, detail="用户名已存在")
            
            user_create = UserCreate(username=username, email=email, password=password)
            admin_user = crud_user.create_user(db=db, user=user_create)
            admin_user.role = "super_admin"
            db.commit()

            # 保存站点标题
            site_title_setting = SettingCreate(
                key="site_title", 
                value={"value": site_title}, 
                description="网站主标题",
                category="basic",
                type="text"
            )
            crud_setting.create_setting(db, site_title_setting)
        finally:
            db.close()

        # 重定向到动态后台登录页面
        return RedirectResponse(url=f"{admin_path}/login", status_code=303)
        
    except HTTPException:
        raise
    except Exception as e:
        env_path = Path(get_env_file_path())
        if env_created and env_path.exists():
            env_path.unlink()  # 仅清理当前安装流程新建的 .env，避免误删已部署配置
        raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")

