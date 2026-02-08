"""简单 FunASR WebSocket 客户端 V3

本模块演示如何通过 WebSocket 与 FunASR 服务进行语音识别交互，
支持基础参数（主机、端口、采样率、是否 ITN/SSL 等）与文件输入。

V3 版本核心改进：
1. 集成协议适配层，统一处理新旧服务端差异
2. 修复 is_final 语义差异导致的识别卡死问题
3. 支持 SenseVoice 相关参数

版本: 3.0
日期: 2026-01-26
"""

import argparse
import asyncio
import gc  # 用于手动触发垃圾回收
import json
import os
import ssl
import sys
import time
import traceback
from multiprocessing import Process
from typing import Any, Optional

# WebSocket 兼容层：处理不同 websockets 版本的参数差异
from websocket_compat import connect_websocket

# 解决中文显示乱码问题
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

# 协议适配层导入（延迟导入以支持独立运行）
try:
    from protocol_adapter import (
        MessageProfile,
        ParsedResult,
        ProtocolAdapter,
        RecognitionMode,
        ServerType,
        create_adapter,
    )
except ImportError:
    # 如果作为独立脚本运行，尝试从当前目录导入
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "protocol_adapter",
        os.path.join(os.path.dirname(__file__), "protocol_adapter.py"),
    )
    if spec and spec.loader:
        protocol_adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(protocol_adapter)
        MessageProfile = protocol_adapter.MessageProfile
        ParsedResult = protocol_adapter.ParsedResult
        ProtocolAdapter = protocol_adapter.ProtocolAdapter
        RecognitionMode = protocol_adapter.RecognitionMode
        ServerType = protocol_adapter.ServerType
        create_adapter = protocol_adapter.create_adapter
    else:
        raise ImportError("无法导入 protocol_adapter 模块")

# 命令行参数解析器
parser = argparse.ArgumentParser(description="FunASR WebSocket 客户端 V3")

# 服务器配置
parser.add_argument(
    "--host",
    type=str,
    default="localhost",
    required=False,
    help="服务器IP地址，如 localhost, 127.0.0.1",
)
parser.add_argument(
    "--port", type=int, default=10095, required=False, help="服务器端口"
)
parser.add_argument(
    "--ssl", type=int, default=1, help="是否启用SSL连接：1=启用, 0=禁用"
)
parser.add_argument(
    "--no-ssl", action="store_false", dest="ssl", default=None, help="禁用SSL"
)

# 音频配置
parser.add_argument("--audio_in", type=str, required=True, help="输入音频文件路径")
parser.add_argument("--audio_fs", type=int, default=16000, help="音频采样率")

# 识别配置
parser.add_argument(
    "--mode",
    type=str,
    default="offline",
    choices=["offline", "online", "2pass"],
    help="识别模式: offline, online, 2pass",
)
parser.add_argument(
    "--use_itn", type=int, default=1, help="是否启用ITN：1=启用, 0=禁用"
)
parser.add_argument(
    "--no-itn", action="store_false", dest="use_itn", default=None, help="禁用ITN"
)
parser.add_argument(
    "--hotword",
    type=str,
    default="",
    help="热词文件路径，每行一个热词（格式：词语 权重）",
)

# 2pass/online 模式配置
parser.add_argument("--chunk_size", type=str, default="5, 10, 5", help="分块大小")
parser.add_argument("--chunk_interval", type=int, default=10, help="分块间隔")

# V3 新增：服务端类型配置
parser.add_argument(
    "--server_type",
    type=str,
    default="auto",
    choices=["auto", "legacy", "funasr_main"],
    help="服务端类型: auto=自动探测, legacy=旧版, funasr_main=新版",
)

# V3 新增：SenseVoice 配置
parser.add_argument(
    "--svs_lang",
    type=str,
    default="auto",
    choices=["auto", "zh", "en", "ja", "ko", "yue"],
    help="SenseVoice 语种",
)
parser.add_argument(
    "--svs_itn", type=int, default=1, help="SenseVoice ITN：1=启用, 0=禁用"
)
parser.add_argument(
    "--enable_svs_params",
    type=int,
    default=0,
    help="是否启用 SenseVoice 参数：1=启用, 0=禁用",
)

