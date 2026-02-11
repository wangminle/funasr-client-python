#!/usr/bin/env python3
"""FunASR 语音识别脚本 — Agent 友好版

通过 WebSocket 连接 FunASR 服务端，将音频文件转为文字。
支持 offline（离线转写）、online（实时识别）和 2pass（两遍识别）三种模式。

设计原则：
- 默认 JSON 输出到 stdout（Agent 可直接解析）
- 日志输出到 stderr（不干扰结构化结果）
- 稳定退出码：0=成功, 1=参数错误, 2=连接失败, 3=识别超时, 4=运行时错误
- 单进程设计（简化，适合 Agent 场景）

用法示例：
  python funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav
  python funasr_recognize.py --host www.funasr.com --port 10096 --audio input.wav --format text

基于 FunASR GUI Client V3 核心模块构建。
"""

import argparse
import asyncio
import json
import logging
import os
import ssl
import sys
import time
import traceback
from typing import Any, Dict, List, Optional

# 注入 lib 目录到模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from protocol_adapter import (  # noqa: E402
    MessageProfile,
    ParsedResult,
    ProtocolAdapter,
    RecognitionMode,
    ServerType,
    create_adapter,
)
from websocket_compat import connect_websocket  # noqa: E402

# ---------- 退出码定义 ----------
EXIT_SUCCESS = 0
EXIT_ARG_ERROR = 1
EXIT_CONNECT_FAIL = 2
EXIT_TIMEOUT = 3
EXIT_RUNTIME_ERROR = 4

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("funasr_recognize")


# ============================================================
# 结果格式化
# ============================================================


def format_json_result(
    success: bool,
    text: str = "",
    mode: str = "",
    audio_file: str = "",
    server: str = "",
    duration_ms: float = 0,
    timestamp: Optional[List] = None,
    stamp_sents: Optional[List] = None,
    error: Optional[str] = None,
    error_code: int = 0,
) -> str:
    """格式化为 JSON 结果字符串"""
    result: Dict[str, Any] = {
        "success": success,
        "text": text,
        "mode": mode,
        "audio_file": audio_file,
        "server": server,
        "duration_ms": round(duration_ms, 1),
        "error": error,
    }
    if error_code:
        result["error_code"] = error_code
    if timestamp:
        result["timestamp"] = timestamp
    if stamp_sents:
        result["stamp_sents"] = stamp_sents
    return json.dumps(result, ensure_ascii=False, indent=2)


def format_text_result(text: str) -> str:
    """格式化为纯文本结果"""
    return text


def format_srt_result(
    text: str, timestamp: Optional[List] = None, stamp_sents: Optional[List] = None
) -> str:
    """格式化为 SRT 字幕格式

    如果有时间戳信息，生成标准 SRT 格式；
    否则生成单条字幕。
    """
    lines: List[str] = []

    if stamp_sents:
        # 从 stamp_sents 生成 SRT
        for idx, sent in enumerate(stamp_sents, 1):
            if not isinstance(sent, dict):
                continue
            text_seg = sent.get("text_seg", "")
            start_ms = sent.get("start", 0)
            end_ms = sent.get("end", 0)
            lines.append(str(idx))
            lines.append(f"{_ms_to_srt_time(start_ms)} --> {_ms_to_srt_time(end_ms)}")
            lines.append(text_seg)
            lines.append("")
    elif timestamp and len(timestamp) >= 2:
        # 从 timestamp 数组生成（格式: [[start, end], ...]）
        # 简化处理：整段文本配上首尾时间
        start_ms = timestamp[0][0] if isinstance(timestamp[0], list) else 0
        end_ms = timestamp[-1][1] if isinstance(timestamp[-1], list) else 0
        lines.append("1")
        lines.append(f"{_ms_to_srt_time(start_ms)} --> {_ms_to_srt_time(end_ms)}")
        lines.append(text)
        lines.append("")
    else:
        # 无时间戳信息，生成单条
        lines.append("1")
        lines.append("00:00:00,000 --> 99:59:59,999")
        lines.append(text)
        lines.append("")

    return "\n".join(lines)


def _ms_to_srt_time(ms: int) -> str:
    """毫秒转 SRT 时间格式 HH:MM:SS,mmm"""
    ms = int(ms)
    hours = ms // 3600000
    minutes = (ms % 3600000) // 60000
    seconds = (ms % 60000) // 1000
    millis = ms % 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


# ============================================================
# 音频文件读取
# ============================================================


