# FunASR Speech Recognition Skill — 设计方案

**日期**: 2026-02-11  
**状态**: 设计稿  
**基于**: V3 技术实施方案 + 架构师代码级评审结论

---

## 一、目标与定位

### 1.1 Skill 定位

**名称**: `funasr-speech-recognition`  
**一句话描述**: 让 AI Agent 具备调用 FunASR 服务进行语音识别的能力。

**核心价值**：Agent 只需一条命令即可完成"音频 → 文字"的转换，无需了解 WebSocket 协议、新旧服务端差异、is_final 语义问题等底层细节。

### 1.2 目标用户

- Cursor Agent / Codex Agent / 其他支持 Skill 的 AI 工具
- 使用场景：会议音频转文字、字幕生成、语音笔记整理、FunASR 服务健康检查

### 1.3 前置条件

- Python 3.10+
- `websockets>=10.0` 依赖
- 一个可访问的 FunASR WebSocket 服务端（本地 Docker 或公网测试服务）

---

## 二、架构设计

### 2.1 Skill 目录结构

```
skills/
└── funasr-speech-recognition/
    ├── SKILL.md                          # Skill 入口指令文件（<500行）
    ├── assets/
    │   ├── README.md                     # 资产目录说明
    │   └── test-for-speed.mp3            # 速度测试默认音频（由用户提供）
    ├── scripts/
    │   ├── funasr_recognize.py           # 主脚本：语音识别（Agent友好）
    │   ├── funasr_probe.py               # 辅助脚本：服务探测
    │   ├── funasr_speed_test.py          # 辅助脚本：速度测试
    │   ├── funasr_fileinfo.py            # 辅助脚本：文件信息查询（mutagen）
    │   └── lib/                          # 核心库（从 V3 精简抽取）
    │       ├── __init__.py
    │       ├── protocol_adapter.py       # 协议适配层
    │       ├── server_probe.py           # 服务探测器
    │       └── websocket_compat.py       # WebSocket 兼容层
    └── references/
        └── protocol_guide.md             # FunASR WebSocket 协议参考（含速度测试方法论）
```

### 2.2 模块复用关系

```
V3 原始模块 (src/python-gui-client/)         Skill 模块 (skills/.../scripts/)
─────────────────────────────────────         ──────────────────────────────────
protocol_adapter.py  ────精简复制────►  lib/protocol_adapter.py
server_probe.py      ────精简复制────►  lib/server_probe.py
websocket_compat.py  ────原样复制────►  lib/websocket_compat.py
simple_funasr_client.py ──重构────────►  funasr_recognize.py（Agent友好版）
（新增）             ────────────────►  funasr_probe.py（独立CLI入口）
（新增）             ────────────────►  funasr_speed_test.py（速度测试CLI入口）
（新增）             ────────────────►  funasr_fileinfo.py（文件信息查询CLI入口）
```

### 2.3 导入策略

Skill 脚本使用**相对于脚本目录的 sys.path 注入**，避免依赖安装：

```python
# funasr_recognize.py / funasr_probe.py 顶部
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "lib"))
from protocol_adapter import ProtocolAdapter, ...
from server_probe import ServerProbe, ...
```

`lib/` 内部模块之间使用同级导入（与 V3 原始方式一致）。

---

## 三、核心脚本设计

### 3.1 funasr_recognize.py — 语音识别主脚本

**设计原则**：
- 默认 JSON 输出到 stdout（Agent 友好）
- 稳定的退出码：0=成功, 1=参数错误, 2=连接失败, 3=识别超时, 4=运行时错误
- 日志输出到 stderr（不干扰 JSON 结果）
- 单进程设计（简化，Agent 场景无需多进程并发）

**CLI 接口**：