# 输出配置
parser.add_argument("--output_dir", type=str, default=None, help="结果输出目录")

# 性能配置
parser.add_argument(
    "--send_without_sleep",
    action="store_true",
    default=True,
    help="发送音频时不等待（离线模式推荐）",
)
parser.add_argument("--thread_num", type=int, default=1, help="处理线程数")
parser.add_argument(
    "--transcribe_timeout",
    type=int,
    default=600,
    help="离线识别超时时间（秒）",
)
parser.add_argument("--words_max_print", type=int, default=10000, help="最大打印字数")

# 说明：
# - 作为模块被导入（例如 pytest 自测脚本导入）时，不应在 import 阶段解析命令行参数，
#   否则会误解析 pytest 的参数并触发 SystemExit。
# - CLI 模式下会在 main() 中初始化 args。
args: Any = None

# 全局变量
websocket = None
offline_msg_done = False
adapter: Optional[ProtocolAdapter] = None


def log(msg: str, log_type: str = "调试") -> None:
    """日志输出

    Args:
        msg: 日志消息
        log_type: 日志类型，可以是 '调试' 或 '指令'
    """
    print(f"[{log_type}] {msg}", flush=True)


def load_hotwords(hotword_path: str) -> str:
    """加载热词文件

    Args:
        hotword_path: 热词文件路径

    Returns:
        JSON格式的热词字符串
    """
    if not hotword_path or not hotword_path.strip():
        return ""

    if not os.path.exists(hotword_path):
        log(f"热词文件不存在: {hotword_path}")
        return ""

    fst_dict = {}
    try:
        with open(hotword_path, encoding="utf-8") as f:
            for line in f:
                words = line.strip().split()
                if len(words) < 2:
                    log(f"热词格式错误，跳过: {line.strip()}")
                    continue
                try:
                    fst_dict[" ".join(words[:-1])] = int(words[-1])
                except ValueError:
                    log(f"热词权重格式错误，跳过: {line.strip()}")
    except Exception as e:
        log(f"读取热词文件失败: {e}")
        return ""

    if fst_dict:
        hotword_msg = json.dumps(fst_dict, ensure_ascii=False)
        log(f"热词设置: {hotword_msg}")
        return hotword_msg

    return ""