def read_audio_file(wav_path: str, default_sample_rate: int = 16000) -> tuple:
    """读取音频文件

    Args:
        wav_path: 音频文件路径
        default_sample_rate: 默认采样率

    Returns:
        (audio_bytes, sample_rate, wav_format) 元组
    """
    sample_rate = default_sample_rate
    wav_format = "pcm"

    if not os.path.exists(wav_path):
        raise FileNotFoundError(f"音频文件不存在: {wav_path}")

    file_size = os.path.getsize(wav_path)
    if file_size == 0:
        raise ValueError(f"音频文件为空（0 字节）: {wav_path}")

    logger.info(f"读取音频文件: {wav_path} ({file_size / 1024 / 1024:.2f}MB)")

    if wav_path.endswith(".pcm"):
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes, sample_rate, wav_format

    elif wav_path.endswith(".wav"):
        import wave

        with wave.open(wav_path, "rb") as wav_file:
            sample_rate = wav_file.getframerate()
            frames = wav_file.readframes(wav_file.getnframes())
            audio_bytes = bytes(frames)
        logger.info(f"WAV 采样率: {sample_rate}")
        return audio_bytes, sample_rate, wav_format

    else:
        # 其他格式（mp3, mp4, flac 等）直接二进制读取
        wav_format = "others"
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes, sample_rate, wav_format


def load_hotwords(hotword_path: str) -> str:
    """加载热词文件

    Args:
        hotword_path: 热词文件路径，每行格式：词语 权重

    Returns:
        JSON 格式的热词字符串，失败返回空字符串
    """
    if not hotword_path or not hotword_path.strip():
        return ""

    if not os.path.exists(hotword_path):
        logger.warning(f"热词文件不存在: {hotword_path}")
        return ""

    fst_dict = {}
    try:
        with open(hotword_path, encoding="utf-8") as f:
            for line in f:
                words = line.strip().split()
                if len(words) < 2:
                    continue
                try:
                    fst_dict[" ".join(words[:-1])] = int(words[-1])
                except ValueError:
                    continue
    except Exception as e:
        logger.warning(f"读取热词文件失败: {e}")
        return ""

    if fst_dict:
        return json.dumps(fst_dict, ensure_ascii=False)
    return ""


# ============================================================
# 核心识别逻辑
# ============================================================


