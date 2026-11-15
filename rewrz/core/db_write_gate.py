"""后台写库闸门。

浏览量落库与访问统计刷写都是周期任务，原先各自独立提交，在 SQLite 上会
互相争抢写锁：一方的事务还没提交，另一方就进入 busy_timeout 等待，等待时间
一长就把请求级连接也拖进排队。这里用一把进程内锁把两类后台写入串行化，
把“并发争抢”收敛成“排队执行”，每个事务的持锁时间都可预期。
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from typing import Iterator

_GATE = threading.Lock()

# 拿不到闸门说明上一轮写入还在进行：本轮直接放弃，增量留在内存等下轮，
# 比在原地阻塞更安全（阻塞会把清理/退出流程一起拖住）。
_DEFAULT_TIMEOUT_SECONDS = 5.0


@contextmanager
def background_write_gate(timeout: float = _DEFAULT_TIMEOUT_SECONDS) -> Iterator[bool]:
    """尝试获取后台写入闸门，yield 是否获取成功。"""
    acquired = _GATE.acquire(timeout=max(0.1, float(timeout)))
    try:
        yield acquired
    finally:
        if acquired:
            _GATE.release()
