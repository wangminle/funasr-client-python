---
name: funasr-speech-recognition
description: "FunASR speech recognition via WebSocket. Convert audio/video files to text using a FunASR server. Use when: (1) user needs speech-to-text or audio transcription, (2) connecting to a FunASR service for ASR, (3) batch transcribing audio/video files, (4) testing FunASR server connectivity and capabilities, (5) generating subtitles from audio, (6) measuring FunASR server performance/speed, (7) inspecting audio/video file metadata (duration, format, codec). Requires a running FunASR WebSocket server (local Docker or public test service at www.funasr.com:10096) and Python websockets>=10.0."
---

# FunASR Speech Recognition

Perform speech recognition by connecting to a FunASR WebSocket server. Handles protocol differences between legacy and new FunASR server versions automatically.

## Prerequisites

- Python 3.12 (skill scripts compatible with 3.10+)
- `websockets>=10.0` — install with `pip install websockets`
- `mutagen>=1.47.0` — install with `pip install 'mutagen>=1.47.0'` (required for non-WAV/PCM file duration detection)
- A running FunASR server (local or remote)

Check and install dependencies:

```bash
pip show websockets || pip install 'websockets>=10.0'
pip show mutagen || pip install 'mutagen>=1.47.0'
```

## Quick Start

Single file recognition (SSL enabled by default):

```bash
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav
```

Using the public test server:

```bash
python scripts/funasr_recognize.py --host www.funasr.com --port 10096 --audio input.wav
```

If SSL connection fails, try adding `--no-ssl` to fall back to plain WebSocket.

## Core Scripts

### 1. File Info (`scripts/funasr_fileinfo.py`)

Query audio/video file metadata before transcription. Use this to learn file duration, format, and size — essential for estimating processing time and setting proper timeouts.

**Basic usage:**

```bash
python scripts/funasr_fileinfo.py FILE1 [FILE2 ...]
```

**Key parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `files` (positional) | (required) | One or more audio/video file paths |
| `--audio` | (none) | Alternative way to specify files (repeatable: `--audio f1 --audio f2`) |
| `--output` | stdout | Write result to file instead of stdout |
| `--quiet` | false | Suppress log output (stderr) |

**Supported formats:**

| Category | Formats | Duration detection |
|----------|---------|-------------------|
| Audio (native) | WAV | `wave` module (precise, no extra dependency) |
| Audio (native) | PCM | Estimated from file size (assumes 16kHz, 16bit, mono) |
| Audio (mutagen) | MP3, FLAC, OGG, AAC, M4A, WMA, OPUS, AMR, AIFF, AIF | `mutagen` library (precise) |
| Video (mutagen) | MP4, MKV, AVI, MOV, WebM, FLV, WMV, TS, M4V | `mutagen` library (precise) |

**JSON output format:**

```json
{
  "success": true,
  "total_files": 2,
  "parsed_ok": 2,
  "parse_failed": 0,
  "mutagen_available": true,
  "files": [
    {
      "file_name": "meeting.wav",
      "file_path": "/path/to/meeting.wav",
      "file_size_bytes": 5749278,
      "file_size_display": "5.5MB",
      "format": "wav",
      "media_type": "audio",
      "supported": true,
      "duration_seconds": 179.48,
      "duration_display": "2分59秒",
      "sample_rate": 16000,
      "channels": 1,
      "bit_depth": 16,
      "codec": "pcm",
      "bitrate_kbps": null,
      "parse_method": "wave",
      "error": null
    }
  ],
  "summary": {
    "formats": ["WAV"],
    "total_size_display": "5.5MB",
    "total_duration_seconds": 179.48,
    "total_duration_display": "2分59秒"
  },
  "display_text": "📁 2 个文件 | 格式: WAV | 总大小: 5.5MB | 总时长: 2分59秒"
}
```

**Exit codes:** 0=all files parsed, 1=argument error, 2=some files failed to parse.

**Examples:**

```bash
# Single file
python scripts/funasr_fileinfo.py input.wav

# Multiple files (different formats)
python scripts/funasr_fileinfo.py meeting.wav video.mp4 podcast.m4a

# Save to file
python scripts/funasr_fileinfo.py *.wav *.mp4 --output fileinfo.json --quiet
```

### 2. Speech Recognition (`scripts/funasr_recognize.py`)

Convert audio to text. Outputs structured JSON to stdout by default.

**Basic usage:**

```bash
python scripts/funasr_recognize.py --host HOST --port PORT --audio FILE
```

