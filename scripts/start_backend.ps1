$ErrorActionPreference = "Stop"

if (Test-Path .\.env) {
  Get-Content .\.env | ForEach-Object {
    if ($_ -match "^\s*([^#][^=]+)=(.*)$") {
      [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim(), "Process")
    }
  }
}

$python = ".\.venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
  $python = "py"
}

& $python main.py
