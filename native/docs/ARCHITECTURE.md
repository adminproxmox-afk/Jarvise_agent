# JARVIS Native Architecture

The native assistant is a lightweight Win32 background process. It avoids Electron, Qt and Python at runtime. The executable owns microphone capture, clap detection, workspace launch, tray integration, autorun and the cinematic overlay.

## Modules

- `audio`: WASAPI default microphone capture. Captures shared-mode audio on a dedicated MMCSS thread and emits normalized mono float chunks.
- `clap_detection`: double clap detector with RMS, peak and sharpness checks, adaptive noise floor and cooldown protection.
- `config`: self-contained JSON parser and typed `AppConfig` loader.
- `launcher`: workspace launcher for Chrome, AyuGram, VS Code and Android Studio with process checks.
- `spotify`: Spotify deep-link launcher for the configured track, with media-key fallback.
- `system`: logging, registry autorun, process enumeration, startup sound, config hot reload, single-instance guard and tray icon.
- `ui`: Win32/GDI+ topmost overlay with startup animation, rings, waveform and tray menu callbacks.

## Activation Flow

1. `WasapiCapture` streams microphone samples into `ClapDetector`.
2. `ClapDetector` detects two clap-like transients within `double_clap_window_ms`.
3. The UI thread receives an activation message.
4. `OverlayWindow` shows the JARVIS overlay.
5. `StartupSound` plays a configured WAV or cinematic beep fallback.
6. `SpotifyController` launches Spotify, opens the track URI and sends a media play key.
7. `WorkspaceLauncher` starts Chrome, AyuGram, VS Code and Android Studio if they are not already running.

## Stability Choices

- Single instance mutex prevents duplicate microphone listeners.
- App startup is installed under HKCU, so no admin rights are required.
- Config changes are detected every two seconds and applied to clap settings without restart.
- Workspace launch failures are logged and do not crash the assistant.
- The overlay is hidden by default and does not steal focus.
