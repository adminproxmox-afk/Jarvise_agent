$ErrorActionPreference = "Stop"

$env:PYTHONDONTWRITEBYTECODE = "1"
@'
import importlib

modules = [
    "agents.registry",
    "ai.gateway",
    "ai.brain",
    "api.app",
    "automation.launcher",
    "core.actions",
    "core.commands",
    "core.events",
    "core.orchestrator",
    "core.security",
    "core.task_manager",
    "integrations.telegram",
    "memory.store",
    "music.local_player",
    "system.stats",
    "tools.registry",
    "voice.clap",
]

for module in modules:
    importlib.import_module(module)

print("Python imports passed.")
'@ | .\.venv\Scripts\python.exe -
if ($LASTEXITCODE -ne 0) {
  throw "Python import check failed."
}

Push-Location ui
if (-not (Test-Path node_modules)) {
  npm install
}
npm run build
if ($LASTEXITCODE -ne 0) {
  throw "UI build failed."
}
Pop-Location

Write-Host "JARVIS checks passed."
