# FunASR WebSocket Protocol Guide

## Protocol Overview

FunASR uses WebSocket for audio streaming and recognition. The client sends JSON control messages and binary audio data; the server responds with JSON recognition results. A robust client must not rely only on `is_final`, because its offline semantics differ between server variants.

## Connection

- **Protocol**: `wss://` (SSL) or `ws://` (plain)
- **Subprotocol**: `binary`
- **Default ports**: 10095 (local), 10096 (public test)
- **Practical default**:
  - This Skill defaults to `wss://` (SSL) for all connections
  - Public test service: `wss://www.funasr.com:10096`
  - Local Docker: `wss://127.0.0.1:10095` — if SSL fails, fall back with `--no-ssl`

## Message Flow

Common pattern:

```
Client                              Server
  |-- JSON (start message) ----------->|
  |-- binary (audio chunk 1..N) ------>|
  |-- JSON (end message) ------------->|
  |                                    |
  |<-- JSON (result(s), 1..M messages)-|
```

Notes:
- `offline` often returns one message.
- `online` and `2pass` can return multiple incremental messages.
- `2pass` usually ends with a `mode="2pass-offline"` message.

## Client → Server Messages

### Start Message (JSON)

```json
{
  "mode": "offline",
  "wav_name": "audio.wav",
  "wav_format": "pcm",
  "audio_fs": 16000,
  "is_speaking": true,
  "itn": true,
  "hotwords": "{\"关键词\": 20}",
  "chunk_size": [5, 10, 5],
  "chunk_interval": 10
}
```

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `mode` | string | Yes | `offline`, `online`, or `2pass` |
| `wav_name` | string | Yes | Audio file identifier |
| `wav_format` | string | Yes | `pcm` or `others` |
| `audio_fs` | int | Yes | Sample rate (typically 16000) |
| `is_speaking` | bool | Yes | Always `true` for start |
| `itn` | bool | No | Enable inverse text normalization |
| `hotwords` | string | No | Stringified JSON dict, e.g. `"{\"关键词\": 20}"` |
| `chunk_size` | list | 2pass/online | Chunk configuration `[left, center, right]` |
| `chunk_interval` | int | 2pass/online | Chunk interval in ms |
| `svs_lang` | string | New server | SenseVoice language: auto/zh/en/ja/ko/yue |
| `svs_itn` | bool | New server | SenseVoice ITN switch |

### Audio Data (Binary)

Raw PCM bytes or other audio format bytes. For offline mode, use 64KB chunks. For online/2pass mode, chunk size is calculated from `chunk_size` and `chunk_interval`.

### End Message (JSON)

```json
{"is_speaking": false}
```

## Server → Client Messages

### Recognition Result (JSON)

