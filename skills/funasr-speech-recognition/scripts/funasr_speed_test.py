#!/usr/bin/env python3
"""FunASR 速度测试脚本 — Agent 友好版

测量 FunASR 服务的上传速度（MB/s）和转写速度（倍速）。
默认使用 assets/test-for-speed.mp3 作为测试音频，执行 2 轮测试取平均值。

设计原则：
- 默认 JSON 输出到 stdout（Agent 可直接解析）
- 日志输出到 stderr（不干扰结构化结果）
- 稳定退出码：0=成功, 1=参数错误, 2=连接失败, 3=超时, 4=运行时错误
- 单进程设计（适合 Agent 场景）

用法示例：
  # 使用默认测试音频（assets/test-for-speed.mp3），2轮测试
  python funasr_speed_test.py --host 127.0.0.1 --port 10095

  # 指定自定义音频文件
  python funasr_speed_test.py --host 127.0.0.1 --port 10095 --audio my_test.wav

  # 指定测试轮数
  python funasr_speed_test.py --host 127.0.0.1 --port 10095 --rounds 5

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
logger = logging.getLogger("funasr_speed_test")

# ---------- 常量 ----------
# 默认测试音频采样参数（16kHz, 16bit, mono）
DEFAULT_SAMPLE_RATE = 16000
DEFAULT_SAMPLE_WIDTH = 2  # 16 位 = 2 字节
DEFAULT_CHANNELS = 1

# 默认测试轮数
DEFAULT_ROUNDS = 2

# 默认测试资产文件名
DEFAULT_ASSET_NAME = "test-for-speed.mp3"


# ============================================================
# 音频工具
# ============================================================


def get_audio_duration_seconds(audio_path: str) -> Optional[float]:
    """获取音频文件的时长（秒）

    支持 WAV 格式的精确时长，其他格式通过 mutagen 库获取。

    Args:
        audio_path: 音频文件路径

    Returns:
        音频时长（秒），无法获取时返回 None
    """
    if audio_path.endswith(".wav"):
        try:
            import wave

            with wave.open(audio_path, "rb") as wf:
                frames = wf.getnframes()
                rate = wf.getframerate()
                if rate > 0:
                    return frames / rate
        except Exception as e:
            logger.warning(f"无法解析 WAV 文件时长: {e}")
            return None

    elif audio_path.endswith(".pcm"):
        # PCM 文件：假定 16kHz, 16bit, mono
        file_size = os.path.getsize(audio_path)
        bytes_per_second = DEFAULT_SAMPLE_RATE * DEFAULT_SAMPLE_WIDTH * DEFAULT_CHANNELS
        return file_size / bytes_per_second

    else:
        # mp3 等格式尝试使用 mutagen
        try:
            from mutagen import File as MutagenFile

            audio = MutagenFile(audio_path)
            if audio and audio.info:
                return audio.info.length
        except ImportError:
            logger.debug("mutagen 未安装，无法获取非 WAV/PCM 音频时长")
        except Exception as e:
            logger.debug(f"mutagen 解析失败: {e}")

        return None


def read_audio_file(wav_path: str, default_sample_rate: int = DEFAULT_SAMPLE_RATE) -> tuple:
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

    logger.info(f"读取测试音频: {wav_path} ({file_size / 1024:.1f}KB)")

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
        return audio_bytes, sample_rate, wav_format

    else:
        # 其他格式（mp3, mp4, flac 等）直接二进制读取
        wav_format = "others"
        with open(wav_path, "rb") as f:
            audio_bytes = f.read()
        return audio_bytes, sample_rate, wav_format


# ============================================================
# 核心速度测试逻辑
# ============================================================


async def speed_test_single(
    host: str,
    port: int,
    audio_bytes: bytes,
    audio_name: str,
    wav_format: str = "pcm",
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    mode: str = "offline",
    use_ssl: bool = True,
    server_type: str = "auto",
    use_itn: bool = True,
    timeout: int = 300,
    chunk_size: Optional[List[int]] = None,
    chunk_interval: int = 10,
) -> Dict[str, Any]:
    """执行单次速度测试

    精确测量：
    - upload_time: 从发送第一个音频块到发送结束标志的时间
    - transcribe_time: 从发送结束标志到收到完整识别结果的时间
    - total_time: 整个过程的总耗时

    Args:
        host: 服务器地址
        port: 服务器端口
        audio_bytes: 音频数据字节
        audio_name: 音频文件名（用于协议消息）
        wav_format: 音频格式（pcm / others）
        sample_rate: 采样率
        mode: 识别模式
        use_ssl: 是否使用 SSL
        server_type: 服务端类型
        use_itn: 是否启用 ITN
        timeout: 超时时间（秒）
        chunk_size: 分块大小
        chunk_interval: 分块间隔

    Returns:
        单次测试结果字典
    """
    if chunk_size is None:
        chunk_size = [5, 10, 5]

    total_start = time.time()

    # 初始化协议适配器
    adapter = create_adapter(server_type)

    # 构建 WebSocket URI
    protocol = "wss" if use_ssl else "ws"
    uri = f"{protocol}://{host}:{port}"

    # 配置 SSL
    ssl_context = None
    if use_ssl:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

    # 使用协议适配层构建消息
    profile = MessageProfile(
        server_type=adapter.server_type,
        mode=RecognitionMode(mode),
        wav_name=audio_name,
        wav_format=wav_format,
        audio_fs=sample_rate,
        use_itn=use_itn,
        hotwords="",
        chunk_size=chunk_size,
        chunk_interval=chunk_interval,
    )

    result_text = ""
    upload_start = 0.0
    upload_end = 0.0
    transcribe_start = 0.0
    transcribe_end = 0.0

    # 建立连接
    async with connect_websocket(
        uri,
        subprotocols=["binary"],
        ping_interval=None,
        ssl=ssl_context,
        close_timeout=60,
        max_size=1024 * 1024 * 1024,
    ) as ws:
        logger.info(f"WebSocket 连接已建立: {uri}")

        # 发送初始化消息
        start_message = adapter.build_start_message(profile)
        await ws.send(start_message)

        # === 上传阶段计时 ===
        stride = 65536 if mode == "offline" else int(
            60 * chunk_size[1] / chunk_interval / 1000 * sample_rate * 2
        )
        total_chunks = max(1, (len(audio_bytes) - 1) // stride + 1)

        upload_start = time.time()

        for i in range(total_chunks):
            beg = i * stride
            end = min(beg + stride, len(audio_bytes))
            await ws.send(audio_bytes[beg:end])

            # 非离线模式需要控制发送速度
            if mode != "offline":
                sleep_duration = 60 * chunk_size[1] / chunk_interval / 1000
                await asyncio.sleep(sleep_duration)

        # 发送结束标志
        end_message = adapter.build_end_message()
        await ws.send(end_message)

        upload_end = time.time()
        transcribe_start = upload_end  # 上传结束即开始等待转写结果

        logger.info(
            f"音频上传完毕 ({total_chunks} 块), "
            f"上传耗时: {(upload_end - upload_start)*1000:.0f}ms"
        )

        # === 转写阶段计时 ===
        while True:
            try:
                raw_msg = await asyncio.wait_for(ws.recv(), timeout=timeout)
                parsed: ParsedResult = adapter.parse_result(raw_msg)

                if parsed.error:
                    logger.warning(f"消息解析错误: {parsed.error}")
                    continue

                if parsed.text:
                    result_text = parsed.text
                    logger.info(f"收到识别文本: {parsed.text[:80]}...")

                if parsed.is_complete:
                    transcribe_end = time.time()
                    if parsed.text:
                        result_text = parsed.text
                    logger.info(
                        f"识别完成 (is_complete=True), "
                        f"转写耗时: {(transcribe_end - transcribe_start)*1000:.0f}ms"
                    )
                    break

            except asyncio.TimeoutError:
                raise TimeoutError(f"等待识别结果超时（{timeout}秒）")

    total_end = time.time()

    # 计算指标
    upload_time_s = upload_end - upload_start
    transcribe_time_s = transcribe_end - transcribe_start
    total_time_s = total_end - total_start
    audio_size_mb = len(audio_bytes) / (1024 * 1024)

    # 上传速度（MB/s）
    upload_speed_mbps = audio_size_mb / upload_time_s if upload_time_s > 0 else 0

    return {
        "upload_time_ms": round(upload_time_s * 1000, 1),
        "transcribe_time_ms": round(transcribe_time_s * 1000, 1),
        "total_time_ms": round(total_time_s * 1000, 1),
        "audio_size_bytes": len(audio_bytes),
        "audio_size_mb": round(audio_size_mb, 3),
        "upload_speed_mbps": round(upload_speed_mbps, 3),
        "result_text_length": len(result_text),
        "result_text_preview": result_text[:100] if result_text else "",
    }


async def run_speed_test(
    host: str,
    port: int,
    audio_path: str,
    rounds: int,
    mode: str,
    use_ssl: bool,
    server_type: str,
    use_itn: bool,
    timeout: int,
) -> Dict[str, Any]:
    """执行完整的速度测试流程

    Args:
        host: 服务器地址
        port: 服务器端口
        audio_path: 音频文件路径
        rounds: 测试轮数
        mode: 识别模式
        use_ssl: 是否使用 SSL
        server_type: 服务端类型
        use_itn: 是否启用 ITN
        timeout: 超时时间

    Returns:
        完整测试结果字典
    """
    # === 准备音频数据 ===
    audio_bytes, sample_rate, wav_format = read_audio_file(audio_path)
    audio_name = os.path.basename(audio_path)
    audio_duration = get_audio_duration_seconds(audio_path)

    if audio_duration:
        logger.info(f"音频时长: {audio_duration:.1f}秒")
    else:
        logger.info("无法获取音频精确时长（转写倍速将不计算）")

    audio_size_mb = len(audio_bytes) / (1024 * 1024)
    logger.info(
        f"测试配置: 服务器={host}:{port}, 模式={mode}, "
        f"轮数={rounds}, 音频大小={audio_size_mb:.2f}MB"
    )

    # === 执行多轮测试 ===
    round_results: List[Dict[str, Any]] = []

    for i in range(rounds):
        round_num = i + 1
        logger.info(f"--- 第 {round_num}/{rounds} 轮测试开始 ---")

        try:
            result = await speed_test_single(
                host=host,
                port=port,
                audio_bytes=audio_bytes,
                audio_name=audio_name,
                wav_format=wav_format,
                sample_rate=sample_rate,
                mode=mode,
                use_ssl=use_ssl,
                server_type=server_type,
                use_itn=use_itn,
                timeout=timeout,
            )
            result["round"] = round_num
            result["success"] = True
            round_results.append(result)

            logger.info(
                f"第 {round_num} 轮完成: "
                f"上传 {result['upload_time_ms']:.0f}ms, "
                f"转写 {result['transcribe_time_ms']:.0f}ms, "
                f"上传速度 {result['upload_speed_mbps']:.2f} MB/s"
            )

        except Exception as e:
            logger.error(f"第 {round_num} 轮测试失败: {e}")
            round_results.append({
                "round": round_num,
                "success": False,
                "error": str(e),
            })

    # === 汇总统计 ===
    successful_rounds = [r for r in round_results if r.get("success")]
    failed_count = len(round_results) - len(successful_rounds)

    if not successful_rounds:
        return {
            "success": False,
            "error": "所有测试轮次均失败",
            "server": f"{host}:{port}",
            "rounds_total": rounds,
            "rounds_failed": failed_count,
            "round_details": round_results,
        }

    # 计算平均值
    avg_upload_time_ms = (
        sum(r["upload_time_ms"] for r in successful_rounds) / len(successful_rounds)
    )
    avg_transcribe_time_ms = (
        sum(r["transcribe_time_ms"] for r in successful_rounds) / len(successful_rounds)
    )
    avg_total_time_ms = (
        sum(r["total_time_ms"] for r in successful_rounds) / len(successful_rounds)
    )
    avg_upload_speed = (
        sum(r["upload_speed_mbps"] for r in successful_rounds) / len(successful_rounds)
    )

    # 转写倍速（如果有音频时长数据）
    transcribe_speed_x: Optional[float] = None
    if audio_duration and audio_duration > 0 and avg_transcribe_time_ms > 0:
        transcribe_speed_x = round(
            audio_duration / (avg_transcribe_time_ms / 1000), 2
        )

    # 构建最终结果
    summary: Dict[str, Any] = {
        "success": True,
        "server": f"{host}:{port}",
        "mode": mode,
        "audio_file": audio_path,
        "audio_size_mb": round(audio_size_mb, 3),
        "audio_duration_seconds": round(audio_duration, 1) if audio_duration else None,
        "rounds_total": rounds,
        "rounds_successful": len(successful_rounds),
        "rounds_failed": failed_count,
        "average": {
            "upload_time_ms": round(avg_upload_time_ms, 1),
            "transcribe_time_ms": round(avg_transcribe_time_ms, 1),
            "total_time_ms": round(avg_total_time_ms, 1),
            "upload_speed_mbps": round(avg_upload_speed, 3),
            "transcribe_speed_x": transcribe_speed_x,
        },
        "round_details": round_results,
    }

    # 生成可读的摘要文本
    speed_text = f"上传速度: {avg_upload_speed:.2f} MB/s"
    if transcribe_speed_x is not None:
        speed_text += f", 转写倍速: {transcribe_speed_x:.1f}x"
    summary["display_text"] = (
        f"✅ 速度测试完成 | {speed_text} | "
        f"成功 {len(successful_rounds)}/{rounds} 轮"
    )

    return summary


# ============================================================
# 命令行入口
# ============================================================


def resolve_default_audio(script_dir: str) -> Optional[str]:
    """解析默认测试音频文件路径

    仅查找 assets/test-for-speed.mp3。

    Args:
        script_dir: 脚本所在目录

    Returns:
        找到的音频文件路径，或 None
    """
    skill_root = os.path.dirname(script_dir)
    asset_path = os.path.join(skill_root, "assets", DEFAULT_ASSET_NAME)
    if os.path.exists(asset_path):
        return asset_path
    return None


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="FunASR 速度测试工具 — 测量上传速度和转写倍速",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 使用默认测试音频（assets/test-for-speed.mp3），默认 2 轮
  python funasr_speed_test.py --host 127.0.0.1 --port 10095

  # 指定自定义音频
  python funasr_speed_test.py --host 127.0.0.1 --port 10095 --audio test.wav

  # 指定测试轮数
  python funasr_speed_test.py --host 127.0.0.1 --port 10095 --rounds 5

  # 输出结果到文件
  python funasr_speed_test.py --host 127.0.0.1 --port 10095 --output result.json

  # 禁用 SSL
  python funasr_speed_test.py --host 127.0.0.1 --port 10095 --no-ssl
        """,
    )

    # 服务器配置
    parser.add_argument("--host", type=str, required=True, help="FunASR 服务器地址")
    parser.add_argument("--port", type=int, required=True, help="FunASR 服务器端口")

    ssl_group = parser.add_mutually_exclusive_group()
    ssl_group.add_argument(
        "--ssl", action="store_true", default=True, help="启用 SSL（默认）"
    )
    ssl_group.add_argument(
        "--no-ssl", action="store_false", dest="ssl", help="禁用 SSL"
    )

    # 音频配置
    parser.add_argument(
        "--audio", type=str, default=None,
        help="测试音频文件路径（默认使用 assets/test-for-speed.mp3）",
    )

    # 测试配置
    parser.add_argument(
        "--rounds", type=int, default=DEFAULT_ROUNDS,
        help=f"测试轮数（默认 {DEFAULT_ROUNDS}，多轮取平均值）",
    )
    parser.add_argument(
        "--mode", type=str, default="offline",
        choices=["offline", "online", "2pass"],
        help="识别模式（默认 offline）",
    )
    parser.add_argument(
        "--server-type", type=str, default="auto",
        choices=["auto", "legacy", "funasr_main"],
        help="服务端类型（默认 auto 自动探测）",
    )
    parser.add_argument("--no-itn", action="store_true", help="禁用 ITN")
    parser.add_argument(
        "--timeout", type=int, default=300,
        help="单次测试超时时间（秒，默认 300）",
    )

    # 输出配置
    parser.add_argument(
        "--output", type=str, default=None,
        help="输出结果到文件（默认 stdout）",
    )
    parser.add_argument(
        "--no-details", action="store_true",
        help="不输出每轮测试的详细数据",
    )

    # 调试选项
    parser.add_argument("--verbose", action="store_true", help="详细日志输出")
    parser.add_argument("--quiet", action="store_true", help="静默模式（仅输出结果）")

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
        _output_error(args, "缺少依赖: pip install websockets>=10.0", EXIT_ARG_ERROR)
        return

    # 确定音频源
    audio_path: Optional[str] = args.audio

    if audio_path is None:
        # 自动查找默认测试音频
        script_dir = os.path.dirname(os.path.abspath(__file__))
        audio_path = resolve_default_audio(script_dir)
        if audio_path is None:
            _output_error(
                args,
                "速度测试不可用: 默认测试音频 assets/test-for-speed.mp3 不存在。"
                "请联系 Skill 的作者沟通，或使用 --audio 参数指定测试音频文件。",
                EXIT_ARG_ERROR,
            )
            return
        logger.info(f"使用默认测试音频: {audio_path}")

    # 验证音频文件存在
    if not os.path.exists(audio_path):
        _output_error(args, f"音频文件不存在: {audio_path}", EXIT_ARG_ERROR)
        return

    # 验证音频文件可读且非空
    file_size = os.path.getsize(audio_path)
    if file_size == 0:
        _output_error(
            args,
            f"测试音频文件为空: {audio_path}。"
            "请联系 Skill 的作者沟通，或使用 --audio 参数指定有效的测试音频文件。",
            EXIT_ARG_ERROR,
        )
        return

    # 验证轮数参数
    if args.rounds < 1:
        _output_error(args, "测试轮数必须 >= 1", EXIT_ARG_ERROR)
        return

    server_str = f"{args.host}:{args.port}"
    logger.info(f"开始速度测试: 服务器={server_str}")

    # 执行测试
    try:
        result = asyncio.run(
            run_speed_test(
                host=args.host,
                port=args.port,
                audio_path=audio_path,
                rounds=args.rounds,
                mode=args.mode,
                use_ssl=args.ssl,
                server_type=args.server_type,
                use_itn=not args.no_itn,
                timeout=args.timeout,
            )
        )

        # 精简输出（如果指定了 --no-details）
        if args.no_details and "round_details" in result:
            del result["round_details"]

        output = json.dumps(result, ensure_ascii=False, indent=2)

        # 输出结果
        if args.output:
            os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
            with open(args.output, "w", encoding="utf-8") as f:
                f.write(output)
            logger.info(f"结果已写入: {args.output}")
        else:
            print(output)

        sys.exit(EXIT_SUCCESS if result.get("success") else EXIT_RUNTIME_ERROR)

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
    result: Dict[str, Any] = {
        "success": False,
        "error": error_msg,
        "error_code": exit_code,
        "server": f"{getattr(args, 'host', '')}:{getattr(args, 'port', '')}",
    }
    output = json.dumps(result, ensure_ascii=False, indent=2)

    if hasattr(args, "output") and args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
    else:
        print(output)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
