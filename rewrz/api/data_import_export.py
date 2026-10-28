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
import logging
import tempfile
import threading
import time
import uuid
import re
import shutil
import zipfile
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Depends, HTTPException, Request, File, UploadFile, Body, Header
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from ..core.admin_path import get_request_admin_path
from ..core.config import settings
from ..core.database import (
    get_db,
    db_manager,
    get_sqlite_database_path,
    get_sqlite_storage_status,
    vacuum_sqlite_database,
)
from ..core.time_utils import utc_iso, utc_now_naive
from ..core.security import get_current_user, verify_csrf_token
from ..core.template_filters import get_templates
from ..core.data_manager import (
    get_data_export_manager, 
    get_wordpress_importer, 
    get_rewrz_importer,
    DEFAULT_WP_IMPORT_OPTIONS,
)
from ..core.content_intents import normalize_intent_slug
from ..models.import_job import ImportJob
from ..schemas import User
from datetime import datetime, timedelta
from ..crud import setting as crud_setting
from ..schemas import SettingCreate, SettingUpdate

router = APIRouter()
templates = get_templates()
logger = logging.getLogger(__name__)

IMPORT_JOB_STATUSES = {"queued", "running", "completed", "failed", "interrupted"}
_IMPORT_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix="import-jobs")
# 终态任务保留时长，超期后在创建新任务时顺手清理
_IMPORT_JOB_RETENTION_SECONDS = 7 * 24 * 3600
# 执行进程心跳间隔与僵死判定阈值（多 worker 部署下 worker 重启后可及时收敛任务）
_IMPORT_JOB_HEARTBEAT_INTERVAL_SECONDS = 30
_IMPORT_JOB_STALE_SECONDS = 120
# 进度落库节流：阶段切换与终态立即写入，同阶段连续更新合并，降低数据库写压力
_PROGRESS_THROTTLE_SECONDS = 0.3
_PROGRESS_THROTTLE_STATE: Dict[str, tuple] = {}
_PROGRESS_THROTTLE_LOCK = threading.Lock()
_UPLOAD_CHUNK_SIZE = 1024 * 1024
_MAX_WXR_IMPORT_SIZE = 50 * 1024 * 1024
_MAX_JSON_IMPORT_SIZE = 10 * 1024 * 1024
_MAX_BACKUP_IMPORT_SIZE = 100 * 1024 * 1024
_MAX_BACKUP_ZIP_ENTRIES = 2000
_MAX_BACKUP_ZIP_SINGLE_FILE_BYTES = 100 * 1024 * 1024
_MAX_BACKUP_ZIP_TOTAL_BYTES = 300 * 1024 * 1024
_MAX_BACKUP_ZIP_RATIO = 200.0


async def _save_upload_to_temp_file(
    upload_file: UploadFile,
    *,
    suffix: str,
    max_size: int,
    dir_path: Optional[str] = None,
) -> str:
    """将上传文件流式写入临时文件，并在写入阶段执行大小限制。"""
    temp_file = tempfile.NamedTemporaryFile(mode="wb", suffix=suffix, delete=False, dir=dir_path)
    total_size = 0
    try:
        while True:
            chunk = await upload_file.read(_UPLOAD_CHUNK_SIZE)
            if not chunk:
                break
            total_size += len(chunk)
            if total_size > max_size:
                raise HTTPException(status_code=400, detail=f"文件大小超过限制（最大{max_size // (1024 * 1024)}MB）")
            temp_file.write(chunk)
    except Exception:
        temp_file.close()
        try:
            os.unlink(temp_file.name)
        except OSError:
            pass
        raise
    finally:
        try:
            await upload_file.close()
        except Exception:
            pass
    temp_file.close()
    return temp_file.name


def _normalize_zip_member_name(member_name: str) -> str:
    normalized = str(member_name or "").replace("\\", "/").strip()
    if not normalized:
        return ""
    normalized = normalized.lstrip("/")
    parts = [part for part in normalized.split("/") if part not in {"", "."}]
    if not parts:
        return ""
    for part in parts:
        if part == ".." or ":" in part:
            raise HTTPException(status_code=400, detail="备份包包含非法路径，导入已拒绝")
    return "/".join(parts)


