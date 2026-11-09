# Downloads the official VB-CABLE package used by the installer.
# VB-CABLE is donationware by VB-Audio - https://vb-audio.com/Cable/
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$dest = Join-Path $root 'packaging\vendor\vbcable'
$zip = Join-Path $dest 'VBCABLE_Driver_Pack46.zip'
New-Item -ItemType Directory -Force -Path $dest | Out-Null
if (-not (Test-Path $zip)) {
    Write-Host 'downloading VB-CABLE Driver Pack 46'
    Invoke-WebRequest -Uri 'https://download.vb-audio.com/Download_CABLE/VBCABLE_Driver_Pack46.zip' -OutFile $zip -UseBasicParsing
}
$pack = Join-Path $dest 'pack'
if (Test-Path $pack) { Remove-Item $pack -Recurse -Force }
Expand-Archive -Path $zip -DestinationPath $pack -Force
Write-Host "VB-CABLE ready in $pack"