**Key parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--host` | (required) | FunASR server address |
| `--port` | (required) | FunASR server port |
| `--audio` | (required) | Audio file path (.wav, .pcm, .mp3, .mp4, .m4a, etc.), must be non-empty |
| `--mode` | `offline` | Recognition mode: `offline`, `online`, `2pass` |
| `--ssl` / `--no-ssl` | `--ssl` | Enable/disable SSL |
| `--server-type` | `auto` | Server type: `auto`, `legacy`, `funasr_main` |
| `--format` | `json` | Output format: `json`, `text`, `srt` |
| `--output` | stdout | Write result to file instead of stdout |
| `--timeout` | `600` | Recognition timeout in seconds |
| `--hotword` | (none) | Hotword file path |
| `--no-itn` | false | Disable inverse text normalization |
| `--quiet` | false | Suppress log output (stderr) |

**JSON output format:**

```json
{
  "success": true,
  "text": "recognized text content",
  "mode": "offline",
  "audio_file": "input.wav",
  "server": "127.0.0.1:10095",
  "duration_ms": 1234.5,
  "timestamp": [[0, 1000], [1000, 2000]],
  "error": null
}
```

**Error output:**

```json
{
  "success": false,
  "text": "",
  "error": "connection refused",
  "error_code": 2
}
```

**Exit codes:** 0=success, 1=argument error, 2=connection failure, 3=timeout, 4=runtime error.

**Examples:**

```bash
# Plain text output
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio meeting.wav --format text

# SRT subtitles
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio video.mp4 --format srt --output subtitles.srt

# 2pass mode (faster intermediate + accurate final)
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --mode 2pass

# Save JSON to file
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --output result.json

# If SSL fails, fall back to plain WebSocket
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --no-ssl
```

### 3. Speed Test (`scripts/funasr_speed_test.py`)

Measure FunASR server upload speed (MB/s) and transcription speed (x realtime). Run this before batch transcription to establish a performance baseline and calculate expected processing times.

**Basic usage:**

```bash
python scripts/funasr_speed_test.py --host HOST --port PORT
```

**Key parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--host` | (required) | FunASR server address |
| `--port` | (required) | FunASR server port |
| `--audio` | auto-detect | Test audio file path (auto-finds `assets/test-for-speed.mp3`) |
| `--rounds` | `2` | Number of test rounds (averaged) |
| `--mode` | `offline` | Recognition mode: `offline`, `online`, `2pass` |
| `--ssl` / `--no-ssl` | `--ssl` | Enable/disable SSL |
| `--server-type` | `auto` | Server type: `auto`, `legacy`, `funasr_main` |
| `--timeout` | `300` | Per-round timeout in seconds |
| `--output` | stdout | Write result to file |
| `--no-details` | false | Omit per-round details from output |
| `--quiet` | false | Suppress log output (stderr) |

**Audio source:**

1. `--audio FILE` — user-specified file (highest priority)
2. `assets/test-for-speed.mp3` — default Skill asset (auto-detected)
3. If no audio available, returns error with guidance to contact Skill author

**JSON output format:**

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
  "display_text": "✅ 速度测试完成 | 上传速度: 4.09 MB/s, 转写倍速: 26.4x | 成功 2/2 轮"
}
```

**Key metrics:**

| Metric | Unit | Description |
|--------|------|-------------|
| `upload_speed_mbps` | MB/s | Average upload throughput |
| `transcribe_speed_x` | x realtime | How many times faster than realtime (e.g., 30x = 1min audio in 2s) |
| `upload_time_ms` | ms | Time from first audio chunk to end signal |
| `transcribe_time_ms` | ms | Time from end signal to recognition result |

**Exit codes:** 0=success, 1=argument error, 2=connection failure, 3=timeout, 4=runtime error.

**Examples:**

```bash
# Default: 2-round test using assets/test-for-speed.mp3
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095

# 5-round test with custom audio, for more stable benchmarks
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --audio meeting.wav --rounds 5

# Save results to file, suppress logs
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --output speed_result.json --quiet

# If SSL fails, fall back to plain WebSocket
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --no-ssl
```

### 4. Server Probe (`scripts/funasr_probe.py`)

Test FunASR server connectivity and detect capabilities. Always run this first when unsure if the server is available.

**Basic usage:**

```bash
python scripts/funasr_probe.py --host HOST --port PORT
```

**Key parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `--host` | (required) | FunASR server address |
| `--port` | (required) | FunASR server port |
| `--ssl` / `--no-ssl` | `--ssl` | Enable/disable SSL |
| `--level` | `offline_light` | Probe depth: `connect_only`, `offline_light`, `twopass_full` |
| `--timeout` | `5.0` | Probe timeout in seconds |

**Probe levels:**

- `connect_only` — WebSocket handshake only (<1s)
- `offline_light` — Send short silence, check offline support (1-3s, recommended)
- `twopass_full` — Full 2pass capability test (3-15s)

**Output example:**

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
  "display_text": "✅ 服务可用 | 模式: 离线 | 能力: 时间戳 | 类型: 可能旧版（仅供参考）"
}
```

