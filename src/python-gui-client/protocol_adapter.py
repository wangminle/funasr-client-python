"""FunASR 协议适配层

统一处理新旧服务端的协议差异，提供一致的内部接口。

核心功能：
1. 消息构建：根据服务端类型构建兼容的JSON消息
2. 结果解析：宽容解析各种响应格式
3. 结束判定：正确处理is_final语义差异（核心修复）

版本: 3.0
日期: 2026-01-26
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

# 配置日志
logger = logging.getLogger(__name__)


class ServerType(Enum):
    """服务端类型枚举

    用于区分不同版本的FunASR服务端，以便适配协议差异。
    """

    AUTO = "auto"  # 自动探测（推荐）
    LEGACY = "legacy"  # 旧版服务端
    FUNASR_MAIN = "funasr_main"  # 新版FunASR-main


class RecognitionMode(Enum):
    """识别模式枚举

    FunASR支持的三种识别模式。
    """

    OFFLINE = "offline"  # 离线转写模式
    ONLINE = "online"  # 实时识别模式
    TWOPASS = "2pass"  # 两遍识别模式（先快后准）


@dataclass
class MessageProfile:
    """消息构建配置

    封装构建WebSocket消息所需的所有参数。
    """

    # 必需参数
    server_type: ServerType
    mode: RecognitionMode
    wav_name: str

    # 音频格式参数
    wav_format: str = "pcm"
    audio_fs: int = 16000

    # 功能开关
    use_itn: bool = True  # 是否启用逆文本正则化
    use_ssl: bool = True  # 已废弃：SSL 由连接层处理，此字段不参与消息构建

    # 热词参数
    hotwords: str = ""

    # SenseVoice 相关参数（新版专用）
    enable_svs_params: bool = False  # 是否启用并下发 SenseVoice 相关参数
    svs_lang: str = "auto"  # SenseVoice 语种：auto/zh/en/ja/ko/yue
    svs_itn: bool = True  # SenseVoice ITN开关

    # 2pass/online 模式参数
    chunk_size: List[int] = field(default_factory=lambda: [5, 10, 5])
    chunk_interval: int = 10
    encoder_chunk_look_back: int = 4
    decoder_chunk_look_back: int = 1


@dataclass
class ParsedResult:
    """解析后的识别结果

    统一的结果格式，屏蔽新旧协议差异。
    """

    # 核心字段
    text: str = ""  # 识别文本
    mode: str = ""  # 识别模式
    wav_name: str = ""  # 音频文件名

    # 状态字段
    is_final: bool = False  # 原始 is_final 字段值
    is_complete: bool = False  # 是否应该结束等待（核心！）

    # 时间戳信息
    timestamp: Optional[List[Any]] = None
    stamp_sents: Optional[List[Any]] = None

    # 原始数据（用于调试和兜底）
    raw: Optional[Dict[str, Any]] = None
    raw_string: Optional[str] = None

    # 错误信息
    error: Optional[str] = None


class ProtocolAdapter:
    """协议适配器

    核心职责：
    1. 根据服务端类型构建兼容的消息
    2. 宽容解析各种响应格式
    3. 正确判断识别是否完成（修复 is_final 语义差异）
    """

    def __init__(self, server_type: ServerType = ServerType.AUTO):
        """初始化协议适配器

        Args:
            server_type: 服务端类型，默认为自动探测
        """
        self.server_type = server_type
        self._detected_is_final_semantics = "unknown"

    def build_start_message(self, profile: MessageProfile) -> str:
        """构建开始消息

        根据服务端类型和模式构建兼容的初始化JSON。

        Args:
            profile: 消息构建配置

        Returns:
            JSON格式的消息字符串
        """
        msg: Dict[str, Any] = {
            "mode": profile.mode.value,
            "wav_name": profile.wav_name,
            "wav_format": profile.wav_format,
            "audio_fs": profile.audio_fs,
            "is_speaking": True,
            "itn": profile.use_itn,
        }

        # 热词（新旧都支持）
        if profile.hotwords:
            msg["hotwords"] = profile.hotwords

        # 2pass/online 模式需要 chunk 参数
        if profile.mode in [RecognitionMode.ONLINE, RecognitionMode.TWOPASS]:
            msg["chunk_size"] = profile.chunk_size
            msg["chunk_interval"] = profile.chunk_interval
            msg["encoder_chunk_look_back"] = profile.encoder_chunk_look_back
            msg["decoder_chunk_look_back"] = profile.decoder_chunk_look_back

        # 新版参数（SenseVoice 相关）
        # 仅在用户显式启用（enable_svs_params=True）或用户明确指定 FUNASR_MAIN 时下发。
        # AUTO 模式不自动下发，避免旧服务端拒绝未知字段。
        should_send_svs = profile.enable_svs_params or (
            profile.server_type == ServerType.FUNASR_MAIN
        )
        if should_send_svs:
            msg["svs_lang"] = profile.svs_lang
            msg["svs_itn"] = profile.svs_itn

        logger.debug(f"构建开始消息: {msg}")
        return json.dumps(msg, ensure_ascii=False)

    def build_end_message(self) -> str:
        """构建结束消息

        Returns:
            JSON格式的结束消息字符串
        """
        return json.dumps({"is_speaking": False})

    def parse_result(self, raw_msg: str) -> ParsedResult:
        """解析结果消息（宽容解析）

        统一输出格式，屏蔽新旧协议差异。

        Args:
            raw_msg: 原始消息字符串

        Returns:
            ParsedResult: 解析后的结果对象
        """
        result = ParsedResult(raw_string=str(raw_msg) if raw_msg is not None else None)

        # 尝试解析JSON
        try:
            data = json.loads(raw_msg)
        except (json.JSONDecodeError, TypeError) as e:
            msg_preview = repr(raw_msg)[:200] if raw_msg is not None else "None"
            result.error = f"JSON解析失败: {e}"
            logger.warning(f"JSON解析失败: {e}, 原始数据: {msg_preview}...")
            return result

        result.raw = data

        # 提取基础字段
        result.mode = data.get("mode", "unknown")
        result.wav_name = data.get("wav_name", "")
        result.is_final = self._coerce_bool(data.get("is_final", False))
        result.timestamp = data.get("timestamp")
        result.stamp_sents = data.get("stamp_sents")

        # 文本提取（兼容多种格式）
        result.text = self._extract_text(data)

        # 🔴 核心修复：结束判定逻辑
        result.is_complete = self._should_complete(data)

        logger.debug(
            f"解析结果: mode={result.mode}, text_len={len(result.text)}, "
            f"is_final={result.is_final}, is_complete={result.is_complete}"
        )

        return result

    def _extract_text(self, data: Dict[str, Any]) -> str:
        """从响应数据中提取文本

        兼容多种格式：
        1. 直接的 text 字段
        2. stamp_sents 中的分段文本
        3. 2pass 模式的特殊字段

        Args:
            data: 解析后的JSON数据

        Returns:
            提取的文本字符串
        """
        # 优先使用 text 字段
        if "text" in data and data["text"]:
            return data["text"]

        # 从 stamp_sents 提取文本
        raw_stamp_sents = data.get("stamp_sents")
        if raw_stamp_sents and isinstance(raw_stamp_sents, list):
            segments = []
            for sent in raw_stamp_sents:
                if isinstance(sent, dict) and "text_seg" in sent:
                    segments.append(sent["text_seg"])
            if segments:
                text = "".join(segments)
                logger.debug(f"从 stamp_sents 提取文本，共 {len(segments)} 个片段")
                return text

        # 2pass 模式特殊字段
        if "text_2pass_offline" in data:
            return data["text_2pass_offline"]
        if "text_2pass_online" in data:
            return data["text_2pass_online"]

        return ""

    def _should_complete(self, data: Dict[str, Any]) -> bool:
        """判断是否应该结束等待

        这是解决新旧版本差异的核心逻辑！

        设计原则（必须兼容"静音/空文本"场景）：
        - offline：服务端通常只回一条结果（可能 text 为空、is_final=False），
                   收到回包就应结束等待
        - 2pass：收到 2pass-offline 即认为"最终纠错结果"已到达
                 （即便 text 为空也应结束，避免静音卡死）
        - 其他：优先遵循 is_final=True 的明确结束标志

        Args:
            data: 解析后的JSON数据

        Returns:
            是否应该结束等待
        """
        mode = data.get("mode", "")
        is_final = self._coerce_bool(data.get("is_final", False))

        # 情况1：服务端明确标记完成
        if is_final:
            logger.debug("结束判定: is_final=True，明确结束标志")
            return True

        # 情况2：离线模式（新版 runtime 可能永远 is_final=False）
        # 收到任何 offline 回包即可结束（不依赖 text 是否为空）
        if mode == "offline":
            logger.debug("结束判定: offline 模式收到回包，视为完成")
            return True

        # 情况3：2pass 最终纠错结果（不依赖 text 是否为空）
        if mode == "2pass-offline":
            logger.debug("结束判定: 2pass-offline 模式收到回包，视为完成")
            return True

        # 情况4：兜底 - 出现句子级时间戳通常代表本轮已结束/可结束等待
        # 注意：仅对 offline / 2pass 模式生效；online 模式中间结果也可能带 stamp_sents
        if mode != "online":
            stamp_sents = data.get("stamp_sents")
            if stamp_sents and len(stamp_sents) > 0:
                logger.debug("结束判定: 收到 stamp_sents（非online模式），视为完成")
                return True

        return False

    @staticmethod
    def _coerce_bool(value: Any) -> bool:
        """将 is_final 等字段做宽容布尔转换。

        兼容 bool / int / str（"true"/"false"/"1"/"0" 等）等常见情况。
        """
        if isinstance(value, bool):
            return value
        if value is None:
            return False
        if isinstance(value, (int, float)):
            if value != value:  # NaN 检查：NaN != NaN 为 True
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

    def update_server_type(self, server_type: ServerType) -> None:
        """更新服务端类型

        在运行时根据探测结果更新服务端类型。

        Args:
            server_type: 新的服务端类型
        """
        old_type = self.server_type
        self.server_type = server_type
        logger.info(f"服务端类型更新: {old_type.value} -> {server_type.value}")

    def get_is_final_semantics(self) -> str:
        """获取检测到的 is_final 语义

        Returns:
            "legacy_true" / "always_false" / "unknown"
        """
        return self._detected_is_final_semantics

    def record_is_final_semantics(self, is_final_value: bool, mode: str) -> None:
        """记录 is_final 语义特征

        用于根据实际响应推断服务端类型。

        Args:
            is_final_value: is_final 字段的值
            mode: 识别模式
        """
        is_final_value = self._coerce_bool(is_final_value)
        if mode == "offline":
            if is_final_value:
                self._detected_is_final_semantics = "legacy_true"
            else:
                self._detected_is_final_semantics = "always_false"
        elif mode in ("online", "2pass", "2pass-online", "2pass-offline"):
            if is_final_value:
                self._detected_is_final_semantics = "legacy_true"
        logger.debug(
            f"记录 is_final 语义: mode={mode}, "
            f"is_final={is_final_value}, "
            f"semantics={self._detected_is_final_semantics}"
        )


# 便捷函数
def create_adapter(server_type_str: str = "auto") -> ProtocolAdapter:
    """创建协议适配器的便捷函数

    Args:
        server_type_str: 服务端类型字符串 ("auto" / "legacy" / "funasr_main")

    Returns:
        ProtocolAdapter 实例
    """
    try:
        server_type = ServerType(server_type_str)
    except ValueError:
        logger.warning(f"无效的服务端类型: {server_type_str}，使用默认值 auto")
        server_type = ServerType.AUTO

    return ProtocolAdapter(server_type=server_type)


def create_message_profile(
    mode: str = "offline",
    wav_name: str = "audio",
    server_type: str = "auto",
    **kwargs: Any,
) -> MessageProfile:
    """创建消息配置的便捷函数

    Args:
        mode: 识别模式 ("offline" / "online" / "2pass")
        wav_name: 音频文件名
        server_type: 服务端类型
        **kwargs: 其他 MessageProfile 参数

    Returns:
        MessageProfile 实例
    """
    try:
        server_type_enum = ServerType(server_type)
    except ValueError:
        server_type_enum = ServerType.AUTO

    try:
        mode_enum = RecognitionMode(mode)
    except ValueError:
        mode_enum = RecognitionMode.OFFLINE

    import dataclasses

    valid_fields = {f.name for f in dataclasses.fields(MessageProfile)}
    filtered_kwargs = {k: v for k, v in kwargs.items() if k in valid_fields}
    return MessageProfile(
        server_type=server_type_enum, mode=mode_enum, wav_name=wav_name, **filtered_kwargs
    )
