# FunASR GUI Client V3

A Tkinter-based graphical user interface (GUI) client for interacting with FunASR WebSocket services to perform speech recognition. V3 solves protocol differences between new and legacy servers and supports automatic server capability detection.

## ✨ Features

### Core Features
*   **Server Connection Configuration**: Allows users to input the IP address and port of the FunASR WebSocket server.
*   **Automatic Server Detection**: Automatically detects server capabilities (offline/2pass mode support, timestamp capability, protocol version inference).
*   **Protocol Adaptation**: Automatically adapts to protocol differences between new and legacy FunASR servers, solving the `is_final` semantic inconsistency issue.
*   **File Selection**: Supports selecting local audio/video files (such as `.wav`, `.mp3`, `.pcm`, `.mp4`, etc.) or `.scp` list files for recognition.
*   **Multi-mode Recognition**: Supports both offline transcription and real-time recognition (2pass) modes.
*   **Hotword Support**: Optional hotword file selection to improve recognition accuracy for specific domains, supports weighted configuration.

### User Interface
*   **UI Separation**: Recognition results and running logs displayed in separate tabs, provides "Copy Result" and "Clear Result" buttons.
*   **Server Configuration Area**: Server type selection (auto-detect/legacy/new/public test service), recognition mode selection, auto-probe toggles.
*   **Probe Result Display**: Real-time display of server availability, supported modes, capabilities, and inferred server type.
*   **Enhanced Status Management**: StatusManager class manages 5 status colors (success/info/warning/error/processing), refined 8 recognition stages with Emoji icons.
*   **Internationalization Support**: Provides Chinese and English interface switching to meet the needs of users with different language backgrounds.
*   **Real-time Output Display**: Displays status information and final recognition results in real-time within the GUI during the recognition process.

### Advanced Features
*   **SenseVoice Settings**: Supports SenseVoice language selection (auto/zh/en/ja/ko/yue) and SVS ITN toggle (available for new servers).
*   **Advanced Options**: Supports enabling/disabling Inverse Text Normalization (ITN) and SSL connections.
*   **Server Speed Testing**: Provides dedicated button to test server upload speed and transcription speed.
*   **Intelligent Duration Estimation**: Automatically detects the actual playback duration of audio/video files, dynamically calculates transcription estimated time and wait timeout based on speed test results.
*   **Probe Level Selection**: Light probe (recommended, 1-3s) and full probe (3-5s, for 2pass capability detection).
*   **Fallback Strategy**: Uses a fixed 20-minute wait time when unable to obtain audio duration, ensuring all files can be processed normally.

### System Features
*   **Dependency Check and Installation**: Automatically checks and prompts/attempts to install required Python dependencies (`websockets`, `mutagen`), lazy import to avoid import failure in environments without dependencies.
*   **Logging**: Generates independent log files containing detailed operation records and error information for troubleshooting, supports log rotation (5MB, keeps 3 backups).
*   **Configuration Persistence**: Saves last used server IP, port, server type, recognition mode, probe level, advanced options, and hotword file path, automatically loading them on next startup.
*   **Automatic Config Migration**: V2 → V3 config auto-migration, preserves user custom fields, auto-backup original config.
*   **Probe Result Caching**: Loads cached probe results on startup (24-hour validity), reducing repeated probes.
*   **Enhanced Process Management**: Unified safe process termination method, complete terminate→wait→kill flow, complete process exit status logging.

## 🐍 Requirements

*   **Python**: 3.12 or higher.
*   **Tkinter**: Python standard library, usually installed with Python.
*   **Required Python Packages**:
    *   `websockets>=10.0`: For WebSocket communication.
    *   `mutagen>=1.47.0`: For detecting audio/video file duration.
    *   `logging`: For generating log files (Python standard library).
    *   *(Note: The GUI client will attempt to automatically install these dependencies when first connecting or recognizing)*

## 🚀 Installation and Setup

```bash
pipenv install --skip-lock
pipenv install --dev --skip-lock
```

## 🛠️ Usage

1.  **Start GUI**:
    ```bash
    cd path/to/funasr-client-python # Enter project root directory
    pipenv run python src/python-gui-client/funasr_gui_client_v3.py
    ```