def _extract_backup_zip_safely(zip_path: str, extract_dir: str) -> None:
    os.makedirs(extract_dir, exist_ok=True)
    extract_root = os.path.realpath(extract_dir)
    total_uncompressed = 0
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        entries = zip_ref.infolist()
        if len(entries) > _MAX_BACKUP_ZIP_ENTRIES:
            raise HTTPException(status_code=400, detail="备份包文件数量过多，导入已拒绝")

        for info in entries:
            safe_member = _normalize_zip_member_name(info.filename)
            if not safe_member:
                continue

            destination_path = os.path.realpath(os.path.join(extract_root, safe_member))
            if os.path.commonpath([extract_root, destination_path]) != extract_root:
                raise HTTPException(status_code=400, detail="备份包包含越界路径，导入已拒绝")

            if info.is_dir():
                os.makedirs(destination_path, exist_ok=True)
                continue

            file_size = max(0, int(info.file_size or 0))
            compressed_size = max(0, int(info.compress_size or 0))
            if file_size > _MAX_BACKUP_ZIP_SINGLE_FILE_BYTES:
                raise HTTPException(status_code=400, detail="备份包存在超大文件，导入已拒绝")
            if compressed_size > 0 and (file_size / compressed_size) > _MAX_BACKUP_ZIP_RATIO:
                raise HTTPException(status_code=400, detail="备份包压缩比异常，导入已拒绝")

            total_uncompressed += file_size
            if total_uncompressed > _MAX_BACKUP_ZIP_TOTAL_BYTES:
                raise HTTPException(status_code=400, detail="备份包解压后体积过大，导入已拒绝")

            os.makedirs(os.path.dirname(destination_path), exist_ok=True)
            with zip_ref.open(info, "r") as source, open(destination_path, "wb") as target:
                shutil.copyfileobj(source, target, _UPLOAD_CHUNK_SIZE)


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
        "weibo": "micro",
        "micro": "micro",
        "micro_post": "micro",
        "status": "micro",
        "aside": "micro",
        "post": "article",
        "standard": "article",
        "article": "article",
        "poetry": "poem",
        "song": "poem",
        "audio": "poem",
        "微博": "micro",
        "标准文章": "article",
        "文章": "article",
        "诗词歌赋": "poem",
    }
    for raw_key, raw_value in map_items:
        key = re.sub(r"[^a-z0-9_-]+", "", raw_key.strip().lower())
        target_raw = str(raw_value or "").strip().lower()
        mapped_target = alias_map.get(target_raw, target_raw)
        target = normalize_intent_slug(re.sub(r"[^a-z0-9_-]+", "-", mapped_target).strip("-"))
        if key and target:
            normalized_map[key] = target
    merged["post_type_format_map"] = dict(sorted(normalized_map.items()))

    merged["import_comments"] = bool(merged.get("import_comments", True))
    merged["import_views"] = bool(merged.get("import_views", True))
    merged["download_remote_media"] = bool(merged.get("download_remote_media", False))
    strategy = str(merged.get("remote_media_path_strategy", "latest_month")).strip().lower() or "latest_month"
    if strategy not in {"latest_month", "preserve_relative_path"}:
        strategy = "latest_month"
    merged["remote_media_path_strategy"] = strategy
    markdown_strategy = str(merged.get("markdown_strategy", "html_to_markdown")).strip() or "html_to_markdown"
    if markdown_strategy not in {"html_to_markdown", "raw_html"}:
        markdown_strategy = "html_to_markdown"
    merged["markdown_strategy"] = markdown_strategy
    slug_conflict = str(merged.get("slug_conflict", "skip")).strip().lower()
    if slug_conflict not in {"skip", "suffix"}:
        slug_conflict = "skip"
    merged["slug_conflict"] = slug_conflict
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


def _cleanup_expired_import_jobs(db: Session) -> None:
    """清理超过保留时长的终态任务，避免任务表无限增长。"""
    cutoff = utc_now_naive() - timedelta(seconds=_IMPORT_JOB_RETENTION_SECONDS)
    db.query(ImportJob).filter(
        ImportJob.status.in_(("completed", "failed", "interrupted")),
        ImportJob.created_at < cutoff,
    ).delete(synchronize_session=False)
    db.commit()


