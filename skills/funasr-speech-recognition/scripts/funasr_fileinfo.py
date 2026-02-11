#!/usr/bin/env python3
"""FunASR 文件信息查询工具 — Agent 友好版

查询音频/视频文件的元数据（格式、时长、采样率、声道数等），
帮助 Agent 在转写前了解文件属性、预估处理时间。

设计原则：
- 默认 JSON 输出到 stdout（Agent 可直接解析）
- 日志输出到 stderr（不干扰结构化结果）
- 稳定退出码：0=全部成功, 1=参数错误, 2=部分文件解析失败
- 零网络依赖（纯本地文件操作）

支持的格式：
- WAV：原生解析（标准库 wave 模块），精确时长
- PCM：按约定参数估算时长（默认 16kHz, 16bit, mono）
- MP3/MP4/M4A/FLAC/OGG/AAC/WMA 等：通过 mutagen 库获取元数据
- 其他格式：仅返回文件大小，时长标记为 null

用法示例：
  python funasr_fileinfo.py input.wav
  python funasr_fileinfo.py file1.wav file2.mp4 file3.m4a
  python funasr_fileinfo.py --audio file1.wav --audio file2.mp3
"""

import argparse
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

# ---------- 退出码定义 ----------
EXIT_SUCCESS = 0
EXIT_ARG_ERROR = 1
EXIT_PARTIAL_FAIL = 2

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("funasr_fileinfo")

# ---------- 常量 ----------
# PCM 默认参数（16kHz, 16bit, mono）
DEFAULT_PCM_SAMPLE_RATE = 16000
DEFAULT_PCM_SAMPLE_WIDTH = 2  # 16 位 = 2 字节
DEFAULT_PCM_CHANNELS = 1

# FunASR 已知支持的音频格式（服务端通过 FFmpeg 解码）
KNOWN_AUDIO_EXTENSIONS = {
    ".wav", ".pcm", ".mp3", ".flac", ".ogg", ".aac", ".wma",
    ".m4a", ".opus", ".amr", ".aiff", ".aif",
}
# FunASR 已知支持的视频格式（服务端提取音轨后识别）
KNOWN_VIDEO_EXTENSIONS = {
    ".mp4", ".mkv", ".avi", ".mov", ".webm", ".flv", ".wmv",
    ".ts", ".m4v",
}
ALL_SUPPORTED_EXTENSIONS = KNOWN_AUDIO_EXTENSIONS | KNOWN_VIDEO_EXTENSIONS


# ============================================================
# 文件信息解析
# ============================================================


def _format_duration(seconds: float) -> str:
    """将秒数格式化为人类可读的时长字符串

    Args:
        seconds: 时长（秒）

    Returns:
        格式化字符串，如 "2分30秒"、"1小时5分12秒"
    """
    if seconds < 0:
        return "未知"

    total_secs = int(seconds)
    hours = total_secs // 3600
    minutes = (total_secs % 3600) // 60
    secs = total_secs % 60

    parts = []
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分")
    parts.append(f"{secs}秒")

    return "".join(parts)


def _format_file_size(size_bytes: int) -> str:
    """将字节数格式化为人类可读的大小字符串

    Args:
        size_bytes: 文件大小（字节）

    Returns:
        格式化字符串，如 "3.8MB"、"512KB"
    """
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f}GB"


def _detect_media_type(ext: str) -> str:
    """检测媒体类型

    Args:
        ext: 小写文件扩展名（含点号，如 ".wav"）

    Returns:
        "audio" / "video" / "unknown"
    """
    if ext in KNOWN_AUDIO_EXTENSIONS:
        return "audio"
    elif ext in KNOWN_VIDEO_EXTENSIONS:
        return "video"
    return "unknown"


def _parse_wav(file_path: str) -> Dict[str, Any]:
    """使用标准库 wave 模块解析 WAV 文件

    Args:
        file_path: WAV 文件路径

    Returns:
        解析结果字典
    """
    import wave

    with wave.open(file_path, "rb") as wf:
        sample_rate = wf.getframerate()
        channels = wf.getnchannels()
        sample_width = wf.getsampwidth()
        n_frames = wf.getnframes()
        duration = n_frames / sample_rate if sample_rate > 0 else 0

    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": sample_rate,
        "channels": channels,
        "bit_depth": sample_width * 8,
        "codec": "pcm",
        "bitrate_kbps": None,  # WAV PCM 通常不报告比特率
    }


def _parse_pcm(file_path: str) -> Dict[str, Any]:
    """根据默认参数估算 PCM 文件信息

    Args:
        file_path: PCM 文件路径

    Returns:
        解析结果字典
    """
    file_size = os.path.getsize(file_path)
    bytes_per_second = (
        DEFAULT_PCM_SAMPLE_RATE * DEFAULT_PCM_SAMPLE_WIDTH * DEFAULT_PCM_CHANNELS
    )
    duration = file_size / bytes_per_second if bytes_per_second > 0 else 0

    return {
        "duration_seconds": round(duration, 2),
        "sample_rate": DEFAULT_PCM_SAMPLE_RATE,
        "channels": DEFAULT_PCM_CHANNELS,
        "bit_depth": DEFAULT_PCM_SAMPLE_WIDTH * 8,
        "codec": "pcm",
        "bitrate_kbps": None,
        "_note": "PCM 参数为默认假设值（16kHz, 16bit, mono）",
    }