2.  **Configure Server**: Enter the IP address and port of the FunASR WebSocket server in the "Server Connection Configuration" area.
3.  **Select Server Type**: Choose from dropdown: "Auto-detect (Recommended)", "Legacy Server", "New Server", or "Public Test Service".
4.  **Auto Probe**: The software will automatically probe server capabilities on startup, or click "Probe Now" button to trigger manually.
5.  **Select Recognition Mode**: Choose "Offline Transcription" or "Real-time Recognition (2pass)" from the dropdown.
6.  **Select File**: Click the "Select Audio/Video File" button to choose the audio or video file you want to recognize.
7.  **Configure Options (Optional)**: Check or uncheck "Enable ITN" and "Enable SSL" as needed.
8.  **Switch Language (Optional)**: Select "中文" or "English" from the language dropdown to switch the interface language.
9.  **Start Recognition**: Click the "Start Recognition" button.
10. **View Results**: Logs and final results during the recognition process will be displayed in the "Running Logs and Results" area. The status bar will show the current status. Recognition result text files will be saved in the `dev/output/` directory.
11. **View Logs**: Click the "Open Log File" button to open the log file and view detailed operation records and error information.
12. **View Recognition Results**: Click the "Open Results Directory" button to directly open the directory where recognition results are saved.

### Lint/Type Check (pipenv)
```bash
pipenv run python src/tools/run_lints.py
pipenv run python src/tools/run_lints.py --fix
pipenv run python src/tools/run_lints.py --mypy-only --paths src
```

## 📁 File Structure

```
funasr-client-python/
├── dev/
│   ├── config/                           # Configuration file directory
│   │   ├── config.json                   # User config file (V3 structure with probe cache)
│   │   ├── flake8.ini                    # Flake8 configuration
│   │   ├── mypy.ini                      # MyPy configuration
│   │   └── pyproject.toml                # Black and isort configuration
│   ├── logs/                             # Log file directory
│   │   └── funasr_gui_client.log         # Program runtime log (with rotation)
│   └── output/                           # Recognition result output directory
│       └── [result_files].txt            # Recognition result text files
├── src/
│   ├── python-gui-client/
│   │   ├── funasr_gui_client_v3.py       # GUI client main program (V3)
│   │   ├── simple_funasr_client.py       # WebSocket client script
│   │   ├── protocol_adapter.py           # Protocol adapter module (V3 new)
│   │   ├── server_probe.py               # Server probe module (V3 new)
│   │   ├── websocket_compat.py           # WebSocket compatibility layer (V3 new)
│   │   ├── config_utils.py               # Config utility functions (V3 new)
│   │   ├── connection_tester.py          # WebSocket connection tester module
│   │   └── requirements.txt              # Python dependencies list
│   └── tools/
│       └── run_lints.py                  # Lint & type check runner
├── docs/                                 # Project documentation (markdown format)
│   ├── v3/                              # V3 version documents
│   │   ├── funasr-python-gui-client-v3-技术实施方案.md
│   │   └── funasr-python-gui-client-v3-项目进展总结-20260128.md
│   ├── v2/                              # V2 version documents
│   │   ├── funasr-python-gui-client-v2-架构设计.md
│   │   ├── funasr-python-gui-client-v2-需求文档.md
│   │   ├── funasr-python-gui-client-v2-UI定义.md
│   │   ├── funasr-python-gui-client-v2-项目管理.md
│   │   └── funasr-python-gui-client-v2-CS协议解析.md
│   └── technical-review/                # Technical review documents
├── tests/                                # Test directory
│   ├── scripts/                         # Test scripts
│   └── reports/                         # Test reports
├── ref/                                  # Reference code and documents (read-only)
│   └── FunASR-main/                     # FunASR official repository reference
├── resources/                            # Resource files
│   └── demo/                            # Demo audio/video files
├── skills/                              # AI Agent Skills
│   └── funasr-speech-recognition/       # FunASR speech recognition Skill
│       ├── SKILL.md                     # Skill entry point (<500 lines)
│       ├── assets/                      # Test audio assets
│       ├── scripts/                     # CLI scripts (recognize, probe, speed test, file info)
│       └── references/                  # Protocol documentation
├── Pipfile                              # Pipenv dependencies definition
├── Pipfile.lock                         # Pipenv locked versions
├── README.md                            # English README (this file)
└── README_cn.md                         # Chinese version README
```

## ⚠️ Known Issues and Limitations

