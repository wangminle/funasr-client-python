---
name: funasr-speech-recognition
description: "FunASR speech recognition via WebSocket. Convert audio/video files to text using a FunASR server. Use when: (1) user needs speech-to-text or audio transcription, (2) connecting to a FunASR service for ASR, (3) batch transcribing audio/video files, (4) testing FunASR server connectivity and capabilities, (5) generating subtitles from audio, (6) measuring FunASR server performance/speed. Requires a running FunASR WebSocket server (local Docker or public test service at www.funasr.com:10096) and Python websockets>=10.0."
---

# FunASR Speech Recognition

Perform speech recognition by connecting to a FunASR WebSocket server. Handles protocol differences between legacy and new FunASR server versions automatically.

## Prerequisites

- Python 3.10+
- `websockets>=10.0` — install with `pip install websockets`
- Optional: `mutagen` (for MP3 duration parsing in speed tests)
- A running FunASR server (local or remote)

Check availability first:

```bash
pip show websockets || pip install 'websockets>=10.0'
```

## Quick Start

Single file recognition on local Docker server (most setups are non-SSL):

```bash
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --no-ssl
```

Using the public test server:

```bash
python scripts/funasr_recognize.py --host www.funasr.com --port 10096 --audio input.wav
```

If your local server is configured with TLS/WSS, remove `--no-ssl`.

## Core Scripts

### 1. Speech Recognition (`scripts/funasr_recognize.py`)

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
| `--audio` | (required) | Audio file path (.wav, .pcm, .mp3, etc.), must be non-empty |
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
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio meeting.wav --format text --no-ssl

# SRT subtitles
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio video.mp4 --format srt --output subtitles.srt --no-ssl

# 2pass mode (faster intermediate + accurate final)
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --mode 2pass --no-ssl

# Without SSL
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --no-ssl

# Save JSON to file
python scripts/funasr_recognize.py --host 127.0.0.1 --port 10095 --audio input.wav --output result.json --no-ssl
```

### 2. Speed Test (`scripts/funasr_speed_test.py`)

Measure FunASR server upload speed (MB/s) and transcription speed (x realtime). Use this to benchmark server performance before production use.

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
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --no-ssl

# 5-round test with custom audio
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --audio meeting.wav --rounds 5 --no-ssl

# Save results to file, suppress logs
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --output speed_result.json --quiet --no-ssl

# Test without SSL
python scripts/funasr_speed_test.py --host 127.0.0.1 --port 10095 --no-ssl
```

### 3. Server Probe (`scripts/funasr_probe.py`)

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

Recommended workflow for transcribing audio:

1. **Probe the server** to verify it's available:
   ```bash
   python scripts/funasr_probe.py --host HOST --port PORT
   ```
2. **Check the probe result** — if `success` is `true`, proceed.
3. **Run recognition**:
   ```bash
   python scripts/funasr_recognize.py --host HOST --port PORT --audio FILE
   ```
4. **Parse the JSON output** — the `text` field contains the transcription.

### Performance benchmarking workflow:

1. **Probe the server** (same as above).
2. **Run speed test** to measure performance:
   ```bash
   python scripts/funasr_speed_test.py --host HOST --port PORT --rounds 3
   ```
3. **Interpret results** — `transcribe_speed_x` shows how many times faster than realtime. Values >10x are good; >30x is excellent.

## Common Server Addresses

| Server | Host | Port | SSL | Notes |
|--------|------|------|-----|-------|
| Public test | `www.funasr.com` | `10096` | Yes | Official FunASR test service |
| Local Docker | `127.0.0.1` | `10095` | Usually No | Add `--no-ssl` unless your server is configured with TLS |

## Protocol Reference

For details on the FunASR WebSocket protocol, server types, and `is_final` semantics differences, see [references/protocol_guide.md](references/protocol_guide.md).

## Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| `error_code: 2` connection refused | Server not running or wrong address | Verify host/port, run probe first |
| `error_code: 3` timeout | Audio too long or server overloaded | Increase `--timeout`, check server |
| `error_code: 1` empty audio file | Audio file exists but is zero bytes | Use a non-empty audio file; script validates file size before sending |
| Probe shows `reachable` but not `responsive` | Server may not respond to short silence | Normal for some setups, proceed with recognition |
| SSL error | Server uses self-signed cert | Default config handles this; if issues persist, try `--no-ssl` |
| Speed test `transcribe_speed_x` is `null` | Cannot determine audio duration (non-WAV/PCM format without mutagen) | Use WAV/PCM file, or install `mutagen` (`pip install mutagen`) |
| Speed test all rounds failed | Server may be overloaded or unreachable | Run probe first, reduce `--rounds`, increase `--timeout` |
| Speed test "速度测试不可用" | `assets/test-for-speed.mp3` missing | Contact Skill author, or use `--audio` with your own file |