def _create_import_job(db: Session, user_id: int, job_type: str, filename: str) -> str:
    """创建导入任务并写入数据库，返回任务ID。"""
    job_id = uuid.uuid4().hex
    now = utc_now_naive()
    job = ImportJob(
        id=job_id,
        user_id=int(user_id),
        job_type=job_type,
        filename=filename,
        status="queued",
        progress_stage="queued",
        progress_message="任务已创建，等待执行。",
        progress_current=0,
        progress_total=1,
        progress_percent=0,
        progress_extra=None,
        result=None,
        error=None,
        worker_pid=None,
        heartbeat_at=None,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.commit()
    _cleanup_expired_import_jobs(db)
    return job_id


def _update_import_job(db: Session, job_id: str, **fields: Any) -> None:
    """更新导入任务字段（状态、结果、错误等）。"""
    job = db.get(ImportJob, job_id)
    if not job:
        return
    for key, value in fields.items():
        setattr(job, key, value)
    job.updated_at = utc_now_naive()
    db.commit()


def _should_write_progress(job_id: str, stage: str) -> bool:
    """判断本次进度更新是否需要落库：阶段切换与终态立即写，其余按节流合并。"""
    now = time.monotonic()
    force = stage in {"completed", "failed"}
    with _PROGRESS_THROTTLE_LOCK:
        last = _PROGRESS_THROTTLE_STATE.get(job_id)
        should_write = (
            force
            or last is None
            or last[0] != stage
            or (now - last[1]) >= _PROGRESS_THROTTLE_SECONDS
        )
        if should_write:
            _PROGRESS_THROTTLE_STATE[job_id] = (stage, now)
    return should_write


def _set_import_job_progress(
    db: Session,
    job_id: str,
    stage: str,
    message: str,
    current: Optional[int] = None,
    total: Optional[int] = None,
    percent: Optional[int] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> None:
    if not _should_write_progress(job_id, stage):
        return
    job = db.get(ImportJob, job_id)
    if not job:
        return
    if current is not None:
        job.progress_current = int(max(current, 0))
    if total is not None:
        job.progress_total = int(max(total, 0))
    if percent is None:
        if job.progress_total > 0:
            percent = int(max(0, min(100, round((job.progress_current / job.progress_total) * 100))))
    if percent is not None:
        job.progress_percent = int(max(0, min(100, percent)))
    job.progress_stage = stage
    job.progress_message = message
    if isinstance(extra, dict):
        merged = dict(job.progress_extra or {})
        merged.update(extra)
        job.progress_extra = merged
    job.updated_at = utc_now_naive()
    db.commit()


def _touch_import_job_heartbeat(db: Session, job_id: str, pid: int) -> None:
    """由执行进程周期性调用，更新心跳用于僵死任务检测。"""
    job = db.get(ImportJob, job_id)
    if not job or job.status != "running":
        return
    job.heartbeat_at = utc_now_naive()
    job.worker_pid = pid
    db.commit()


def _import_job_heartbeat_loop(job_id: str, stop_event: threading.Event) -> None:
    """导入任务执行期间的心跳循环，使用独立数据库会话，避免干扰导入事务。"""
    while not stop_event.wait(_IMPORT_JOB_HEARTBEAT_INTERVAL_SECONDS):
        try:
            db_manager.reload_if_needed()
            heartbeat_db = db_manager.get_session()
            if heartbeat_db is None:
                continue
            try:
                _touch_import_job_heartbeat(heartbeat_db, job_id, os.getpid())
            finally:
                heartbeat_db.close()
        except Exception:
            # 心跳失败不影响导入主流程，仅影响僵死检测的时效
            pass


def _finalize_stale_import_job(db: Session, job: ImportJob) -> None:
    """执行进程心跳超时的任务判定为中断（多见于 worker 重启），避免前端无限轮询。"""
    if job.status != "running":
        return
    heartbeat = job.heartbeat_at
    if heartbeat is None:
        # 刚进入 running 尚未写入首次心跳，留给下一次轮询判定
        return
    if (utc_now_naive() - heartbeat).total_seconds() <= _IMPORT_JOB_STALE_SECONDS:
        return
    job.status = "interrupted"
    job.error = "任务执行进程已停止（服务可能已重启），任务被标记为中断，请重新发起导入。"
    job.updated_at = utc_now_naive()
    db.commit()


def _import_job_to_dict(job: ImportJob) -> Dict[str, Any]:
    """将任务模型转换为字典（含 user_id 供权限校验，返回前端前需剥离）。"""
    progress = {
        "stage": job.progress_stage,
        "message": job.progress_message,
        "current": job.progress_current,
        "total": job.progress_total,
        "percent": job.progress_percent,
    }
    if isinstance(job.progress_extra, dict):
        progress.update(job.progress_extra)
    return {
        "id": job.id,
        "user_id": job.user_id,
        "type": job.job_type,
        "filename": job.filename,
        "status": job.status,
        "created_at": utc_iso(job.created_at),
        "updated_at": utc_iso(job.updated_at),
        "progress": progress,
        "result": job.result,
        "error": job.error,
    }


def _get_import_job(db: Session, job_id: str) -> Optional[Dict[str, Any]]:
    """从数据库查询导入任务，任何 worker 进程均可访问。"""
    job = db.get(ImportJob, job_id)
    if not job:
        return None
    _finalize_stale_import_job(db, job)
    return _import_job_to_dict(job)


def _run_wordpress_import_job(job_id: str, wxr_path: str, options: Dict[str, Any]) -> None:
    db = None
    heartbeat_stop = threading.Event()
    heartbeat_thread: Optional[threading.Thread] = None
    try:
        db_manager.reload_if_needed()
        db = db_manager.get_session()
        if db is None:
            raise RuntimeError("数据库连接不可用")

        _update_import_job(db, job_id, status="running", worker_pid=os.getpid(), heartbeat_at=utc_now_naive())
        _set_import_job_progress(db, job_id, "prepare", "开始导入任务...", current=0, total=1, percent=0)

        # 启动心跳线程，供查询端检测执行进程是否存活（worker 重启等场景）
        heartbeat_thread = threading.Thread(
            target=_import_job_heartbeat_loop,
            args=(job_id, heartbeat_stop),
            daemon=True,
            name=f"import-job-hb-{job_id[:8]}",
        )
        heartbeat_thread.start()

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
                db,
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
            _update_import_job(db, job_id, status="failed", error=str(result.get("error")), result={"stats": result})
            _set_import_job_progress(db, job_id, "failed", f"导入失败：{result.get('error')}", percent=100)
        else:
            _update_import_job(db, job_id, status="completed", result={"stats": result}, error=None)
            _set_import_job_progress(db, job_id, "completed", "导入完成。", percent=100)
    except Exception as exc:
        try:
            if db is not None:
                db.rollback()
        except Exception:
            pass
        if db is not None:
            try:
                _update_import_job(db, job_id, status="failed", error=str(exc), result=None)
                _set_import_job_progress(db, job_id, "failed", f"导入失败：{str(exc)}", percent=100)
            except Exception:
                # 任务状态更新失败时至少保证不吞掉原始异常信息
                logger.exception("更新导入任务失败状态时出错: job_id=%s", job_id)
    finally:
        heartbeat_stop.set()
        if heartbeat_thread is not None:
            heartbeat_thread.join(timeout=2)
        if db is not None:
            db.close()
        try:
            if os.path.exists(wxr_path):
                os.unlink(wxr_path)
        except Exception:
            pass


def data_management_page(
    request: Request,
    db: Session,
    current_user: User
):
    """
    数据管理页面
    
    显示数据导入导出的管理界面
    """
    return templates.TemplateResponse(request, "admin/data_management.html", {
        "request": request,
        "user": current_user,
        "admin_path": get_request_admin_path(request),
        "supports_sqlite_vacuum": bool(get_sqlite_database_path()),
    })


@router.get("/api/v1/export/json")
@router.get("/api/export/json")
def export_data_json(
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
def export_backup_package(
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
    request: Request,
    wxr_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """
    导入WordPress WXR文件
    
    支持WordPress标准导出格式
    """
    verify_csrf_token(request, csrf_token)
    filename = str(wxr_file.filename or "").lower()
    if not filename.endswith('.xml'):
        raise HTTPException(status_code=400, detail="请上传XML格式的WXR文件")
    temp_file_path = await _save_upload_to_temp_file(
        wxr_file,
        suffix=".xml",
        max_size=_MAX_WXR_IMPORT_SIZE,
    )

    try:
        # 执行导入
        wp_options = _get_wp_import_options(db)
        importer = get_wordpress_importer(db, options=wp_options)
        result = importer.import_from_wxr(temp_file_path)
        
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
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@router.post("/api/v1/import/wordpress/tasks")
@router.post("/api/import/wordpress/tasks")
async def create_wordpress_import_task(
    request: Request,
    wxr_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """
    创建 WordPress 导入异步任务，并返回任务ID用于查询进度。
    """
    verify_csrf_token(request, csrf_token)
    filename = wxr_file.filename or ""
    if not filename.lower().endswith(".xml"):
        raise HTTPException(status_code=400, detail="请上传XML格式的WXR文件")

    temp_file_path = await _save_upload_to_temp_file(
        wxr_file,
        suffix=".xml",
        max_size=_MAX_WXR_IMPORT_SIZE,
    )
    try:
        wp_options = _get_wp_import_options(db)
        job_id = _create_import_job(
            db,
            user_id=current_user.id,
            job_type="wordpress_import",
            filename=filename,
        )
        _IMPORT_EXECUTOR.submit(_run_wordpress_import_job, job_id, temp_file_path, wp_options)
        return JSONResponse(
            {
                "success": True,
                "message": "WordPress导入任务已启动",
                "job_id": job_id,
            },
            status_code=202,
        )
    except Exception:
        try:
            if os.path.exists(temp_file_path):
                os.unlink(temp_file_path)
        except Exception:
            pass
        raise


@router.get("/api/v1/import/jobs/{job_id}")
@router.get("/api/import/jobs/{job_id}")
def get_import_job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取异步导入任务状态。
    任务状态持久化在数据库中，多 worker 部署下任意进程均可查询。
    """
    job = _get_import_job(db, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="任务不存在或已过期")
    if int(job.get("user_id", -1)) != int(current_user.id):
        raise HTTPException(status_code=403, detail="无权访问该任务")
    job_view = {k: v for k, v in job.items() if k != "user_id"}
    return JSONResponse({"success": True, "job": job_view})


@router.get("/api/v1/import/wordpress/options")
@router.get("/api/import/wordpress/options")
def get_wordpress_import_options(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    options = _get_wp_import_options(db)
    return JSONResponse({"success": True, "options": options})


@router.post("/api/v1/import/wordpress/options")
@router.post("/api/import/wordpress/options")
def update_wordpress_import_options(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    verify_csrf_token(request, csrf_token)
    options = _save_wp_import_options(db, payload)
    return JSONResponse({"success": True, "options": options})


@router.post("/api/v1/import/rewrz")
@router.post("/api/import/rewrz")
async def import_rewrz_data(
    request: Request,
    json_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """
    导入RewrZ JSON文件
    
    支持RewrZ标准导出格式
    """
    verify_csrf_token(request, csrf_token)
    filename = str(json_file.filename or "").lower()
    if not filename.endswith('.json'):
        raise HTTPException(status_code=400, detail="请上传JSON格式的数据文件")
    temp_file_path = await _save_upload_to_temp_file(
        json_file,
        suffix=".json",
        max_size=_MAX_JSON_IMPORT_SIZE,
    )

    try:
        # 执行导入
        importer = get_rewrz_importer(db)
        result = importer.import_from_json(temp_file_path)
        
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
        if os.path.exists(temp_file_path):
            os.unlink(temp_file_path)


@router.post("/api/v1/import/backup")
@router.post("/api/import/backup")
async def import_backup_package(
    request: Request,
    backup_file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """
    导入完整备份包
    
    支持RewrZ备份ZIP文件
    """
    verify_csrf_token(request, csrf_token)
    filename = str(backup_file.filename or "").lower()
    if not filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="请上传ZIP格式的备份文件")

    # 创建临时目录
    temp_dir = tempfile.mkdtemp()

    try:
        # 流式保存上传文件，避免一次性读入内存。
        zip_path = await _save_upload_to_temp_file(
            backup_file,
            suffix=".zip",
            max_size=_MAX_BACKUP_IMPORT_SIZE,
            dir_path=temp_dir,
        )

        # 解压ZIP文件
        extract_dir = os.path.join(temp_dir, "extracted")
        _extract_backup_zip_safely(zip_path, extract_dir)
        
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
        
        # 先恢复媒体文件，再导入 JSON 元数据，保证 media 记录能找到对应文件。
        media_restored = 0
        media_files_total = 0
        media_dir = os.path.join(extract_dir, "media")
        target_media_dir = os.path.abspath(str(settings.MEDIA_UPLOAD_DIR or "media_uploads"))
        if os.path.exists(media_dir):
            os.makedirs(target_media_dir, exist_ok=True)
            for root, dirs, files in os.walk(media_dir):
                for file in files:
                    src_path = os.path.join(root, file)
                    rel_path = os.path.relpath(src_path, media_dir)
                    dst_path = os.path.join(target_media_dir, rel_path)
                    media_files_total += 1

                    # 确保目标目录存在
                    os.makedirs(os.path.dirname(dst_path), exist_ok=True)

                    if not os.path.exists(dst_path):
                        shutil.copy2(src_path, dst_path)
                        media_restored += 1

        # 导入数据（包含评论与媒体元数据）
        importer = get_rewrz_importer(db)
        result = importer.import_from_json(data_file)

        result["media_files_total"] = media_files_total
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
def get_data_stats(
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
        media_count = len(crud_media.get_all_media(db, limit=10**9))
        settings_count = len(crud_setting.get_all_settings(db))
        
        # 计算媒体文件总大小
        media_items = crud_media.get_all_media(db, limit=10**9)
        total_media_size = 0
        media_root = os.path.abspath(str(settings.MEDIA_UPLOAD_DIR or "media_uploads"))
        for item in media_items:
            # 获取实际文件大小
            if os.path.exists(item.filepath):
                total_media_size += os.path.getsize(item.filepath)
            # 兼容历史相对路径记录
            elif os.path.exists(os.path.join(media_root, item.filepath)):
                total_media_size += os.path.getsize(os.path.join(media_root, item.filepath))
        
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
            "total_media_size_bytes": total_media_size,
            "database": get_sqlite_storage_status(db.get_bind()),
        })
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取统计失败: {str(e)}")


@router.post("/api/v1/database/vacuum")
@router.post("/api/database/vacuum")
def vacuum_database(
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
    csrf_token: str = Header(..., alias="X-CSRF-Token"),
):
    """压缩 SQLite 数据库，回收已删除数据占用的空闲页。"""
    verify_csrf_token(request, csrf_token)

    # 先结束当前请求的读事务，避免自己阻塞 WAL checkpoint
    try:
        db.commit()
    except Exception:
        db.rollback()

    # 仍有其他请求持有连接时直接拒绝：VACUUM 会长时间占写锁，
    # 在流量期间执行会把连接池和写路径一起拖住。
    pool_status = db_manager.get_pool_status()
    if int(pool_status.get("checked_out") or 0) > 2:
        return JSONResponse(
            {
                "success": False,
                "error": "当前仍有请求在使用数据库，请等流量空闲后再压缩。",
            },
            status_code=409,
        )

    try:
        stats = vacuum_sqlite_database()
    except RuntimeError as exc:
        return JSONResponse({"success": False, "error": str(exc)}, status_code=400)
    except Exception as exc:
        logger.exception("数据库压缩失败")
        return JSONResponse(
            {"success": False, "error": f"数据库压缩失败：{exc}"},
            status_code=500,
        )

    return JSONResponse({
        "success": True,
        "message": "数据库压缩完成",
        "data": stats,
    })


def _cleanup_temp_files(temp_dir: str):
    """清理临时文件和目录"""
    try:
        import shutil
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"清理临时文件失败: {str(e)}")

