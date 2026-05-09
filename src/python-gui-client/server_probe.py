"""FunASR 服务探测器

职责：
1. 连接可达性检测
2. 服务能力探测（轻量级）
3. 协议语义推断

版本: 3.0
日期: 2026-01-26
"""

import asyncio
import json
import logging
import ssl
import sys
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# asyncio.timeout 需要 Python >= 3.11；项目要求 3.12，
# 但若被低版本误用，在此给出明确错误而非 AttributeError
if sys.version_info < (3, 11):
    raise RuntimeError("server_probe 模块需要 Python >= 3.11 (asyncio.timeout)")

# WebSocket 兼容层：处理不同 websockets 版本的参数差异
from websocket_compat import connect_websocket

# 配置日志
logger = logging.getLogger(__name__)


class ProbeLevel(Enum):
    """探测级别枚举

    用于控制探测的深度和耗时。
    """

    CONNECT_ONLY = 0  # 仅连接测试（<1s）
    OFFLINE_LIGHT = 1  # 离线轻量探测（1-3s，推荐）
    TWOPASS_FULL = 2  # 2pass完整探测（3-5s）


@dataclass
class ServerCapabilities:
    """服务器能力描述

    封装探测结果，包括连接状态、支持的模式、能力特征等。
    """

    # 基础状态
    reachable: bool = False  # 是否可连接
    responsive: bool = False  # 是否有响应
    error: Optional[str] = None  # 错误信息

    # 支持的模式（三态：None=未判定, True=支持, False=不支持）
    supports_offline: Optional[bool] = None
    supports_online: Optional[bool] = None
    supports_2pass: Optional[bool] = None

    # 能力特征
    has_timestamp: bool = False  # 是否支持时间戳
    has_stamp_sents: bool = False  # 是否支持句子级时间戳

    # 协议语义（用于适配层参考）
    is_final_semantics: str = "unknown"  # legacy_true / always_false / unknown

    # 推断的服务端类型（最佳努力，仅用于UI提示，不作为协议决策依据）
    inferred_server_type: str = "unknown"  # legacy / funasr_main / unknown

    # 探测详情
    probe_level: ProbeLevel = ProbeLevel.CONNECT_ONLY
    probe_notes: List[str] = field(default_factory=list)

    # 探测时间信息
    probe_duration_ms: float = 0.0

    def to_display_text(self) -> str:
        """生成用于UI展示的文本

        Returns:
            用户友好的状态描述字符串
        """
        if not self.reachable:
            return f"❌ 不可连接 | {self.error or '请检查IP/端口/SSL'}"

        parts = ["✅ 服务可用" if self.responsive else "✅ 已连接（未响应）"]

        # 模式支持
        modes = []
        if self.supports_offline is True:
            modes.append("离线")
        if self.supports_2pass is True:
            modes.append("2pass")
        if self.supports_online is True:
            modes.append("实时")
        if modes:
            parts.append(f"模式: {'/'.join(modes)}")
        elif not self.responsive:
            parts.append("模式: 未判定（可直接开始识别验证）")

        # 能力
        caps = []
        if self.has_timestamp or self.has_stamp_sents:
            caps.append("时间戳")
        if caps:
            parts.append(f"能力: {', '.join(caps)}")

        # 服务端类型
        if self.inferred_server_type != "unknown":
            type_name = (
                "可能新版" if self.inferred_server_type == "funasr_main" else "可能旧版"
            )
            parts.append(f"类型: {type_name}（仅供参考）")

        return " | ".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于配置缓存）

        Returns:
            包含所有关键信息的字典
        """
        return {
            "reachable": self.reachable,
            "responsive": self.responsive,
            "error": self.error,
            "supports_offline": self.supports_offline,
            "supports_online": self.supports_online,
            "supports_2pass": self.supports_2pass,
            "has_timestamp": self.has_timestamp,
            "has_stamp_sents": self.has_stamp_sents,
            "is_final_semantics": self.is_final_semantics,
            "inferred_server_type": self.inferred_server_type,
            "probe_level": self.probe_level.name,
            "probe_notes": self.probe_notes,
            "probe_duration_ms": self.probe_duration_ms,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServerCapabilities":
        """从字典创建实例（用于缓存恢复）

        Args:
            data: 包含能力信息的字典

        Returns:
            ServerCapabilities 实例
        """
        # 处理 probe_level 枚举
        probe_level_str = data.get("probe_level", "CONNECT_ONLY")
        try:
            probe_level = ProbeLevel[probe_level_str]
        except KeyError:
            probe_level = ProbeLevel.CONNECT_ONLY

        return cls(
            reachable=data.get("reachable", False),
            responsive=data.get("responsive", False),
            error=data.get("error"),
            supports_offline=data.get("supports_offline"),
            supports_online=data.get("supports_online"),
            supports_2pass=data.get("supports_2pass"),
            has_timestamp=data.get("has_timestamp", False),
            has_stamp_sents=data.get("has_stamp_sents", False),
            is_final_semantics=data.get("is_final_semantics", "unknown"),
            inferred_server_type=data.get("inferred_server_type", "unknown"),
            probe_level=probe_level,
            probe_notes=data.get("probe_notes", []),
            probe_duration_ms=data.get("probe_duration_ms", 0.0),
        )


class ServerProbe:
    """服务探测器

    核心职责：
    1. 检测服务器连接可达性
    2. 探测服务能力（离线/2pass模式支持）
    3. 推断服务端类型和协议语义
    """

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """将 is_final 等字段做宽容布尔转换

        兼容 bool / int / str（"true"/"false"/"1"/"0" 等）等常见情况。
        与 protocol_adapter.py 中的 _coerce_bool 保持一致。

        Args:
            value: 需要转换的值

        Returns:
            转换后的布尔值
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            if value != value:  # NaN 检查
                return False
            return value != 0
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "y", "on"):
                return True
            if s in ("false", "0", "no", "n", "off", ""):
                return False
            return True
        return bool(value)

    def __init__(self, host: str, port: str, use_ssl: bool = True):
        """初始化服务探测器

        Args:
            host: 服务器主机地址
            port: 服务器端口（字符串或整数）
            use_ssl: 是否使用SSL连接
        """
        self.host = host
        self.port = str(port)
        self.use_ssl = use_ssl
        # 复用 SSL context 避免重复创建
        self._ssl_context: Optional[ssl.SSLContext] = None
        if use_ssl:
            self._ssl_context = ssl.create_default_context()
            self._ssl_context.check_hostname = False
            self._ssl_context.verify_mode = ssl.CERT_NONE

    async def probe(
        self,
        level: ProbeLevel = ProbeLevel.OFFLINE_LIGHT,
        timeout: float = 5.0,
    ) -> ServerCapabilities:
        """执行探测

        Args:
            level: 探测级别
            timeout: 总超时时间（秒）
                注意：TWOPASS_FULL 级别建议使用至少 12 秒超时

        Returns:
            ServerCapabilities: 探测结果
        """
        import time

        start_time = time.time()
        caps = ServerCapabilities(probe_level=level)

        # Bug修复[P2]: TWOPASS_FULL 级别自动提升超时时间到最小推荐值
        # 避免因默认5秒超时导致误判
        if level == ProbeLevel.TWOPASS_FULL and timeout < 12.0:
            logger.info(f"TWOPASS_FULL 级别超时时间 {timeout}s 较短，自动提升到 12s")
            timeout = 12.0

        # 构建URI
        protocol = "wss" if self.use_ssl else "ws"
        uri = f"{protocol}://{self.host}:{self.port}"

        logger.info(f"开始探测服务器: {uri}, 级别: {level.name}")

        try:
            # 动态导入 websockets
            try:
                import websockets  # noqa: F401
            except ImportError as e:
                caps.error = "websockets库未安装"
                logger.error(f"websockets库未安装: {e}")
                return caps

            # 使用缓存的 SSL context
            ssl_context = self._ssl_context

            # 总超时：覆盖所有阶段，避免 TWOPASS_FULL 最坏跑到 2*timeout
            async with asyncio.timeout(timeout):
                # 阶段0：连接测试
                async with connect_websocket(
                    uri,
                    subprotocols=["binary"],
                    ping_interval=None,
                    ssl=ssl_context,
                    open_timeout=float(timeout),
                ) as ws:
                    caps.reachable = True
                    caps.probe_notes.append("WebSocket连接成功")
                    logger.debug("WebSocket连接成功")

                    if level == ProbeLevel.CONNECT_ONLY:
                        caps.probe_duration_ms = (time.time() - start_time) * 1000
                        return caps

                    # 阶段1：离线轻量探测（默认推荐）
                    if level in [ProbeLevel.OFFLINE_LIGHT, ProbeLevel.TWOPASS_FULL]:
                        await self._probe_offline(ws, caps)

                # 阶段2：2pass探测（仅在 TWOPASS_FULL 级别时执行）
                # 注意：需要新建连接避免状态干扰
                #
                # 关键修复：离线无响应并不能推出“不支持2pass”
                # 因为离线探测使用短/静音输入，部分服务端可能不回包。
                if level == ProbeLevel.TWOPASS_FULL and caps.reachable:
                    if not caps.responsive:
                        caps.probe_notes.append("离线探测无响应，仍尝试2pass以避免误判")
                    # 内层超时使用外层的 80%，避免内层超时被外层抢先触发
                    inner_timeout = max(timeout * 0.8, 3.0)
                    await self._probe_2pass_with_new_connection(
                        uri, ssl_context, caps, inner_timeout
                    )

        except asyncio.TimeoutError:
            # Bug修复[P1]: 区分"连接超时"和"探测超时"
            # - 如果尚未完成连接（caps.reachable == False），使用"连接超时"
            # - 如果已完成连接但在后续探测阶段超时，使用"探测超时"
            if caps.reachable:
                caps.error = "探测超时"
                logger.warning(f"探测超时: {uri}")
            else:
                caps.error = "连接超时"
                logger.warning(f"连接超时: {uri}")
        except ConnectionRefusedError:
            caps.error = "连接被拒绝"
            logger.warning(f"连接被拒绝: {uri}")
        except OSError as e:
            caps.error = f"网络错误: {e}"
            logger.warning(f"网络错误: {uri}, {e}")
        except Exception as e:
            # 检查是否是 websockets 的特定异常
            exception_name = type(e).__name__
            if "InvalidStatusCode" in exception_name:
                caps.error = f"服务器返回错误状态码: {e}"
            elif "ConnectionClosed" in exception_name:
                caps.error = f"连接被关闭: {e}"
                caps.reachable = True  # 连接成功但被关闭
            else:
                caps.error = str(e)
            logger.warning(f"探测异常: {uri}, {type(e).__name__}: {e}")

        # 推断服务端类型
        self._infer_server_type(caps)

        caps.probe_duration_ms = (time.time() - start_time) * 1000
        logger.info(
            f"探测完成: {uri}, 耗时: {caps.probe_duration_ms:.1f}ms, "
            f"结果: {caps.to_display_text()}"
        )

        return caps

    async def _probe_offline(self, ws: Any, caps: ServerCapabilities) -> None:
        """离线模式轻量探测

        发送短静音数据进行探测，检测服务端响应特征。

        Args:
            ws: WebSocket连接对象
            caps: 能力描述对象（会被修改）
        """
        try:
            # 发送探测消息
            probe_msg = json.dumps(
                {
                    "mode": "offline",
                    "wav_name": "__probe__",
                    "wav_format": "pcm",
                    "audio_fs": 16000,
                    "is_speaking": True,
                    "itn": True,
                }
            )
            await ws.send(probe_msg)
            logger.debug(f"发送探测消息: {probe_msg}")

            # 发送极短静音PCM，提升"空输入不回包"场景下的探测成功率
            # 16000Hz * 2bytes * 0.25s ≈ 8000 bytes
            silence_data = bytes(8000)
            await ws.send(silence_data)
            logger.debug(f"发送静音数据: {len(silence_data)} bytes")

            # 立即发送结束
            end_msg = json.dumps({"is_speaking": False})
            await ws.send(end_msg)
            logger.debug(f"发送结束消息: {end_msg}")

            # 等待响应（短超时）
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                caps.responsive = True
                logger.debug(
                    f"收到响应: {response[:200] if len(response) > 200 else response}"
                )

                # 解析响应
                try:
                    data = json.loads(response)
                    caps.supports_offline = True

                    # 分析响应特征
                    if "timestamp" in data:
                        caps.has_timestamp = True
                    if "stamp_sents" in data:
                        caps.has_stamp_sents = True

                    # 分析 is_final 语义（使用宽容布尔解析）
                    raw_is_final = data.get("is_final", None)
                    is_final = self._coerce_bool(raw_is_final)
                    if is_final is True:
                        caps.is_final_semantics = "legacy_true"
                    elif is_final is False:
                        # 注意：该特征无法100%区分新旧服务端，仅作"可能"提示
                        caps.is_final_semantics = "always_false"
                    # is_final 为 None 时保持 unknown

                    caps.probe_notes.append("离线模式探测成功")
                    logger.debug(
                        f"离线探测成功: is_final={is_final} (raw={raw_is_final}), "
                        f"has_timestamp={caps.has_timestamp}"
                    )

                except json.JSONDecodeError:
                    caps.probe_notes.append("离线探测响应非JSON格式")
                    logger.warning("离线探测响应非JSON格式")

            except asyncio.TimeoutError:
                # 无响应但连接成功
                caps.responsive = False
                caps.supports_offline = None  # 未判定
                caps.probe_notes.append(
                    "离线探测无响应（部分服务对短/静音输入可能不回包）"
                )
                logger.debug("离线探测无响应（超时）")

        except Exception as e:
            caps.probe_notes.append(f"离线探测异常: {e}")
            logger.warning(f"离线探测异常: {e}")

    async def _probe_2pass(self, ws: Any, caps: ServerCapabilities) -> None:
        """2pass模式探测（需要发送音频数据）

        Args:
            ws: WebSocket连接对象
            caps: 能力描述对象（会被修改）
        """
        try:
            # 发送2pass初始化
            probe_msg = json.dumps(
                {
                    "mode": "2pass",
                    "wav_name": "__probe_2pass__",
                    "wav_format": "pcm",
                    "audio_fs": 16000,
                    "is_speaking": True,
                    "chunk_size": [5, 10, 5],
                    "chunk_interval": 10,
                }
            )
            await ws.send(probe_msg)
            logger.debug(f"发送2pass探测消息: {probe_msg}")

            # 发送1秒静音PCM数据 (16000Hz * 2bytes * 1s = 32000bytes)
            silence_data = bytes(32000)
            await ws.send(silence_data)
            logger.debug(f"发送2pass静音数据: {len(silence_data)} bytes")

            # 发送结束
            end_msg = json.dumps({"is_speaking": False})
            await ws.send(end_msg)

            # 等待响应
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                try:
                    data = json.loads(response)
                except (json.JSONDecodeError, TypeError) as je:
                    caps.probe_notes.append(f"2pass探测响应非JSON: {je}")
                    logger.warning(f"2pass探测JSON解析失败: {je}")
                    return

                mode = data.get("mode", "")
                # 兼容连字符和下划线两种变体
                if mode in [
                    "2pass", "2pass-online", "2pass-offline",
                    "2pass_online", "2pass_offline",
                ]:
                    caps.supports_2pass = True
                    caps.supports_online = True
                    caps.responsive = True
                    caps.probe_notes.append("2pass模式探测成功")
                    logger.debug(f"2pass探测成功: mode={mode}")

            except asyncio.TimeoutError:
                caps.probe_notes.append("2pass探测超时")
                logger.debug("2pass探测超时")

        except Exception as e:
            caps.probe_notes.append(f"2pass探测异常: {e}")
            logger.warning(f"2pass探测异常: {e}")

    async def _probe_2pass_with_new_connection(
        self,
        uri: str,
        ssl_context: Optional[ssl.SSLContext],
        caps: ServerCapabilities,
        timeout: float,
    ) -> None:
        """使用新连接执行2pass模式探测

        为了避免与离线探测的状态干扰，2pass探测需要新建连接。

        Args:
            uri: WebSocket URI
            ssl_context: SSL上下文
            caps: 能力描述对象（会被修改）
            timeout: 超时时间
        """
        logger.debug("开始2pass探测（新建连接）")
        try:
            async with asyncio.timeout(timeout):
                connection = connect_websocket(
                    uri,
                    subprotocols=["binary"],
                    ping_interval=None,
                    ssl=ssl_context,
                    open_timeout=float(timeout),
                )
                async with connection as ws:
                    await self._probe_2pass(ws, caps)

        except asyncio.TimeoutError:
            caps.probe_notes.append("2pass探测连接超时")
            logger.warning("2pass探测连接超时")
        except ConnectionRefusedError as e:
            caps.probe_notes.append(f"2pass探测连接被拒绝: {e}")
            logger.warning(f"2pass探测连接被拒绝: {e}")
        except OSError as e:
            caps.probe_notes.append(f"2pass探测网络错误: {e}")
            logger.warning(f"2pass探测网络错误: {e}")
        except Exception as e:
            caps.probe_notes.append(f"2pass探测新建连接异常({type(e).__name__}): {e}")
            logger.warning(f"2pass探测新建连接异常({type(e).__name__}): {e}")

    def _infer_server_type(self, caps: ServerCapabilities) -> None:
        """根据探测结果推断服务端类型

        Args:
            caps: 能力描述对象（会被修改）
        """
        if caps.is_final_semantics == "always_false":
            caps.inferred_server_type = "funasr_main"
            logger.debug("推断服务端类型: funasr_main (is_final=false)")
        elif caps.is_final_semantics == "legacy_true":
            caps.inferred_server_type = "legacy"
            logger.debug("推断服务端类型: legacy (is_final=true)")
        else:
            caps.inferred_server_type = "unknown"
            logger.debug("推断服务端类型: unknown")


