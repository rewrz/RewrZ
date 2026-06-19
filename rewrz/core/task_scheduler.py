"""
统一任务调度器。

当前项目处于开发期，优先提供一套轻量、可测试、可扩展的原生调度器，
避免先为单一业务引入额外重依赖。
"""

from __future__ import annotations

import asyncio
import inspect
import logging
from dataclasses import asdict, dataclass
from datetime import datetime, time
from typing import Any, Awaitable, Callable, Dict, Literal, Optional, Protocol

from ..crud import setting as crud_setting
from ..core.database import db_manager
from ..schemas import SettingCreate
from ..schemas.setting import SettingUpdate

logger = logging.getLogger(__name__)

ScheduleType = Literal["interval", "daily", "yearly"]
TaskHandler = Callable[[], Any]


@dataclass
class TaskRunState:
    last_attempted_at: Optional[str] = None
    last_completed_at: Optional[str] = None
    last_attempt_period_key: Optional[str] = None
    last_success_period_key: Optional[str] = None
    last_error: Optional[str] = None
    last_trigger: Optional[str] = None


@dataclass
class ScheduledTask:
    name: str
    schedule_type: ScheduleType
    handler: TaskHandler
    description: str = ""
    enabled: bool = True
    interval_seconds: Optional[int] = None
    hour: int = 0
    minute: int = 0
    second: int = 0
    month: Optional[int] = None
    day: Optional[int] = None

    def scheduled_time(self) -> time:
        return time(hour=self.hour, minute=self.minute, second=self.second)


class SchedulerStateStore(Protocol):
    def load_states(self) -> Dict[str, TaskRunState]:
        ...

    def save_state(self, task_name: str, state: TaskRunState) -> None:
        ...


class InMemorySchedulerStateStore:
    """测试用内存状态存储。"""

    def __init__(self, initial: Optional[Dict[str, TaskRunState]] = None):
        self._states = initial or {}

    def load_states(self) -> Dict[str, TaskRunState]:
        return {
            name: TaskRunState(**asdict(state))
            for name, state in self._states.items()
        }

    def save_state(self, task_name: str, state: TaskRunState) -> None:
        self._states[task_name] = TaskRunState(**asdict(state))


class SettingBackedSchedulerStateStore:
    """基于 settings 表的任务运行状态存储。"""

    def __init__(self, setting_key: str = "scheduler_task_runtime_state"):
        self.setting_key = setting_key

    def load_states(self) -> Dict[str, TaskRunState]:
        session = db_manager.get_session()
        if session is None:
            return {}

        try:
            setting = crud_setting.get_setting(session, self.setting_key)
            raw_payload = setting.value if setting and isinstance(setting.value, dict) else {}
            raw_states = raw_payload.get("value", {}).get("tasks", {}) if isinstance(raw_payload, dict) else {}
            if not isinstance(raw_states, dict):
                return {}
            states: Dict[str, TaskRunState] = {}
            for task_name, state_payload in raw_states.items():
                if isinstance(state_payload, dict):
                    states[str(task_name)] = TaskRunState(**state_payload)
            return states
        finally:
            session.close()

    def save_state(self, task_name: str, state: TaskRunState) -> None:
        session = db_manager.get_session()
        if session is None:
            return

        try:
            setting = crud_setting.get_setting(session, self.setting_key)
            payload: Dict[str, Any] = setting.value if setting and isinstance(setting.value, dict) else {"value": {"tasks": {}}}
            value_payload = payload.get("value")
            if not isinstance(value_payload, dict):
                value_payload = {"tasks": {}}
            tasks_payload = value_payload.get("tasks")
            if not isinstance(tasks_payload, dict):
                tasks_payload = {}

            tasks_payload[task_name] = asdict(state)
            value_payload["tasks"] = tasks_payload
            payload["value"] = value_payload

            if setting is None:
                crud_setting.create_setting(
                    session,
                    SettingCreate(
                        key=self.setting_key,
                        value=payload,
                        description="统一任务调度器运行状态",
                        category="system",
                        type="json",
                    ),
                )
            else:
                crud_setting.update_setting(
                    session,
                    self.setting_key,
                    SettingUpdate(
                        value=payload,
                        description="统一任务调度器运行状态",
                        category="system",
                        type="json",
                    ),
                )
        finally:
            session.close()


