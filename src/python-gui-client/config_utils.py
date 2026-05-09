"""配置文件工具函数（V3）。

目标：
1) 避免 V2 配置在自动保存/缓存写回时被无备份覆盖导致数据丢失
2) 合并保存时保留未知字段与用户自定义 presets 等内容
3) 提供缓存时间有效性判断（24h 规则）等可测试的纯函数
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import shutil
import tempfile
from typing import Any, Dict, Optional


def read_json_file(path: str) -> Dict[str, Any]:
    """读取 JSON 文件，失败返回空字典。"""
    import logging

    try:
        if not os.path.exists(path):
            return {}
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
        return {}
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    except Exception as e:
        logging.warning(f"读取配置文件异常 ({path}): {type(e).__name__}: {e}")
        return {}


def write_json_file_atomic(path: str, data: Dict[str, Any]) -> None:
    """原子写入 JSON（先写临时文件再替换），避免写入中断导致文件损坏。"""
    dir_path = os.path.dirname(path)
    if dir_path:
        os.makedirs(dir_path, exist_ok=True)

    fd, tmp_path = tempfile.mkstemp(
        prefix=os.path.basename(path) + ".tmp.",
        suffix=".json",
        dir=os.path.dirname(path),
        text=True,
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        os.replace(tmp_path, path)
    finally:
        # 若 replace 失败，确保临时文件不残留
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except Exception:
            pass


def ensure_backup_file(path: str, backup_suffix: str = ".v2.bak") -> Optional[str]:
    """为指定文件创建一次性备份（若已存在则不重复创建）。

    返回备份文件路径；若未创建（原文件不存在或备份已存在）返回 None。
    """
    import logging

    try:
        if not os.path.exists(path):
            return None
        backup_path = path + backup_suffix
        if os.path.exists(backup_path):
            return None
        shutil.copy2(path, backup_path)
        return backup_path
    except Exception as e:
        logging.warning(f"创建备份文件失败 ({path}): {type(e).__name__}: {e}")
        return None


def merge_config_preserving_unknown(
    base: Dict[str, Any],
    previous: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """合并配置：以 base 为准，同时尽量保留 previous 中的未知字段。

    规则：
    - base 的值优先（代表当前 UI/逻辑的“确定值”）
    - 对于常见分组节点（server/options/ui/protocol/sensevoice/cache/presets），采用“深拷贝 previous，再用 base 覆盖”
      这样可保留这些分组里未来新增/用户自定义字段
    - 对于 previous 的顶层未知字段（base 中没有的 key），直接原样保留到输出顶层
    """
    merged: Dict[str, Any] = copy.deepcopy(base) if isinstance(base, dict) else {}
    if not isinstance(previous, dict):
        return merged

    group_keys = [
        "server",
        "options",
        "ui",
        "protocol",
        "sensevoice",
        "cache",
        "presets",
    ]

    for key in group_keys:
        prev_val = previous.get(key)
        base_val = merged.get(key)
        if isinstance(prev_val, dict) and isinstance(base_val, dict):
            tmp = copy.deepcopy(prev_val)
            tmp.update(copy.deepcopy(base_val))
            merged[key] = tmp

    # 顶层未知字段保留（不覆盖 base 已写入的键）
    for k, v in previous.items():
        if k not in merged:
            merged[k] = copy.deepcopy(v)

    return merged


def is_cache_time_valid(
    cache_time_str: Optional[str],
    now: Optional[datetime.datetime] = None,
    ttl_hours: int = 24,
) -> bool:
    """判断缓存时间是否在 ttl_hours 之内（默认 24h，恰好 24h 视为过期）。"""
    if not cache_time_str:
        return False
    try:
        cache_time = datetime.datetime.fromisoformat(cache_time_str)
        # 统一时区：若 cache_time 携带时区信息，now 也必须是 aware datetime
        if cache_time.tzinfo is not None:
            now_dt = now or datetime.datetime.now(datetime.timezone.utc)
            if now_dt.tzinfo is None:
                now_dt = now_dt.replace(tzinfo=datetime.timezone.utc)
        else:
            now_dt = now or datetime.datetime.now()
            if now_dt.tzinfo is not None:
                now_dt = now_dt.replace(tzinfo=None)
        age = now_dt - cache_time
        return age.total_seconds() < ttl_hours * 3600
    except Exception:
        return False