async def recognize(
    host: str,
    port: int,
    audio_path: str,
    mode: str = "offline",
    use_ssl: bool = True,
    server_type: str = "auto",
    audio_fs: int = 16000,
    use_itn: bool = True,
    hotword: str = "",
    timeout: int = 600,
    chunk_size: Optional[List[int]] = None,
    chunk_interval: int = 10,
) -> Dict[str, Any]:
    """执行语音识别

    Args:
        host: 服务器地址
        port: 服务器端口
        audio_path: 音频文件路径
        mode: 识别模式 (offline/online/2pass)
        use_ssl: 是否使用 SSL
        server_type: 服务端类型 (auto/legacy/funasr_main)
        audio_fs: 音频采样率
        use_itn: 是否启用 ITN
        hotword: 热词文件路径
        timeout: 超时时间（秒）
        chunk_size: 分块大小
        chunk_interval: 分块间隔

    Returns:
        结果字典，包含 text, mode, timestamp 等字段
    """
    if chunk_size is None:
        chunk_size = [5, 10, 5]

    start_time = time.time()

    # 初始化协议适配器
    adapter = create_adapter(server_type)
    logger.info(f"协议适配器已初始化，服务端类型: {adapter.server_type.value}")

    # 读取音频文件
    audio_bytes, sample_rate, wav_format = read_audio_file(audio_path, audio_fs)
    wav_name = os.path.basename(audio_path)

    # 加载热词
    hotword_msg = load_hotwords(hotword)

    # 构建 WebSocket URI
    protocol = "wss" if use_ssl else "ws"
    uri = f"{protocol}://{host}:{port}"

    # 配置 SSL
    ssl_context = None
    if use_ssl:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    logger.info(f"连接服务器: {uri}")

    # 使用协议适配层构建消息
    profile = MessageProfile(
        server_type=adapter.server_type,
        mode=RecognitionMode(mode),
        wav_name=wav_name,
        wav_format=wav_format,
        audio_fs=sample_rate,
        use_itn=use_itn,
        hotwords=hotword_msg,
        chunk_size=chunk_size,
        chunk_interval=chunk_interval,
    )

    # 最终结果容器
    final_result: Dict[str, Any] = {
        "text": "",
        "mode": mode,
        "timestamp": None,
        "stamp_sents": None,
        "is_final": False,
    }

    # 建立连接并执行识别
    async with connect_websocket(
        uri,
        subprotocols=["binary"],
        ping_interval=None,
        ssl=ssl_context,
        close_timeout=60,
        max_size=1024 * 1024 * 1024,
    ) as ws:
        logger.info("WebSocket 连接已建立")

        # 发送初始化消息
        start_message = adapter.build_start_message(profile)
        await ws.send(start_message)
        logger.info(f"已发送初始化消息: {start_message[:200]}")

        # 发送音频数据
        if len(audio_bytes) == 0:
            raise ValueError("音频数据为空（0 字节），无法发送")

        stride = 65536 if mode == "offline" else int(
            60 * chunk_size[1] / chunk_interval / 1000 * sample_rate * 2
        )
        total_chunks = (len(audio_bytes) - 1) // stride + 1
        logger.info(f"开始发送音频，共 {total_chunks} 块")

        for i in range(total_chunks):
            beg = i * stride
            end = min(beg + stride, len(audio_bytes))
            await ws.send(audio_bytes[beg:end])

            # 最后一块发送结束标志
            if i == total_chunks - 1:
                end_message = adapter.build_end_message()
                await ws.send(end_message)
                logger.info("已发送结束标志")

            # 非离线模式需要控制发送速度
            if mode != "offline":
                sleep_duration = 60 * chunk_size[1] / chunk_interval / 1000
                await asyncio.sleep(sleep_duration)

        logger.info("音频数据发送完毕，等待识别结果...")

        # 接收结果
        all_texts: List[str] = []
        while True:
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                result: ParsedResult = adapter.parse_result(raw_msg)

                if result.error:
                    logger.warning(f"消息解析错误: {result.error}")
                    continue

                # 收集文本
                if result.text:
                    all_texts.append(result.text)
                    logger.info(f"收到识别文本 ({result.mode}): {result.text[:100]}...")

                # 更新最终结果
                if result.text or result.is_complete:
                    final_result["text"] = result.text or final_result["text"]
                    final_result["mode"] = result.mode
                    final_result["is_final"] = result.is_final
                    if result.timestamp:
                        final_result["timestamp"] = result.timestamp
                    if result.stamp_sents:
                        final_result["stamp_sents"] = result.stamp_sents

                # 判断是否结束
                if result.is_complete:
                    logger.info(
                        f"识别完成 (is_complete=True, is_final={result.is_final})"
                    )
                    break

            except asyncio.TimeoutError:
                raise TimeoutError(f"识别超时（{timeout}秒）")

    # 对于 2pass 模式，如果收到多段文本，合并使用最后一段（2pass-offline纠错结果）
    # 对于 offline 模式，通常只有一段
    elapsed_ms = (time.time() - start_time) * 1000
    final_result["duration_ms"] = elapsed_ms
    logger.info(f"识别完成，总耗时: {elapsed_ms:.0f}ms")

    return final_result