# ============ 便捷函数 ============


async def probe_server(
    host: str,
    port: str,
    use_ssl: bool = True,
    level: ProbeLevel = ProbeLevel.OFFLINE_LIGHT,
    timeout: float = 5.0,
) -> ServerCapabilities:
    """便捷函数：探测服务器

    Args:
        host: 服务器主机地址
        port: 服务器端口
        use_ssl: 是否使用SSL
        level: 探测级别
        timeout: 超时时间（秒）

    Returns:
        ServerCapabilities: 探测结果
    """
    probe = ServerProbe(host, port, use_ssl)
    return await probe.probe(level=level, timeout=timeout)


def probe_server_sync(
    host: str,
    port: str,
    use_ssl: bool = True,
    level: ProbeLevel = ProbeLevel.OFFLINE_LIGHT,
    timeout: float = 5.0,
) -> ServerCapabilities:
    """同步版本的便捷函数：探测服务器

    用于非异步环境（如Tkinter后台线程）。
    自动处理已有事件循环的情况，避免 RuntimeError。

    Args:
        host: 服务器主机地址
        port: 服务器端口
        use_ssl: 是否使用SSL
        level: 探测级别
        timeout: 超时时间（秒）

    Returns:
        ServerCapabilities: 探测结果
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # 已有事件循环运行中，创建新线程执行
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(
                asyncio.run,
                probe_server(host, port, use_ssl, level, timeout),
            )
            return future.result(timeout=timeout + 2)
    else:
        return asyncio.run(probe_server(host, port, use_ssl, level, timeout))


def create_probe_level(level_str: str) -> ProbeLevel:
    """从字符串创建探测级别

    Args:
        level_str: 探测级别字符串
            ("connect_only" / "offline_light" / "twopass_full")

    Returns:
        ProbeLevel 枚举值
    """
    level_map = {
        "connect_only": ProbeLevel.CONNECT_ONLY,
        "offline_light": ProbeLevel.OFFLINE_LIGHT,
        "twopass_full": ProbeLevel.TWOPASS_FULL,
    }
    return level_map.get(level_str.lower(), ProbeLevel.OFFLINE_LIGHT)
