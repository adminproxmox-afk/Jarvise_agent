# Native Roadmap

## Phase 1: Current MVP

- Buildable VS2022/CMake project.
- Win32 background app with tray icon.
- HKCU Run autorun installer.
- WASAPI microphone capture.
- Double clap activation.
- Spotify track launch.
- Workspace launcher for Chrome, AyuGram, VS Code and Android Studio.
- Futuristic GDI+ overlay.
- JSON config and hot reload.
- File logging.

## Phase 2: Production Hardening

- Signed installer and update channel.
- Tray settings window for sensitivity calibration.
- Per-device microphone selection.
- Startup task fallback for machines where registry startup is managed by policy.
- More detailed telemetry in local logs.
- Safer Spotify control via Spotify Web API OAuth when credentials are provided.

## Phase 3: JARVIS Experience

- Voice command layer using local Whisper/Vosk service or Windows speech APIs.
- Window layout automation.
- Focus/coding/gaming modes.
- Animated tray status.
- Optional Direct2D/DirectComposition overlay renderer.
- Plugin bridge to the existing Python/FastAPI assistant.