# ============================================================
# 命令行入口
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="FunASR 语音识别工具 — 通过 WebSocket 连接 FunASR 服务进行语音转文字",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 离线识别（默认模式）
  python funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav

  # 使用公网测试服务
  python funasr_recognize.py --host www.funasr.com --port 10096 --audio input.wav

  # 纯文本输出
  python funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --format text

  # 2pass 模式
  python funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --mode 2pass

  # 输出到文件
  python funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --output result.json
        """,
    )

    # 服务器配置
    parser.add_argument("--host", type=str, required=True, help="FunASR 服务器地址")
    parser.add_argument("--port", type=int, required=True, help="FunASR 服务器端口")

    ssl_group = parser.add_mutually_exclusive_group()
    ssl_group.add_argument(
        "--ssl", action="store_true", default=True, help="启用 SSL（默认）"
    )
    ssl_group.add_argument("--no-ssl", action="store_false", dest="ssl", help="禁用 SSL")

    # 音频配置
    parser.add_argument("--audio", type=str, required=True, help="输入音频文件路径")
    parser.add_argument("--audio-fs", type=int, default=16000, help="音频采样率（默认 16000）")

    # 识别配置
    parser.add_argument(
        "--mode",
        type=str,
        default="offline",
        choices=["offline", "online", "2pass"],
        help="识别模式（默认 offline）",
    )
    parser.add_argument(
        "--server-type",
        type=str,
        default="auto",
        choices=["auto", "legacy", "funasr_main"],
        help="服务端类型（默认 auto 自动探测）",
    )
    parser.add_argument("--no-itn", action="store_true", help="禁用 ITN（逆文本正则化）")
    parser.add_argument("--hotword", type=str, default="", help="热词文件路径")
    parser.add_argument("--timeout", type=int, default=600, help="识别超时（秒，默认 600）")

    # 输出配置
    parser.add_argument(
        "--format",
        type=str,
        default="json",
        choices=["json", "text", "srt"],
        help="输出格式（默认 json）",
    )
    parser.add_argument("--output", type=str, default=None, help="输出到文件（可选，默认 stdout）")

    # 调试选项
    parser.add_argument("--verbose", action="store_true", help="详细日志输出")
    parser.add_argument("--quiet", action="store_true", help="静默模式（仅输出结果，无日志）")

    return parser


def main() -> None:
    """主函数"""
    parser = build_parser()
    args = parser.parse_args()

    # 日志级别调整
    if args.quiet:
        logging.getLogger().setLevel(logging.CRITICAL)
    elif args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    # 检查依赖
    try:
        import websockets  # noqa: F401
    except ImportError:
        _output_error(
            args,
            "缺少依赖: pip install websockets>=10.0",
            EXIT_ARG_ERROR,
        )
        return

    # 检查音频文件
    if not os.path.exists(args.audio):
        _output_error(args, f"音频文件不存在: {args.audio}", EXIT_ARG_ERROR)
        return

    if os.path.getsize(args.audio) == 0:
        _output_error(
            args,
            f"音频文件为空（0 字节）: {args.audio}",
            EXIT_ARG_ERROR,
        )
        return

    server_str = f"{args.host}:{args.port}"

    # 执行识别
    try:
        result = asyncio.run(
            recognize(
                host=args.host,
                port=args.port,
                audio_path=args.audio,
                mode=args.mode,
                use_ssl=args.ssl,
                server_type=args.server_type,
                audio_fs=args.audio_fs,
                use_itn=not args.no_itn,
                hotword=args.hotword,
                timeout=args.timeout,
            )
        )

        # 格式化输出
        text = result.get("text", "")
        timestamp_data = result.get("timestamp")
        stamp_sents_data = result.get("stamp_sents")
        duration_ms = result.get("duration_ms", 0)

        if args.format == "json":
            output = format_json_result(
                success=True,
                text=text,
                mode=result.get("mode", args.mode),
                audio_file=args.audio,
                server=server_str,
                duration_ms=duration_ms,
                timestamp=timestamp_data,
                stamp_sents=stamp_sents_data,
            )
        elif args.format == "text":
            output = format_text_result(text)
        elif args.format == "srt":
            output = format_srt_result(text, timestamp_data, stamp_sents_data)
        else:
            output = format_text_result(text)

        # 输出结果
        if args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            logger.info(f"结果已写入: {args.output}")
        else:
            print(output)

        sys.exit(EXIT_SUCCESS)

    except ConnectionRefusedError:
        _output_error(args, f"连接失败: {server_str} 连接被拒绝", EXIT_CONNECT_FAIL)
    except OSError as e:
        _output_error(args, f"连接失败: {e}", EXIT_CONNECT_FAIL)
    except TimeoutError as e:
        _output_error(args, str(e), EXIT_TIMEOUT)
    except FileNotFoundError as e:
        _output_error(args, str(e), EXIT_ARG_ERROR)
    except ValueError as e:
        _output_error(args, str(e), EXIT_ARG_ERROR)
    except Exception as e:
        logger.error(f"运行时错误: {traceback.format_exc()}")
        _output_error(args, f"运行时错误: {e}", EXIT_RUNTIME_ERROR)


def _output_error(args: argparse.Namespace, error_msg: str, exit_code: int) -> None:
    """输出错误信息并退出

    Args:
        args: 命令行参数
        error_msg: 错误信息
        exit_code: 退出码
    """
    if hasattr(args, "format") and args.format == "json":
        output = format_json_result(
            success=False,
            error=error_msg,
            error_code=exit_code,
            audio_file=getattr(args, "audio", ""),
            server=f"{getattr(args, 'host', '')}:{getattr(args, 'port', '')}",
        )
        if hasattr(args, "output") and args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
        else:
            print(output)
    else:
        print(f"错误: {error_msg}", file=sys.stderr)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
