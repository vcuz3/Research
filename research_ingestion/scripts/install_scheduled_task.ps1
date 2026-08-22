param(
    [string]$PythonExe = "python",
    [string]$OmniRouteExe = "omniroute.cmd",
    [string]$TaskName = "Trading Research Ingestion"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonPath = (Get-Command $PythonExe).Source
$OmniRoutePath = (Get-Command $OmniRouteExe).Source
$PowerShellPath = (Get-Command "powershell.exe").Source
$RunnerPath = (Resolve-Path (Join-Path $PSScriptRoot "run_scheduled.ps1")).Path
$Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$RunnerPath`" -PythonExe `"$PythonPath`" -OmniRouteExe `"$OmniRoutePath`""
$Action = New-ScheduledTaskAction -Execute $PowerShellPath -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "22:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Starts OmniRoute if needed, downloads public trading research at 22:00, and catches up after missed runs." -Force
Write-Output "Installed scheduled task '$TaskName' at 22:00 with OmniRoute preflight and StartWhenAvailable."
