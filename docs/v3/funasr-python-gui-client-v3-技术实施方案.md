# FunASR GUI 客户端 - V3 技术实施方案

**版本**: 3.0  
**日期**: 2026-01-26  
**状态**: 方案评审稿  
**作者**: 开发团队

---

## 目录

1. [核心问题与设计目标](#一核心问题与设计目标)
2. [总体架构设计](#二总体架构设计)
3. [A层：协议适配层（核心）](#三a层协议适配层核心--必做)
4. [B层：服务探测层（新增）](#四b层服务探测层新增)
5. [C层：配置管理（更新）](#五c层配置管理更新)
6. [D层：GUI界面设计](#六d层gui界面设计)
7. [实施计划与优先级](#七实施计划与优先级)
8. [风险与兜底策略](#八风险与兜底策略)
9. [文件变更清单](#九文件变更清单)

---

## 一、核心问题与设计目标

### 1.1 背景说明

FunASR 开源项目持续更新，新版 `FunASR-main` 在协议实现上与旧版存在差异。为了让 GUI 客户端能够同时兼容新旧两种服务端，需要进行适配改造。

### 1.2 核心问题识别

| 问题 | 影响 | 紧急度 |
|------|------|--------|
| **新版runtime离线模式`is_final`永远为`false`** | 识别卡死到超时 | 🔴 P0 |
| **协议参数差异（svs_lang/svs_itn等）** | 新功能无法使用 | 🟡 P1 |
| **无法自动获取模型类型** | 用户需手动选择 | 🟢 P2 |
| **服务端类型判断困难** | 配置错误导致失败 | 🟡 P1 |

### 1.3 关键发现：协议兼容性分析

经过对 `ref/FunASR-main` 代码库的详细分析，确认以下要点：

**协议层面（WebSocket）：**
- 新旧协议**向后兼容**，核心字段一致
- 新版增加了可选参数（`svs_lang`/`svs_itn`），多数旧服务端会忽略未知字段；为保险起见需支持“发送失败→降级重试”
- **关键差异**：离线模式 `is_final` 字段语义变化

**能力查询限制：**
- FunASR WebSocket 协议**没有官方的 `capabilities/model_info` 返回**
- 无法可靠自动获取服务端加载的具体模型名/版本
- 但可以通过**最佳努力探测**推断部分能力

### 1.4 设计目标

```
┌─────────────────────────────────────────────────────────────────────┐
│                        用户体验目标                                  │
├─────────────────────────────────────────────────────────────────────┤
│  1. 启动即知状态：打开软件1-2秒内显示服务器可用性与能力               │
│  2. 切换即验证：更改配置后立即反馈是否有效                           │
│  3. 新旧都能跑：无论连接哪种服务端，识别流程都不会卡死               │
│  4. 零配置可用：默认"自动探测"模式，用户无需理解协议差异             │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 二、总体架构设计

### 2.1 四层架构

```
┌─────────────────────────────────────────────────────────────────────┐
│                        FunASR GUI Client V3                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  D. GUI 展示层                                                 │ │
│  │  ├─ 服务端类型开关 (自动/传统/新版)                            │ │
│  │  ├─ 自动探测控制 (启动时/切换时)                               │ │
│  │  ├─ 能力状态展示 (可用性/支持模式/时间戳)                      │ │
│  │  └─ 刷新探测按钮                                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  C. 业务逻辑层                                                 │ │
│  │  ├─ 识别控制器 (调用适配层)                                    │ │
│  │  ├─ 速度测试器 (调用适配层)                                    │ │
│  │  └─ 配置管理器 (读写config.json)                               │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  B. 服务探测层 (新增) - server_probe.py                        │ │
│  │  ├─ 连接探测 (WebSocket握手)                                   │ │
│  │  ├─ 能力探测 (离线轻量/2pass可选)                              │ │
│  │  └─ 结果输出 (ServerCapabilities)                              │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                              │                                      │
│                              ▼                                      │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  A. 协议适配层 (核心) - protocol_adapter.py                    │ │
│  │  ├─ 消息构建 (新旧参数兼容)                                    │ │
│  │  ├─ 结果解析 (宽容解析+正确结束条件)                           │ │
│  │  └─ 结束判定 (修复is_final语义差异)                            │ │
│  └───────────────────────────────────────────────────────────────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 2.2 数据流设计

```
启动软件
    │
    ▼
┌─────────────────┐
│ 加载config.json │
└────────┬────────┘
         │
         ▼
┌─────────────────────────┐     ┌─────────────────────────┐
│ auto_probe_on_start=true│────►│ 后台启动服务探测        │
└─────────────────────────┘     │ (不阻塞UI)              │
         │                      └────────────┬────────────┘
         │                                   │
         ▼                                   ▼
┌─────────────────┐              ┌─────────────────────────┐
│ UI初始化完成    │              │ 探测完成                │
│ 显示"探测中..." │              │ 更新ServerCapabilities  │
└─────────────────┘              └────────────┬────────────┘
                                              │
                                              ▼
                                 ┌─────────────────────────┐
                                 │ 更新UI状态              │
                                 │ • 连接指示灯            │
                                 │ • 能力摘要              │
                                 │ • 模式可用性            │
                                 └─────────────────────────┘
```

### 2.3 新旧接口对比

| 参数 | 旧版本 | 新版本 | 兼容策略 |
|------|--------|--------|----------|
| `mode` | ✅ | ✅ | 通用 |
| `wav_name` | ✅ | ✅ | 通用 |
| `wav_format` | ✅ | ✅ | 通用 |
| `is_speaking` | ✅ | ✅ | 通用 |
| `audio_fs` | ✅ | ✅ | 通用 |
| `hotwords` | ✅ | ✅ | 通用 |
| `itn` | ✅ | ✅ | 通用 |
| `chunk_size` | ✅ | ✅ | 通用 |
| `svs_lang` | ❌ | ✅ | 新版专用，旧版忽略 |
| `svs_itn` | ❌ | ✅ | 新版专用，旧版忽略 |
| `is_final` (返回) | 语义正常 | 离线永远false | **需特殊处理** |

---

## 三、A层：协议适配层（核心 - 必做）

### 3.1 模块设计：`protocol_adapter.py`

**文件位置**：`src/python-gui-client/protocol_adapter.py`

**核心职责**：
1. 消息构建：根据服务端类型构建兼容的JSON消息
2. 结果解析：宽容解析各种响应格式
3. 结束判定：正确处理is_final语义差异（核心修复）

```python
"""FunASR 协议适配层

统一处理新旧服务端的协议差异，提供一致的内部接口。
"""

from enum import Enum
from dataclasses import dataclass
from typing import Optional, Dict, Any, List
import json


class ServerType(Enum):
    """服务端类型"""
    AUTO = "auto"           # 自动探测（推荐）
    LEGACY = "legacy"       # 旧版服务端
    FUNASR_MAIN = "funasr_main"  # 新版FunASR-main


class RecognitionMode(Enum):
    """识别模式"""
    OFFLINE = "offline"
    ONLINE = "online"
    TWOPASS = "2pass"


@dataclass
class MessageProfile:
    """消息构建配置"""
    server_type: ServerType
    mode: RecognitionMode
    wav_name: str
    wav_format: str = "pcm"
    audio_fs: int = 16000
    use_itn: bool = True
    use_ssl: bool = True
    hotwords: str = ""
    # 新版参数
    enable_svs_params: bool = False  # 是否启用并下发 SenseVoice 相关参数（AUTO 默认关闭）
    svs_lang: str = "auto"
    svs_itn: bool = True
    # 2pass参数
    chunk_size: List[int] = None
    chunk_interval: int = 10
    
    def __post_init__(self):
        if self.chunk_size is None:
            self.chunk_size = [5, 10, 5]


class ProtocolAdapter:
    """协议适配器"""
    
    def __init__(self, server_type: ServerType = ServerType.AUTO):
        self.server_type = server_type
        self._detected_is_final_semantics = "unknown"
    
    def build_start_message(self, profile: MessageProfile) -> str:
        """构建开始消息
        
        根据服务端类型和模式构建兼容的初始化JSON
        """
        msg = {
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
        
        # 2pass/online模式需要chunk参数
        if profile.mode in [RecognitionMode.ONLINE, RecognitionMode.TWOPASS]:
            msg["chunk_size"] = profile.chunk_size
            msg["chunk_interval"] = profile.chunk_interval
            msg["encoder_chunk_look_back"] = 4
            msg["decoder_chunk_look_back"] = 1
        
        # 新版参数（多数旧服务端会忽略未知字段；为避免严格服务端拒绝，AUTO 默认不下发，除非显式启用）
        if profile.enable_svs_params or self.server_type == ServerType.FUNASR_MAIN:
            msg["svs_lang"] = profile.svs_lang
            msg["svs_itn"] = profile.svs_itn
        
        return json.dumps(msg, ensure_ascii=False)
    
    def build_end_message(self) -> str:
        """构建结束消息"""
        return json.dumps({"is_speaking": False})
    
    def parse_result(self, raw_msg: str) -> Dict[str, Any]:
        """解析结果消息（宽容解析）
        
        统一输出格式：
        {
            "text": str,
            "mode": str,
            "wav_name": str,
            "is_final": bool,        # 原始字段值
            "is_complete": bool,     # 是否应该结束等待（核心！）
            "timestamp": list | None,
            "stamp_sents": list | None,
            "raw": dict              # 原始数据
        }
        """
        try:
            data = json.loads(raw_msg)
        except json.JSONDecodeError:
            return {"text": "", "is_complete": False, "error": "JSON解析失败"}
        
        result = {
            "text": "",
            "mode": data.get("mode", "unknown"),
            "wav_name": data.get("wav_name", ""),
            "is_final": data.get("is_final", False),
            "is_complete": False,
            "timestamp": data.get("timestamp"),
            "stamp_sents": data.get("stamp_sents"),
            "raw": data
        }
        
        # 文本提取（兼容多种格式）
        if "text" in data:
            result["text"] = data["text"]
        elif "stamp_sents" in data:
            # 从stamp_sents提取文本
            segments = []
            for sent in data.get("stamp_sents", []):
                if isinstance(sent, dict) and "text_seg" in sent:
                    segments.append(sent["text_seg"])
            result["text"] = "".join(segments)
        
        # 🔴 核心修复：结束判定逻辑
        result["is_complete"] = self._should_complete(data)
        
        return result
    
    def _should_complete(self, data: Dict) -> bool:
        """判断是否应该结束等待
        
        这是解决新旧版本差异的核心逻辑！
        
        设计原则（必须兼容“静音/空文本”场景）：
        - offline：服务端通常只回一条结果（可能 text 为空、is_final=False），收到回包就应结束等待
        - 2pass：收到 2pass-offline 即认为“最终纠错结果”已到达（即便 text 为空也应结束，避免静音卡死）
        - 其他：优先遵循 is_final=True 的明确结束标志
        """
        mode = data.get("mode", "")
        is_final = bool(data.get("is_final", False))
        
        # 情况1：服务端明确标记完成
        if is_final:
            return True
        
        # 情况2：离线模式（新版 runtime 可能永远 is_final=False）
        # 收到任何 offline 回包即可结束（不依赖 text 是否为空）
        if mode == "offline":
            return True
        
        # 情况3：2pass 最终纠错结果（不依赖 text 是否为空）
        if mode == "2pass-offline":
            return True
        
        # 情况4：兜底 - 出现句子级时间戳通常代表本轮已结束/可结束等待
        if data.get("stamp_sents") and len(data.get("stamp_sents", [])) > 0:
            return True
        
        return False
```

### 3.2 子进程集成修改

修改 `simple_funasr_client.py`，在消息接收循环中使用适配层：

```python
# simple_funasr_client.py 中的关键修改

from protocol_adapter import ProtocolAdapter, ServerType

# 初始化适配器（建议由GUI在启动子进程时传入 --server_type）
# server_type_str: "auto" | "legacy" | "funasr_main"
adapter = ProtocolAdapter(server_type=ServerType(server_type_str))

async def message(id):
    """接收服务器返回的消息并处理"""
    global offline_msg_done
    
    try:
        while True:
            raw_msg = await asyncio.wait_for(websocket.recv(), timeout=600)
            
            # 使用适配层解析
            result = adapter.parse_result(raw_msg)
            
            if result.get("error"):
                log(f"解析错误: {result['error']}")
                continue
            
            # 输出识别结果
            if result["text"]:
                print(f"识别结果: {result['text']}", flush=True)
            
            # 🔴 关键：使用 is_complete 而非 is_final 判断结束
            if result["is_complete"]:
                log("收到完整结果，结束等待")
                offline_msg_done = True
                break
                
    except asyncio.TimeoutError:
        log("接收超时")
        offline_msg_done = True
```

---

## 四、B层：服务探测层（新增）

### 4.1 模块设计：`server_probe.py`

**文件位置**：`src/python-gui-client/server_probe.py`

**核心职责**：
1. 连接可达性检测
2. 服务能力探测（轻量级）
3. 协议语义推断

```python
"""FunASR 服务探测器

职责：
1. 连接可达性检测
2. 服务能力探测（轻量级）
3. 协议语义推断
"""

import asyncio
import json
import ssl
from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class ProbeLevel(Enum):
    """探测级别"""
    CONNECT_ONLY = 0      # 仅连接测试
    OFFLINE_LIGHT = 1     # 离线轻量探测（推荐）
    TWOPASS_FULL = 2      # 2pass完整探测


@dataclass
class ServerCapabilities:
    """服务器能力描述"""
    # 基础状态
    reachable: bool = False
    responsive: bool = False
    error: Optional[str] = None
    
    # 支持的模式
    # 说明：这里使用三态（None/True/False），避免“未判定”被误解为“不支持”
    supports_offline: Optional[bool] = None
    supports_online: Optional[bool] = None
    supports_2pass: Optional[bool] = None
    
    # 能力特征
    has_timestamp: bool = False
    has_stamp_sents: bool = False
    
    # 协议语义（用于适配层参考）
    is_final_semantics: str = "unknown"  # legacy_true / always_false / unknown
    
    # 推断的服务端类型（最佳努力，仅用于UI提示，不作为协议决策依据）
    inferred_server_type: str = "unknown"  # legacy / funasr_main / unknown
    
    # 探测详情
    probe_level: ProbeLevel = ProbeLevel.CONNECT_ONLY
    probe_notes: List[str] = field(default_factory=list)
    
    def to_display_text(self) -> str:
        """生成用于UI展示的文本"""
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
            type_name = "可能新版" if self.inferred_server_type == "funasr_main" else "可能旧版"
            parts.append(f"类型: {type_name}（仅供参考）")
        
        return " | ".join(parts)
    
    def to_dict(self) -> dict:
        """转换为字典（用于配置缓存）"""
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
            "probe_notes": self.probe_notes
        }


class ServerProbe:
    """服务探测器"""
    
    def __init__(self, host: str, port: str, use_ssl: bool = True):
        self.host = host
        self.port = port
        self.use_ssl = use_ssl
    
    async def probe(
        self, 
        level: ProbeLevel = ProbeLevel.OFFLINE_LIGHT,
        timeout: float = 5.0
    ) -> ServerCapabilities:
        """执行探测
        
        Args:
            level: 探测级别
            timeout: 总超时时间
            
        Returns:
            ServerCapabilities: 探测结果
        """
        caps = ServerCapabilities(probe_level=level)
        
        # 构建URI
        protocol = "wss" if self.use_ssl else "ws"
        uri = f"{protocol}://{self.host}:{self.port}"
        
        try:
            # 配置SSL
            ssl_context = None
            if self.use_ssl:
                ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
            
            # 阶段0：连接测试
            import websockets
            async with asyncio.timeout(timeout):
                async with websockets.connect(
                    uri,
                    subprotocols=["binary"],
                    ping_interval=None,
                    ssl=ssl_context,
                    proxy=None,  # 显式禁用代理，避免环境代理导致连接异常
                ) as ws:
                    caps.reachable = True
                    caps.probe_notes.append("WebSocket连接成功")
                    
                    if level == ProbeLevel.CONNECT_ONLY:
                        return caps
                    
                    # 阶段1：离线轻量探测（默认推荐）
                    if level == ProbeLevel.OFFLINE_LIGHT:
                        await self._probe_offline(ws, caps)
                    
                    # 阶段2：2pass探测（可选，避免与离线探测混跑导致状态干扰）
                    if level == ProbeLevel.TWOPASS_FULL:
                        await self._probe_2pass(ws, caps)
        
        except asyncio.TimeoutError:
            caps.error = "连接超时"
        except ConnectionRefusedError:
            caps.error = "连接被拒绝"
        except Exception as e:
            caps.error = str(e)
        
        # 推断服务端类型
        self._infer_server_type(caps)
        
        return caps
    
    async def _probe_offline(self, ws, caps: ServerCapabilities):
        """离线模式轻量探测"""
        try:
            # 发送探测消息
            probe_msg = json.dumps({
                "mode": "offline",
                "wav_name": "__probe__",
                "wav_format": "pcm",
                "audio_fs": 16000,
                "is_speaking": True,
                "itn": True
            })
            await ws.send(probe_msg)

            # 发送极短静音PCM，提升“空输入不回包”场景下的探测成功率
            # 16000Hz * 2bytes * 0.25s ≈ 8000 bytes
            await ws.send(bytes(8000))
            
            # 立即发送结束
            await ws.send(json.dumps({"is_speaking": False}))
            
            # 等待响应（短超时）
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                caps.responsive = True
                
                data = json.loads(response)
                caps.supports_offline = True
                
                # 分析响应特征
                if "timestamp" in data:
                    caps.has_timestamp = True
                if "stamp_sents" in data:
                    caps.has_stamp_sents = True
                
                # 分析is_final语义
                is_final = data.get("is_final", None)
                if is_final is True:
                    caps.is_final_semantics = "legacy_true"
                elif is_final is False:
                    # 注意：该特征无法 100% 区分新旧服务端，仅作“可能”提示
                    caps.is_final_semantics = "always_false"
                
                caps.probe_notes.append("离线模式探测成功")
                
            except asyncio.TimeoutError:
                # 无响应但连接成功
                caps.responsive = False
                caps.supports_offline = None  # 未判定
                caps.probe_notes.append("离线探测无响应（部分服务对短/静音输入可能不回包）")
                
        except Exception as e:
            caps.probe_notes.append(f"离线探测异常: {e}")
    
    async def _probe_2pass(self, ws, caps: ServerCapabilities):
        """2pass模式探测（需要发送音频数据）"""
        try:
            # 发送2pass初始化
            probe_msg = json.dumps({
                "mode": "2pass",
                "wav_name": "__probe_2pass__",
                "wav_format": "pcm",
                "audio_fs": 16000,
                "is_speaking": True,
                "chunk_size": [5, 10, 5],
                "chunk_interval": 10
            })
            await ws.send(probe_msg)
            
            # 发送1秒静音PCM数据 (16000Hz * 2bytes * 1s = 32000bytes)
            silence_data = bytes(32000)
            await ws.send(silence_data)
            
            # 发送结束
            await ws.send(json.dumps({"is_speaking": False}))
            
            # 等待响应
            try:
                response = await asyncio.wait_for(ws.recv(), timeout=3.0)
                data = json.loads(response)
                
                mode = data.get("mode", "")
                if mode in ["2pass", "2pass-online", "2pass-offline"]:
                    caps.supports_2pass = True
                    caps.supports_online = True
                    caps.responsive = True
                    caps.probe_notes.append("2pass模式探测成功")
                    
            except asyncio.TimeoutError:
                caps.probe_notes.append("2pass探测超时")
                
        except Exception as e:
            caps.probe_notes.append(f"2pass探测异常: {e}")
    
    def _infer_server_type(self, caps: ServerCapabilities):
        """根据探测结果推断服务端类型"""
        if caps.is_final_semantics == "always_false":
            caps.inferred_server_type = "funasr_main"
        elif caps.is_final_semantics == "legacy_true":
            caps.inferred_server_type = "legacy"
        else:
            caps.inferred_server_type = "unknown"
```

### 4.2 探测时机与防抖

**实现建议（与 Tkinter 线程模型一致，避免“无事件循环”问题）：**
- **防抖**：统一使用 Tkinter 的 `after(…, …)` + `after_cancel(...)` 实现 300–800ms 防抖（多次快速切换只执行最后一次）
- **执行**：在后台线程中运行 `asyncio.run(ServerProbe(...).probe(...))`
- **回写UI**：探测完成后使用 `self.after(0, ...)` 回到主线程更新控件状态

> 说明：不建议在 Tk 主线程直接 `asyncio.create_task(...)`，因为 Tk 应用默认没有长期运行的 asyncio event loop。

### 4.3 探测级别说明

| 级别 | 说明 | 耗时 | 使用场景 |
|------|------|------|----------|
| `CONNECT_ONLY` | 仅WebSocket握手 | <1s | 快速检查连通性 |
| `OFFLINE_LIGHT` | 发送短静音离线请求（最佳努力） | 1-3s | **默认推荐** |
| `TWOPASS_FULL` | 发送静音音频 | 3-5s | 需要2pass能力检测时 |

---

## 五、C层：配置管理（更新）

### 5.1 配置文件结构更新

**文件位置**：`dev/config/config.json`

```json
{
    "config_version": 3,
    "server": {
        "ip": "127.0.0.1",
        "port": "10095"
    },
    "options": {
        "use_itn": 1,
        "use_ssl": 1,
        "hotword_path": ""
    },
    "ui": {
        "language": "zh"
    },
    "protocol": {
        "server_type": "auto",
        "preferred_mode": "offline",
        "auto_probe_on_start": true,
        "auto_probe_on_switch": true,
        "probe_level": "offline_light",
        "connection_test_timeout": 5
    },
    "sensevoice": {
        "svs_lang": "auto",
        "svs_itn": true
    },
    "cache": {
        "last_probe_result": null,
        "last_probe_time": null
    },
    "presets": {
        "public_cloud": {
            "ip": "www.funasr.com",
            "port": "10096",
            "use_ssl": true,
            "description": "FunASR公网测试服务"
        }
    }
}
```

### 5.2 配置字段说明

| 字段路径 | 类型 | 默认值 | 说明 |
|----------|------|--------|------|
| `config_version` | int | 3 | 配置版本号（用于自动迁移与兼容判断） |
| `options.hotword_path` | string | "" | 热词文件路径（与现有 V2 字段名保持一致） |
| `protocol.server_type` | string | "auto" | 服务端类型：auto/legacy/funasr_main |
| `protocol.preferred_mode` | string | "offline" | 首选识别模式：offline/2pass |
| `protocol.auto_probe_on_start` | bool | true | 启动时自动探测 |
| `protocol.auto_probe_on_switch` | bool | true | 切换配置时自动探测 |
| `protocol.probe_level` | string | "offline_light" | 探测级别 |
| `protocol.connection_test_timeout` | int | 5 | 连接/探测超时时间（秒） |
| `sensevoice.svs_lang` | string | "auto" | SenseVoice语种 |
| `sensevoice.svs_itn` | bool | true | SenseVoice ITN开关 |
| `cache.last_probe_result` | object | null | 上次探测结果缓存 |
| `cache.last_probe_time` | string | null | 上次探测时间 |

### 5.3 配置迁移策略（必须实现，保证向后兼容）

当前 V2 配置为“扁平结构”（例如包含 `ip/port/use_itn/use_ssl/language/hotword_path/connection_test_timeout`）。V3 改为分组结构后，需要提供自动迁移：

- **加载时**：
  - 若存在 `config_version == 3`：按 V3 结构读取
  - 否则：按 V2 结构读取 → 生成 V3 结构（填充默认值）→ 写回保存一次（升级完成）
- **保存时**：统一写 V3 结构；必要时保留兼容字段（可选，视是否需要与旧版本共用同一配置文件）

---

## 六、D层：GUI界面设计

### 6.1 界面布局更新

```
┌────────────────────────────────────────────────────────────────────────────┐
│  服务器连接配置                                                            │
├────────────────────────────────────────────────────────────────────────────┤
│                                                                            │
│  服务器 IP: [127.0.0.1______]  端口: [10095]  [连接服务器]  🟢 已连接     │
│                                                                            │
│  ┌─ 服务端配置 ──────────────────────────────────────────────────────────┐│
│  │                                                                        ││
│  │  服务端类型: [自动探测（推荐）▼]    识别模式: [离线转写 ▼]            ││
│  │                                                                        ││
│  │  [✓] 启动时自动探测    [✓] 切换时自动探测    [🔄 立即探测]           ││
│  │                                                                        ││
│  │  ┌─ 探测结果 ─────────────────────────────────────────────────────┐  ││
│  │  │  ✅ 服务可用 | 模式: 离线/2pass | 能力: 时间戳 | 类型: 新版服务 │  ││
│  │  └────────────────────────────────────────────────────────────────┘  ││
│  │                                                                        ││
│  └────────────────────────────────────────────────────────────────────────┘│
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────────────────────────┐
│  高级选项                                                                  │
├────────────────────────────────────────────────────────────────────────────┤
│  [✓] 启用 ITN    [✓] 启用 SSL    [打开日志文件]  [打开结果目录]   [EN]    │
│                                                                            │
│  热词文件: [选择热词] [_________________(路径)______________] [清除热词]   │
│                                                                            │
│  ─── SenseVoice 设置（新版服务可用）──────────────────────────────────────│
│  语种: [auto ▼]  [✓] 启用 SVS ITN    ⚠️ 需要服务端加载SenseVoice模型      │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 控件定义

```python
# === 服务端配置区域 ===

# 服务端类型下拉框（显示值 ↔ 内部值映射，避免UI文案影响逻辑判断）
SERVER_TYPE_OPTIONS = [
    ("自动探测（推荐）", "auto"),
    ("旧版服务端 (Legacy)", "legacy"),
    ("新版服务端 (FunASR-main)", "funasr_main"),
    ("公网测试服务", "public_cloud"),
]
SERVER_TYPE_DISPLAY_TO_VALUE = {d: v for d, v in SERVER_TYPE_OPTIONS}
SERVER_TYPE_VALUE_TO_DISPLAY = {v: d for d, v in SERVER_TYPE_OPTIONS}

self.server_type_display_var = tk.StringVar(
    value=SERVER_TYPE_VALUE_TO_DISPLAY.get(
        self.config.get("protocol", {}).get("server_type", "auto"),
        "自动探测（推荐）",
    )
)
self.server_type_combo = ttk.Combobox(
    server_config_frame,
    textvariable=self.server_type_display_var,
    values=[d for d, _ in SERVER_TYPE_OPTIONS],
    state="readonly",
    width=18
)
self.server_type_combo.bind("<<ComboboxSelected>>", self._on_server_type_changed)

# 识别模式下拉框
MODE_OPTIONS = [
    ("离线转写", "offline"),
    ("实时识别 (2pass)", "2pass"),
]
MODE_DISPLAY_TO_VALUE = {d: v for d, v in MODE_OPTIONS}
MODE_VALUE_TO_DISPLAY = {v: d for d, v in MODE_OPTIONS}

self.mode_display_var = tk.StringVar(
    value=MODE_VALUE_TO_DISPLAY.get(
        self.config.get("protocol", {}).get("preferred_mode", "offline"),
        "离线转写",
    )
)
self.mode_combo = ttk.Combobox(
    server_config_frame,
    textvariable=self.mode_display_var,
    values=[d for d, _ in MODE_OPTIONS],
    state="readonly",
    width=15
)

# 自动探测复选框
self.auto_probe_start_var = tk.IntVar(value=1)
self.auto_probe_start_check = ttk.Checkbutton(
    server_config_frame,
    text="启动时自动探测",
    variable=self.auto_probe_start_var
)

self.auto_probe_switch_var = tk.IntVar(value=1)
self.auto_probe_switch_check = ttk.Checkbutton(
    server_config_frame,
    text="切换时自动探测",
    variable=self.auto_probe_switch_var
)

# 立即探测按钮
self.probe_button = ttk.Button(
    server_config_frame,
    text="🔄 立即探测",
    command=self._schedule_probe
)

# 探测结果展示标签
self.probe_result_var = tk.StringVar(value="等待探测...")
self.probe_result_label = ttk.Label(
    server_config_frame,
    textvariable=self.probe_result_var,
    foreground="gray"
)

# === SenseVoice 设置区域 ===

# 说明：仅当用户选择“新版服务端(FunASR-main)”或显式启用 SenseVoice 参数时，
# 才在 MessageProfile 中设置 enable_svs_params=True 并下发 svs_lang/svs_itn。

# 语种选择
self.svs_lang_var = tk.StringVar(value="auto")
self.svs_lang_combo = ttk.Combobox(
    sensevoice_frame,
    textvariable=self.svs_lang_var,
    values=["auto", "zh", "en", "ja", "ko", "yue"],
    state="readonly",
    width=8
)

# SVS ITN开关
self.svs_itn_var = tk.IntVar(value=1)
self.svs_itn_check = ttk.Checkbutton(
    sensevoice_frame,
    text="启用 SVS ITN",
    variable=self.svs_itn_var
)
```

### 6.3 事件绑定与状态更新

```python
def __init__(self):
    # ... 初始化 ...
    
    # 绑定事件
    self.server_type_combo.bind("<<ComboboxSelected>>", self._on_server_type_changed)
    self.mode_combo.bind("<<ComboboxSelected>>", self._on_mode_changed)
    
    # 启动后自动探测
    if self.config.get("protocol", {}).get("auto_probe_on_start", True):
        self.after(1000, self._auto_probe_on_startup)

def _auto_probe_on_startup(self):
    """启动时自动探测"""
    if self.ip_var.get() and self.port_var.get():
        logging.info("系统事件: 启动时自动检测服务器状态...")
        self._schedule_probe()

def _on_server_type_changed(self, event=None):
    """服务端类型切换"""
    # 注意：Combobox 显示值需要映射到内部值
    server_type_value = SERVER_TYPE_DISPLAY_TO_VALUE.get(
        self.server_type_display_var.get(), "auto"
    )
    
    # 公网测试服务预设
    if server_type_value == "public_cloud":
        self.ip_var.set("www.funasr.com")
        self.port_var.set("10096")
        self.use_ssl_var.set(1)
        self.ip_entry.config(state="readonly")
        self.port_entry.config(state="readonly")
    else:
        self.ip_entry.config(state="normal")
        self.port_entry.config(state="normal")

    # 写入配置（使用内部值，避免依赖UI显示文案）
    self.config.setdefault("protocol", {})
    self.config["protocol"]["server_type"] = server_type_value
    
    # 自动探测
    if self.auto_probe_switch_var.get():
        self._schedule_probe()
    
    # 保存配置
    self._save_config()

def _schedule_probe(self):
    """调度探测（带防抖）"""
    if hasattr(self, '_probe_timer') and self._probe_timer:
        self.after_cancel(self._probe_timer)
    
    self.probe_result_var.set("🔄 正在探测...")
    self.probe_result_label.config(foreground="blue")
    
    self._probe_timer = self.after(500, self._run_probe_async)

def _run_probe_async(self):
    """在后台线程执行探测"""
    def probe_thread():
        import asyncio
        from server_probe import ServerProbe, ProbeLevel
        
        probe = ServerProbe(
            self.ip_var.get(),
            self.port_var.get(),
            bool(self.use_ssl_var.get())
        )
        result = asyncio.run(probe.probe(ProbeLevel.OFFLINE_LIGHT))
        self.after(0, lambda: self._update_probe_result(result))
    
    thread = threading.Thread(target=probe_thread, daemon=True)
    thread.start()

def _update_probe_result(self, caps):
    """更新探测结果到UI"""
    display_text = caps.to_display_text()
    self.probe_result_var.set(display_text)
    
    # 更新颜色
    if caps.reachable:
        self.probe_result_label.config(foreground="green")
        self._update_connection_indicator(True)
    else:
        self.probe_result_label.config(foreground="red")
        self._update_connection_indicator(False)
    
    # 保存探测结果供适配层使用
    self._last_capabilities = caps
    
    # 缓存探测结果
    self._cache_probe_result(caps)
    
    # 更新SenseVoice选项可用性
    self._update_sensevoice_options(caps)
    
    logging.info(f"探测完成: {display_text}")

def _update_sensevoice_options(self, caps):
    """根据探测结果更新SenseVoice选项"""
    # 注意：仅凭探测无法可靠判断“是否加载了SenseVoice模型”。
    # 建议按“用户选择的服务端类型/是否启用SenseVoice参数”控制控件可用性，探测仅提供提示。
    server_type_value = SERVER_TYPE_DISPLAY_TO_VALUE.get(
        self.server_type_display_var.get(), "auto"
    )
    enable = server_type_value in ("funasr_main", "auto")
    self.svs_lang_combo.config(state="readonly" if enable else "disabled")
    self.svs_itn_check.config(state="normal" if enable else "disabled")

def _cache_probe_result(self, caps):
    """缓存探测结果到配置文件"""
    import datetime
    self.config.setdefault("cache", {})
    self.config["cache"]["last_probe_result"] = caps.to_dict()
    self.config["cache"]["last_probe_time"] = datetime.datetime.now().isoformat()
    self._save_config()
```

---

## 七、实施计划与优先级

### 7.1 分阶段实施

| 阶段 | 任务 | 优先级 | 预计工作量 | 产出 |
|------|------|--------|-----------|------|
| **Phase 1** | 协议适配层 + is_final修复 | 🔴 P0 | 0.5天 | `protocol_adapter.py` |
| **Phase 2** | 服务探测器（离线轻量） | 🟡 P1 | 0.5天 | `server_probe.py` |
| **Phase 3** | GUI集成（开关+状态展示） | 🟡 P1 | 1天 | UI更新 |
| **Phase 4** | 配置持久化 | 🟢 P2 | 0.5天 | config.json更新 |
| **Phase 5** | 2pass探测增强 | 🟢 P2 | 0.5天 | 完整能力探测 |
| **Phase 6** | 测试与文档 | 🟡 P1 | 1天 | 测试报告 |

### 7.2 里程碑定义

```
┌────────────────────────────────────────────────────────────────────────────┐
│  M1: 核心兼容（Phase 1完成）                                               │
│  ─────────────────────────────────────────────────────────────────────────│
│  ✓ 新旧服务端离线识别都能正常完成                                          │
│  ✓ 不会因is_final语义差异导致卡死                                          │
│  ✓ 适配层可被GUI和子进程共用                                               │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  M2: 自动探测（Phase 2-3完成）                                             │
│  ─────────────────────────────────────────────────────────────────────────│
│  ✓ 启动时自动探测服务器状态                                                │
│  ✓ 切换配置时自动重新探测                                                  │
│  ✓ UI展示探测结果和服务能力                                                │
└────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌────────────────────────────────────────────────────────────────────────────┐
│  M3: 完整功能（Phase 4-6完成）                                             │
│  ─────────────────────────────────────────────────────────────────────────│
│  ✓ 配置持久化与缓存                                                        │
│  ✓ 2pass能力探测                                                           │
│  ✓ SenseVoice参数支持                                                      │
│  ✓ 完整测试覆盖                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 7.3 验收标准

| 场景 | 期望行为 |
|------|----------|
| 启动软件（有保存的服务器配置） | 1-2秒内显示"正在探测..." → 探测完成显示能力摘要 |
| 切换服务端类型 | 500ms防抖后自动探测，实时更新状态 |
| 连接旧版服务端做离线识别 | 正常完成，不会因is_final=true而提前结束 |
| 连接新版服务端做离线识别 | 正常完成，不会因is_final=false而卡到超时 |
| 探测失败但手动开始识别 | 可以继续使用，不强依赖探测结果 |
| 选择公网测试服务 | 自动填充地址，自动启用SSL，自动探测 |

---

## 八、风险与兜底策略

### 8.1 风险评估

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 探测无响应（部分服务对短/静音输入可能不回包） | 中 | 能力判断不准 | 标记为"已连接但能力未判定"，允许继续使用 |
| 探测超时 | 低 | 启动变慢 | 后台执行不阻塞UI，5秒超时 |
| 新服务端参数被旧服务端拒绝 | 低-中 | 识别失败 | 不假设一定忽略未知字段；若出现“服务器关闭/协议错误”，自动降级重试（不带新字段） |
| 用户选错服务端类型 | 中 | 功能异常 | 默认"自动探测"模式，减少手动配置 |
| 适配层bug导致结果解析错误 | 低 | 识别结果丢失 | 保留raw原始数据，增加单元测试 |

### 8.2 兜底策略

```python
# 1. 探测失败兜底
def _update_probe_result(self, caps):
    if not caps.reachable:
        # 显示错误但不阻止用户操作
        self.probe_result_var.set(f"⚠️ 探测失败: {caps.error} (可手动尝试识别)")
        # 不更新连接指示灯为红色，保持之前状态

# 2. 适配层解析失败兜底
def parse_result(self, raw_msg: str) -> Dict[str, Any]:
    try:
        data = json.loads(raw_msg)
    except json.JSONDecodeError:
        # 返回空结果但包含原始数据
        return {
            "text": "",
            "is_complete": False,
            "error": "JSON解析失败",
            "raw_string": raw_msg  # 保留原始字符串用于调试
        }

# 3. 结束判定兜底
def _should_complete(self, data: Dict) -> bool:
    # ... 正常逻辑 ...
    
    # 兜底：如果收到任何包含text的消息且已超过一定时间，也视为完成
    # 这由外层超时机制保证，这里不做处理
    return False
```

---

## 九、文件变更清单

### 9.1 新增文件

| 文件路径 | 说明 |
|----------|------|
| `src/python-gui-client/protocol_adapter.py` | 协议适配层模块 |
| `src/python-gui-client/server_probe.py` | 服务探测器模块 |
| `docs/v3/funasr-python-gui-client-v3-技术实施方案.md` | 本文档 |

### 9.2 修改文件

| 文件路径 | 修改内容 |
|----------|----------|
| `src/python-gui-client/simple_funasr_client.py` | 集成适配层，修改结束判定逻辑 |
| `src/python-gui-client/funasr_gui_client_v3.py` | GUI集成探测器，新增控件 |
| `dev/config/config.json` | 新增protocol/sensevoice/cache配置节 |

### 9.3 文档更新

| 文件路径 | 更新内容 |
|----------|----------|
| `docs/v3/funasr-python-gui-client-v3-架构设计.md` | 新建，描述V3架构 |
| `docs/v3/funasr-python-gui-client-v3-UI定义.md` | 新建，描述V3 UI |
| `README.md` | 更新版本说明和新功能介绍 |

---

## 十、附录

### 10.1 协议参考

**FunASR WebSocket协议文档位置**：`ref/FunASR-main/runtime/docs/websocket_protocol_zh.md`

**关键协议字段**：
- 客户端→服务端：`mode`, `wav_name`, `wav_format`, `audio_fs`, `is_speaking`, `hotwords`, `itn`, `chunk_size`, `chunk_interval`, `svs_lang`, `svs_itn`
- 服务端→客户端：`mode`, `wav_name`, `text`, `is_final`, `timestamp`, `stamp_sents`

### 10.2 测试服务器

| 名称 | 地址 | 端口 | SSL | 说明 |
|------|------|------|-----|------|
| FunASR公网测试 | www.funasr.com | 10096 | 是 | 官方测试服务 |
| 本地Docker | 127.0.0.1 | 10095 | 是 | 本地部署 |

### 10.3 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| V3.0-draft | 2026-01-26 | 初稿，方案评审 |
| V3.0-impl | 2026-01-26 | Phase 1-3 实施完成，接口同步更新 |
| V3.0.6 | 2026-02-08 | 旧版服务器集成测试通过，修复子进程启动/速度测试检测/Tk竞态条件等4个bug |

### 10.4 重要说明

> **接口以代码为准**：本文档中的代码片段为设计阶段的伪代码/示例，实际接口形态以 `src/python-gui-client/` 目录下的源代码为准。
> 
> 主要差异点：
> - `ProtocolAdapter.parse_result()` 返回 `ParsedResult` 数据类（而非示例中的 `dict`）
> - `ServerCapabilities` 增加了 `from_dict()` 类方法用于缓存恢复
> - GUI 客户端使用 `funasr_gui_client_v3.py`（而非文档早期提到的 v2）

---

**文档结束**
