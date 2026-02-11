#!/usr/bin/env python3
"""FunASR 服务探测脚本

检测 FunASR WebSocket 服务的连接可达性、能力支持和协议语义。
输出 JSON 格式的探测结果，方便 Agent 判断服务状态。

退出码：0=服务可达, 1=参数错误, 2=服务不可达

用法示例：
  python funasr_probe.py --host 127.0.0.1 --port 10095
  python funasr_probe.py --host www.funasr.com --port 10096 --level offline_light

基于 FunASR GUI Client V3 核心模块构建。
"""

import argparse
import asyncio
import json
import logging
import os
import sys

# 注入 lib 目录到模块搜索路径
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lib"))

from server_probe import (  # noqa: E402
    ProbeLevel,
    ServerProbe,
    create_probe_level,
)

# ---------- 退出码定义 ----------
EXIT_REACHABLE = 0
EXIT_ARG_ERROR = 1
EXIT_UNREACHABLE = 2

# ---------- 日志配置 ----------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("funasr_probe")


def build_parser() -> argparse.ArgumentParser:
    """构建命令行参数解析器"""
    parser = argparse.ArgumentParser(
        description="FunASR 服务探测工具 — 检测 FunASR 服务的可达性和能力",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 基础探测（离线轻量，推荐）
  python funasr_probe.py --host 127.0.0.1 --port 10095

  # 仅连接测试
  python funasr_probe.py --host 127.0.0.1 --port 10095 --level connect_only

  # 完整探测（含 2pass）
  python funasr_probe.py --host 127.0.0.1 --port 10095 --level twopass_full --timeout 15

  # 公网测试服务
  python funasr_probe.py --host www.funasr.com --port 10096

  # 禁用 SSL
  python funasr_probe.py --host 127.0.0.1 --port 10095 --no-ssl
        """,
    )

    parser.add_argument("--host", type=str, required=True, help="FunASR 服务器地址")
    parser.add_argument("--port", type=int, required=True, help="FunASR 服务器端口")

    ssl_group = parser.add_mutually_exclusive_group()
    ssl_group.add_argument(
        "--ssl", action="store_true", default=True, help="启用 SSL（默认）"
    )
    ssl_group.add_argument("--no-ssl", action="store_false", dest="ssl", help="禁用 SSL")

    parser.add_argument(
        "--level",
        type=str,
        default="offline_light",
        choices=["connect_only", "offline_light", "twopass_full"],
        help="探测级别（默认 offline_light）",
    )
    parser.add_argument(
        "--timeout", type=float, default=5.0, help="探测超时（秒，默认 5.0）"
    )
    parser.add_argument("--quiet", action="store_true", help="静默模式（仅输出 JSON）")
    parser.add_argument("--verbose", action="store_true", help="详细日志输出")

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
        result = {
            "success": False,
            "error": "缺少依赖: pip install websockets>=10.0",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(EXIT_ARG_ERROR)

    # 执行探测
    server_str = f"{args.host}:{args.port}"
    logger.info(f"开始探测: {server_str} (级别: {args.level})")

    probe = ServerProbe(args.host, str(args.port), args.ssl)
    level = create_probe_level(args.level)

    try:
        caps = asyncio.run(probe.probe(level=level, timeout=args.timeout))
    except Exception as e:
        result = {
            "success": False,
            "server": server_str,
            "error": f"探测执行失败: {e}",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        sys.exit(EXIT_UNREACHABLE)

    # 构建输出
    output = {
        "success": caps.reachable,
        "server": server_str,
        "reachable": caps.reachable,
        "responsive": caps.responsive,
        "supports_offline": caps.supports_offline,
        "supports_online": caps.supports_online,
        "supports_2pass": caps.supports_2pass,
        "inferred_server_type": caps.inferred_server_type,
        "is_final_semantics": caps.is_final_semantics,
        "has_timestamp": caps.has_timestamp,
        "has_stamp_sents": caps.has_stamp_sents,
        "probe_duration_ms": round(caps.probe_duration_ms, 1),
        "probe_notes": caps.probe_notes,
        "display_text": caps.to_display_text(),
    }

    if caps.error:
        output["error"] = caps.error

    print(json.dumps(output, ensure_ascii=False, indent=2))

    # 退出码：可达=0，不可达=2
    sys.exit(EXIT_REACHABLE if caps.reachable else EXIT_UNREACHABLE)


if __name__ == "__main__":
    main()