async def record_from_scp(chunk_begin: int, chunk_size: int) -> None:
    """从音频文件读取数据并发送

    Args:
        chunk_begin: 起始块索引
        chunk_size: 块大小
    """
    global adapter

    # 获取文件列表
    if args.audio_in.endswith(".scp"):
        with open(args.audio_in, encoding="utf-8") as f_scp:
            wavs = f_scp.readlines()
    else:
        wavs = [args.audio_in]

    # 加载热词
    hotword_msg = load_hotwords(args.hotword)

    # 配置参数
    sample_rate = args.audio_fs
    wav_format = "pcm"
    use_itn = args.use_itn != 0

    if chunk_size > 0:
        wavs = wavs[chunk_begin : chunk_begin + chunk_size]

    log(f"处理文件数: {len(wavs)}")

    for wav in wavs:
        wav_splits = wav.strip().split()
        if len(wav_splits) > 1:
            # 来自 scp 文件，格式为 "name path"
            wav_name = wav_splits[0]
            wav_path = wav_splits[1]
        else:
            # 单个文件路径输入
            wav_path = wav_splits[0]
            wav_name = os.path.basename(wav_path)

        if not wav_path.strip():
            continue

        log(f"处理文件: {wav_path}")

        if not os.path.exists(wav_path):
            log(f"文件不存在: {wav_path}")
            continue

        file_size = os.path.getsize(wav_path)
        log(f"文件大小: {file_size / 1024 / 1024:.2f}MB")

        # 读取音频文件
        audio_bytes, sample_rate, wav_format = read_audio_file(wav_path, sample_rate)
        if audio_bytes is None:
            continue

        log(f"已读取音频文件，大小: {len(audio_bytes) / 1024 / 1024:.2f}MB")

        # 计算分块大小
        if args.mode != "offline":
            stride = int(
                60 * args.chunk_size[1] / args.chunk_interval / 1000 * sample_rate * 2
            )
        else:
            stride = 65536

        chunk_num = (len(audio_bytes) - 1) // stride + 1
        log(f"分块数: {chunk_num}, 每块大小: {stride / 1024:.2f}KB")

        # 使用协议适配层构建消息
        profile = MessageProfile(
            server_type=adapter.server_type if adapter else ServerType.AUTO,
            mode=RecognitionMode(args.mode),
            wav_name=wav_name,
            wav_format=wav_format,
            audio_fs=sample_rate,
            use_itn=use_itn,
            hotwords=hotword_msg,
            enable_svs_params=bool(args.enable_svs_params),
            svs_lang=args.svs_lang,
            svs_itn=bool(args.svs_itn),
            chunk_size=args.chunk_size,
            chunk_interval=args.chunk_interval,
        )

        message = adapter.build_start_message(profile) if adapter else ""
        log(f"发送WebSocket: {message}", log_type="指令")
        
        # [风险兜底] SVS 参数降级重试机制：
        # 如果发送带 svs_* 参数的消息失败，自动降级重试（不带 svs_* 参数）
        try:
            await websocket.send(message)
        except Exception as send_err:
            if profile.enable_svs_params:
                log(f"发送消息失败，尝试降级重试（不带SVS参数）: {send_err}")
                # 构建不带 SVS 参数的降级消息
                fallback_profile = MessageProfile(
                    server_type=adapter.server_type if adapter else ServerType.AUTO,
                    mode=RecognitionMode(args.mode),
                    wav_name=wav_name,
                    wav_format=wav_format,
                    audio_fs=sample_rate,
                    use_itn=use_itn,
                    hotwords=hotword_msg,
                    enable_svs_params=False,  # 禁用 SVS 参数
                    svs_lang="auto",
                    svs_itn=False,
                    chunk_size=args.chunk_size,
                    chunk_interval=args.chunk_interval,
                )
                fallback_message = adapter.build_start_message(fallback_profile) if adapter else ""
                log(f"发送降级WebSocket: {fallback_message}", log_type="指令")
                await websocket.send(fallback_message)
            else:
                raise  # 非 SVS 相关错误，直接抛出

        # 发送音频数据
        await send_audio_data(audio_bytes, stride, chunk_num)

    # 非离线模式等待一段时间
    if args.mode != "offline":
        await asyncio.sleep(2)

    # 离线模式需要等待结果接收完成
    if args.mode == "offline":
        log("等待服务器处理完成...")
        timeout = args.transcribe_timeout
        start_time = time.time()
        while not offline_msg_done:
            await asyncio.sleep(1)
            if time.time() - start_time > timeout:
                log(f"等待超时 ({timeout}秒)，强制结束")
                break

    log("处理完成，关闭连接")
    await websocket.close()


def read_audio_file(wav_path: str, default_sample_rate: int) -> tuple:
    """读取音频文件

    Args:
        wav_path: 音频文件路径
        default_sample_rate: 默认采样率

    Returns:
        (audio_bytes, sample_rate, wav_format) 元组
    """
    sample_rate = default_sample_rate
    wav_format = "pcm"

    try:
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
            log(f"WAV采样率: {sample_rate}")
            return audio_bytes, sample_rate, wav_format

        else:
            wav_format = "others"
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
            return audio_bytes, sample_rate, wav_format

    except Exception as e:
        log(f"读取音频文件失败: {e}")
        return None, sample_rate, wav_format