```bash
# 基础用法
python funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav

# 完整参数
python funasr_recognize.py \
  --host 127.0.0.1 \
  --port 10095 \
  --audio input.wav \
  --mode offline \          # offline / online / 2pass
  --ssl \                   # 启用SSL（默认）
  --no-ssl \                # 禁用SSL
  --server-type auto \      # auto / legacy / funasr_main
  --format json \           # json / text / srt
  --output result.json \    # 输出到文件（可选）
  --timeout 600 \           # 超时时间（秒）
  --hotword hotwords.txt    # 热词文件（可选）
```

**JSON 输出格式**：

```json
{
  "success": true,
  "text": "识别出的文本内容",
  "mode": "offline",
  "duration_ms": 1234,
  "audio_file": "input.wav",
  "server": "127.0.0.1:10095",
  "timestamp": [...],
  "error": null
}
```

**错误输出格式**：

```json
{
  "success": false,
  "text": "",
  "error": "连接失败: 连接被拒绝",
  "error_code": 2
}
```

### 3.2 funasr_probe.py — 服务探测脚本

**CLI 接口**：

```bash
# 基础用法
python funasr_probe.py --host 127.0.0.1 --port 10095

# 完整参数
python funasr_probe.py \
  --host 127.0.0.1 \
  --port 10095 \
  --ssl \                      # 启用SSL（默认）
  --level offline_light \      # connect_only / offline_light / twopass_full
  --timeout 5                  # 超时时间（秒）
```

**JSON 输出格式**：

```json
{
  "success": true,
  "server": "127.0.0.1:10095",
  "reachable": true,
  "responsive": true,
  "supports_offline": true,
  "supports_2pass": null,
  "inferred_server_type": "legacy",
  "is_final_semantics": "legacy_true",
  "has_timestamp": true,
  "probe_duration_ms": 1523.4,
  "probe_notes": ["WebSocket连接成功", "离线模式探测成功"]
}
```

### 3.3 funasr_speed_test.py — 速度测试脚本

**设计原则**：
- 精确测量上传速度（MB/s）和转写倍速（x realtime）
- 支持多轮测试取平均值，提高数据可靠性
- 音频源选择：用户指定音频 > assets/test-for-speed.mp3（缺失则报错）
- JSON 结构化输出，与 `funasr_recognize.py` 保持一致的错误处理风格

**CLI 接口**：

```bash
# 自动查找测试音频（默认 SSL 连接）
python funasr_speed_test.py --host 127.0.0.1 --port 10095

# 使用指定音频，3轮测试
python funasr_speed_test.py --host 127.0.0.1 --port 10095 --audio test.wav --rounds 3
```

**JSON 输出格式**：

```json
{
  "success": true,
  "server": "127.0.0.1:10095",
  "mode": "offline",
  "audio_file": "test-for-speed.mp3",
  "audio_size_mb": 0.512,
  "audio_duration_seconds": 15.3,
  "rounds_total": 2,
  "rounds_successful": 2,
  "rounds_failed": 0,
  "average": {
    "upload_time_ms": 125.3,
    "transcribe_time_ms": 580.2,
    "total_time_ms": 812.6,
    "upload_speed_mbps": 4.09,
    "transcribe_speed_x": 26.4
  },
  "round_details": [...]
}
```

**测量方法论**：
- `upload_time`: 从发送第一个音频块到发送 `is_speaking=false` 结束标志
- `transcribe_time`: 从结束标志到收到 `is_complete=True` 的识别结果
- `upload_speed_mbps = audio_size_MB / upload_time_seconds`
- `transcribe_speed_x = audio_duration_seconds / transcribe_time_seconds`

**资产管理**：
- `assets/test-for-speed.mp3` 由用户手动提供（推荐 5-30 秒的短音频）
- 如果默认音频缺失且未指定 `--audio`，脚本返回错误提示联系 Skill 作者

### 3.4 funasr_fileinfo.py — 文件信息查询脚本（2026-02-11 新增）

