# FunASR GUI 客户端 V3

这是一个基于 Tkinter 的图形用户界面 (GUI) 客户端，用于与 FunASR WebSocket 服务进行交互，实现语音识别功能。V3 版本解决了新旧服务端协议差异问题，支持自动探测服务器能力。

## ✨ 功能特性

### 核心功能
*   **服务器连接配置**: 允许用户输入 FunASR WebSocket 服务器的 IP 地址和端口。
*   **服务器自动探测**: 自动检测服务器能力（离线/2pass模式支持、时间戳能力、协议版本推断）。
*   **协议自适应**: 自动适配新旧版本 FunASR 服务端的协议差异，解决 `is_final` 语义不一致问题。
*   **文件选择**: 支持选择本地的音频/视频文件（如 `.wav`, `.mp3`, `.pcm`, `.mp4` 等）或 `.scp` 列表文件进行识别。
*   **多模式识别**: 支持离线转写和实时识别（2pass）两种识别模式。
*   **热词支持**: 可选择热词文件提高特定领域识别准确率，支持带权重配置。

### 用户界面
*   **UI分离**: 识别结果与运行日志分选项卡显示，提供"复制结果"和"清空结果"按钮。
*   **服务端配置区**: 服务端类型选择（自动探测/旧版/新版/公网测试服务）、识别模式选择、自动探测开关。
*   **探测结果展示**: 实时显示服务器可用性、支持模式、能力特征和推断的服务端类型。
*   **状态管理增强**: StatusManager类管理5种状态颜色（成功/信息/警告/错误/处理中），细化识别8个阶段提示+Emoji图标。
*   **国际化支持**: 提供中英文界面切换功能，满足不同语言背景用户的需求。
*   **实时输出显示**: 在 GUI 中实时显示识别过程中的状态信息和最终识别结果。

### 高级功能
*   **SenseVoice设置**: 支持 SenseVoice 语种选择（auto/zh/en/ja/ko/yue）和 SVS ITN 开关（新版服务可用）。
*   **高级选项**: 支持启用/禁用逆文本标准化 (ITN) 和 SSL 连接。
*   **服务器速度测试**: 提供专用按钮测试服务器的上传速度和转写速度。
*   **智能时长预估**: 自动检测音频/视频文件的真实播放时长，根据速度测试结果动态计算转写预估时间和等待超时时长。
*   **探测级别选择**: 轻量探测（推荐，1-3秒）和完整探测（3-5秒，用于2pass能力检测）。
*   **兜底处理策略**: 当无法获取音频时长时，使用固定20分钟等待时长，确保所有文件都能正常处理。

### 系统功能
*   **依赖检查与安装**: 自动检查并提示/尝试安装所需的 Python 依赖包 (`websockets`, `mutagen`)，延迟导入避免无依赖环境导入失败。
*   **日志记录**: 生成独立的日志文件，包含详细的操作记录和错误信息，便于问题排查，支持日志轮转（5MB，保留3个备份）。
*   **配置持久化**: 保存上次使用的服务器IP、端口、服务端类型、识别模式、探测级别、高级选项和热词文件路径，下次启动时自动加载。
*   **配置自动迁移**: V2 → V3 配置自动迁移，保留用户自定义字段，自动备份原配置。
*   **探测结果缓存**: 启动时加载缓存的探测结果（24小时有效期），减少重复探测。
*   **进程管理增强**: 统一的进程安全终止方法，terminate→wait→kill完整流程，完整的进程退出状态日志记录。

## 🐍 环境要求

*   **Python**: 3.12 或更高版本。
*   **Tkinter**: Python 标准库，通常随 Python 安装。
*   **必要的 Python 包**:
    *   `websockets>=10.0`: 用于 WebSocket 通信。
    *   `mutagen>=1.47.0`: 用于检测音频/视频文件时长。
    *   `logging`: 用于生成日志文件（Python 标准库）。
    *   *(注意: GUI 客户端会在首次连接或识别时尝试自动安装这些依赖)*

## 🚀 安装与设置（pipenv）

```bash
pipenv install --skip-lock
pipenv install --dev --skip-lock
```

## 🛠️ 使用方法

1.  **启动 GUI**:
    ```bash
    cd path/to/funasr-client-python # 进入项目根目录
    pipenv run python src/python-gui-client/funasr_gui_client_v3.py
    ```
