"""简单 FunASR WebSocket 客户端示例。

本模块演示如何通过 WebSocket 与 FunASR 服务进行语音识别交互，
支持基础参数（主机、端口、采样率、是否 ITN/SSL 等）与文件输入。
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

# websockets库改为延迟导入，避免无依赖环境下导入失败
# import websockets 移到main()函数内

# 解决中文显示乱码问题
if sys.platform == "win32":
    import io

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8")

parser = argparse.ArgumentParser()
parser.add_argument(
    "--host",
    type=str,
    default="localhost",
    required=False,
    help="host ip, localhost, 0.0.0.0",
)
parser.add_argument(
    "--port", type=int, default=10095, required=False, help="grpc server port"
)
parser.add_argument("--chunk_size", type=str, default="5, 10, 5", help="chunk")
parser.add_argument("--chunk_interval", type=int, default=10, help="chunk")
parser.add_argument(
    "--hotword",
    type=str,
    default="",
    help="hotword file path, one hotword perline (e.g.:阿里巴巴 20)",
)
parser.add_argument("--audio_in", type=str, required=True, help="audio_in")
parser.add_argument("--audio_fs", type=int, default=16000, help="audio_fs")
parser.add_argument(
    "--send_without_sleep",
    action="store_true",
    default=True,
    help="if audio_in is set, send_without_sleep",
)
parser.add_argument("--thread_num", type=int, default=1, help="thread_num")
parser.add_argument("--words_max_print", type=int, default=10000, help="chunk")
parser.add_argument("--output_dir", type=str, default=None, help="output_dir")
parser.add_argument(
    "--ssl", type=int, default=1, help="1 for ssl connect, 0 for no ssl"
)
parser.add_argument(
    "--use_itn", type=int, default=1, help="1 for using itn, 0 for not itn"
)
parser.add_argument(
    "--no-itn", action="store_false", dest="use_itn", default=None, help="disable ITN"
)
parser.add_argument(
    "--no-ssl", action="store_false", dest="ssl", default=None, help="disable SSL"
)
parser.add_argument(
    "--mode", type=str, default="offline", help="offline, online, 2pass"
)
parser.add_argument(
    "--transcribe_timeout",
    type=int,
    default=600,
    help="transcribe timeout in seconds for offline mode",
)

# 初始化全局变量
args = parser.parse_args()
# 在全局范围内转换chunk_size为整数列表
args.chunk_size = [int(x) for x in args.chunk_size.split(",")]
websocket = None
offline_msg_done = False


def log(msg, type="调试"):
    """日志输出, type可以是 '调试' 或 '指令'"""
    print(f"[{type}] {msg}", flush=True)


async def record_from_scp(chunk_begin, chunk_size):
    """从音频文件读取数据并发送"""
    if args.audio_in.endswith(".scp"):
        f_scp = open(args.audio_in)
        wavs = f_scp.readlines()
    else:
        wavs = [args.audio_in]

    # 热词处理
    fst_dict = {}
    hotword_msg = ""
    if args.hotword.strip() != "":
        f_scp = open(args.hotword)
        hot_lines = f_scp.readlines()
        for line in hot_lines:
            words = line.strip().split(" ")
            if len(words) < 2:
                print("Please checkout format of hotwords")
                continue
            try:
                fst_dict[" ".join(words[:-1])] = int(words[-1])
            except ValueError:
                print("Please checkout format of hotwords")
        hotword_msg = json.dumps(fst_dict)
        log(f"热词设置: {hotword_msg}")

    sample_rate = args.audio_fs
    wav_format = "pcm"
    use_itn = True
    if args.use_itn == 0:
        use_itn = False

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
            wav_name = os.path.basename(wav_path)  # 使用实际文件名

        if not len(wav_path.strip()) > 0:
            continue

        log(f"处理文件: {wav_path}")
        file_size = os.path.getsize(wav_path)
        log(f"文件大小: {file_size/1024/1024:.2f}MB")

        # 读取音频文件
        if wav_path.endswith(".pcm"):
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
                log(f"已读取PCM文件，大小: {len(audio_bytes)/1024/1024:.2f}MB")
        elif wav_path.endswith(".wav"):
            import wave

            with wave.open(wav_path, "rb") as wav_file:
                sample_rate = wav_file.getframerate()
                frames = wav_file.readframes(wav_file.getnframes())
                audio_bytes = bytes(frames)
                log(
                    f"已读取WAV文件，采样率: {sample_rate}, "
                    f"大小: {len(audio_bytes)/1024/1024:.2f}MB"
                )
        else:
            wav_format = "others"
            with open(wav_path, "rb") as f:
                audio_bytes = f.read()
                log(f"已读取其他格式文件，大小: {len(audio_bytes)/1024/1024:.2f}MB")

        # 计算每个音频块的大小 (仅在非 offline 模式下实际使用)
        # offline 模式给一个默认较大的stride
        if args.mode != "offline":
            stride = int(
                60 * args.chunk_size[1] / args.chunk_interval / 1000 * sample_rate * 2
            )
        else:
            stride = 65536
        chunk_num = (len(audio_bytes) - 1) // stride + 1
        log(
            f"分块数: {chunk_num}, 每块大小: {stride/1024:.2f}KB "
            f"(注：offline模式下stride值仅用于分块，不影响协议)"
        )

        # --- 构造初始化消息 (区分模式) ---
        message_dict = {
            "mode": args.mode,
            "audio_fs": sample_rate,
            "wav_name": wav_name,
            "wav_format": wav_format,
            "is_speaking": True,
            "hotwords": hotword_msg,
            "itn": use_itn,
        }
        # 只有 online 或 2pass 模式才添加 chunk_size 和 chunk_interval
        if args.mode != "offline":
            message_dict["chunk_size"] = args.chunk_size
            message_dict["chunk_interval"] = args.chunk_interval

        message = json.dumps(message_dict)
        # --- 结束构造初始化消息 ---

        log(f"发送WebSocket: {message}", type="指令")
        await websocket.send(message)

        # 发送音频数据
        is_speaking = True
        total_bytes_sent = 0  # Track sent bytes for progress calculation
        last_logged_percent = -1  # 初始化上次记录的百分比
        for i in range(chunk_num):
            beg = i * stride
            end = min(beg + stride, len(audio_bytes))
            data = audio_bytes[beg:end]
            await websocket.send(data)
            total_bytes_sent += len(data)

            # 计算并打印整数上传进度
            current_progress_percent = int(total_bytes_sent / len(audio_bytes) * 100)
            # 只有当进度是2的倍数且与上次不同时才打印
            if (
                current_progress_percent % 2 == 0
                and current_progress_percent != last_logged_percent
            ):
                print(
                    f"上传进度: {current_progress_percent}%", flush=True
                )  # 直接打印到stdout，并刷新
                last_logged_percent = current_progress_percent  # 更新上次记录的百分比

            # 最后一块发送结束标志
            if i == chunk_num - 1:
                is_speaking = False
                message = json.dumps({"is_speaking": is_speaking})
                log(f"发送WebSocket: {message}", type="指令")
                await websocket.send(message)

            # 发送间隔控制
            if not args.send_without_sleep and args.mode != "offline":
                sleep_duration = 60 * args.chunk_size[1] / args.chunk_interval / 1000
                await asyncio.sleep(sleep_duration)

    if not args.mode == "offline":
        await asyncio.sleep(2)

    # 离线模式需要等待结果接收完成
    if args.mode == "offline":
        log("等待服务器处理完成...")
        timeout = args.transcribe_timeout  # 使用动态超时时间
        start_time = time.time()
        while not offline_msg_done:
            await asyncio.sleep(1)
            if time.time() - start_time > timeout:
                log(f"等待超时 ({timeout}秒)，强制结束")
                break

    log("处理完成，关闭连接")
    await websocket.close()


async def message(id):
    """接收服务器返回的消息并处理"""
    global offline_msg_done
    if args.output_dir is not None:
        os.makedirs(args.output_dir, exist_ok=True)
        ibest_writer = open(
            os.path.join(args.output_dir, f"text.{id}"), "a", encoding="utf-8"
        )
        base_name = os.path.splitext(os.path.basename(args.audio_in))[0]
        json_file_path = os.path.join(args.output_dir, f"{base_name}.{id}.json")
        json_writer = open(json_file_path, "w", encoding="utf-8")
        all_results_for_json = []  # 用于存储所有JSON结果以便最后写入
    else:
        ibest_writer = None
        json_writer = None
        json_file_path = None
    
    # 统计变量
    first_result_time = None
    total_bytes_received = 0
    total_text_length = 0
    message_count = 0
    start_recv_time = time.time()

    try:
        while True:
            # 设置超时
            try:
                log("等待接收消息...")
                meg = await asyncio.wait_for(websocket.recv(), timeout=600)
                
                # 统计接收字节数和消息数
                message_count += 1
                msg_size = len(meg) if isinstance(meg, (str, bytes)) else 0
                total_bytes_received += msg_size
                log(f"已接收消息 #{message_count}，大小: {msg_size/1024/1024:.2f}MB，累计: {total_bytes_received/1024/1024:.2f}MB")

                try:
                    # 尝试解析JSON，设置更大的递归限制
                    old_limit = sys.getrecursionlimit()
                    sys.setrecursionlimit(10000)  # 增加递归限制
                    meg = json.loads(meg)
                    sys.setrecursionlimit(old_limit)  # 恢复原来的递归限制

                    # 手动垃圾回收以释放内存
                    gc.collect()

                    wav_name = meg.get("wav_name", "demo")
                    text = meg.get("text", "")
                    timestamp = ""
                    
                    # 处理 stamp_sents 格式（分段时间戳结果）
                    if "stamp_sents" in meg and not text:
                        # 从 stamp_sents 中提取并拼接所有文本片段
                        stamp_sents = meg.get("stamp_sents", [])
                        text_segments = []
                        for sent in stamp_sents:
                            if isinstance(sent, dict) and "text_seg" in sent:
                                text_segments.append(sent["text_seg"])
                        text = "".join(text_segments)
                        log(f"从 stamp_sents 提取文本，共 {len(stamp_sents)} 个片段，总长度 {len(text)} 字符")
                    
                    # 记录首次收到结果的时间
                    if text and first_result_time is None:
                        first_result_time = time.time()
                        log(f"收到首个识别结果，消息序号: {message_count}")
                    
                    # 累计文本长度
                    if text:
                        total_text_length += len(text)
                    
                    # 判断识别是否完成：
                    # 1) 优先检查 is_final 标志（新版服务器协议）
                    # 2) 离线模式下，收到非空文本即视为完成（兼容未设置 is_final 的服务器）
                    is_final = meg.get("is_final", False)
                    if is_final:
                        log(f"收到最终结果标志 (is_final=True)，文本长度: {len(text)}")
                        offline_msg_done = True
                    elif args.mode == "offline" and text.strip():
                        log(f"离线模式收到非空文本，识别完成，文本长度: {len(text)}")
                        offline_msg_done = True
                    
                    if "timestamp" in meg:
                        timestamp = meg["timestamp"]

                    # 写入结果文件
                    if ibest_writer is not None and text != "":
                        if len(timestamp) > 0:
                            ibest_writer.write(
                                wav_name
                                + "\t"
                                + json.dumps(timestamp)
                                + "\t"
                                + text
                                + "\n"
                            )
                        else:
                            ibest_writer.write(wav_name + "\t" + text + "\n")
                        ibest_writer.flush()  # 确保立即写入

                    # 增量写入JSON结果（改进：立即写入而不是累积）
                    if json_file_path is not None and (text or timestamp):
                        # 过滤掉可能导致JSON文件过大的字段
                        if len(meg) > 1000000:  # 如果消息太大
                            log("消息太大，只保留关键字段")
                            filtered_meg = {
                                "wav_name": wav_name,
                                "text": text,
                                "is_final": meg.get("is_final", False),
                            }
                            if "timestamp" in meg:
                                filtered_meg["timestamp"] = timestamp
                            all_results_for_json.append(filtered_meg)
                        else:
                            all_results_for_json.append(meg)
                        
                        # 增量写入：立即写入JSON文件
                        try:
                            with open(json_file_path, "w", encoding="utf-8") as f:
                                json.dump(all_results_for_json, f, ensure_ascii=False, indent=2)
                            log(f"增量写入JSON结果，当前累计 {len(all_results_for_json)} 条消息")
                        except Exception as e:
                            log(f"增量写入JSON失败: {e}")

                    # -- 修改：直接打印当前收到的文本 --
                    current_output = ""
                    if args.mode == "2pass":
                        if "text_2pass_offline" in meg:
                            current_output = f"[2pass离线] {text}"
                        elif "text_2pass_online" in meg:
                            current_output = f"[2pass在线] {text}"
                        elif text:  # 普通中间结果
                            current_output = text
                    elif text:  # 非2pass模式直接使用text
                        current_output = text

                    if current_output:
                        # 直接打印当前结果到stdout
                        print(f"识别结果: {current_output}", flush=True)

                except json.JSONDecodeError as e:
                    log(f"JSON解析错误: {e}")
                    if len(meg) > 1000:
                        log(f"数据预览: {meg[:500]}...{meg[-500:]}")
                    else:
                        log(f"数据全文: {meg}")
                except Exception as e:
                    log(f"消息处理错误: {e}\n{traceback.format_exc()}")

                # 检查是否是最后的消息
                if offline_msg_done:
                    log("收到结束标志或完整结果，退出消息循环")
                    break
            except asyncio.TimeoutError:
                log("消息接收超时")
                offline_msg_done = True  # 超时也认为结束
                break
            except websockets.exceptions.ConnectionClosed:
                log("WebSocket 连接已关闭")
                offline_msg_done = True  # 连接关闭也认为结束
                break
            except Exception as e:
                log(f"处理消息时发生错误: {e}\n{traceback.format_exc()}")
                offline_msg_done = True
                break
    finally:
        # 输出统计信息
        total_time = time.time() - start_recv_time
        log("=" * 60)
        log("识别结果统计:")
        log(f"  总接收消息数: {message_count}")
        log(f"  总接收字节数: {total_bytes_received:,} bytes ({total_bytes_received/1024/1024:.2f} MB)")
        log(f"  总文本长度: {total_text_length:,} 字符")
        log(f"  接收总耗时: {total_time:.2f} 秒")
        if first_result_time:
            time_to_first_result = first_result_time - start_recv_time
            log(f"  首个结果耗时: {time_to_first_result:.2f} 秒")
        log("=" * 60)
        
        if ibest_writer is not None:
            ibest_writer.close()
            log("文本结果文件已关闭")
        if json_writer is not None:
            # 写入完整的JSON列表
            try:
                log(f"尝试写入JSON结果文件，包含 {len(all_results_for_json)} 条记录")
                json.dump(
                    all_results_for_json, json_writer, ensure_ascii=False, indent=2
                )
                log(f"JSON结果文件已写入并关闭: {json_file_path}")
            except Exception as e:
                log(f"写入JSON文件出错: {e}")
            finally:
                json_writer.close()


async def ws_client(id, chunk_begin, chunk_size):
    """创建WebSocket客户端并开始通信。

    返回布尔值表示整体是否成功：True 表示所有任务都成功完成；False 表示期间发生过异常。
    """
    global offline_msg_done

    # 成功标志，任一循环或连接出错则置为 False
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
            # 设置更大的max_size参数以支持更大的消息
            # 默认是1MB，这里设置为1GB
            async with websockets.connect(
                uri,
                subprotocols=["binary"],
                ping_interval=None,
                ssl=ssl_context,
                close_timeout=60,
                proxy=None,
                max_size=1024 * 1024 * 1024,  # 1GB的最大消息大小
            ) as ws_connection:
                global websocket
                websocket = ws_connection
                log("连接已建立")

                # 创建并启动任务
                task1 = asyncio.create_task(record_from_scp(i, 1))
                task2 = asyncio.create_task(message(f"{id}_{i}"))

                try:
                    # 等待所有任务完成
                    await asyncio.gather(task1, task2)
                except websockets.exceptions.ConnectionClosedOK:
                    # 连接正常关闭，可能是服务器处理完成
                    log("连接已正常关闭，可能是处理完成")
                except Exception as e:
                    # 任务过程中出现异常
                    overall_success = False
                    log(f"任务执行异常: {e}")
                    traceback.print_exc()

        except Exception as e:
            overall_success = False
            log(f"WebSocket连接异常: {e}")
            traceback.print_exc()

    return overall_success


def one_thread(id, chunk_begin, chunk_size):
    """每个线程要执行的主函数"""
    # 子进程中也需要导入websockets（跨平台兼容性考虑）
    try:
        global websockets
        import websockets
    except ImportError as e:
        print(f"子进程导入错误: {e}", file=sys.stderr)
        sys.exit(1)
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    success = loop.run_until_complete(ws_client(id, chunk_begin, chunk_size))
    # 根据结果返回合适的退出码（供父进程统计）
    sys.exit(0 if success else 1)


def main():
    """主函数，解析参数并启动处理线程"""
    # 延迟导入websockets，并提供友好的错误提示
    try:
        global websockets
        import websockets
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
    
    # 不再需要重复初始化args和转换chunk_size
    # args = parser.parse_args()
    # args.chunk_size = [int(x) for x in args.chunk_size.split(",")]
    print(f"参数: {args}")

    # 计算每个进程处理的文件数量
    if args.audio_in.endswith(".scp"):
        with open(args.audio_in) as f_scp:
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

    # 汇总所有子进程退出码，任一非零则整体失败
    exit_codes = [p.exitcode for p in process_list]
    overall_success = all(code == 0 for code in exit_codes)

    print("处理完成")
    sys.exit(0 if overall_success else 1)


if __name__ == "__main__":
    main()