*   Mainly supports FunASR's **offline** and **2pass** recognition modes.
*   Visual configuration for Online mode is not fully implemented yet.
*   Some audio files may have corrupted metadata, in which case the fallback strategy (fixed 20-minute wait time) is automatically enabled.
*   Probe result cache validity is 24 hours, re-probe required after expiration.

## 🔜 Development Plan

### Completed ✅
*   **Protocol Adapter Layer**: Solves is_final semantic difference between new and legacy servers
*   **Server Probe**: Automatic server capability detection
*   **GUI Integration**: Server config area, probe result display, SenseVoice settings
*   **Config Persistence**: V2→V3 config migration, probe result caching
*   **2pass Probe Enhancement**: Probe level selection, automatic mode switching

### In Progress 🟡
*   **End-to-end Integration Testing**: Legacy server verified (2026-02-08), new server pending

### Planned ⏳
*   **Log Cleanup Strategy**: Add automatic cleanup mechanism with "keep N days/max M MB" configuration
*   **Support for Online Mode**: Extend support for more recognition modes
*   **Packaging and Distribution**: Use Nuitka to package as executable file, one-click run without Python environment
*   **Configuration Enhancements**: Common server list, one-click retry, quick SSL toggle

## ✅ Recent Updates

### V3.0.6 - Legacy Server Compatibility Fix (2026-02-08)

*   **Subprocess Launch Fix** (P0): Fixed `AttributeError` crash due to `args=None` in Windows spawn mode child processes
*   **Speed Test Fix** (P0): Fixed transcription completion detection failure ("missing transcription end time")
    - Added `"收到完整结果标志"` pattern matching V3 protocol adapter actual output
    - Added `"识别结果:"` fallback detection and `"等待超时"` timeout detection
    - Enhanced error messages to distinguish "server timeout" from "missing timestamps"
*   **Connection Status Race Fix** (P1): Fixed Tk event queue race condition in speed test / recognition start, flushing pending events after `thread.join()` to ensure `connection_status` is correctly updated
*   **Window Size Optimization**: Default window size changed from 840×720 to 850×950 to ensure status bar visibility
*   **Integration Testing**: Speed test and file recognition verified working with legacy FunASR server

### V3.0 - Protocol Compatibility & Auto-Probe Edition (2026-01-28)

*   **Protocol Adapter Layer** (P0): Core fix for is_final semantic difference causing recognition hang
    - `ProtocolAdapter` class for unified message building, result parsing, and completion detection
    - Supports `ServerType` enum (AUTO/LEGACY/FUNASR_MAIN)
    - Offline mode completes on receiving response, not dependent on is_final field
    - 2pass mode completes on receiving 2pass-offline ✅

*   **Server Probe** (P1): Automatic server capability detection
    - `ServerProbe` class supports connection test, offline light probe, 2pass full probe
    - `ServerCapabilities` dataclass describes server capabilities
    - Supports probe result caching and restoration
    - Protocol semantics inference (legacy_true/always_false) ✅

*   **GUI Integration** (P1): Server configuration area and probe functionality
    - Server type dropdown: auto-detect/legacy/new/public test service
    - Recognition mode dropdown: offline transcription/real-time recognition (2pass)
    - Auto-probe checkboxes and probe now button
    - Real-time probe result display (supports Chinese/English)
    - SenseVoice settings area ✅

*   **Config Management Enhancement** (P2): Config persistence and migration
    - V2 → V3 automatic config migration
    - Probe result caching (24-hour validity)
    - Probe level persistence
    - Atomic config write protection ✅

*   **Bug Fixes**: Fixed 18 issues total (5 P0, 6 P1, 4 P2, 3 P3)

*   **Quality Improvements** (2026-01-28 Update):
    - config_version tolerant conversion (supports string format)
    - V2 config auto-upgrade with silent V3 writeback
    - SVS parameter fallback retry mechanism (graceful degradation)
    - Unified probe timeout error display strategy
    - Repository cleanliness verification (.DS_Store/__pycache__ clean)

### Technical Achievements

*   **New Modules**: `protocol_adapter.py`, `server_probe.py`, `websocket_compat.py`, `config_utils.py`
*   **Test Coverage**: Extensive test coverage with complete test reports
*   **Code Quality**: Lint checks passed (black, isort, flake8, mypy), complete Chinese comments
*   **Acceptance Criteria**: 100% passed (6/6)

## 🤝 Contributing

Welcome to raise issues, report bugs, or contribute code improvements!

## 📄 License

MIT License