def _parse_with_mutagen(file_path: str) -> Dict[str, Any]:
    """使用 mutagen 库解析音频/视频文件元数据

    Args:
        file_path: 文件路径

    Returns:
        解析结果字典

    Raises:
        ImportError: mutagen 未安装
        Exception: 解析失败
    """
    from mutagen import File as MutagenFile

    audio = MutagenFile(file_path)
    if audio is None or audio.info is None:
        raise ValueError(f"mutagen 无法识别文件格式: {file_path}")

    info = audio.info
    # 注意：使用 is not None 而非 truthy 判断，避免合法的 0.0 / 0 被吞
    raw_length = getattr(info, "length", None)
    result: Dict[str, Any] = {
        "duration_seconds": (
            round(raw_length, 2) if raw_length is not None else None
        ),
        "sample_rate": getattr(info, "sample_rate", None),
        "channels": getattr(info, "channels", None),
        "bit_depth": None,
        "codec": type(audio).__name__.lower(),
        "bitrate_kbps": None,
    }

    # 尝试获取比特率（使用 is not None 判断，0 也是合法值）
    bitrate = getattr(info, "bitrate", None)
    if bitrate is not None and bitrate > 0:
        result["bitrate_kbps"] = round(bitrate / 1000, 1)

    # 尝试获取位深度（某些格式支持）
    bits_per_sample = getattr(info, "bits_per_sample", None)
    if bits_per_sample is not None:
        result["bit_depth"] = bits_per_sample

    return result


def get_file_info(file_path: str) -> Dict[str, Any]:
    """获取单个文件的完整信息

    Args:
        file_path: 文件路径

    Returns:
        文件信息字典，包含以下字段：
        - file_name: 文件名
        - file_path: 完整路径
        - file_size_bytes: 文件大小（字节）
        - file_size_display: 可读大小
        - format: 文件格式（扩展名，如 "wav"）
        - media_type: 媒体类型（audio/video/unknown）
        - supported: 是否为 FunASR 支持的格式
        - duration_seconds: 时长（秒），无法获取时为 null
        - duration_display: 可读时长
        - sample_rate: 采样率
        - channels: 声道数
        - bit_depth: 位深度
        - codec: 编解码器
        - bitrate_kbps: 比特率（kbps）
        - parse_method: 解析方法（wave/pcm_estimate/mutagen/none）
        - error: 解析错误信息（成功时为 null）
    """
    result: Dict[str, Any] = {
        "file_name": os.path.basename(file_path),
        "file_path": os.path.abspath(file_path),
        "file_size_bytes": 0,
        "file_size_display": "0B",
        "format": "",
        "media_type": "unknown",
        "supported": False,
        "duration_seconds": None,
        "duration_display": "未知",
        "sample_rate": None,
        "channels": None,
        "bit_depth": None,
        "codec": None,
        "bitrate_kbps": None,
        "parse_method": "none",
        "error": None,
    }

    # 检查文件是否存在
    if not os.path.exists(file_path):
        result["error"] = f"文件不存在: {file_path}"
        return result

    # 基础信息
    file_size = os.path.getsize(file_path)
    result["file_size_bytes"] = file_size
    result["file_size_display"] = _format_file_size(file_size)

    if file_size == 0:
        result["error"] = "文件为空（0 字节）"
        return result

    # 扩展名与格式判断
    _, ext = os.path.splitext(file_path)
    ext = ext.lower()
    result["format"] = ext.lstrip(".") if ext else "unknown"
    result["media_type"] = _detect_media_type(ext)
    result["supported"] = ext in ALL_SUPPORTED_EXTENSIONS

    # 解析元数据
    try:
        if ext == ".wav":
            # WAV：使用标准库精确解析
            meta = _parse_wav(file_path)
            result["parse_method"] = "wave"
            result.update({
                "duration_seconds": meta["duration_seconds"],
                "sample_rate": meta["sample_rate"],
                "channels": meta["channels"],
                "bit_depth": meta["bit_depth"],
                "codec": meta["codec"],
                "bitrate_kbps": meta.get("bitrate_kbps"),
            })

        elif ext == ".pcm":
            # PCM：基于默认参数估算
            meta = _parse_pcm(file_path)
            result["parse_method"] = "pcm_estimate"
            result.update({
                "duration_seconds": meta["duration_seconds"],
                "sample_rate": meta["sample_rate"],
                "channels": meta["channels"],
                "bit_depth": meta["bit_depth"],
                "codec": meta["codec"],
            })

        else:
            # 其他格式：尝试 mutagen
            try:
                meta = _parse_with_mutagen(file_path)
                result["parse_method"] = "mutagen"
                result.update({
                    "duration_seconds": meta["duration_seconds"],
                    "sample_rate": meta["sample_rate"],
                    "channels": meta["channels"],
                    "bit_depth": meta.get("bit_depth"),
                    "codec": meta["codec"],
                    "bitrate_kbps": meta.get("bitrate_kbps"),
                })
            except ImportError:
                result["parse_method"] = "none"
                result["error"] = (
                    "mutagen 未安装，无法解析非 WAV/PCM 格式的元数据。"
                    "安装方法: pip install mutagen"
                )
            except Exception as e:
                result["parse_method"] = "none"
                result["error"] = f"mutagen 解析失败: {e}"

    except Exception as e:
        result["error"] = f"元数据解析失败: {e}"

    # 生成可读时长
    if result["duration_seconds"] is not None:
        result["duration_display"] = _format_duration(result["duration_seconds"])

    return result


