param(
    [string]$PythonExe = "python",
    [string]$TaskName = "Trading Research Ingestion"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$PythonPath = (Get-Command $PythonExe).Source
$Arguments = "-m research_ingestion.cli run --catch-up"
$Action = New-ScheduledTaskAction -Execute $PythonPath -Argument $Arguments -WorkingDirectory $ProjectRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At "22:00"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 4)
$Principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "Downloads public trading research at 22:00 and catches up after missed runs."
Write-Output "Installed scheduled task '$TaskName' at 22:00 with StartWhenAvailable."

