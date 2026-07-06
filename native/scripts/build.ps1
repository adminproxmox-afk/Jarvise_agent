$ErrorActionPreference = "Stop"

$cmake = Get-Command cmake -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Source -First 1
if (-not $cmake) {
  $vsCmake = "C:\Program Files\Microsoft Visual Studio\2022\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
  if (Test-Path $vsCmake) {
    $cmake = $vsCmake
  }
}

if (-not $cmake) {
  throw "CMake was not found. Install Visual Studio 2022 with C++ Desktop Development and CMake tools."
}

Push-Location (Join-Path $PSScriptRoot "..")
& $cmake -S . -B build -G "Visual Studio 17 2022" -A x64
& $cmake --build build --config Release
Pop-Location

Write-Host "Built native\build\Release\JARVIS.exe"