async def send_audio_data(audio_bytes: bytes, stride: int, chunk_num: int) -> None:
    """发送音频数据

    Args:
        audio_bytes: 音频字节数据
        stride: 每块大小
        chunk_num: 总块数
    """
    global adapter

    total_bytes_sent = 0
    last_logged_percent = -1

    for i in range(chunk_num):
        beg = i * stride
        end = min(beg + stride, len(audio_bytes))
        data = audio_bytes[beg:end]
        await websocket.send(data)
        total_bytes_sent += len(data)

        # 计算并打印上传进度
        current_progress_percent = int(total_bytes_sent / len(audio_bytes) * 100)
        if (
            current_progress_percent % 2 == 0
            and current_progress_percent != last_logged_percent
        ):
            print(f"上传进度: {current_progress_percent}%", flush=True)
            last_logged_percent = current_progress_percent

        # 最后一块发送结束标志
        if i == chunk_num - 1:
            end_message = (
                adapter.build_end_message()
                if adapter
                else json.dumps({"is_speaking": False})
            )
            log(f"发送WebSocket: {end_message}", log_type="指令")
            await websocket.send(end_message)

        # 发送间隔控制
        if not args.send_without_sleep and args.mode != "offline":
            sleep_duration = 60 * args.chunk_size[1] / args.chunk_interval / 1000
            await asyncio.sleep(sleep_duration)


async def message(id: str) -> None:
    """接收服务器返回的消息并处理

    Args:
        id: 消息标识符
    """
    global offline_msg_done, adapter

    # 初始化输出文件
    ibest_writer = None
    json_file_path = None
    all_results_for_json = []

    if args.output_dir is not None:
        os.makedirs(args.output_dir, exist_ok=True)
        ibest_writer = open(
            os.path.join(args.output_dir, f"text.{id}"), "a", encoding="utf-8"
        )
        base_name = os.path.splitext(os.path.basename(args.audio_in))[0]
        json_file_path = os.path.join(args.output_dir, f"{base_name}.{id}.json")

    # 统计变量
    first_result_time = None
    total_bytes_received = 0
    total_text_length = 0
    message_count = 0
    start_recv_time = time.time()

    try:
        while True:
            try:
                log("等待接收消息...")
                raw_msg = await asyncio.wait_for(websocket.recv(), timeout=600)

                # 统计接收字节数和消息数
                message_count += 1
                msg_size = len(raw_msg) if isinstance(raw_msg, (str, bytes)) else 0
                total_bytes_received += msg_size
                log(
                    f"已接收消息 #{message_count}，大小: {msg_size / 1024:.2f}KB，"
                    f"累计: {total_bytes_received / 1024 / 1024:.2f}MB"
                )

                # 🔴 V3 核心改进：使用协议适配层解析消息
                result: ParsedResult = (
                    adapter.parse_result(raw_msg)
                    if adapter
                    else ParsedResult(error="适配器未初始化")
                )

                if result.error:
                    log(f"消息解析错误: {result.error}")
                    continue

                # 记录 is_final 语义（用于推断服务端类型）
                if adapter and result.mode == "offline":
                    adapter.record_is_final_semantics(result.is_final, result.mode)

                # 手动垃圾回收以释放内存
                gc.collect()

                # 记录首次收到结果的时间
                if result.text and first_result_time is None:
                    first_result_time = time.time()
                    log(f"收到首个识别结果，消息序号: {message_count}")

                # 累计文本长度
                if result.text:
                    total_text_length += len(result.text)

                # 写入结果文件
                write_result_to_file(
                    result, ibest_writer, json_file_path, all_results_for_json
                )

                # 打印识别结果
                print_recognition_result(result)

                # 🔴 V3 核心改进：使用 is_complete 而非 is_final 判断结束
                if result.is_complete:
                    log(
                        f"收到完整结果标志 (is_complete=True, is_final={result.is_final})，"
                        f"结束消息循环"
                    )
                    offline_msg_done = True
                    break

            except asyncio.TimeoutError:
                log("消息接收超时")
                offline_msg_done = True
                break
            except Exception as e:
                if "ConnectionClosed" in str(type(e)):
                    log("WebSocket 连接已关闭")
                else:
                    log(f"处理消息时发生错误: {e}\n{traceback.format_exc()}")
                offline_msg_done = True
                break

    finally:
        # 输出统计信息
        total_time = time.time() - start_recv_time
        log("=" * 60)
        log("识别结果统计:")
        log(f"  总接收消息数: {message_count}")
        log(
            f"  总接收字节数: {total_bytes_received:,} bytes "
            f"({total_bytes_received / 1024 / 1024:.2f} MB)"
        )
        log(f"  总文本长度: {total_text_length:,} 字符")
        log(f"  接收总耗时: {total_time:.2f} 秒")
        if first_result_time:
            time_to_first_result = first_result_time - start_recv_time
            log(f"  首个结果耗时: {time_to_first_result:.2f} 秒")
        log("=" * 60)

        # 关闭文件
        if ibest_writer is not None:
            ibest_writer.close()
            log("文本结果文件已关闭")

        if json_file_path and all_results_for_json:
            try:
                with open(json_file_path, "w", encoding="utf-8") as f:
                    json.dump(all_results_for_json, f, ensure_ascii=False, indent=2)
                log(f"JSON结果文件已写入: {json_file_path}")
            except Exception as e:
                log(f"写入JSON文件出错: {e}")