# ============================================================
# 命令行入口
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="FunASR 文件信息查询工具 — 获取音频/视频文件的元数据",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 查询单个文件
  python funasr_fileinfo.py input.wav

  # 查询多个文件
  python funasr_fileinfo.py file1.wav file2.mp4 file3.m4a

  # 使用 --audio 参数指定
  python funasr_fileinfo.py --audio file1.wav --audio file2.mp3

  # 静默模式（仅 JSON 输出）
  python funasr_fileinfo.py input.wav --quiet

  # 输出到文件
  python funasr_fileinfo.py file1.wav file2.mp4 --output fileinfo.json
        """,
    )

    # 文件参数（两种方式均可）
    parser.add_argument(
        "files",
        nargs="*",
        help="音频/视频文件路径（位置参数）",
    )
    parser.add_argument(
        "--audio",
        type=str,
        action="append",
        default=[],
        help="音频/视频文件路径（可多次指定）",
    )

    # 输出配置
    parser.add_argument(
        "--output", type=str, default=None,
        help="输出结果到文件（默认 stdout）",
    )

    # 调试选项
    parser.add_argument("--verbose", action="store_true", help="详细日志输出")
    parser.add_argument("--quiet", action="store_true", help="静默模式（仅输出 JSON）")

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

    # 合并文件列表：位置参数 + --audio 参数
    all_files: List[str] = list(args.files) + list(args.audio)

    if not all_files:
        parser.print_help(sys.stderr)
        print(
            json.dumps(
                {"success": False, "error": "未指定任何文件", "files": []},
                ensure_ascii=False,
                indent=2,
            )
        )
        sys.exit(EXIT_ARG_ERROR)

    # 检查 mutagen 可用性
    mutagen_available = False
    try:
        import mutagen  # noqa: F401
        mutagen_available = True
        logger.info(f"mutagen {mutagen.version_string} 可用")
    except ImportError:
        logger.warning(
            "mutagen 未安装，非 WAV/PCM 格式的时长和元数据将不可用。"
            "安装方法: pip install mutagen"
        )

    # 逐个解析文件
    file_results: List[Dict[str, Any]] = []
    success_count = 0
    fail_count = 0

    for file_path in all_files:
        logger.info(f"解析文件: {file_path}")
        info = get_file_info(file_path)
        file_results.append(info)

        if info["error"] is None:
            success_count += 1
            logger.info(
                f"  → {info['format'].upper()} | "
                f"{info['file_size_display']} | "
                f"{info['duration_display']} | "
                f"解析方式: {info['parse_method']}"
            )
        else:
            fail_count += 1
            logger.warning(f"  → 解析失败: {info['error']}")

    # 构建汇总结果
    output_data: Dict[str, Any] = {
        "success": fail_count == 0,
        "total_files": len(all_files),
        "parsed_ok": success_count,
        "parse_failed": fail_count,
        "mutagen_available": mutagen_available,
        "files": file_results,
    }

    # 生成汇总文本
    formats_found = set(
        f["format"].upper() for f in file_results if f["format"]
    )
    # 收集所有有已知时长的文件，区分"无已知时长"和"时长之和为 0"
    known_durations = [
        f["duration_seconds"]
        for f in file_results
        if f["duration_seconds"] is not None
    ]
    has_any_duration = len(known_durations) > 0
    total_duration = sum(known_durations)  # 无已知时长时为 0
    total_size = sum(f["file_size_bytes"] for f in file_results)

    output_data["summary"] = {
        "formats": sorted(formats_found),
        "total_size_display": _format_file_size(total_size),
        "total_duration_seconds": (
            round(total_duration, 2) if has_any_duration else None
        ),
        "total_duration_display": (
            _format_duration(total_duration) if has_any_duration else "未知"
        ),
    }

    duration_text = (
        _format_duration(total_duration) if has_any_duration else "未知"
    )
    output_data["display_text"] = (
        f"📁 {len(all_files)} 个文件 | "
        f"格式: {', '.join(sorted(formats_found))} | "
        f"总大小: {_format_file_size(total_size)} | "
        f"总时长: {duration_text}"
    )

    # 输出
    output_json = json.dumps(output_data, ensure_ascii=False, indent=2)

    if args.output:
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output_json)
        logger.info(f"结果已写入: {args.output}")
    else:
        print(output_json)

    # 退出码
    if fail_count > 0:
        sys.exit(EXIT_PARTIAL_FAIL)
    sys.exit(EXIT_SUCCESS)


if __name__ == "__main__":
    main()