```json
{
  "mode": "offline",
  "wav_name": "audio.wav",
  "text": "识别出的文字",
  "is_final": true,
  "timestamp": [[0, 1000], [1000, 2000]],
  "stamp_sents": [
    {"text_seg": "识别出的", "start": 0, "end": 1000},
    {"text_seg": "文字", "start": 1000, "end": 2000}
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `mode` | string | Response mode: `offline`, `online`, `2pass-online`, `2pass-offline` |
| `text` | string | Recognized text |
| `is_final` | bool/int/string | Completion flag (must be parsed leniently; **semantics differ by server version**) |
| `timestamp` | list | Word-level timestamps `[[start_ms, end_ms], ...]` |
| `stamp_sents` | list | Sentence-level timestamps with text segments |

## Critical: `is_final` Semantics Difference

This is the most important protocol difference between server versions:

| Server Version | `is_final` in offline mode | Impact |
|---------------|---------------------------|--------|
| **Legacy** | `true` when complete | Works as expected |
| **New (FunASR-main)** | Always `false` | Client hangs waiting for `true` that never comes |

### Solution (built into this skill)

The protocol adapter uses `is_complete` logic instead of relying solely on `is_final`:

1. **is_final=true** → Complete (works for legacy servers)
2. **mode="offline"** → Complete on any response (handles new servers)
3. **mode="2pass-offline"** → Complete (final corrected result received)
4. **stamp_sents present** → Complete (fallback heuristic)

Implementation guidance for third-party clients:
- Coerce `is_final` leniently (`true/false`, `1/0`, `"true"/"false"`)
- Treat offline response arrival itself as a completion signal
- Keep a global timeout to avoid waiting indefinitely on malformed sessions

## Recognition Modes

### Offline Mode (`offline`)

- Send all audio at once, receive one final result
- Best for: file transcription, batch processing
- Typical latency: depends on audio length

### Online Mode (`online`)

- Stream audio in chunks, receive incremental results
- Best for: real-time captioning
- Requires `chunk_size` and `chunk_interval` parameters

### 2pass Mode (`2pass`)

- Combines online (fast, less accurate) and offline (slower, more accurate)
- Returns `2pass-online` results during streaming, then `2pass-offline` final result
- Best for: live scenarios needing both speed and accuracy

## Server Types

| Type | Description | Auto-detection |
|------|-------------|----------------|
| `auto` | Let the adapter infer behavior automatically (recommended) | Based on observed response behavior |
| `legacy` | Original FunASR runtime | `is_final=true` in offline |
| `funasr_main` | New FunASR-main runtime | `is_final=false` in offline |

## Deploying a FunASR Server

### Docker (recommended)

```bash
# Pull and run (CPU runtime image)
docker pull registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.12
docker run -p 10095:10095 -it registry.cn-hangzhou.aliyuncs.com/funasr_repo/funasr:funasr-runtime-sdk-online-cpu-0.1.12

# Or use the official one-click script
# See: https://github.com/modelscope/FunASR
```

This Skill defaults to SSL (`wss://`). If the container does not support SSL, add `--no-ssl` to fall back to plain WebSocket.

### Public Test Server

- Host: `www.funasr.com`
- Port: `10096`
- SSL: Yes
- Note: For testing only, not for production use

## Speed Testing Methodology

The speed test script (`funasr_speed_test.py`) measures two key performance metrics by instrumenting the WebSocket message flow:

### Measurement Points

```
Client                                  Server
  |-- JSON (start message) ------------>|
  |                                     |
  | ┌── upload_start                    |
  | |   binary (chunk 1) ------------->|
  | |   binary (chunk 2) ------------->|
  | |   ...                            |
  | |   binary (chunk N) ------------->|
  | └── JSON (end message) ----------->|
  |     upload_end = transcribe_start   |
  |                                     |
  |                              [processing]
  |                                     |
  |     transcribe_end                  |
  |<--- JSON (recognition result) -----|
```

### Upload Speed

```
upload_speed (MB/s) = audio_size_MB / upload_time_seconds
```

- `upload_time` = time from first audio chunk to end-of-speech message
- Reflects network throughput between client and server
- Not affected by server processing time

### Transcription Speed (Realtime Factor)

```
transcribe_speed_x = audio_duration_seconds / transcribe_time_seconds
```

- `transcribe_time` = time from end-of-speech message to final recognition result
- A value of 30x means: 30 seconds of audio are transcribed in 1 second
- Requires known audio duration (WAV/PCM files or `mutagen` library for MP3)
- Affected by: server hardware (CPU/GPU), model size, audio content complexity

### Multi-Round Testing

When running multiple rounds (`--rounds N`):
- Each round is an independent WebSocket connection + full recognition cycle
- Results are averaged across successful rounds
- Failed rounds are tracked but excluded from averages
- Default is 2 rounds; for more stable results, use `--rounds N` to specify additional rounds

### Test Audio Asset

The speed test uses `assets/test-for-speed.mp3` as the default test audio. If this file is missing, the script reports an error and advises contacting the Skill author. Users can also specify their own audio file via `--audio`.
