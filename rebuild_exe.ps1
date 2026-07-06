$ErrorActionPreference = "Stop"

$root = (Resolve-Path $PSScriptRoot).Path
Set-Location $root

$python = Join-Path $root ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    $python = "py"
}

Write-Host "Cleaning old build artifacts..."
Remove-Item -LiteralPath (Join-Path $root "build\jarvise_launcher") -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root "build\jarvise_launcher.exe") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root "dist\jarvise_launcher.exe") -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath (Join-Path $root "dist\jarvise_launcher.py") -Force -ErrorAction SilentlyContinue

Write-Host "Building jarvise_launcher.exe from current source..."
& $python -m PyInstaller --clean --noconfirm (Join-Path $root "jarvise_launcher.spec")

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed."
}

$exePath = Join-Path $root "dist\jarvise_launcher.exe"
if (-not (Test-Path $exePath)) {
    throw "Build finished but the executable was not found at $exePath"
}

$legacyExePath = Join-Path $root "build\jarvise_launcher.exe"
Copy-Item -LiteralPath $exePath -Destination $legacyExePath -Force

$shortcutPath = Join-Path $root "build\jarvise_launcher.exe - Ярлик.lnk"
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $legacyExePath
$shortcut.WorkingDirectory = $root
$shortcut.IconLocation = "$legacyExePath,0"
$shortcut.Save()

$info = Get-Item -LiteralPath $exePath
Write-Host "Build complete: $($info.FullName)"
Write-Host "LastWriteTime: $($info.LastWriteTime)"
Write-Host "Legacy copy updated: $legacyExePath"
Write-Host "Shortcut updated: $shortcutPath"