2.  **配置服务器**: 在 "服务器连接配置" 区域输入 FunASR WebSocket 服务器的 IP 地址和端口。
3.  **选择服务端类型**: 从下拉框选择"自动探测（推荐）"、"旧版服务端"、"新版服务端"或"公网测试服务"。
4.  **自动探测**: 软件启动后会自动探测服务器能力，也可点击"立即探测"按钮手动触发。
5.  **选择识别模式**: 从下拉框选择"离线转写"或"实时识别(2pass)"。
6.  **选择文件**: 点击 "选择音/视频文件" 按钮，选择您要识别的音频或视频文件。
7.  **配置选项 (可选)**: 根据需要勾选或取消勾选 "启用 ITN" 和 "启用 SSL"。
8.  **切换语言 (可选)**: 从语言下拉框中选择"中文"或"English"来切换界面语言。
9.  **开始识别**: 点击 "开始识别" 按钮。
10. **查看结果**: 识别过程中的日志和最终结果将显示在 "运行日志与结果" 区域。状态栏会显示当前状态。识别结果文本文件将保存在 `dev/output/` 目录下。
11. **查看日志**: 点击 "打开日志文件" 按钮可以打开日志文件，查看详细的操作记录和错误信息。
12. **查看识别结果**: 点击 "打开结果目录" 按钮可以直接打开保存识别结果的目录。

### 代码检查（pipenv）
```bash
pipenv run python src/tools/run_lints.py
pipenv run python src/tools/run_lints.py --fix
pipenv run python src/tools/run_lints.py --mypy-only --paths src
```

## 📁 文件结构

```
funasr-client-python/
├── dev/
│   ├── config/                           # 配置文件目录
│   │   ├── config.json                   # 用户配置文件（V3结构，含探测缓存）
│   │   ├── flake8.ini                    # Flake8配置
│   │   ├── mypy.ini                      # MyPy配置
│   │   └── pyproject.toml                # Black和isort配置
│   ├── logs/                             # 日志文件目录
│   │   └── funasr_gui_client.log         # 程序运行日志（支持轮转）
│   └── output/                           # 识别结果输出目录
│       └── [识别结果文件].txt            # 识别结果文本文件
├── src/
│   ├── python-gui-client/
│   │   ├── funasr_gui_client_v3.py       # GUI 客户端主程序 (V3)
│   │   ├── simple_funasr_client.py       # WebSocket 客户端脚本
│   │   ├── protocol_adapter.py           # 协议适配层模块 (V3新增)
│   │   ├── server_probe.py               # 服务探测器模块 (V3新增)
│   │   ├── websocket_compat.py           # WebSocket兼容层 (V3新增)
│   │   ├── config_utils.py               # 配置工具函数 (V3新增)
│   │   ├── connection_tester.py          # WebSocket 连接测试模块
│   │   └── requirements.txt              # Python依赖列表
│   └── tools/
│       └── run_lints.py                  # Lint 与类型检查脚本
├── docs/                                 # 项目文档（markdown格式）
│   ├── v3/                              # V3版本文档
│   │   ├── funasr-python-gui-client-v3-技术实施方案.md
│   │   └── funasr-python-gui-client-v3-项目进展总结-20260128.md
│   ├── v2/                              # V2版本文档
│   │   ├── funasr-python-gui-client-v2-架构设计.md
│   │   ├── funasr-python-gui-client-v2-需求文档.md
│   │   ├── funasr-python-gui-client-v2-UI定义.md
│   │   ├── funasr-python-gui-client-v2-项目管理.md
│   │   └── funasr-python-gui-client-v2-CS协议解析.md
│   └── technical-review/                # 技术评审文档
├── tests/                                # 测试目录
│   ├── scripts/                         # 测试脚本
│   └── reports/                         # 测试报告
├── ref/                                  # 参考代码和文档（只读）
│   └── FunASR-main/                     # FunASR官方仓库参考
├── resources/                            # 资源文件
│   └── demo/                            # Demo音视频文件
├── skills/                              # AI Agent Skills
│   └── funasr-speech-recognition/       # FunASR 语音识别 Skill
│       ├── SKILL.md                     # Skill 入口指令文件（<500行）
│       ├── assets/                      # 测试音频资产
│       ├── scripts/                     # CLI 脚本（识别、探测、速度测试、文件信息）
│       └── references/                  # 协议参考文档
├── Pipfile                              # Pipenv依赖定义
├── Pipfile.lock                         # Pipenv锁定版本
├── README.md                            # 英文README
└── README_cn.md                         # 中文README（本文件）
```

## ⚠️ 已知问题与限制

