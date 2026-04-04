# Integrated System Notes

`integrated_system/` is built from `system/` and keeps the original pipeline behavior as the default.

## What changed

- Introduced modular TTS providers under `src/services/tts/`.
- Preserved the original local Piper path as the default (`TTS_BACKEND=piper`).
- Added optional hybrid provider (`TTS_BACKEND=hybrid|auto`) that uses ElevenLabs when available and falls back to Piper.
- Extended `/speak` payload to support optional `timestamp` and `language` from Hackbyte's interface.
- Integrated Hackbyte weapon detection into `src/models/weapon_detection/` using `assets/weapon_detection/best.pt`.
- Wired orchestrator support for `ENABLED_MODELS=face_recognition,weapon_detection`.
- **Unified Vision**: when both models are enabled, one `VideoCapture` and one window (`Unified Vision`) feed each frame through face then weapon; overlays are composited on the same frame.

## Why this architecture

- Keeps `system/` execution flow stable and compatible.
- Avoids duplicate speech logic in route handlers by using a provider strategy.
- Supports incremental extension (new TTS providers can be added without changing the speech server).
- Single camera path avoids duplicate device opens and duplicate UI when running face + weapon together.

## Environment knobs

- `TTS_BACKEND`: `piper` | `hybrid` | `auto`
- `ELEVENLABS_API_KEY` (optional)
- `PIPER_MODEL_PATH`, `PIPER_CONFIG_PATH`
- `UNIFIED_CAMERA`: `1` (default) uses one window when both `face_recognition` and `weapon_detection` are enabled; `0` restores two separate capture loops.
- `CAMERA_INDEX` / `MAX_CAMERA_INDEX`: used for unified camera selection (same as face recognition).
