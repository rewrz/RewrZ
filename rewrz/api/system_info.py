"""
系统信息API模块

提供系统运行环境信息的查看功能，包括：
1. 操作系统信息
2. Python版本信息
3. 框架版本信息
4. 数据库信息
5. 媒体库统计
6. 系统性能信息
"""

import math
import os
import sys
import platform
import psutil
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, select, text
from typing import Dict, Any
from ..core.admin_path import get_request_admin_path
from ..core.config import settings
from ..core.database import get_db, resolve_sqlite_database_path
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..models import Media
from ..schemas import User

router = APIRouter()
templates = get_templates()


async def system_info_page(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    系统信息页面
    
    显示完整的系统运行环境信息
    """
    # 收集系统信息
    system_info = await get_system_info(db)
    
    return templates.TemplateResponse(request, "admin/system_info.html", {
        "request": request,
        "user": current_user,
        "system_info": system_info,
        "admin_path": get_request_admin_path(request),
    })


async def get_system_info_api(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取系统信息API接口
    
    用于主动更新系统信息，返回JSON格式数据
    """
    from fastapi.responses import JSONResponse
    
    try:
        # 收集最新的系统信息
        system_info = await get_system_info(db)
        
        return JSONResponse({
            "success": True,
            "data": system_info,
            "message": "系统信息更新成功",
            "timestamp": __import__('datetime').datetime.now().isoformat()
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"获取系统信息失败: {str(e)}",
            "timestamp": __import__('datetime').datetime.now().isoformat()
        }, status_code=500)


async def get_system_info(db: Session) -> Dict[str, Any]:
    """
    收集系统信息
    
    Args:
        db: 数据库会话
        
    Returns:
        Dict: 包含所有系统信息的字典
    """
    info = {}
    
    # 操作系统信息
    info['os'] = {
        'name': platform.system(),
        'version': platform.release(),
        'architecture': platform.machine(),
        'platform': platform.platform(),
        'hostname': platform.node(),
        'processor': platform.processor() or "Unknown"
    }
    
    # Python信息
    # 说明：sys.executable 是当前进程真正使用的解释器，生产环境应为虚拟环境内的 Python；
    # 项目根目录按本文件位置推导，避免依赖启动目录。
    project_root = Path(__file__).resolve().parents[2]
    is_venv = sys.prefix != sys.base_prefix
    info['python'] = {
        'version': platform.python_version(),
        'implementation': platform.python_implementation(),
        'compiler': platform.python_compiler(),
        'executable': sys.executable,
        'prefix': sys.prefix,
        'base_prefix': sys.base_prefix,
        'is_venv': is_venv,
        # 虚拟环境路径，未启用时显示系统环境说明
        'virtualenv': sys.prefix if is_venv else "未使用虚拟环境",
        'project_root': str(project_root),
        'working_directory': os.getcwd(),
        'path': str(project_root),
    }
    
    # 框架版本信息
    info['frameworks'] = get_framework_versions()
    
    # 数据库信息
    info['database'] = await get_database_info(db)
    
    # 媒体库信息
    info['media'] = await get_media_info(db)
    
    # 系统资源信息
    info['resources'] = get_system_resources()
    
    # 磁盘空间信息
    info['disk'] = get_disk_info()
    
    # 网络信息
    info['network'] = get_network_info()
    
    return info


def get_framework_versions() -> Dict[str, str]:
    """获取框架和依赖库版本信息"""
    versions = {}
    
    try:
        import fastapi
        versions['FastAPI'] = fastapi.__version__
    except:
        versions['FastAPI'] = "Unknown"
    
    try:
        import sqlalchemy
        versions['SQLAlchemy'] = sqlalchemy.__version__
    except:
        versions['SQLAlchemy'] = "Unknown"
    
    try:
        import alembic
        versions['Alembic'] = alembic.__version__
    except:
        versions['Alembic'] = "Unknown"
    
    try:
        import pydantic
        versions['Pydantic'] = pydantic.__version__
    except:
        versions['Pydantic'] = "Unknown"
    
    try:
        import jinja2
        versions['Jinja2'] = jinja2.__version__
    except:
        versions['Jinja2'] = "Unknown"
    
    try:
        import uvicorn
        versions['Uvicorn'] = uvicorn.__version__
    except:
        versions['Uvicorn'] = "Unknown"
    
    try:
        import markdown
        versions['Markdown'] = markdown.__version__
    except:
        versions['Markdown'] = "Unknown"
    
    try:
        import PIL
        versions['Pillow'] = PIL.__version__
    except:
        versions['Pillow'] = "Unknown"
    
    return versions


def _describe_database_type(driver_name: str) -> str:
    driver = str(driver_name or "").split("+", 1)[0].strip().lower()
    type_names = {
        "sqlite": "SQLite",
        "postgresql": "PostgreSQL",
        "mysql": "MySQL/MariaDB",
        "mariadb": "MySQL/MariaDB",
    }
    if driver in type_names:
        return type_names[driver]
    return driver.upper() if driver else "未知"


def _get_database_version(db: Session, dialect_name: str) -> str:
    try:
        if dialect_name == "sqlite":
            value = db.execute(text("SELECT sqlite_version()")).scalar()
        else:
            value = db.execute(text("SELECT version()")).scalar()
        return str(value) if value else "未知"
    except Exception as exc:
        return f"无法获取：{exc}"


def _get_database_table_count(db: Session, dialect_name: str):
    try:
        if dialect_name == "sqlite":
            # 排除 SQLite 内部表（sqlite_sequence 等），只统计业务表。
            sql = text("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
        elif dialect_name == "postgresql":
            sql = text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
            )
        elif dialect_name in {"mysql", "mariadb"}:
            sql = text(
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
            )
        else:
            return "未知"
        return int(db.execute(sql).scalar() or 0)
    except Exception as exc:
        return f"无法获取：{exc}"


async def get_database_info(db: Session) -> Dict[str, Any]:
    """获取数据库信息。

    以当前会话实际绑定的引擎为准，而不是读取进程环境变量：
    生产环境的配置来自 .env 文件，进程环境里通常没有 DATABASE_URL，
    直接读环境变量会错误地显示成默认 SQLite 路径。
    """
    db_info = {}

    try:
        bind = db.get_bind()
        url = getattr(bind, "url", None)
        if url is None and hasattr(bind, "engine"):
            url = getattr(bind.engine, "url", None)

        dialect = getattr(bind, "dialect", None)
        dialect_name = str(getattr(dialect, "name", "") or "").lower()
        driver_name = str(getattr(url, "drivername", "") or "")
        if not dialect_name:
            dialect_name = driver_name.split("+", 1)[0].lower()

        db_info["type"] = _describe_database_type(driver_name or dialect_name)
        db_info["driver"] = driver_name or dialect_name or "未知"

        # 展示连接地址前必须隐藏密码，避免系统信息页泄露数据库凭据。
        try:
            db_info["url"] = url.render_as_string(hide_password=True)
        except Exception:
            db_info["url"] = "无法解析连接地址"

        if dialect_name == "sqlite":
            db_path = resolve_sqlite_database_path(bind)
            if not db_path:
                db_info["path"] = ":memory:（内存数据库）"
                db_info["size"] = "不适用"
                db_info["size_bytes"] = 0
            else:
                db_info["path"] = db_path
                if os.path.isfile(db_path):
                    size_bytes = os.path.getsize(db_path)
                    db_info["size"] = format_file_size(size_bytes)
                    db_info["size_bytes"] = size_bytes
                else:
                    db_info["size"] = "文件不存在"
                    db_info["size_bytes"] = 0

        db_info["version"] = _get_database_version(db, dialect_name)
        db_info["table_count"] = _get_database_table_count(db, dialect_name)
    except Exception as e:
        db_info["error"] = str(e)

    return db_info


async def get_media_info(db: Session) -> Dict[str, Any]:
    """获取媒体库信息。

    统计口径以数据库记录为准，并使用聚合查询：
    旧的 get_all_media(db) 默认只返回最新 100 条，媒体超过 100 个后
    总数与总大小都会偏小，在正式部署环境中显示明显不正确。
    """
    media_info = {}

    try:
        total_files, total_size = db.execute(
            select(
                func.count(Media.id),
                func.coalesce(func.sum(Media.file_size), 0),
            )
        ).one()
        total_files = int(total_files or 0)
        total_size = int(total_size or 0)

        type_counts: Dict[str, int] = {}
        for file_type, count in db.execute(
            select(Media.file_type, func.count(Media.id)).group_by(Media.file_type)
        ).all():
            key = str(file_type or "").strip().lower()
            type_counts[key] = type_counts.get(key, 0) + int(count or 0)

        def count_by_prefix(prefix: str) -> int:
            return sum(value for key, value in type_counts.items() if key.startswith(prefix))

        image_count = count_by_prefix("image")
        video_count = count_by_prefix("video")
        audio_count = count_by_prefix("audio")

        media_info["total_files"] = total_files
        media_info["total_size"] = format_file_size(total_size)
        media_info["total_size_bytes"] = total_size
        media_info["image_count"] = image_count
        media_info["video_count"] = video_count
        media_info["audio_count"] = audio_count
        # 其余类型（文档、压缩包等）统一计入“其他文件”
        media_info["document_count"] = max(0, total_files - image_count - video_count - audio_count)

        # 使用应用真实配置的媒体目录，而不是进程环境变量里的默认值。
        media_dir_setting = str(getattr(settings, "MEDIA_UPLOAD_DIR", "") or "media_uploads").strip() or "media_uploads"
        media_dir = Path(os.path.abspath(os.path.expanduser(media_dir_setting)))
        media_info["directory"] = str(media_dir)
        media_info["directory_exists"] = media_dir.is_dir()

        if media_info["directory_exists"]:
            dir_size, dir_file_count = get_directory_stats(media_dir)
            media_info["directory_size"] = format_file_size(dir_size)
            media_info["directory_size_bytes"] = dir_size
            media_info["directory_file_count"] = dir_file_count
    except Exception as e:
        media_info["error"] = str(e)

    return media_info


def get_system_resources() -> Dict[str, Any]:
    """获取系统资源信息"""
    resources = {}
    
    try:
        # 部分虚拟化环境不支持读取频率，单独兜底，避免影响内存、交换分区信息展示。
        try:
            cpu_frequency = psutil.cpu_freq()
        except Exception:
            cpu_frequency = None

        # CPU信息
        resources['cpu'] = {
            'count': psutil.cpu_count() or 0,
            'count_logical': psutil.cpu_count(logical=True) or 0,
            'usage_percent': psutil.cpu_percent(interval=0.1),
            'frequency': cpu_frequency._asdict() if cpu_frequency else None
        }
        
        # 内存信息
        memory = psutil.virtual_memory()
        resources['memory'] = {
            'total': format_file_size(memory.total),
            'available': format_file_size(memory.available),
            'used': format_file_size(memory.used),
            'usage_percent': memory.percent,
            'total_bytes': memory.total,
            'available_bytes': memory.available,
            'used_bytes': memory.used
        }
        
        # 交换分区信息
        swap = psutil.swap_memory()
        resources['swap'] = {
            'total': format_file_size(swap.total),
            'used': format_file_size(swap.used),
            'free': format_file_size(swap.free),
            'usage_percent': swap.percent,
            'total_bytes': swap.total
        }
        
    except Exception as e:
        resources['error'] = str(e)
    
    return resources


def get_disk_info() -> Dict[str, Any]:
    """获取磁盘空间信息"""
    disk_info = {}
    
    try:
        # 获取当前工作目录的磁盘使用情况
        disk_usage = psutil.disk_usage('.')
        
        disk_info['current_drive'] = {
            'total': format_file_size(disk_usage.total),
            'used': format_file_size(disk_usage.used),
            'free': format_file_size(disk_usage.free),
            'usage_percent': (disk_usage.used / disk_usage.total) * 100 if disk_usage.total else 0,
            'total_bytes': disk_usage.total,
            'used_bytes': disk_usage.used,
            'free_bytes': disk_usage.free
        }
        
        # 获取所有磁盘分区
        partitions = psutil.disk_partitions()
        disk_info['partitions'] = []
        
        for partition in partitions:
            try:
                partition_usage = psutil.disk_usage(partition.mountpoint)
                disk_info['partitions'].append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'total': format_file_size(partition_usage.total),
                    'used': format_file_size(partition_usage.used),
                    'free': format_file_size(partition_usage.free),
                    'usage_percent': (partition_usage.used / partition_usage.total) * 100 if partition_usage.total else 0
                })
            except OSError as exc:
                # Linux 上部分伪文件系统会直接抛出 OSError，不能只处理 PermissionError。
                disk_info['partitions'].append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'error': '无权限访问' if isinstance(exc, PermissionError) else f'无法访问：{exc}'
                })
                
    except Exception as e:
        disk_info['error'] = str(e)
    
    return disk_info


