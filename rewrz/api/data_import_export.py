"""
数据导入导出API模块

提供数据导入导出功能的HTTP接口，包括：
1. 数据导出（JSON格式）
2. 备份包创建和下载
3. WordPress WXR文件导入
4. RewrZ JSON文件导入
"""

import os
import json
import copy
import tempfile
import threading
import uuid
import re
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile, Body
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from ..core.database import get_db, db_manager
from ..core.security import get_current_user
from ..core.template_filters import get_templates
from ..core.data_manager import (
    get_data_export_manager, 
    get_wordpress_importer, 
    get_rewrz_importer,
    DEFAULT_WP_IMPORT_OPTIONS,
)
from ..schemas import User
from datetime import datetime
from ..crud import setting as crud_setting
from ..schemas import SettingCreate, SettingUpdate

router = APIRouter()
templates = get_templates()

IMPORT_JOB_STATUSES = {"queued", "running", "completed", "failed"}
_IMPORT_JOBS: Dict[str, Dict[str, Any]] = {}
_IMPORT_JOBS_LOCK = threading.Lock()
_IMPORT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import-jobs")
_MAX_IMPORT_JOB_COUNT = 200


def _normalize_wp_import_options(payload: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    merged = dict(DEFAULT_WP_IMPORT_OPTIONS)
    if isinstance(payload, dict):
        merged.update(payload)

    raw_types = merged.get("import_post_types", ["post", "page"])
    if isinstance(raw_types, str):
        raw_types = [part.strip() for part in raw_types.split(",")]
    merged["import_post_types"] = sorted({str(x).strip().lower() for x in raw_types if str(x).strip()}) or ["post", "page"]

    raw_whitelist = merged.get("postmeta_whitelist", ["views", "post_views_count"])
    if isinstance(raw_whitelist, str):
        raw_whitelist = [part.strip() for part in raw_whitelist.split(",")]
    merged["postmeta_whitelist"] = sorted({str(x).strip() for x in raw_whitelist if str(x).strip()}) or ["views", "post_views_count"]

    raw_map = merged.get("post_type_format_map", {})
    normalized_map: Dict[str, str] = {}
    map_items = []
    if isinstance(raw_map, dict):
        map_items = [(str(k), str(v)) for k, v in raw_map.items()]
    elif isinstance(raw_map, str):
        for token in re.split(r"[,;\n]+", raw_map):
            part = token.strip()
            if not part or ":" not in part:
                continue
            left, right = part.split(":", 1)
            map_items.append((left, right))

    alias_map = {
        "post": "article",
        "standard": "article",
        "weibo": "micro-post",
        "micro": "micro-post",
        "micro_post": "micro-post",
        "photo": "photo-album",
        "gallery": "photo-album",
        "album": "photo-album",
        "poetry": "poetry-song",
        "song": "poetry-song",
        "微博": "micro-post",
        "标准文章": "article",
        "相册": "photo-album",
        "视频": "video",
        "诗词歌赋": "poetry-song",
    }
    for raw_key, raw_value in map_items:
        key = re.sub(r"[^a-z0-9_-]+", "", raw_key.strip().lower())
        target_raw = str(raw_value or "").strip().lower()
        mapped_target = alias_map.get(target_raw, target_raw)
        target = re.sub(r"[^a-z0-9_-]+", "-", mapped_target).strip("-")
        if key and target:
            normalized_map[key] = target
    merged["post_type_format_map"] = dict(sorted(normalized_map.items()))

    merged["import_comments"] = bool(merged.get("import_comments", True))
    merged["import_views"] = bool(merged.get("import_views", True))
    markdown_strategy = str(merged.get("markdown_strategy", "html_to_markdown")).strip() or "html_to_markdown"
    if markdown_strategy not in {"html_to_markdown", "raw_html"}:
        markdown_strategy = "html_to_markdown"
    merged["markdown_strategy"] = markdown_strategy
    return merged


def _get_wp_import_options(db: Session) -> Dict[str, Any]:
    setting = crud_setting.get_setting(db, "wordpress_import_options")
    if setting and isinstance(setting.value, dict):
        return _normalize_wp_import_options(setting.value)
    return _normalize_wp_import_options({})


def _save_wp_import_options(db: Session, options: Dict[str, Any]) -> Dict[str, Any]:
    normalized = _normalize_wp_import_options(options)
    existing = crud_setting.get_setting(db, "wordpress_import_options")
    if existing:
        crud_setting.update_setting(
            db,
            "wordpress_import_options",
            SettingUpdate(
                value=normalized,
                description="WordPress import options",
                category="import",
                type="json",
            ),
        )
    else:
        crud_setting.create_setting(
            db,
            SettingCreate(
                key="wordpress_import_options",
                value=normalized,
                description="WordPress import options",
                category="import",
                type="json",
            ),
        )
    return normalized


def _create_import_job(user_id: int, job_type: str, filename: str) -> Dict[str, Any]:
    job_id = uuid.uuid4().hex
    now = datetime.utcnow().isoformat()
    job = {
        "id": job_id,
        "user_id": int(user_id),
        "type": job_type,
        "filename": filename,
        "status": "queued",
        "created_at": now,
        "updated_at": now,
        "progress": {
            "stage": "queued",
            "message": "任务已创建，等待执行。",
            "current": 0,
            "total": 1,
            "percent": 0,
        },
        "result": None,
        "error": None,
    }
    with _IMPORT_JOBS_LOCK:
        _IMPORT_JOBS[job_id] = job
        _prune_import_jobs_locked()
    return job


def _prune_import_jobs_locked() -> None:
    if len(_IMPORT_JOBS) <= _MAX_IMPORT_JOB_COUNT:
        return
    sorted_jobs = sorted(_IMPORT_JOBS.values(), key=lambda item: item.get("updated_at", ""))
    overflow = len(_IMPORT_JOBS) - _MAX_IMPORT_JOB_COUNT
    for job in sorted_jobs[:overflow]:
        _IMPORT_JOBS.pop(job["id"], None)


def _update_import_job(job_id: str, **fields: Any) -> None:
    with _IMPORT_JOBS_LOCK:
        job = _IMPORT_JOBS.get(job_id)
        if not job:
            return
        job.update(fields)
        job["updated_at"] = datetime.utcnow().isoformat()


def _set_import_job_progress(
    job_id: str,
    stage: str,
    message: str,
    current: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    with _IMPORT_JOBS_LOCK:
        job = _IMPORT_JOBS.get(job_id)
        if not job:
            return
        progress = dict(job.get("progress") or {})
        progress["stage"] = stage
        progress["message"] = message
        if current is not None:
            progress["current"] = int(max(current, 0))
        if total is not None:
            progress["total"] = int(max(total, 0))
        if percent is None:
            cur = progress.get("current")
            tot = progress.get("total")
            if isinstance(cur, int) and isinstance(tot, int) and tot > 0:
                percent = int(max(0, min(100, round((cur / tot) * 100))))
        if percent is not None:
            progress["percent"] = int(max(0, min(100, percent)))
        if isinstance(extra, dict):
            progress.update(extra)
        job["progress"] = progress
        job["updated_at"] = datetime.utcnow().isoformat()


def _get_import_job(job_id: str) -> Optional[Dict[str, Any]]:
    with _IMPORT_JOBS_LOCK:
        job = _IMPORT_JOBS.get(job_id)
        if not job:
            return None
        return copy.deepcopy(job)


def _run_wordpress_import_job(job_id: str, wxr_path: str, options: Dict[str, Any]) -> None:
    _update_import_job(job_id, status="running")
    _set_import_job_progress(job_id, "prepare", "开始导入任务...", current=0, total=1, percent=0)

    db = None
    try:
        db_manager.reload_if_needed()
        db = db_manager.get_session()
        if db is None:
            raise RuntimeError("数据库连接不可用")

        def progress_callback(payload: Dict[str, Any]) -> None:
            stage = str(payload.get("stage") or "running")
            message = str(payload.get("message") or "正在导入...")
            current = payload.get("current")
            total = payload.get("total")
            extra = {
                key: value
                for key, value in payload.items()
                if key not in {"stage", "message", "current", "total"}
            }
            _set_import_job_progress(
                job_id,
                stage=stage,
                message=message,
                current=current if isinstance(current, int) else None,
                total=total if isinstance(total, int) else None,
                extra=extra or None,
            )

        importer = get_wordpress_importer(db, options=options, progress_callback=progress_callback)
        result = importer.import_from_wxr(wxr_path)

        if isinstance(result, dict) and result.get("error"):
            _update_import_job(job_id, status="failed", error=str(result.get("error")), result={"stats": result})
            _set_import_job_progress(job_id, "failed", f"导入失败：{result.get('error')}", percent=100)
        else:
            _update_import_job(job_id, status="completed", result={"stats": result}, error=None)
            _set_import_job_progress(job_id, "completed", "导入完成。", percent=100)
    except Exception as exc:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        _update_import_job(job_id, status="failed", error=str(exc), result=None)
        _set_import_job_progress(job_id, "failed", f"导入失败：{str(exc)}", percent=100)
    finally:
        if db is not None:
            db.close()
        try:
            if os.path.exists(wxr_path):
                os.unlink(wxr_path)
        except Exception:
            pass


async def data_management_page(
    request: Request,
    db: Session,
    current_user: User
):
    """
    数据管理页面
    
    显示数据导入导出的管理界面
    """
    return templates.TemplateResponse("admin/data_management.html", {
        "request": request,
        "user": current_user,
        "admin_path": getattr(request.state, 'admin_path', os.getenv('ADMIN_PATH', '/admin'))
    })


@router.get("/api/v1/export/json")
@router.get("/api/export/json")
async def export_data_json(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导出数据为JSON格式
    
    返回包含所有博客数据的JSON文件
    """
    try:
        export_manager = get_data_export_manager(db)
        data = export_manager.export_all_data()
        
        # 生成文件名
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"rewrz_export_{timestamp}.json"
        
        # 创建临时文件
        temp_file = tempfile.NamedTemporaryFile(
            mode='w', 
            suffix='.json', 
            delete=False,
            encoding='utf-8'
        )
        
        try:
            json.dump(data, temp_file, ensure_ascii=False, indent=2)
            temp_file.close()
            
            return FileResponse(
                path=temp_file.name,
                filename=filename,
                media_type='application/json',
                background=lambda: os.unlink(temp_file.name)  # 下载后删除临时文件
            )
            
        except Exception as e:
            if not temp_file.closed:
                temp_file.close()
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise e
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"导出失败: {str(e)}")


@router.get("/api/v1/export/backup")
@router.get("/api/export/backup")
async def export_backup_package(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    创建并下载完整备份包
    
    包含数据文件和媒体文件的ZIP包
    """
    try:
        export_manager = get_data_export_manager(db)
        
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        
        try:
            # 创建备份包
            backup_path = export_manager.create_backup_package(temp_dir)
            
            if not os.path.exists(backup_path):
                raise HTTPException(status_code=500, detail="备份包创建失败")
            
            return FileResponse(
                path=backup_path,
                filename=os.path.basename(backup_path),
                media_type='application/zip',
                background=lambda: _cleanup_temp_files(temp_dir)
            )
            
        except Exception as e:
            _cleanup_temp_files(temp_dir)
            raise e
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"备份失败: {str(e)}")


@router.post("/api/v1/import/wordpress")
@router.post("/api/import/wordpress")
async def import_wordpress_data(
    wxr_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导入WordPress WXR文件
    
    支持WordPress标准导出格式
    """
    if not wxr_file.filename.endswith('.xml'):
        raise HTTPException(status_code=400, detail="请上传XML格式的WXR文件")
    
    # 检查文件大小（限制50MB）
    max_size = 50 * 1024 * 1024  # 50MB
    content = await wxr_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大50MB）")
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.xml',
        delete=False
    )
    
    try:
        temp_file.write(content)
        temp_file.close()
        
        # 执行导入
        wp_options = _get_wp_import_options(db)
        importer = get_wordpress_importer(db, options=wp_options)
        result = importer.import_from_wxr(temp_file.name)
        
        return JSONResponse({
            "success": True,
            "message": "WordPress数据导入完成",
            "stats": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}"
        }, status_code=500)
        
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


@router.post("/api/v1/import/wordpress/tasks")
@router.post("/api/import/wordpress/tasks")
async def create_wordpress_import_task(
    wxr_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    创建 WordPress 导入异步任务，并返回任务ID用于查询进度。
    """
    filename = wxr_file.filename or ""
    if not filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="请上传XML格式的WXR文件")

    max_size = 50 * 1024 * 1024  # 50MB
    content = await wxr_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大50MB）")

    temp_file = tempfile.NamedTemporaryFile(mode="wb", suffix=".xml", delete=False)
    try:
        temp_file.write(content)
        temp_file.close()
        wp_options = _get_wp_import_options(db)
        job = _create_import_job(
            user_id=current_user.id,
            job_type="wordpress_import",
            filename=filename,
        )
        _IMPORT_EXECUTOR.submit(_run_wordpress_import_job, job["id"], temp_file.name, wp_options)
        return JSONResponse(
            {
                "success": True,
                "message": "WordPress导入任务已启动",
                "job_id": job["id"],
            },
            status_code=202,
        )
    except Exception:
        try:
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
        except Exception:
            pass
        raise


@router.get("/api/v1/import/jobs/{job_id}")
@router.get("/api/import/jobs/{job_id}")
async def get_import_job_status(
    job_id: str,
    current_user: User = Depends(get_current_user),
):
    """
    获取异步导入任务状态。
    """
    job = _get_import_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if int(job.get("user_id", -1)) != int(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该任务")
    job_view = {k: v for k, v in job.items() if k != "user_id"}
    return JSONResponse({"success": True, "job": job_view})


@router.get("/api/v1/import/wordpress/options")
@router.get("/api/import/wordpress/options")
async def get_wordpress_import_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    options = _get_wp_import_options(db)
    return JSONResponse({"success": True, "options": options})


@router.post("/api/v1/import/wordpress/options")
@router.post("/api/import/wordpress/options")
async def update_wordpress_import_options(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    options = _save_wp_import_options(db, payload)
    return JSONResponse({"success": True, "options": options})


@router.post("/api/v1/import/rewrz")
@router.post("/api/import/rewrz")
async def import_rewrz_data(
    json_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导入RewrZ JSON文件
    
    支持RewrZ标准导出格式
    """
    if not json_file.filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="请上传JSON格式的数据文件")
    
    # 检查文件大小（限制10MB）
    max_size = 10 * 1024 * 1024  # 10MB
    content = await json_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大10MB）")
    
    # 创建临时文件
    temp_file = tempfile.NamedTemporaryFile(
        mode='wb',
        suffix='.json',
        delete=False
    )
    
    try:
        temp_file.write(content)
        temp_file.close()
        
        # 执行导入
        importer = get_rewrz_importer(db)
        result = importer.import_from_json(temp_file.name)
        
        return JSONResponse({
            "success": True,
            "message": "RewrZ数据导入完成",
            "stats": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}"
        }, status_code=500)
        
    finally:
        if os.path.exists(temp_file.name):
            os.unlink(temp_file.name)


@router.post("/api/v1/import/backup")
@router.post("/api/import/backup")
async def import_backup_package(
    backup_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    导入完整备份包
    
    支持RewrZ备份ZIP文件
    """
    if not backup_file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="请上传ZIP格式的备份文件")
    
    # 检查文件大小（限制100MB）
    max_size = 100 * 1024 * 1024  # 100MB
    content = await backup_file.read()
    if len(content) > max_size:
        raise HTTPException(status_code=400, detail="文件大小超过限制（最大100MB）")
    
    import zipfile
    import shutil
    
    # 创建临时目录
    temp_dir = tempfile.mkdtemp()
    
    try:
        # 保存上传的ZIP文件
        zip_path = os.path.join(temp_dir, backup_file.filename)
        with open(zip_path, 'wb') as f:
            f.write(content)
        
        # 解压ZIP文件
        extract_dir = os.path.join(temp_dir, "extracted")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_dir)
        
        # 查找数据文件
        data_file = None
        for root, dirs, files in os.walk(extract_dir):
            for file in files:
                if file.endswith('.json') and 'rewrz' in file.lower():
                    data_file = os.path.join(root, file)
                    break
            if data_file:
                break
        
        if not data_file:
            raise HTTPException(status_code=400, detail="备份包中未找到有效的数据文件")
        
        # 导入数据
        importer = get_rewrz_importer(db)
        result = importer.import_from_json(data_file)
        
        # 恢复媒体文件
        media_restored = 0
        media_dir = os.path.join(extract_dir, "media")
        if os.path.exists(media_dir):
            target_media_dir = "media_uploads"
            if not os.path.exists(target_media_dir):
                os.makedirs(target_media_dir)
            
            for root, dirs, files in os.walk(media_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, media_dir)
                    dst_path = os.path.join(target_media_dir, rel_path)
                    
                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                    
                    if not os.path.exists(dst_path):
                        shutil.copy2(src_path, dst_path)
                        media_restored += 1
        
        result["media_restored"] = media_restored
        
        return JSONResponse({
            "success": True,
            "message": "备份包导入完成",
            "stats": result
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": f"导入失败: {str(e)}"
        }, status_code=500)
        
    finally:
        _cleanup_temp_files(temp_dir)


@router.get("/api/v1/data/stats")
@router.get("/api/data/stats")
async def get_data_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    获取数据统计信息
    
    用于显示当前博客的数据概况
    """
    try:
        from ..crud import post as crud_post
        from ..crud import category as crud_category
        from ..crud import tag as crud_tag
        from ..crud import media as crud_media
        from ..crud import setting as crud_setting
        
        # 统计数据
        posts_count = len(crud_post.get_all_posts(db))
        categories_count = len(crud_category.get_all_categories(db))
        tags_count = len(crud_tag.get_all_tags(db))
        media_count = len(crud_media.get_all_media(db))
        settings_count = len(crud_setting.get_all_settings(db))
        
        # 计算媒体文件总大小
        import os
        media_items = crud_media.get_all_media(db)
        total_media_size = 0
        for item in media_items:
            # 获取实际文件大小
            if os.path.exists(item.filepath):
                total_media_size += os.path.getsize(item.filepath)
            # 如果文件不存在，尝试从文件名推断路径
            elif os.path.exists(os.path.join("media_uploads", item.filepath)):
                total_media_size += os.path.getsize(os.path.join("media_uploads", item.filepath))
            # 如果还是找不到文件，则跳过
        
        # 格式化文件大小
        def format_file_size(size_bytes):
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            elif size_bytes < 1024 * 1024 * 1024:
                return f"{size_bytes / (1024 * 1024):.1f} MB"
            else:
                return f"{size_bytes / (1024 * 1024 * 1024):.1f} GB"
        
        return JSONResponse({
            "posts": posts_count,
            "categories": categories_count,
            "tags": tags_count,
            "media_files": media_count,
            "settings": settings_count,
            "total_media_size": format_file_size(total_media_size),
            "total_media_size_bytes": total_media_size
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


def _cleanup_temp_files(temp_dir: str):
    """清理临时文件和目录"""
    try:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"清理临时文件失败: {str(e)}")
