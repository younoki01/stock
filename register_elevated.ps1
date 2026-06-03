$ErrorActionPreference = 'Stop'
$logPath = 'C:\project\stock\logs\register.log'
$logDir = Split-Path $logPath
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }

function WriteLog($msg) {
    "$([DateTime]::Now.ToString('HH:mm:ss')) $msg" | Out-File -FilePath $logPath -Append -Encoding utf8
}

try {
    WriteLog "Start registration"
    WriteLog "WhoAmI: $(whoami)"
    WriteLog "IsAdmin: $((New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))"

    $xml = Get-Content -Raw -Path 'C:\project\stock\watcher_task.xml'
    Register-ScheduledTask -Xml $xml -TaskName 'StockWatcher' -Force -ErrorAction Stop | Out-Null
    WriteLog "REGISTERED OK"

    Start-ScheduledTask -TaskName 'StockWatcher'
    WriteLog "STARTED"

    Start-Sleep -Seconds 2
    $task = Get-ScheduledTask -TaskName 'StockWatcher'
    $info = Get-ScheduledTaskInfo -TaskName 'StockWatcher'
    WriteLog "State: $($task.State)  LastResult: $($info.LastTaskResult)"
}
catch {
    WriteLog "FAILED: $($_.Exception.Message)"
    exit 1
}