def get_network_info() -> Dict[str, Any]:
    """获取网络信息"""
    network_info = {}
    
    try:
        # 获取网络接口信息
        network_info['interfaces'] = []
        
        for interface_name, addresses in psutil.net_if_addrs().items():
            interface_info = {
                'name': interface_name,
                'addresses': []
            }
            
            for addr in addresses:
                if addr.family.name in ['AF_INET', 'AF_INET6']:
                    interface_info['addresses'].append({
                        'family': addr.family.name,
                        'address': addr.address,
                        'netmask': addr.netmask,
                        'broadcast': addr.broadcast
                    })
            
            if interface_info['addresses']:
                network_info['interfaces'].append(interface_info)
        
        # 获取网络连接统计
        net_io = psutil.net_io_counters()
        if net_io:
            network_info['io_stats'] = {
                'bytes_sent': format_file_size(net_io.bytes_sent),
                'bytes_recv': format_file_size(net_io.bytes_recv),
                'packets_sent': net_io.packets_sent,
                'packets_recv': net_io.packets_recv
            }
    
    except Exception as e:
        network_info['error'] = str(e)
    
    return network_info


def format_file_size(size_bytes: int) -> str:
    """格式化文件大小显示"""
    if size_bytes <= 0:
        return "0 B"

    size_names = ["B", "KB", "MB", "GB", "TB", "PB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    i = min(i, len(size_names) - 1)
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def get_directory_stats(directory: str) -> tuple[int, int]:
    """获取目录总大小（字节）与文件数量"""
    total_size = 0
    file_count = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                    file_count += 1
                except (OSError, FileNotFoundError):
                    pass
    except (OSError, FileNotFoundError):
        pass
    return total_size, file_count
