# start_runners.ps1 을 5분마다 실행하는 작업 스케줄러 항목을 등록하고, AC 전원에서 절전을 끈다.
# 한 번만 실행: powershell -ExecutionPolicy Bypass -File scripts\keepalive_windows.ps1 [-Root C:\proj] [-TaskName lanerun_keepalive]
# 해제: Unregister-ScheduledTask -TaskName lanerun_keepalive -Confirm:$false
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string]$TaskName = "lanerun_keepalive",
    [string]$Python = ""
)
$script = Join-Path $PSScriptRoot "start_runners.ps1"
$args = "-ExecutionPolicy Bypass -WindowStyle Hidden -File `"$script`" -Root `"$Root`""
if ($Python) { $args += " -Python `"$Python`"" }
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $args
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date) -RepetitionInterval (New-TimeSpan -Minutes 5)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Force | Out-Null
Write-Host "registered task $TaskName (every 5 min) -> $script"
powercfg /change standby-timeout-ac 0
powercfg /change hibernate-timeout-ac 0