**设计原则**：
- 纯本地操作，零网络依赖
- 使用 `mutagen` 库解析非 WAV/PCM 格式的音频/视频元数据
- WAV 使用标准库 `wave` 模块精确解析
- PCM 使用默认参数（16kHz, 16bit, mono）估算时长
- 为 Agent 提供转写前的文件预分析能力（解决 Agent 无法获取文件时长的问题）

**CLI 接口**：

```bash
# 查询单个文件
python funasr_fileinfo.py input.wav

# 查询多个文件
python funasr_fileinfo.py file1.wav file2.mp4 file3.m4a

# 使用 --audio 参数
python funasr_fileinfo.py --audio file1.wav --audio file2.mp3
```

**JSON 输出格式**：

```json
{
  "success": true,
  "total_files": 2,
  "parsed_ok": 2,
  "parse_failed": 0,
  "mutagen_available": true,
  "files": [
    {
      "file_name": "input.wav",
      "file_size_bytes": 5749278,
      "file_size_display": "5.5MB",
      "format": "wav",
      "media_type": "audio",
      "supported": true,
      "duration_seconds": 179.48,
      "duration_display": "2分59秒",
      "sample_rate": 16000,
      "channels": 1,
      "parse_method": "wave",
      "error": null
    }
  ],
  "summary": {
    "formats": ["WAV"],
    "total_size_display": "5.5MB",
    "total_duration_seconds": 179.48,
    "total_duration_display": "2分59秒"
  }
}
```

**新增背景**：Agent 在批量转写时无法获取文件时长和格式信息（会错误地回退到 `ffprobe` 等系统工具），
导致预估处理时间计算错误。此脚本填补了 Skill 的文件预分析能力空白。

---

## 四、SKILL.md 设计要点

遵循 `$skill-creator` 规范：

1. **Frontmatter**：name + description（含触发条件）
2. **Body**：<500行，包含 Quick Start + 核心用法 + 参数说明 + 错误处理
3. **渐进披露**：详细协议信息放 `references/protocol_guide.md`
4. **语气**：祈使句/不定式，面向另一个 Claude 实例
5. **不含多余文件**：不生成 README、CHANGELOG 等

---

## 五、lib/ 模块抽取策略

### 5.1 protocol_adapter.py

- **来源**: `src/python-gui-client/protocol_adapter.py`（425行）
- **改动**: 无需改动，纯标准库依赖，直接复制
- **保留全部**: ServerType, RecognitionMode, MessageProfile, ParsedResult, ProtocolAdapter, 便捷函数

### 5.2 server_probe.py

- **来源**: `src/python-gui-client/server_probe.py`（599行）
- **改动**: 导入语句从 `from websocket_compat import` 改为同目录导入（保持不变，因为 lib/ 内部互相导入）
- **保留全部**: ProbeLevel, ServerCapabilities, ServerProbe, 便捷函数

### 5.3 websocket_compat.py

- **来源**: `src/python-gui-client/websocket_compat.py`（83行）
- **改动**: 无需改动
- **保留全部**: connect_websocket 函数

---

## 六、开发计划

### Phase 1：Skill 骨架与核心库（已完成）

| 序号 | 任务 | 预计工作量 | 状态 |
|------|------|-----------|------|
| 1.1 | 创建 Skill 目录结构 | 5分钟 | ✅ 已完成 |
| 1.2 | 复制 V3 核心模块到 lib/ | 10分钟 | ✅ 已完成 |
| 1.3 | 开发 funasr_recognize.py | 30分钟 | ✅ 已完成 |
| 1.4 | 开发 funasr_probe.py | 15分钟 | ✅ 已完成 |
| 1.5 | 编写 SKILL.md | 20分钟 | ✅ 已完成 |
| 1.6 | 编写 references/protocol_guide.md | 15分钟 | ✅ 已完成 |
| 1.7 | 编写测试脚本并执行 | 20分钟 | ✅ 已完成 |

