param(
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"

$root = (Resolve-Path $PSScriptRoot).Path
$exePath = Join-Path $root "build\jarvise_launcher.exe"

if (-not (Test-Path $exePath)) {
    throw "Executable not found at $exePath. Run .\rebuild_exe.ps1 first."
}

if ($Arguments -and $Arguments.Count -gt 0) {
    $process = Start-Process -FilePath $exePath -ArgumentList $Arguments -WorkingDirectory $root -PassThru
} else {
    $process = Start-Process -FilePath $exePath -WorkingDirectory $root -PassThru
}

Write-Host "Started jarvise_launcher.exe"
Write-Host "PID: $($process.Id)"
