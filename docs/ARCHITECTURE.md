# JARVIS Architecture

JARVIS is split into independent runtime modules connected through an async event bus. The backend owns hardware, automation, memory, AI and integration logic. The desktop UI consumes state through REST and a WebSocket event stream.

## Runtime Flow

1. `main.py` starts FastAPI from `api/app.py`.
2. The app lifespan connects SQLite memory, starts the orchestrator and arms clap detection.
3. `voice/clap.py` listens in a background thread and calls `JarvisOrchestrator.activate()` after a double clap.
4. The orchestrator starts the persistent task manager and optional Telegram polling/notification loops.
5. The orchestrator plays startup audio, emits overlay events, speaks a greeting and launches the configured workspace.
6. UI receives `JarvisEvent` messages over `/ws` and renders the operator console.

## Module Boundaries

- `api`: FastAPI app, REST routes and WebSocket event stream.
- `core`: event bus, action system, command intent routing and orchestration.
- `ai`: AI Brain and AI Gateway with auto-routing across OpenAI, Claude, Gemini, DeepSeek, Groq, OpenRouter, Ollama, LM Studio and local OpenAI-compatible models.
- `agents`: Coding, Research, Desktop, Browser and Automation agents.
- `voice`: clap detection, STT and TTS providers.
- `automation`: app launcher, AutoHotkey bridge and Windows system actions.
- `music`: local Windows music playback from the `music/` library.
- `memory`: SQLite preferences, command history, event history, long-term memory and task records.
- `system`: sound feedback and system metrics.
- `tools`: guarded tool registry for filesystem, terminal, browser, Docker, Git, Telegram, VS Code and plugins.
- `integrations`: external bridges such as Telegram.
- `plugins`: plugin loading foundation for future extensions.
- `config`: YAML settings loader with environment variable expansion.
- `ui`: Electron, React, Tailwind and Framer Motion operator console.

## Extension Points

- Add wake-word detection as a new `voice` service that publishes `voice.wake_word`.
- Add ESP32 or smart home support as a plugin that subscribes to the event bus.
- Add OBS or Stream Deck integrations as plugin packages under `plugins/<name>/plugin.py`.
- Add new actions in `core/actions.py` and expose them through `core/commands.py` or the AI provider.

## Command Path

```text
UI / voice
  -> JarvisBrain
  -> AIGateway task classifier / provider router
  -> VoiceCommandRouter fuzzy intent parser
  -> ActionSystem
  -> workspace / music / system / voice modules
  -> EventBus
  -> WebSocket UI
```

High-frequency telemetry such as `system.stats` is delivered live but not retained in event replay history, which keeps reconnects fast and prevents the console from feeling like a fake log dump.

## Operator Task Path

```text
Desktop UI / Telegram / chat command
  -> JarvisOrchestrator
  -> TaskManager
  -> AgentRegistry
  -> selected agent
  -> Tools layer
  -> task progress persisted in SQLite
  -> EventBus / WebSocket / Telegram notification
```

The task manager is backend-owned, so tasks continue when the desktop window is closed. If the backend process itself restarts, unfinished records are preserved and marked as interrupted instead of being lost.

## Tool Security

Tools resolve filesystem paths through configured `tools.allowed_roots` in `safe` and `developer` modes. `full_control` can address arbitrary paths, but destructive operations still return `requires_confirmation` until the caller sends `confirmed: true`.

The Tools page includes an execution runner that sends JSON payloads to `/tools/{tool}`, so supported actions can be tested from the desktop UI without adding a custom frontend for each integration.
