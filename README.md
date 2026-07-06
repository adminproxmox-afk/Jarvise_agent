# JARVIS Desktop AI Assistant

Production-style foundation for a Windows desktop AI assistant: clap activated, voice-ready, automation-focused and backed by FastAPI, WebSockets, Electron, React, Tailwind and Framer Motion.

## What Is Included

- Modular backend: `core`, `voice`, `automation`, `music`, `memory`, `system`, `plugins`, `api`, `config`.
- Double clap detector with calibration, adaptive noise floor, cooldown and low-CPU chunked audio loop.
- Startup sequence: cinematic beep fallback, holographic overlay event, voice greeting and workspace launch.
- Workspace launcher for VS Code, Android Studio, Chrome, AyuGram, Discord, terminal, Codex/Cursor, Docker Desktop and local dev server.
- Local music player for files in `music/` with play/pause/resume/volume control through the native Windows media stack.
- Multilingual RU/UK/EN natural command handling: deterministic hot commands still work, but free-form requests can now be planned as tool calls, for example `создай папку reports`, `create file notes.txt with text hello`, or `відкрий chrome`.
- Voice command router examples:
  - `Запусти рабочий режим`
  - `Открой проект`
  - `Включи музыку`
  - `Останови музыку`
  - `Закрой лишнее`
  - `Focus mode`
  - `Открой Telegram`
  - `Выключи компьютер`
  - `Запусти сервер`
- SQLite memory for command history, events and preferences.
- Operator Console UI with Chat, Tasks, Agents, Memory, Models, Tools, Projects, Notifications, Settings and Telegram sections.
- Menu Builder inside Settings for showing, hiding, renaming and reordering sidebar sections, plus adding/removing custom quick actions that run commands, modes, music controls or activation.
- Production refactor: AI Brain -> fuzzy intent parser -> action system -> modules.
- JARVIS-like pyttsx3 voice profile with command response speech.
- Chrome launches as `chrome.exe` without URLs; Telegram launches AyuGram from `C:\AG\AyuGram.exe`.
- AI Gateway with provider registry, free-first routing, persistent global model selection and model discovery for Gemini, Groq, OpenRouter, Ollama, LM Studio and other OpenAI-compatible LLMs.
- Persistent task manager with agent assignment, progress, steps, logs and WebSocket task events.
- Multi-agent foundation: Coding, Research, Desktop, Browser and Automation agents.
- Tools layer with descriptors and guarded execution for filesystem, terminal, browser, Docker, Git, Telegram, VS Code and custom plugins.
- Agentic tool execution from chat, Telegram and UI: the assistant can translate normal language into guarded filesystem, terminal, browser, Docker, Git, Telegram, VS Code and plugin calls.
- Telegram service foundation for `/status`, `/task <id>`, natural command intake and task completion/progress notifications.

## Requirements

- Windows 10/11.
- Python 3.11+ available through `py`.
- Node.js 20+ and npm.
- Microphone access for clap detection.
- Optional: Vosk model, AutoHotkey, Docker Desktop, Cursor/Codex, Android Studio.

## Install

```powershell
cd E:\app\JARVIS
copy .env.example .env
.\scripts\install.ps1
```

Optional voice/STT and AI packs:

```powershell
.\scripts\install.ps1 -WithVoice -WithAI
```

If PyAudio fails to install, install a matching wheel for your Python version or temporarily set `clap.enabled: false` in `config/default.yaml`. Core backend/UI development does not require the optional voice pack.

## Configure

Main config lives in `config/default.yaml`.

For local overrides:

```powershell
copy config\local.example.yaml config\local.yaml
```

Then set:

```powershell
$env:JARVIS_CONFIG="config/local.yaml"
```

Useful fields:

- `workspace.chrome_tabs`: defaults to empty; Chrome is launched without URLs.
- `workspace.apps`: applications and launch commands. Local overrides merge app entries by `id`.
- `clap.energy_threshold`: clap sensitivity.
- `music.library_path`: folder scanned for local tracks.
- `music.default_file`: default track played by “включи музыку”.
- `voice.pyttsx3.preferred_voice_keywords`: installed SAPI voice keywords for the JARVIS-like voice profile.
- `safety.allow_shutdown_command`: enable only if you really want voice shutdown.
- `ai.routing`: automatic task-to-provider routing.
- `ai.free_only`: when true, the gateway avoids paid providers/models unless you explicitly disable that guard.
- `ai.model_selection_path`: persistent global model choice. When one model is selected in the UI, chat, tasks and Telegram all use it.
- `telegram.enabled`, `telegram.bot_token`, `telegram.chat_id`: Telegram command and notification bridge.
- `security.mode`: `safe`, `developer` or `full_control` for guarded tools.
- `tools.allowed_roots`: filesystem/tool paths allowed in `safe` and `developer` modes.

Dangerous tool actions such as delete, shutdown, format and git reset are blocked outside `full_control`. In `full_control`, they still require `confirmed: true` in the tool payload.

## Local Music

Put music files into `music/`. The default config points to:

```powershell
music\The_Clash_-_Should_I_Stay_Or_Should_I_Go_AfishaFm.ru_320_kbps_(mp3.pm).mp3
```

The assistant uses Windows MCI for local playback, so it does not need Spotify OAuth or browser deep links. If MCI cannot play a file, `music.external_fallback: true` opens it in the default Windows media app.

## Run

Terminal 1:

```powershell
.\scripts\start_backend.ps1
```

Terminal 2:

```powershell
.\scripts\start_ui.ps1
```

Backend API: `http://127.0.0.1:8765`

UI dev server: `http://127.0.0.1:5173`

Electron opens automatically from `npm run dev`.

## API

```http
GET  /health
GET  /status
POST /activate
POST /command
GET  /tasks
POST /tasks
GET  /tasks/{task_id}
POST /tasks/{task_id}/cancel
GET  /agents
GET  /models
POST /models/{provider}/test
POST /models/select
POST /models/reset
GET  /tools
POST /tools/{tool}
GET  /memory
POST /memory
GET  /memory/search?q=...
GET  /notifications
GET  /telegram/status
POST /telegram/test
POST /workspace/start
POST /modes/{mode}
GET  /music/status
POST /music/play
POST /music/pause
POST /music/resume
POST /music/stop
WS   /ws
```

Example:

```powershell
Invoke-RestMethod http://127.0.0.1:8765/activate -Method Post -ContentType "application/json" -Body '{"trigger":"manual"}'
```

## Checks

```powershell
.\scripts\check.ps1
```

This compiles Python modules and builds the UI.

## Notes

- The project is intentionally modular; each integration can be replaced without rewriting the orchestrator.
- Missing apps are reported as launch results instead of crashing the startup sequence.
- Free-form AI chat and tool planning are wired through `ai/brain.py`. Configure Gemini/Groq/OpenRouter/Ollama/LM Studio to get GPT-style understanding and real actions beyond deterministic command routing.
- Voice shutdown is blocked by default for safety.
