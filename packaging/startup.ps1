param(
    [string]$Exe = "$env:LOCALAPPDATA\DeskGadget\DeskGadget.exe",
    [string]$TaskName = "DeskGadget",
    [switch]$Uninstall
)

# Starts the DeskGadget desktop app at Windows login so the phone and the Car
# Thing always find a running server. Per-user, no UAC.
#
#   powershell -ExecutionPolicy Bypass -File packaging\startup.ps1
#   powershell -ExecutionPolicy Bypass -File packaging\startup.ps1 -Uninstall

$ErrorActionPreference = "Stop"

if ($Uninstall) {
    & schtasks /Delete /TN $TaskName /F 2>$null | Out-Null
    Write-Host "removed '$TaskName'"
    exit 0
}

if (-not (Test-Path $Exe)) { throw "DeskGadget.exe not found at $Exe" }

$action = New-ScheduledTaskAction -Execute $Exe -WorkingDirectory (Split-Path $Exe)
$trigger = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$trigger.Delay = "PT20S"
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" `
    -LogonType Interactive -RunLevel Limited

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Principal $principal -Force | Out-Null

Write-Host "registered '$TaskName' -> $Exe (20s after login)"
