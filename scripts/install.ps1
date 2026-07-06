param(
  [switch]$WithVoice,
  [switch]$WithAI,
  [switch]$WithDev
)

$ErrorActionPreference = "Stop"

if (-not (Get-Command py -ErrorAction SilentlyContinue)) {
  throw "Python launcher 'py' was not found. Install Python 3.11+ first."
}

function Test-PythonVersion {
  param([string]$Version)
  & py "-$Version" -c "import sys" | Out-Null
  return $LASTEXITCODE -eq 0
}

$pythonArgs = @("-3")
foreach ($version in @("3.13", "3.12", "3.11")) {
  if (Test-PythonVersion $version) {
    $pythonArgs = @("-$version")
    break
  }
}

& py @pythonArgs -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if ($WithVoice) {
  .\.venv\Scripts\python.exe -m pip install -r requirements-voice.txt
}

if ($WithAI) {
  .\.venv\Scripts\python.exe -m pip install -r requirements-ai.txt
}

if ($WithDev) {
  .\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
}

Push-Location ui
npm install
Pop-Location

Write-Host "JARVIS dependencies installed."
