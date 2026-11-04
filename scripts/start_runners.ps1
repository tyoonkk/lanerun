# 레인별 러너가 떠 있는지 확인하고, 없으면 숨김 창으로 띄운다.
# 사용: powershell -ExecutionPolicy Bypass -File scripts\start_runners.ps1 [-Root C:\proj] [-Lanes gpu,cpu]
# lanerun 이 PATH 에 없으면 -Python 으로 가상환경의 python.exe 를 지정한다 (python -m lanerun 으로 띄움).
param(
    [string]$Root = (Split-Path -Parent $PSScriptRoot),
    [string[]]$Lanes = @("gpu", "cpu"),
    [string]$Python = ""
)
New-Item -ItemType Directory -Force (Join-Path $Root "logs") | Out-Null
foreach ($lane in $Lanes) {
    $running = Get-CimInstance Win32_Process | Where-Object {
        $_.CommandLine -like "*lanerun*run*--lane*$lane*"
    }
    if ($running) { Write-Host "runner $lane already running (pid $($running.ProcessId))"; continue }
    $out = Join-Path $Root "logs\runner_$lane.out"
    $err = Join-Path $Root "logs\runner_$lane.err"
    if ($Python) {
        Start-Process -FilePath $Python -ArgumentList "-m", "lanerun", "run", "--lane", $lane `
            -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    } else {
        Start-Process -FilePath "lanerun" -ArgumentList "run", "--lane", $lane `
            -WorkingDirectory $Root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err
    }
    Write-Host "started runner $lane"
}
