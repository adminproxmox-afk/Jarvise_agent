# JARVIS Native Windows Assistant

Native C++20 Windows desktop assistant that runs in the background, listens for two claps and launches the configured workspace.

## Features

- Builds to a standalone `JARVIS.exe`.
- Starts with Windows using `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`.
- Runs hidden in the system tray.
- Captures microphone audio with WASAPI.
- Detects two claps with noise filtering, adjustable sensitivity and cooldown.
- Starts Spotify and opens `The Clash - Should I Stay or Should I Go`.
- Starts Chrome with `chrome.exe` only, no URLs and no extra tabs.
- Starts `C:\AG\AyuGram.exe`.
- Starts VS Code and Android Studio.
- Shows a futuristic JARVIS-style overlay.
- Supports `config\config.json` hot reload.
- Writes logs to `logs\jarvis-native.log`.

## Dependencies

- Visual Studio 2022.
- Workload: Desktop development with C++.
- Windows 10/11 SDK.
- CMake tools for Visual Studio.

No Qt, Node, Python or external C++ packages are required for the native assistant.

## Build

From `E:\app\JARVIS`:

```powershell
.\native\scripts\build.ps1
```

Manual CMake:

```powershell
cd E:\app\JARVIS\native
cmake -S . -B build -G "Visual Studio 17 2022" -A x64
cmake --build build --config Release
```

Output:

```text
native\build\Release\JARVIS.exe
```

## Run

```powershell
.\native\build\Release\JARVIS.exe
```

On first run it installs itself into HKCU Run if `assistant.enable_autorun` is `true`.

Right-click the tray icon for:

- Launch workspace
- Show JARVIS overlay
- Reload config
- Exit

## Configuration

Edit:

```text
native\build\Release\config\config.json
```

Source default:

```text
native\config\config.json
```

Important fields:

- `clap.sensitivity`: lower means more sensitive. Start around `0.18`.
- `startup.sound_path`: optional WAV path.
- `spotify.track_uri`: default track deep link.
- `workspace.chrome.command`: must remain `chrome.exe` if you want Chrome to restore its own tabs.
- `workspace.ayugram.command`: fixed to `C:\AG\AyuGram.exe`.

## Notes

- Chrome is launched without URLs by design.
- If Spotify deep linking opens the track but does not start playback on a given client version, keep `spotify.send_media_play_key` enabled.
- If the microphone is unavailable, the app stays in tray and logs the audio startup error.