*   主要支持 FunASR 的 **离线 (offline)** 和 **2pass** 识别模式。
*   Online 模式的可视化配置暂未完全实现。
*   部分音频文件的元数据可能损坏，此时会自动启用兜底策略（固定20分钟等待时长）。
*   探测结果缓存有效期为24小时，超时后需要重新探测。

## 🔜 开发计划

### 已完成 ✅
*   **协议适配层**: 解决新旧服务端is_final语义差异
*   **服务探测器**: 自动探测服务器能力
*   **GUI集成**: 服务端配置区、探测结果展示、SenseVoice设置
*   **配置持久化**: V2→V3配置迁移、探测结果缓存
*   **2pass探测增强**: 探测级别选择、自动模式切换

### 进行中 🟡
*   **端到端集成测试**: 旧版服务器已验证通过（2026-02-08），新版服务器待测试

### 计划中 ⏳
*   **日志清理策略**: 增加"保留N天/最大M MB"的自动清理机制
*   **支持 Online 模式**: 扩展支持更多识别模式
*   **打包分发**: 使用Nuitka打包成可执行文件，一键运行无需Python环境
*   **配置功能增强**: 常用服务器列表、一键重试、快速切换SSL

## ✅ 最近更新

### V3.0.6 - 旧版服务器兼容修复 (2026-02-08)

*   **子进程启动修复** (P0): 修复 Windows spawn 模式下子进程 `args=None` 导致 `AttributeError` 崩溃
*   **速度测试修复** (P0): 修复 V3 转写完成标志字符串不匹配导致"未能获取到转写结束时间"
    - 新增 `"收到完整结果标志"` 匹配 V3 协议适配层实际输出
    - 新增 `"识别结果:"` 备用检测和 `"等待超时"` 超时检测
    - 增强错误信息，区分"服务器超时"与"缺少时间点"
*   **连接状态竞态修复** (P1): 修复速度测试/开始识别时 Tk 事件队列竞态条件，`thread.join()` 后刷新事件队列确保 `connection_status` 正确更新
*   **窗口尺寸优化**: 默认窗口从 840×720 调整为 850×950，确保状态栏可见
*   **集成测试**: 旧版 FunASR 服务器环境下速度测试和文件识别均验证通过

### V3.0 - 协议兼容与自动探测版 (2026-01-28)

*   **协议适配层** (P0): 核心修复，解决新旧版本is_final语义差异导致的识别卡死问题
    - `ProtocolAdapter` 类统一处理消息构建、结果解析和结束判定
    - 支持 `ServerType` 枚举（AUTO/LEGACY/FUNASR_MAIN）
    - 离线模式收到回包即结束，不依赖is_final字段
    - 2pass模式收到2pass-offline即结束 ✅

*   **服务探测器** (P1): 自动检测服务器能力
    - `ServerProbe` 类支持连接测试、离线轻量探测、2pass完整探测
    - `ServerCapabilities` 数据类描述服务器能力
    - 支持探测结果缓存和恢复
    - 协议语义推断（legacy_true/always_false） ✅

*   **GUI集成** (P1): 服务端配置区域和探测功能
    - 服务端类型下拉框：自动探测/旧版/新版/公网测试服务
    - 识别模式下拉框：离线转写/实时识别(2pass)
    - 自动探测复选框和立即探测按钮
    - 探测结果实时展示（支持中英文）
    - SenseVoice设置区域 ✅

*   **配置管理增强** (P2): 配置持久化与迁移
    - V2 → V3 配置自动迁移
    - 探测结果缓存（24小时有效期）
    - 探测级别持久化
    - 配置写入原子性保护 ✅

*   **Bug修复**: 共修复18个问题（5个P0、6个P1、4个P2、3个P3）

*   **质量改进** (2026-01-28 更新):
    - config_version 宽容转换（支持字符串格式）
    - V2 配置自动升级并静默写回 V3
    - SVS 参数降级重试机制（优雅降级）
    - 统一探测超时的错误展示策略
    - 仓库洁净度验证（.DS_Store/__pycache__ 已清理）

### 技术成果

*   **新增模块**: `protocol_adapter.py`、`server_probe.py`、`websocket_compat.py`、`config_utils.py`
*   **测试覆盖**: 316个单元测试通过，测试报告齐全
*   **代码质量**: Lint检查通过（black, isort, flake8, mypy），中文注释完整
*   **验收标准**: 100% 通过 (6/6)

## 🤝 贡献

欢迎提出问题、报告错误或贡献代码改进！

## 📄 许可证

MIT License
