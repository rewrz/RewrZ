from __future__ import annotations

from datetime import datetime

from rewrz import main as main_module
from rewrz.core.task_scheduler import InMemorySchedulerStateStore, UnifiedTaskScheduler


def test_scheduler_runs_daily_task_only_once_per_day():
    runs: list[str] = []
    scheduler = UnifiedTaskScheduler(
        state_store=InMemorySchedulerStateStore(),
        now_provider=lambda: datetime(2026, 6, 8, 0, 0, 5),
    )
    scheduler.register_daily_task(
        name="daily-demo",
        hour=0,
        minute=0,
        second=0,
        handler=lambda: runs.append("ok"),
        description="测试每日任务",
    )

    due, period_key = scheduler.get_due_state(
        scheduler.get_registered_tasks()["daily-demo"],
        datetime(2026, 6, 8, 0, 0, 5),
    )
    assert due is True
    assert period_key == "2026-06-08"


def test_scheduler_runs_yearly_task_only_after_scheduled_date():
    scheduler = UnifiedTaskScheduler(
        state_store=InMemorySchedulerStateStore(),
        now_provider=lambda: datetime(2026, 12, 30, 23, 59, 59),
    )
    scheduler.register_yearly_task(
        name="yearly-demo",
        month=12,
        day=31,
        hour=0,
        minute=0,
        second=0,
        handler=lambda: None,
        description="测试年度任务",
    )

    due_before, _ = scheduler.get_due_state(
        scheduler.get_registered_tasks()["yearly-demo"],
        datetime(2026, 12, 30, 23, 59, 59),
    )
    due_after, period_key = scheduler.get_due_state(
        scheduler.get_registered_tasks()["yearly-demo"],
        datetime(2026, 12, 31, 0, 0, 0),
    )

    assert due_before is False
    assert due_after is True
    assert period_key == "2026"


def test_register_default_scheduled_tasks_registers_effect_tasks():
    main_module.default_task_scheduler.tasks.clear()
    main_module.default_task_scheduler.task_states.clear()
    main_module.default_task_scheduler.task_locks.clear()

    main_module.register_default_scheduled_tasks()
    registered = main_module.default_task_scheduler.get_registered_tasks()

    assert "effects_daily_refresh" in registered
    assert "public_holiday_rollover" in registered
    assert registered["effects_daily_refresh"].schedule_type == "daily"
    assert registered["public_holiday_rollover"].schedule_type == "yearly"
