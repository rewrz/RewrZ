"""
异步导入任务模型

用于持久化数据导入任务（WordPress WXR / RewrZ JSON 等）的状态与进度：
1. 支持多 worker 部署下跨进程查询任务进度
2. 服务重启后任务状态不丢失，可识别被中断的任务
3. 通过心跳检测执行进程存活，及时收敛僵死任务
"""
from sqlalchemy import Column, DateTime, Integer, String, Text, JSON
from ..core.time_utils import utc_now_naive

from .base import Base


class ImportJob(Base):
    """异步导入任务模型类"""
    __tablename__ = "import_jobs"

    id = Column(String(32), primary_key=True, index=True)
    user_id = Column(Integer, nullable=False, index=True)
    job_type = Column(String(50), nullable=False, default="wordpress_import", index=True)
    filename = Column(String(500), nullable=True)
    # queued / running / completed / failed / interrupted
    status = Column(String(20), nullable=False, default="queued", index=True)
    progress_stage = Column(String(50), nullable=False, default="queued")
    progress_message = Column(Text, nullable=False, default="")
    progress_current = Column(Integer, nullable=False, default=0)
    progress_total = Column(Integer, nullable=False, default=1)
    progress_percent = Column(Integer, nullable=False, default=0)
    progress_extra = Column(JSON, nullable=True)
    result = Column(JSON, nullable=True)
    error = Column(Text, nullable=True)
    # 执行进程信息，用于僵死任务检测
    worker_pid = Column(Integer, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utc_now_naive, nullable=False, index=True)
    updated_at = Column(DateTime, default=utc_now_naive, onupdate=utc_now_naive, nullable=False)