class UnifiedTaskScheduler:
    """统一任务调度器。"""

    def __init__(
        self,
        *,
        state_store: Optional[SchedulerStateStore] = None,
        poll_interval_seconds: int = 30,
        now_provider: Optional[Callable[[], datetime]] = None,
    ):
        self.state_store = state_store or SettingBackedSchedulerStateStore()
        self.poll_interval_seconds = max(1, int(poll_interval_seconds))
        self.now_provider = now_provider or (lambda: datetime.now().astimezone())
        self.tasks: Dict[str, ScheduledTask] = {}
        self.task_states: Dict[str, TaskRunState] = {}
        self.task_locks: Dict[str, asyncio.Lock] = {}
        self._runner_task: Optional[asyncio.Task] = None
        self._started = False

    def register_interval_task(
        self,
        *,
        name: str,
        interval_seconds: int,
        handler: TaskHandler,
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            schedule_type="interval",
            interval_seconds=max(1, int(interval_seconds)),
            handler=handler,
            description=description,
            enabled=enabled,
        )
        return self._register(task)

    def register_daily_task(
        self,
        *,
        name: str,
        hour: int,
        minute: int = 0,
        second: int = 0,
        handler: TaskHandler,
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            schedule_type="daily",
            hour=hour,
            minute=minute,
            second=second,
            handler=handler,
            description=description,
            enabled=enabled,
        )
        return self._register(task)

    def register_yearly_task(
        self,
        *,
        name: str,
        month: int,
        day: int,
        hour: int = 0,
        minute: int = 0,
        second: int = 0,
        handler: TaskHandler,
        description: str = "",
        enabled: bool = True,
    ) -> ScheduledTask:
        task = ScheduledTask(
            name=name,
            schedule_type="yearly",
            month=month,
            day=day,
            hour=hour,
            minute=minute,
            second=second,
            handler=handler,
            description=description,
            enabled=enabled,
        )
        return self._register(task)

    def _register(self, task: ScheduledTask) -> ScheduledTask:
        self.tasks[task.name] = task
        self.task_locks.setdefault(task.name, asyncio.Lock())
        self.task_states.setdefault(task.name, TaskRunState())
        return task

    async def start(self) -> None:
        if self._started:
            return
        self.task_states = await asyncio.to_thread(self.state_store.load_states)
        for task_name in self.tasks:
            self.task_states.setdefault(task_name, TaskRunState())
            self.task_locks.setdefault(task_name, asyncio.Lock())
        self._started = True
        self._runner_task = asyncio.create_task(self._run_loop(), name="rewrz-unified-task-scheduler")
        logger.info("统一任务调度器已启动，共注册 %s 个任务", len(self.tasks))

    async def stop(self) -> None:
        self._started = False
        runner = self._runner_task
        self._runner_task = None
        if runner is None:
            return
        runner.cancel()
        try:
            await runner
        except asyncio.CancelledError:
            pass
        logger.info("统一任务调度器已停止")

    async def _run_loop(self) -> None:
        try:
            while self._started:
                await self.tick()
                await asyncio.sleep(self.poll_interval_seconds)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("统一任务调度器主循环异常退出")

    async def tick(self, now: Optional[datetime] = None, *, run_inline: bool = False) -> None:
        current = now or self.now_provider()
        for task in self.tasks.values():
            due, period_key = self.get_due_state(task, current)
            if not due or period_key is None:
                continue

            lock = self.task_locks.setdefault(task.name, asyncio.Lock())
            if lock.locked():
                continue

            if run_inline:
                await self._execute_task(task, period_key=period_key, trigger="schedule")
            else:
                asyncio.create_task(
                    self._execute_task(task, period_key=period_key, trigger="schedule"),
                    name=f"rewrz-task-{task.name}",
                )

    def get_due_state(self, task: ScheduledTask, now: datetime) -> tuple[bool, Optional[str]]:
        if not task.enabled:
            return False, None

        state = self.task_states.setdefault(task.name, TaskRunState())

        if task.schedule_type == "interval":
            if task.interval_seconds is None:
                return False, None
            if not state.last_attempted_at:
                return True, "initial"
            try:
                last_attempt = datetime.fromisoformat(state.last_attempted_at)
            except ValueError:
                return True, "recover"
            elapsed_seconds = (now - last_attempt).total_seconds()
            if elapsed_seconds >= task.interval_seconds:
                return True, now.strftime("%Y-%m-%dT%H:%M:%S%z")
            return False, None

        if task.schedule_type == "daily":
            period_key = now.date().isoformat()
            if now.time() < task.scheduled_time():
                return False, None
            return state.last_attempt_period_key != period_key, period_key

        if task.schedule_type == "yearly":
            if task.month is None or task.day is None:
                return False, None
            period_key = str(now.year)
            current_tuple = (now.month, now.day, now.time())
            scheduled_tuple = (task.month, task.day, task.scheduled_time())
            if current_tuple < scheduled_tuple:
                return False, None
            return state.last_attempt_period_key != period_key, period_key

        return False, None

    async def run_task_now(self, task_name: str) -> None:
        task = self.tasks.get(task_name)
        if task is None:
            raise KeyError(f"未注册的任务: {task_name}")
        period_key = f"manual-{self.now_provider().strftime('%Y-%m-%dT%H:%M:%S%z')}"
        await self._execute_task(task, period_key=period_key, trigger="manual")

    async def _execute_task(self, task: ScheduledTask, *, period_key: str, trigger: str) -> None:
        lock = self.task_locks.setdefault(task.name, asyncio.Lock())
        async with lock:
            state = self.task_states.setdefault(task.name, TaskRunState())
            now = self.now_provider().isoformat()
            state.last_attempted_at = now
            state.last_attempt_period_key = period_key
            state.last_trigger = trigger
            state.last_error = None
            await asyncio.to_thread(self.state_store.save_state, task.name, state)

            try:
                result = task.handler()
                if inspect.isawaitable(result):
                    await result
                state.last_completed_at = self.now_provider().isoformat()
                state.last_success_period_key = period_key
                state.last_error = None
                logger.info("定时任务执行完成: %s", task.name)
            except Exception as exc:
                state.last_error = str(exc)
                logger.exception("定时任务执行失败: %s", task.name)
            finally:
                await asyncio.to_thread(self.state_store.save_state, task.name, state)

    def get_registered_tasks(self) -> Dict[str, ScheduledTask]:
        return dict(self.tasks)

    def get_task_states(self) -> Dict[str, TaskRunState]:
        return {
            task_name: TaskRunState(**asdict(state))
            for task_name, state in self.task_states.items()
        }


default_task_scheduler = UnifiedTaskScheduler()
