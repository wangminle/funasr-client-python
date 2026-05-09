"""WebSocket 兼容层工具

本模块用于屏蔽不同版本 `websockets` 库在连接参数上的差异，避免运行时因参数不兼容导致崩溃。

目前重点处理：
1. `proxy` 参数：新版本 `websockets.connect` 支持 `proxy`，旧版本可能不支持。
   我们希望"尽可能禁用代理"，以避免环境代理导致连接异常；但若版本不支持则自动降级不传该参数。
2. `open_timeout` 参数：websockets 10.x 引入 `open_timeout` 代替旧版的 `timeout` 参数。
   旧版本传入 `open_timeout` 会抛 TypeError，需自动降级为 `timeout`。

说明：
- 该模块仅提供轻量封装，不引入额外依赖。
- 代码使用中文注释，符合项目约定。
"""

from __future__ import annotations

from typing import Any


def connect_websocket(uri: str, disable_proxy: bool = True, **kwargs: Any) -> Any:
    """创建兼容版 WebSocket 连接对象（返回 websockets.connect(...) 的结果）。

    用法示例：
        async with connect_websocket("wss://127.0.0.1:10095", ssl=ctx) as ws:
            ...

    Args:
        uri: WebSocket URI
        disable_proxy: 是否尽可能禁用代理（默认 True）
        **kwargs: 透传给 `websockets.connect` 的其他参数

    Returns:
        `websockets.connect(...)` 返回的连接对象（可 await / 可 async with）
    """
    import inspect
    from contextlib import asynccontextmanager

    import websockets

    def _wrap_if_needed(connect_obj: Any) -> Any:
        """将"仅 awaitable 但不可 async with"的对象包装成异步上下文管理器。

        说明：
        - 正常情况下 `websockets.connect(...)` 返回对象本身就支持 `async with`；
        - 但在单元测试使用 `AsyncMock` 伪造 connect 时，可能返回 coroutine，
          这会导致 `async with` 直接报错且产生"未 await"的警告。
        """
        if hasattr(connect_obj, "__aenter__") and hasattr(connect_obj, "__aexit__"):
            return connect_obj

        if inspect.isawaitable(connect_obj):

            @asynccontextmanager
            async def _ctx() -> Any:
                ws = await connect_obj
                try:
                    yield ws
                finally:
                    try:
                        close_func = getattr(ws, "close", None)
                        if callable(close_func):
                            maybe = close_func()
                            if inspect.isawaitable(maybe):
                                await maybe
                    except Exception:
                        pass

            return _ctx()

        raise TypeError(
            f"WebSocket 连接对象既不支持 async with 也不支持 await: {type(connect_obj)}"
        )

    def _normalize_timeout_params(kw: dict) -> dict:
        """处理 open_timeout 与 timeout 参数在不同版本 websockets 间的兼容性。

        websockets >= 10.0 使用 open_timeout，旧版使用 timeout。
        若调用失败则自动降级。
        """
        return kw

    def _try_connect(kw: dict) -> Any:
        """尝试连接，处理 proxy 和 open_timeout 的兼容性降级。"""
        try:
            connect_obj = websockets.connect(uri, **kw)
        except TypeError as e:
            err_msg = str(e)
            if "proxy" in err_msg:
                kw.pop("proxy", None)
                return _try_connect(kw)
            if "open_timeout" in err_msg:
                timeout_val = kw.pop("open_timeout", None)
                if timeout_val is not None:
                    kw.setdefault("timeout", timeout_val)
                return _try_connect(kw)
            raise
        return _wrap_if_needed(connect_obj)

    connect_kwargs = dict(kwargs)

    if disable_proxy:
        connect_kwargs["proxy"] = None

    return _try_connect(connect_kwargs)