### Phase 1.5：速度测试功能（2026-02-11 新增）

| 序号 | 任务 | 预计工作量 | 状态 |
|------|------|-----------|------|
| 1.5.1 | 创建 assets/ 目录结构 | 5分钟 | ✅ 已完成 |
| 1.5.2 | 开发 funasr_speed_test.py | 30分钟 | ✅ 已完成 |
| 1.5.3 | 更新 SKILL.md 增加速度测试文档 | 15分钟 | ✅ 已完成 |
| 1.5.4 | 更新 protocol_guide.md 增加速度测试方法论 | 10分钟 | ✅ 已完成 |
| 1.5.5 | 用户提供 test-for-speed.mp3 测试资产 | — | ✅ 已完成 |

### Phase 1.6：文件信息查询与工作流优化（2026-02-11 新增）

| 序号 | 任务 | 预计工作量 | 状态 |
|------|------|-----------|------|
| 1.6.1 | 开发 funasr_fileinfo.py | 20分钟 | ✅ 已完成 |
| 1.6.2 | 重写 SKILL.md 工作流（合并为单一流程） | 15分钟 | ✅ 已完成 |
| 1.6.3 | 更新设计方案文档 | 10分钟 | ✅ 已完成 |
| 1.6.4 | mutagen 依赖从可选升级为推荐 | 5分钟 | ✅ 已完成 |

**变更说明**：
- 问题：Agent 执行批量转写时，无法获取文件时长（回退到 ffprobe 失败），导致预估处理时间错误
- 问题：SKILL.md 存在"两套工作流"歧义，Agent 误解为速度测试是独立流程而跳过
- 方案：新增 `funasr_fileinfo.py` 填补文件预分析能力；合并工作流为 6 步标准流程

### Phase 2：优化与验证（后续）

| 序号 | 任务 | 说明 |
|------|------|------|
| 2.1 | Skill 级回归测试 | 离线/2pass/超时/降级 6-10 个用例 |
| 2.2 | 端到端验证 | 在 Cursor Agent 中实际使用 Skill |
| 2.3 | 安装与分发 | 复制到 `~/.cursor/skills/` 或打包 |

### Phase 3：迭代完善（持续）

| 序号 | 任务 | 说明 |
|------|------|------|
| 3.1 | 根据实际使用反馈优化 SKILL.md | 触发词、示例补充 |
| 3.2 | 增加 SRT 字幕输出支持 | 可选功能 |
| 3.3 | 增加批量识别模式 | 支持 .scp 文件列表 |

---

## 七、测试计划

### 7.1 单元测试（离线）

| 测试项 | 验证内容 |
|--------|---------|
| lib/ 模块导入 | 确认三个核心模块可独立导入无报错 |
| funasr_recognize.py --help | 参数解析正确 |
| funasr_probe.py --help | 参数解析正确 |
| JSON 输出格式 | 错误场景输出符合约定格式 |
| 退出码 | 各错误场景退出码正确 |

### 7.2 集成测试（需服务端）

| 测试项 | 验证内容 |
|--------|---------|
| 公网服务探测 | `funasr_probe.py --host www.funasr.com --port 10096` |
| 公网离线识别 | `funasr_recognize.py --host www.funasr.com --port 10096 --audio test.wav` |
| 本地服务探测 | `funasr_probe.py --host 127.0.0.1 --port 10095` |
| 连接失败处理 | 不可达地址的错误输出和退出码 |

---

## 八、与现有项目的关系

- `skills/` 是项目根目录的新增顶级目录，与 `src/`、`docs/`、`tests/` 并列
- `skills/` 中的核心库是 `src/` 的精简副本，**不存在代码依赖关系**
- V3 GUI 版本继续使用 `src/` 下的模块，Skill 使用 `skills/` 下的独立副本
- 后续如 V3 核心模块有重要更新，需手动同步到 `skills/lib/`

---

**文档结束**