def write_result_to_file(
    result: ParsedResult,
    ibest_writer,
    json_file_path: str,
    all_results_for_json: list,
) -> None:
    """将识别结果写入文件

    Args:
        result: 解析后的结果
        ibest_writer: 文本结果文件句柄
        json_file_path: JSON文件路径
        all_results_for_json: JSON结果列表
    """
    if not result.text and not result.timestamp:
        return

    # 写入文本结果
    if ibest_writer is not None and result.text:
        if result.timestamp:
            ibest_writer.write(
                f"{result.wav_name}\t"
                f"{json.dumps(result.timestamp, ensure_ascii=False)}\t"
                f"{result.text}\n"
            )
        else:
            ibest_writer.write(f"{result.wav_name}\t{result.text}\n")
        ibest_writer.flush()

    # 收集JSON结果
    if json_file_path:
        # 过滤掉可能导致JSON文件过大的字段
        if result.raw and len(json.dumps(result.raw)) > 1000000:
            log("消息太大，只保留关键字段")
            filtered_result = {
                "wav_name": result.wav_name,
                "text": result.text,
                "is_final": result.is_final,
                "is_complete": result.is_complete,
            }
            if result.timestamp:
                filtered_result["timestamp"] = result.timestamp
            all_results_for_json.append(filtered_result)
        elif result.raw:
            all_results_for_json.append(result.raw)


def print_recognition_result(result: ParsedResult) -> None:
    """打印识别结果

    Args:
        result: 解析后的结果
    """
    if not result.text:
        return

    current_output = ""

    if args.mode == "2pass":
        if result.mode == "2pass-offline":
            current_output = f"[2pass离线] {result.text}"
        elif result.mode == "2pass-online":
            current_output = f"[2pass在线] {result.text}"
        else:
            current_output = result.text
    else:
        current_output = result.text

    if current_output:
        print(f"识别结果: {current_output}", flush=True)


async def ws_client(id: int, chunk_begin: int, chunk_size: int) -> bool:
    """创建WebSocket客户端并开始通信

    Args:
        id: 客户端标识符
        chunk_begin: 起始块索引
        chunk_size: 块大小

    Returns:
        布尔值表示整体是否成功
    """
    global offline_msg_done, adapter

    # 初始化协议适配器
    adapter = create_adapter(args.server_type)
    log(f"协议适配器初始化完成，服务端类型: {adapter.server_type.value}")

    # 成功标志
    overall_success = True

    if args.audio_in is None:
        chunk_begin = 0
        chunk_size = 1

    for i in range(chunk_begin, chunk_begin + chunk_size):
        offline_msg_done = False

        # 创建WebSocket连接
        if args.ssl == 1:
            log("使用SSL连接")
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            uri = f"wss://{args.host}:{args.port}"
        else:
            log("使用非SSL连接")
            uri = f"ws://{args.host}:{args.port}"
            ssl_context = None

        log(f"连接到 {uri}")

        try:
            # websockets 库
            import websockets

            async with connect_websocket(
                uri,
                subprotocols=["binary"],
                ping_interval=None,
                ssl=ssl_context,
                close_timeout=60,
                max_size=1024 * 1024 * 1024,  # 1GB的最大消息大小
            ) as ws_connection:
                global websocket
                websocket = ws_connection
                log("连接已建立")

                # 创建并启动任务
                task1 = asyncio.create_task(record_from_scp(i, 1))
                task2 = asyncio.create_task(message(f"{id}_{i}"))

                try:
                    await asyncio.gather(task1, task2)
                except Exception as e:
                    if "ConnectionClosedOK" in str(type(e)):
                        log("连接已正常关闭，可能是处理完成")
                    else:
                        overall_success = False
                        log(f"任务执行异常: {e}")
                        traceback.print_exc()

        except Exception as e:
            overall_success = False
            log(f"WebSocket连接异常: {e}")
            traceback.print_exc()

    return overall_success


