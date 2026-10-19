"""
按请求自动判定的会话中间件。

Starlette 原生 ``SessionMiddleware`` 的 ``https_only`` 在构造期固化为
``security_flags``，整个进程只能按同一个协议假设工作，HTTP↔HTTPS 切换或
新增反向代理时必须修改配置并重启服务。

本子类在构造期强制 ``https_only=False``，改为在每个响应发出前调用
``should_use_secure_cookie`` 按实际请求（``X-Forwarded-Proto`` / 请求
scheme）判定是否追加 ``Secure`` 标志，使协议切换零配置。

``__call__`` 复刻自 Starlette 对应实现，唯一差异是 security flags 改为
按请求计算（原实现使用构造期固化的 ``self.security_flags``）。
"""
from __future__ import annotations

import json
from base64 import b64decode, b64encode
from typing import Optional

from itsdangerous.exc import BadSignature
from starlette.datastructures import MutableHeaders
from starlette.middleware.sessions import Session, SessionMiddleware
from starlette.requests import HTTPConnection
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .security import should_use_secure_cookie


class RequestAwareSessionMiddleware(SessionMiddleware):
    """会话 Cookie 的 Secure 标志按实际请求自动判定。"""

    def __init__(
        self,
        app: ASGIApp,
        secret_key: str,
        session_cookie: str = "session",
        max_age: Optional[int] = 14 * 24 * 60 * 60,
        path: str = "/",
        same_site: str = "lax",
        domain: Optional[str] = None,
    ) -> None:
        # 构造期不固化 Secure，改为逐请求判定
        super().__init__(
            app,
            secret_key,
            session_cookie=session_cookie,
            max_age=max_age,
            path=path,
            same_site=same_site,  # type: ignore[arg-type]
            https_only=False,
            domain=domain,
        )

    def _security_flags_for(self, connection: HTTPConnection) -> str:
        """按实际请求计算 Set-Cookie 的安全属性。"""
        flags = self.security_flags
        if should_use_secure_cookie(connection):
            flags += "; secure"
        return flags

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):  # pragma: no cover
            await self.app(scope, receive, send)
            return

        connection = HTTPConnection(scope)
        initial_session_was_empty = True

        if self.session_cookie in connection.cookies:
            data = connection.cookies[self.session_cookie].encode("utf-8")
            try:
                data = self.signer.unsign(data, max_age=self.max_age)
                scope["session"] = Session(json.loads(b64decode(data)))
                initial_session_was_empty = False
            except BadSignature:
                scope["session"] = Session()
        else:
            scope["session"] = Session()

        # 每个请求按实际协议判定是否追加 Secure
        security_flags = self._security_flags_for(connection)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                session: Session = scope["session"]
                headers = MutableHeaders(scope=message)
                if session.accessed:
                    headers.add_vary_header("Cookie")
                if session.modified and session:
                    # 有会话数据需要持久化
                    data = b64encode(json.dumps(session).encode("utf-8"))
                    data = self.signer.sign(data)
                    header_value = "{session_cookie}={data}; path={path}; {max_age}{security_flags}".format(
                        session_cookie=self.session_cookie,
                        data=data.decode("utf-8"),
                        path=self.path,
                        max_age=f"Max-Age={self.max_age}; " if self.max_age else "",
                        security_flags=security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
                elif session.modified and not initial_session_was_empty:
                    # 会话已被清空
                    header_value = "{session_cookie}={data}; path={path}; {expires}{security_flags}".format(
                        session_cookie=self.session_cookie,
                        data="null",
                        path=self.path,
                        expires="expires=Thu, 01 Jan 1970 00:00:00 GMT; ",
                        security_flags=security_flags,
                    )
                    headers.append("Set-Cookie", header_value)
            await send(message)

        await self.app(scope, receive, send_wrapper)
