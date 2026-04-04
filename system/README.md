# Multi-model + Speech Router

This repo is structured to support **multiple perception models** (face recognition, future models) that emit **structured events** into a shared **Speech Router**. The Speech Router applies **dedupe/cooldowns/priorities** and performs **offline TTS** using Piper.

## Project layout
- `src/models/`: model plugins (each model is isolated)
- `src/speech/`: speech router API + offline TTS backend
- `src/core/`: shared schemas (events)
- `scripts/`: runnable entrypoints
- `assets/faces/`: face DB images (DeepFace)
- `assets/tts_models/`: Piper `.onnx` + `.json`

## Run

### 1) Start the speech router (offline TTS)

```bash
. ./.venv/bin/activate
python scripts/run_speech.py
```

Environment overrides:
- `SPEECH_HOST` (default `0.0.0.0`)
- `SPEECH_PORT` (default `8000`)
- `SPEECH_DISABLE_PLAYBACK=1` (disables audio playback; useful for CI/testing)
- `PIPER_MODEL_PATH` (default `assets/tts_models/en_US-lessac-medium.onnx`)
- `PIPER_CONFIG_PATH` (default `assets/tts_models/en_US-lessac-medium.onnx.json`)

### 2) Run face recognition model (sends events to speech router)

```bash
. ./.venv/bin/activate
python scripts/run_face.py
```

List cameras:

```bash
python scripts/run_face.py --list-cameras
```

Runtime controls:
- Press `c` to switch camera
- Press `q` to quit

Environment overrides:
- `FACE_DB_PATH` (default `./assets/faces`)
- `SPEECH_ROUTER_URL` (default `http://127.0.0.1:8000`)
- `CAMERA_INDEX` (default `0`)
- `MAX_CAMERA_INDEX` (default `10`)

### 3) Run orchestrator (multiple models in one process)

```bash
. ./.venv/bin/activate
ENABLED_MODELS=face_recognition python scripts/run_orchestrator.py
```

## Speech Router API

### `POST /speak` (backwards compatible)

```bash
curl -X POST http://127.0.0.1:8000/speak \
  -H "Content-Type: application/json" \
  -d '{"text":"hello"}'
```

### `POST /event` (recommended)

```bash
curl -X POST http://127.0.0.1:8000/event \
  -H "Content-Type: application/json" \
  -d '{
    "source":"face_recognition",
    "type":"person_distance",
    "message":"Devesh is very close",
    "priority":0,
    "dedupe_key":"face:devesh:very_close",
    "cooldown_s":10
  }'
```