**Exit codes:** 0=server reachable, 1=argument error, 2=server unreachable.

## Workflow

There is ONE standard workflow. Follow ALL steps in order. Do NOT skip steps.

Steps 1–3 are **one-time setup** (run once per session). Steps 4–6 are **per-batch** (repeat for each set of files).

### Step 1 — Check dependencies

```bash
pip show websockets || pip install 'websockets>=10.0'
pip show mutagen || pip install 'mutagen>=1.47.0'
```

### Step 2 — Probe the server

Verify the FunASR server is reachable and responsive:

```bash
python scripts/funasr_probe.py --host HOST --port PORT
```

Check the JSON output: if `"success": true`, proceed. If not, check server address/port and SSL settings.

### Step 3 — Run speed test

Establish a performance baseline for the current server and network conditions. This baseline is reused for all subsequent files.

```bash
python scripts/funasr_speed_test.py --host HOST --port PORT --output /tmp/funasr_speed_result.json
```

From the output, note the `transcribe_speed_x` value:
- **>30x** — excellent, server is fast
- **10x–30x** — good, normal performance
- **<10x** — slow, increase `--timeout` for long audio

**Reusing speed test results:** If `/tmp/funasr_speed_result.json` already exists and was created recently (within the same session or the last few hours), read it directly instead of re-running. Only re-run when the server address changes, network conditions may have shifted, or significant time has elapsed.

---

**Steps 4–6 below can be repeated for each batch of files.**

### Step 4 — Analyze input files

Before transcribing, inspect all target files to learn their duration, format, and size:

```bash
python scripts/funasr_fileinfo.py FILE1 [FILE2 ...] --quiet
```

From the output, note:
- `duration_seconds` — needed to estimate processing time
- `format` and `supported` — confirm the file can be processed
- `file_size_display` — large files (>50MB) may need higher `--timeout`

If a file's `supported` is `false`, it may still work (FunASR server uses FFmpeg internally), but results are not guaranteed.

**Estimating processing time:** Combine file duration (from this step) with the speed baseline (from Step 3):

```
expected_time = duration_seconds / transcribe_speed_x
```

For example: a 10-minute (600s) audio file with 15x speed ≈ 40 seconds processing time. Use this to set `--timeout` (add a 2x safety margin).

### Step 5 — Run recognition

Transcribe each file:

```bash
python scripts/funasr_recognize.py --host HOST --port PORT --audio FILE [--timeout TIMEOUT]
```

For batch processing, loop through files and save results individually:

```bash
python scripts/funasr_recognize.py --host HOST --port PORT --audio FILE1 --output result1.json
python scripts/funasr_recognize.py --host HOST --port PORT --audio FILE2 --output result2.json
```

### Step 6 — Parse results

The JSON output `text` field contains the transcription. Key fields:
- `success` — whether recognition succeeded
- `text` — transcribed text
- `duration_ms` — actual processing time (compare with Step 4 estimate)
- `timestamp` / `stamp_sents` — word/sentence level timestamps (if available)

To process more files, return to **Step 4** with the next batch.

## Common Server Addresses

| Server | Host | Port | SSL | Notes |
|--------|------|------|-----|-------|
| Public test | `www.funasr.com` | `10096` | Yes | Official FunASR test service |
| Local Docker | `127.0.0.1` | `10095` | Yes (default) | SSL enabled by default; add `--no-ssl` only if SSL connection fails |

## Protocol Reference

For details on the FunASR WebSocket protocol, server types, and `is_final` semantics differences, see [references/protocol_guide.md](references/protocol_guide.md).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `error_code: 2` connection refused | Server not running or wrong address | Verify host/port, run probe first |
| `error_code: 3` timeout | Audio too long or server overloaded | Increase `--timeout`, check server load |
| `error_code: 1` empty audio file | Audio file exists but is zero bytes | Use a non-empty audio file; script validates file size before sending |
| Probe shows `reachable` but not `responsive` | Server may not respond to short silence | Normal for some setups, proceed with recognition |
| SSL handshake error | Server does not support SSL or uses incompatible cert | Try `--no-ssl` to fall back to plain WebSocket |
| File info `duration_seconds` is `null` | mutagen not installed or unsupported format | Install mutagen: `pip install mutagen` |
| File info `supported` is `false` | Unknown file extension | May still work if FunASR server supports the format; test with a small sample first |
| Speed test `transcribe_speed_x` is `null` | Cannot determine audio duration | Run `funasr_fileinfo.py` first; install `mutagen` if needed |
| Speed test all rounds failed | Server may be overloaded or unreachable | Run probe first, reduce `--rounds`, increase `--timeout` |
| Speed test "速度测试不可用" | `assets/test-for-speed.mp3` missing | Contact Skill author, or use `--audio` with your own file |
