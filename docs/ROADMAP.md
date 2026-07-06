# Roadmap

## Phase 1: MVP Foundation

- Modular FastAPI backend.
- Double clap detection with calibration and cooldown.
- Voice TTS layer with pyttsx3 and ElevenLabs hook.
- Command parser for core Russian and English commands.
- Workspace autostart from YAML config.
- Local music playback from the `music/` library.
- SQLite memory for preferences and command history.
- Electron React UI with WebSocket event stream.

## Phase 2: Assistant Intelligence

- OpenAI/Ollama tool-calling agent for natural desktop commands.
- Project registry with per-project startup tasks.
- Voice confirmation for dangerous actions.
- Better STT streaming with Vosk partial results and Whisper fallback.
- Semantic command memory and habit learning.
- Local playlist/folder picker and audio device health panel in UI.

## Phase 3: Windows Control

- Signed AutoHotkey script library.
- Window layout profiles.
- Notification and focus assist integration through supported Windows APIs.
- Process health monitor and auto-recovery.
- Installer, tray icon and auto-start service.

## Phase 4: JARVIS Expansion

- ESP32/Arduino bridge over serial or MQTT.
- Smart home adapters.
- OBS and Stream Deck plugins.
- Mobile companion app.
- Face recognition and presence detection.
- Scheduling and proactive workspace routines.
