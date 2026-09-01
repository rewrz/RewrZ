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

import os
import sys
import platform
import psutil
from pathlib import Path
from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import Dict, Any
from ..core.admin_path import get_request_admin_path
from ..core.database import get_db
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..schemas import User
from ..crud import media as crud_media

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
    info['python'] = {
        'version': platform.python_version(),
        'implementation': platform.python_implementation(),
        'compiler': platform.python_compiler(),
        'executable': sys.executable,
        'path': sys.path[0]
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


async def get_database_info(db: Session) -> Dict[str, Any]:
    """获取数据库信息"""
    db_info = {}
    
    try:
        # 获取数据库URL
        db_url = os.getenv('DATABASE_URL', 'sqlite:///./rewrz.db')
        db_info['url'] = db_url
        
        # 解析数据库类型
        if db_url.startswith('sqlite'):
            db_info['type'] = 'SQLite'
            db_path = db_url.replace('sqlite:///', '')
            db_info['path'] = os.path.abspath(db_path)
            
            # 获取数据库文件大小
            if os.path.exists(db_info['path']):
                size_bytes = os.path.getsize(db_info['path'])
                db_info['size'] = format_file_size(size_bytes)
                db_info['size_bytes'] = size_bytes
            else:
                db_info['size'] = "文件不存在"
                db_info['size_bytes'] = 0
        
        elif db_url.startswith('postgresql'):
            db_info['type'] = 'PostgreSQL'
        elif db_url.startswith('mysql'):
            db_info['type'] = 'MySQL'
        else:
            db_info['type'] = 'Unknown'
        
        # 获取数据库版本
        try:
            result = db.execute(text("SELECT version() as version"))
            version_row = result.fetchone()
            if version_row:
                db_info['version'] = str(version_row[0])
            else:
                db_info['version'] = "Unknown"
        except:
            db_info['version'] = "Unable to retrieve"
        
        # 统计表数量
        try:
            if db_info['type'] == 'SQLite':
                result = db.execute(text("SELECT count(*) FROM sqlite_master WHERE type='table'"))
            else:
                result = db.execute(text("SELECT count(*) FROM information_schema.tables WHERE table_schema = current_schema()"))
            
            count_row = result.fetchone()
            db_info['table_count'] = count_row[0] if count_row else 0
        except:
            db_info['table_count'] = "Unknown"
        
    except Exception as e:
        db_info['error'] = str(e)
    
    return db_info


async def get_media_info(db: Session) -> Dict[str, Any]:
    """获取媒体库信息"""
    media_info = {}
    
    try:
        # 获取媒体文件数量
        media_items = crud_media.get_all_media(db)
        media_info['total_files'] = len(media_items)
        
        # 计算总大小
        total_size = 0
        image_count = 0
        video_count = 0
        audio_count = 0
        document_count = 0
        
        # 获取媒体目录路径
        media_dir = os.getenv('MEDIA_UPLOAD_DIR', 'media_uploads')
        
        for item in media_items:
            # 获取实际文件大小
            file_path = item.filepath
            full_path = os.path.join(media_dir, file_path) if not os.path.isabs(file_path) else file_path
            if os.path.exists(file_path):
                file_size = os.path.getsize(file_path)
            elif os.path.exists(full_path):
                file_size = os.path.getsize(full_path)
            else:
                file_size = 0
                
            total_size += file_size
            
            # 按文件扩展名分类
            file_extension = os.path.splitext(item.filename)[1].lower()
            if file_extension in ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.tiff', '.svg']:
                image_count += 1
            elif file_extension in ['.mp4', '.avi', '.mov', '.wmv', '.flv', '.webm', '.mkv']:
                video_count += 1
            elif file_extension in ['.mp3', '.wav', '.flac', '.aac', '.ogg', '.m4a']:
                audio_count += 1
            else:
                document_count += 1
        
        media_info['total_size'] = format_file_size(total_size)
        media_info['total_size_bytes'] = total_size
        media_info['image_count'] = image_count
        media_info['video_count'] = video_count
        media_info['audio_count'] = audio_count
        media_info['document_count'] = document_count
        
        # 获取媒体目录路径
        media_dir = os.getenv('MEDIA_UPLOAD_DIR', 'media_uploads')
        media_info['directory'] = os.path.abspath(media_dir)
        
        # 检查目录是否存在
        media_info['directory_exists'] = os.path.exists(media_info['directory'])
        
        if media_info['directory_exists']:
            # 获取目录实际大小
            dir_size = get_directory_size(media_info['directory'])
            media_info['directory_size'] = format_file_size(dir_size)
            media_info['directory_size_bytes'] = dir_size
        
    except Exception as e:
        media_info['error'] = str(e)
    
    return media_info


def get_system_resources() -> Dict[str, Any]:
    """获取系统资源信息"""
    resources = {}
    
    try:
        # CPU信息
        resources['cpu'] = {
            'count': psutil.cpu_count(),
            'count_logical': psutil.cpu_count(logical=True),
            'usage_percent': psutil.cpu_percent(interval=1),
            'frequency': psutil.cpu_freq()._asdict() if psutil.cpu_freq() else None
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
            'usage_percent': (disk_usage.used / disk_usage.total) * 100,
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
                    'usage_percent': (partition_usage.used / partition_usage.total) * 100
                })
            except PermissionError:
                # 无权限访问的分区
                disk_info['partitions'].append({
                    'device': partition.device,
                    'mountpoint': partition.mountpoint,
                    'fstype': partition.fstype,
                    'error': '无权限访问'
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
    if size_bytes == 0:
        return "0 B"
    
    size_names = ["B", "KB", "MB", "GB", "TB"]
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def get_directory_size(directory: str) -> int:
    """获取目录总大小（字节）"""
    total_size = 0
    try:
        for dirpath, dirnames, filenames in os.walk(directory):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    total_size += os.path.getsize(filepath)
                except (OSError, FileNotFoundError):
                    pass
    except (OSError, FileNotFoundError):
        pass
    return total_size
