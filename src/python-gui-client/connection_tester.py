#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebSocket连接测试器

职责：
1. 封装WebSocket连接测试逻辑
2. 统一错误处理和错误类型映射
3. 支持配置化的协议消息
4. 提供友好的测试结果

创建时间：2025-10-24
"""

import asyncio
import json
import logging
import ssl
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

# WebSocket 兼容层：处理不同 websockets 版本的参数差异
from websocket_compat import connect_websocket


class ErrorType(Enum):
    """错误类型枚举"""

    NETWORK = "network"  # 网络错误（无法连接、连接拒绝等）
    PROTOCOL = "protocol"  # 协议错误（消息格式错误、服务器关闭连接等）
    TIMEOUT = "timeout"  # 超时错误
    SSL = "ssl"  # SSL相关错误
    UNKNOWN = "unknown"  # 未知错误


@dataclass
class ConnectionTestResult:
    """连接测试结果"""

    success: bool  # 是否成功
    error_type: Optional[ErrorType]  # 错误类型
    error_message: str  # 错误消息（用户友好）
    technical_details: str  # 技术详情（供日志记录）
    partial_success: bool = False  # 是否部分成功（建链成功但无响应）
    response_received: bool = False  # 是否收到响应
    response_data: Optional[str] = None  # 响应数据


class ConnectionTester:
    """WebSocket连接测试器

    封装连接测试逻辑，统一错误处理。
    """

    # 默认初始化消息模板
    DEFAULT_INIT_MESSAGE = {
        "mode": "offline",
        "audio_fs": 16000,
        "wav_name": "ping",
        "wav_format": "others",
        "is_speaking": True,
        "hotwords": "",
        "itn": True,
    }

    def __init__(
        self, timeout: int = 10, init_message: Optional[Dict[str, Any]] = None
    ):
        """初始化连接测试器

        Args:
            timeout: 单阶段超时时间（秒）。注意：完整测试包含握手+接收两个阶段，
                     最坏情况下总耗时可达 2 * timeout 秒。
            init_message: 初始化消息（None则使用默认值）
        """
        self.timeout = timeout
        self.init_message = init_message or self.DEFAULT_INIT_MESSAGE.copy()

        # 动态导入websockets（延迟导入）
        self._websockets = None

    def _import_websockets(self):
        """延迟导入websockets库"""
        if self._websockets is None:
            try:
                import websockets

                self._websockets = websockets
            except ImportError as e:
                raise ImportError(
                    "缺少websockets库，请安装: pip install websockets>=10.0"
                ) from e
        return self._websockets

    def _create_ssl_context(self, use_ssl: bool) -> Optional[ssl.SSLContext]:
        """创建SSL上下文

        Args:
            use_ssl: 是否使用SSL

        Returns:
            SSL上下文对象（如果不使用SSL则返回None）
        """
        if not use_ssl:
            return None

        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        return ssl_context

    def _build_uri(self, host: str, port: int, use_ssl: bool) -> str:
        """构建WebSocket URI

        Args:
            host: 主机地址
            port: 端口号
            use_ssl: 是否使用SSL

        Returns:
            WebSocket URI
        """
        protocol = "wss" if use_ssl else "ws"
        return f"{protocol}://{host}:{port}"

    def _parse_error(self, exception: Exception) -> ErrorType:
        """解析异常类型

        Args:
            exception: 异常对象

        Returns:
            错误类型
        """
        websockets = self._websockets

        # 超时错误（需要先于OSError检查，因为TimeoutError继承自OSError）
        if isinstance(exception, asyncio.TimeoutError):
            return ErrorType.TIMEOUT

        # SSL错误
        if isinstance(exception, ssl.SSLError):
            return ErrorType.SSL

        # 网络错误
        if isinstance(exception, (ConnectionRefusedError, OSError)):
            return ErrorType.NETWORK

        # WebSocket协议错误
        if websockets:
            try:
                ws_exc_classes = []
                for attr_name in (
                    "ConnectionClosedError",
                    "ConnectionClosedOK",
                    "InvalidStatusCode",
                    "InvalidStatus",
                ):
                    cls = getattr(websockets.exceptions, attr_name, None)
                    if cls is not None:
                        ws_exc_classes.append(cls)
                if ws_exc_classes and isinstance(exception, tuple(ws_exc_classes)):
                    # ConnectionClosedOK 表示正常关闭，视为部分成功而非协议错误
                    ok_cls = getattr(websockets.exceptions, "ConnectionClosedOK", None)
                    if ok_cls and isinstance(exception, ok_cls):
                        return ErrorType.UNKNOWN
                    return ErrorType.PROTOCOL
            except AttributeError:
                pass

        # 兜底：通过异常类名字符串匹配，适配 websockets 各版本
        exc_name = type(exception).__name__
        if exc_name in ("ConnectionClosedError", "InvalidStatusCode", "InvalidStatus"):
            return ErrorType.PROTOCOL

        # 未知错误
        return ErrorType.UNKNOWN

    def _get_user_friendly_message(
        self, error_type: ErrorType, exception: Exception
    ) -> str:
        """获取用户友好的错误消息

        Args:
            error_type: 错误类型
            exception: 异常对象

        Returns:
            用户友好的错误消息
        """
        messages = {
            ErrorType.NETWORK: "无法连接到服务器，请检查IP地址、端口号和网络连接",
            ErrorType.PROTOCOL: "服务器协议不匹配，请确认服务器类型和配置",
            ErrorType.TIMEOUT: "连接超时，请检查服务器是否正常运行",
            ErrorType.SSL: "SSL连接失败，请确认SSL设置是否正确",
            ErrorType.UNKNOWN: f"连接失败: {str(exception)}",
        }
        return messages.get(error_type, messages[ErrorType.UNKNOWN])

    async def test_connection(
        self, host: str, port: int, use_ssl: bool = False
    ) -> ConnectionTestResult:
        """测试WebSocket连接

        Args:
            host: 主机地址
            port: 端口号（1-65535）
            use_ssl: 是否使用SSL

        Returns:
            连接测试结果
        """
        if not (1 <= port <= 65535):
            return ConnectionTestResult(
                success=False,
                error_type=ErrorType.NETWORK,
                error_message=f"端口号无效: {port}",
                technical_details=f"端口号必须在 1-65535 范围内，当前值: {port}",
            )

        # 导入websockets
        try:
            self._import_websockets()
        except ImportError as e:
            return ConnectionTestResult(
                success=False,
                error_type=ErrorType.UNKNOWN,
                error_message="websockets库未安装",
                technical_details=str(e),
            )

        # 构建URI和SSL上下文
        uri = self._build_uri(host, port, use_ssl)
        ssl_context = self._create_ssl_context(use_ssl)

        logging.info(f"正在测试连接: {uri}")
        logging.debug(f"SSL上下文: {ssl_context is not None}")
        logging.debug(f"超时设置: {self.timeout}秒")

        try:
            # 创建连接对象（优先通过 open_timeout 控制握手超时）
            # websocket_compat.connect_websocket 已处理版本兼容性
            connection = connect_websocket(
                uri,
                subprotocols=["binary"],
                ping_interval=None,
                ssl=ssl_context,
                open_timeout=float(self.timeout),
            )

            # 使用连接对象作为上下文管理器，确保自动关闭连接
            async with connection as websocket:
                # 发送初始化消息
                message = json.dumps(self.init_message)
                await websocket.send(message)
                logging.debug(f"已发送初始化消息: {message}")

                # 尝试接收响应
                try:
                    response = await asyncio.wait_for(
                        websocket.recv(), timeout=self.timeout
                    )
                    resp_preview = response[:100] if isinstance(response, str) else repr(response[:100])
                    logging.info(f"收到服务器响应: {resp_preview}...")

                    # 成功：收到响应
                    return ConnectionTestResult(
                        success=True,
                        error_type=None,
                        error_message="连接成功",
                        technical_details=f"成功连接到 {uri} 并收到响应",
                        response_received=True,
                        response_data=response,
                    )

                except asyncio.TimeoutError:
                    # 部分成功：建链成功但无响应
                    logging.info("连接已建立，但未在超时时间内收到响应")
                    return ConnectionTestResult(
                        success=True,  # 仍视为成功（基础连通）
                        error_type=None,
                        error_message="连接成功（无响应）",
                        technical_details=f"成功连接到 {uri}，但服务器未响应",
                        partial_success=True,
                        response_received=False,
                    )

        except asyncio.TimeoutError:
            # 超时错误
            logging.warning(f"连接超时（{self.timeout}秒）")
            return ConnectionTestResult(
                success=False,
                error_type=ErrorType.TIMEOUT,
                error_message="连接超时",
                technical_details=f"在{self.timeout}秒内无法建立连接",
            )

        except ConnectionRefusedError as e:
            # 网络错误：连接被拒绝
            logging.warning(f"连接被拒绝: {e}")
            return ConnectionTestResult(
                success=False,
                error_type=ErrorType.NETWORK,
                error_message="连接被拒绝",
                technical_details=f"服务器拒绝连接，可能未启动或端口错误: {str(e)}",
            )

        except ssl.SSLError as e:
            # SSL错误
            logging.warning(f"SSL错误: {e}")
            return ConnectionTestResult(
                success=False,
                error_type=ErrorType.SSL,
                error_message="SSL连接失败",
                technical_details=f"SSL握手失败: {str(e)}",
            )

        except OSError as e:
            # 网络错误：其他OS级别错误
            logging.warning(f"网络错误: {e}")
            error_type = self._parse_error(e)
            return ConnectionTestResult(
                success=False,
                error_type=error_type,
                error_message=self._get_user_friendly_message(error_type, e),
                technical_details=f"OS错误: {str(e)}",
            )

        except Exception as e:
            # 检查是否是WebSocket连接关闭相关的异常
            exception_name = type(e).__name__
            if "ConnectionClosed" in exception_name:
                is_normal_close = "OK" in exception_name
                if is_normal_close:
                    # ConnectionClosedOK 表示正常关闭，视为部分成功（连接建立成功）
                    logging.info(f"WebSocket连接正常关闭: {e}")
                    return ConnectionTestResult(
                        success=True,
                        error_type=None,
                        error_message="连接被服务器正常关闭",
                        technical_details=f"服务器正常关闭了连接: {str(e)}",
                        partial_success=True,
                    )
                else:
                    logging.warning(f"WebSocket连接异常关闭: {e}")
                    return ConnectionTestResult(
                        success=False,
                        error_type=ErrorType.PROTOCOL,
                        error_message="连接被服务器关闭",
                        technical_details=f"服务器可能不接受当前消息格式: {str(e)}",
                        partial_success=False,
                    )

            # 其他未知错误
            logging.error(f"未知错误: {type(e).__name__}: {e}")
            error_type = self._parse_error(e)
            return ConnectionTestResult(
                success=False,
                error_type=error_type,
                error_message=self._get_user_friendly_message(error_type, e),
                technical_details=f"异常类型: {type(e).__name__}, 详情: {str(e)}",
            )

    def set_init_message(self, message: Dict[str, Any]):
        """设置初始化消息模板

        Args:
            message: 初始化消息字典
        """
        self.init_message = message.copy()

    def set_timeout(self, timeout: int):
        """设置超时时间

        Args:
            timeout: 超时时间（秒），必须为正数
        """
        if timeout <= 0:
            raise ValueError(f"timeout 必须为正数，当前值: {timeout}")
        self.timeout = timeout


# 便捷函数
async def test_connection(
    host: str,
    port: int,
    use_ssl: bool = False,
    timeout: int = 10,
    init_message: Optional[Dict[str, Any]] = None,
) -> ConnectionTestResult:
    """便捷函数：测试WebSocket连接

    Args:
        host: 主机地址
        port: 端口号
        use_ssl: 是否使用SSL
        timeout: 超时时间（秒）
        init_message: 初始化消息（None则使用默认值）

    Returns:
        连接测试结果
    """
    tester = ConnectionTester(timeout=timeout, init_message=init_message)
    return await tester.test_connection(host, port, use_ssl)


# 避免 pytest 将该“业务便捷函数”误判为测试用例并进行收集
# 说明：部分测试脚本会 `from connection_tester import test_connection`，
# 导致 pytest 在测试模块命名空间中看到 `test_*` 符号并尝试按 fixture 注入执行。
test_connection.__test__ = False