def one_thread(id: int, chunk_begin: int, chunk_size: int) -> None:
    """每个线程要执行的主函数

    Args:
        id: 线程标识符
        chunk_begin: 起始块索引
        chunk_size: 块大小
    """
    # Windows spawn 模式下，子进程会重新导入模块，此时 args 为 None
    # 需要在子进程中重新解析命令行参数（子进程继承父进程的 sys.argv）
    global args
    if args is None:
        args = parser.parse_args()
        args.chunk_size = [int(x.strip()) for x in args.chunk_size.split(",")]

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(ws_client(id, chunk_begin, chunk_size))
    sys.exit(0 if success else 1)


def main() -> None:
    """主函数，解析参数并启动处理线程"""
    # 延迟导入websockets，并提供友好的错误提示
    try:
        import websockets  # noqa: F401
    except ImportError as e:
        print("=" * 60, file=sys.stderr)
        print("错误: 缺少必需的依赖库 'websockets'", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        print("", file=sys.stderr)
        print("请运行以下命令安装依赖:", file=sys.stderr)
        print("  pip install websockets>=10.0", file=sys.stderr)
        print("", file=sys.stderr)
        print("或者使用pipenv安装:", file=sys.stderr)
        print("  pipenv install websockets>=10.0", file=sys.stderr)
        print("", file=sys.stderr)
        print(f"详细错误信息: {e}", file=sys.stderr)
        print("=" * 60, file=sys.stderr)
        sys.exit(1)

    # CLI 模式下解析参数（避免 import 阶段解析导致的副作用）
    global args
    args = parser.parse_args()
    # 转换 chunk_size 为整数列表
    args.chunk_size = [int(x.strip()) for x in args.chunk_size.split(",")]

    print(f"参数: {args}")
    print(f"V3 新增参数: server_type={args.server_type}, svs_lang={args.svs_lang}")

    # 计算每个进程处理的文件数量
    if args.audio_in.endswith(".scp"):
        with open(args.audio_in, encoding="utf-8") as f_scp:
            wavs = f_scp.readlines()
    else:
        wavs = [args.audio_in]

    total_len = len(wavs)
    if total_len >= args.thread_num:
        chunk_size = int(total_len / args.thread_num)
        remain_wavs = total_len - chunk_size * args.thread_num
    else:
        chunk_size = 1
        remain_wavs = 0

    process_list = []
    chunk_begin = 0

    # 创建处理进程
    for i in range(args.thread_num):
        now_chunk_size = chunk_size
        if remain_wavs > 0:
            now_chunk_size = chunk_size + 1
            remain_wavs = remain_wavs - 1

        p = Process(target=one_thread, args=(i, chunk_begin, now_chunk_size))
        chunk_begin = chunk_begin + now_chunk_size
        p.start()
        process_list.append(p)

    # 等待所有进程完成
    for p in process_list:
        p.join()

    # 汇总所有子进程退出码
    exit_codes = [p.exitcode for p in process_list]
    overall_success = all(code == 0 for code in exit_codes)

    print("处理完成")
    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
