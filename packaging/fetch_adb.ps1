# Fetch Google's platform-tools so the Windows build can bundle `adb.exe`
# (used for USB mode: adb reverse tcp:8787 tcp:8787).
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $PSScriptRoot 'vendor\adb'
$zip = Join-Path $env:TEMP 'platform-tools.zip'
$tmp = Join-Path $env:TEMP 'platform-tools-extract'

New-Item -ItemType Directory -Force -Path $dest | Out-Null
if (Test-Path (Join-Path $dest 'adb.exe')) {
    Write-Host "adb already vendored"
    exit 0
}

Write-Host "Downloading platform-tools..."
Invoke-WebRequest -Uri 'https://dl.google.com/android/repository/platform-tools-latest-windows.zip' -OutFile $zip -UseBasicParsing
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path $zip -DestinationPath $tmp -Force

foreach ($f in @('adb.exe', 'AdbWinApi.dll', 'AdbWinUsbApi.dll')) {
    Copy-Item (Join-Path $tmp "platform-tools\$f") (Join-Path $dest $f) -Force
}
Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "adb vendored into packaging/vendor/adb"
