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
import os
import json
import secrets
from datetime import datetime
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, status, Request, Response, Form
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from ..core.database import get_db, create_all_tables
from ..core.security import get_password_hash, verify_csrf_token, generate_csrf_token
from ..core.template_filters import get_templates
from ..crud import user as crud_user
from ..crud import setting as crud_setting
from ..crud import category as crud_category
from ..crud import tag as crud_tag
from ..crud import format as crud_format
from ..schemas import UserCreate, SettingCreate, CategoryCreate, TagCreate, FormatCreate
from ..core.config import settings
from typing import Dict, Any

router = APIRouter()
templates = get_templates()

@router.get("/installer", response_class=HTMLResponse)
async def installer_page(request: Request):
    """
    安装向导首页
    
    检查系统是否已安装，如果已安装则重定向到管理后台
    """
    # 如果 .env 文件存在，说明已经安装过了，重定向到动态后台登录页面
    if os.path.exists(".env"):
        admin_path = settings.ADMIN_PATH.rstrip('/')
        return RedirectResponse(url=f"{admin_path}/login")
    
    # 初始化 CSRF 令牌
    csrf_token = generate_csrf_token()
    
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
    
    # 检查是否已安装
    if os.path.exists(".env"):
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
    if os.path.exists(".env"):
        return JSONResponse({"error": "系统已安装"}, status_code=400)
    
    csrf_token = generate_csrf_token()
    
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
    
    return templates.TemplateResponse(step_templates[step_number], {
        "request": request,
        "csrf_token": csrf_token,
        "step_number": step_number
    })

@router.post("/installer/initialize-database")
async def initialize_database(request: Request, database_path: str = Form("./data/rewrz.db")):
    """
    初始化数据库
    
    创建数据库表结构和运行初始迁移
    """
    try:
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
        # verify_csrf_token(request, csrf_token)
        
        # 获取数据库会话
        from ..core.database import SessionLocal
        from sqlalchemy.orm import sessionmaker
        # 使用安装向导中设置的数据库路径
        database_path = request.session.get("database_path", "./data/rewrz.db")
        new_database_url = f"sqlite:///{database_path}"
        import sqlalchemy as sa
        new_engine = sa.create_engine(new_database_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
        db = SessionLocal()
        
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
        # verify_csrf_token(request, csrf_token)
        
        # 获取数据库会话
        from ..core.database import SessionLocal
        from sqlalchemy.orm import sessionmaker
        # 使用安装向导中设置的数据库路径
        database_path = request.session.get("database_path", "./data/rewrz.db")
        new_database_url = f"sqlite:///{database_path}"
        import sqlalchemy as sa
        new_engine = sa.create_engine(new_database_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
        db = SessionLocal()
        
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
    create_sample_content: bool = Form(False),
    csrf_token: str = Form(...),
):
    """
    创建初始内容
    
    创建默认分类、标签、格式和示例内容
    """
    try:
        # 验证 CSRF 令牌
        # verify_csrf_token(request, csrf_token)
        
        # 获取数据库会话
        from ..core.database import SessionLocal
        from sqlalchemy.orm import sessionmaker
        # 使用安装向导中设置的数据库路径
        database_path = request.session.get("database_path", "./data/rewrz.db")
        new_database_url = f"sqlite:///{database_path}"
        import sqlalchemy as sa
        new_engine = sa.create_engine(new_database_url, connect_args={"check_same_thread": False})
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=new_engine)
        db = SessionLocal()
        
        try:
            # 创建默认分类
            default_categories = [
                {"name": "技术", "slug": "tech", "description": "技术相关文章"},
                {"name": "生活", "slug": "life", "description": "生活随笔和感悟"},
                {"name": "思考", "slug": "thoughts", "description": "个人思考和观点"}
            ]
            
            # 只有当用户选择创建默认内容时才创建
            if create_sample_content:
                for cat_data in default_categories:
                    try:
                        category = CategoryCreate(**cat_data)
                        crud_category.create_category(db, category)
                    except:
                        pass  # 忽略重复创建错误
                
                # 创建默认标签
                default_tags = [
                    {"name": "Python", "slug": "python"},
                    {"name": "Web开发", "slug": "web-dev"},
                    {"name": "编程", "slug": "programming"},
                    {"name": "教程", "slug": "tutorial"}
                ]
                
                for tag_data in default_tags:
                    try:
                        tag = TagCreate(**tag_data)
                        crud_tag.create_tag(db, tag)
                    except:
                        pass  # 忽略重复创建错误
                
                # 创建默认格式
                default_formats = [
                    {"name": "标准文章", "slug": "article", "description": "标准的博客文章格式"},
                    {"name": "微博", "slug": "micro-post", "description": "类似微博的短内容"},
                    {"name": "相册", "slug": "photo-album", "description": "图片展示格式"},
                    {"name": "视频", "slug": "video", "description": "视频内容格式"},
                    {"name": "诗词歌赋", "slug": "poetry-song", "description": "诗词歌赋内容格式"}
                ]
                
                for format_data in default_formats:
                    try:
                        format_obj = FormatCreate(**format_data)
                        crud_format.create_format(db, format_obj)
                    except:
                        pass  # 忽略重复创建错误
            
            content_created = {
                "categories": len(default_categories) if create_sample_content else 0,
                "tags": len(default_tags) if create_sample_content else 0, 
                "formats": len(default_formats) if create_sample_content else 0,
                "sample_post": create_sample_content
            }
            
            return JSONResponse({
                "success": True,
                "message": "初始内容创建成功",
                "created": content_created
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
        # verify_csrf_token(request, csrf_token)
        
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
        # verify_csrf_token(request, csrf_token)
        
        # 检查是否已安装
        if os.path.exists(".env"):
            return JSONResponse({
                "success": False,
                "error": "系统已经安装"
            }, status_code=400)
        
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
        with open(".env", "w", encoding="utf-8") as f:
            f.write(env_content)
        
        # 关键修复：立即重新加载配置和数据库连接
        from ..core.config import settings
        from ..core.database import db_manager
        
        # 重新加载配置
        config_reloaded = settings.reload_config()
        
        # 重新初始化数据库连接
        db_initialized = db_manager.initialize()
        
        if not db_initialized:
            return JSONResponse({
                "success": False,
                "error": "配置文件创建成功，但数据库连接初始化失败"
            }, status_code=500)
        
        # 使用新的数据库连接保存安装状态
        db = db_manager.get_session()
        if not db:
            return JSONResponse({
                "success": False,
                "error": "无法获取数据库会话"
            }, status_code=500)
        
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
    try:
        # 验证 CSRF 令牌
        # verify_csrf_token(request, csrf_token)

        # 检查是否已安装
        if os.path.exists(".env"):
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
        with open(".env", "w") as f:
            f.write(env_content.strip())

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
        
    except Exception as e:
        if os.path.exists(".env"):
            os.remove(".env")  # 清理失败的安装
        raise HTTPException(status_code=500, detail=f"安装失败: {str(e)}")
