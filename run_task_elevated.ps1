$out = 'C:\project\stock\logs\task_check.log'
$null = New-Item -ItemType Directory -Path 'C:\project\stock\logs' -Force -ErrorAction SilentlyContinue
"=== $([DateTime]::Now) ===" | Out-File $out -Encoding utf8
"WhoAmI: $(whoami)" | Out-File $out -Append -Encoding utf8
"IsAdmin: $((New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator))" | Out-File $out -Append -Encoding utf8

try {
    Stop-ScheduledTask -TaskName 'StockWatcher' -ErrorAction SilentlyContinue
    Remove-Item 'C:\project\stock\logs\diag.log' -ErrorAction SilentlyContinue
    Remove-Item 'C:\project\stock\logs\watcher.log' -ErrorAction SilentlyContinue
    Start-ScheduledTask -TaskName 'StockWatcher' -ErrorAction Stop
    "Started OK" | Out-File $out -Append -Encoding utf8
}
catch {
    "Start FAILED: $($_.Exception.Message)" | Out-File $out -Append -Encoding utf8
}

Start-Sleep -Seconds 10
$task = Get-ScheduledTask -TaskName 'StockWatcher'
$info = Get-ScheduledTaskInfo -TaskName 'StockWatcher'
"State: $($task.State)" | Out-File $out -Append -Encoding utf8
"LastResult: $($info.LastTaskResult)" | Out-File $out -Append -Encoding utf8
"LastRunTime: $($info.LastRunTime)" | Out-File $out -Append -Encoding utf8

"--- diag.log ---" | Out-File $out -Append -Encoding utf8
if (Test-Path 'C:\project\stock\logs\diag.log') { Get-Content 'C:\project\stock\logs\diag.log' | Out-File $out -Append -Encoding utf8 } else { "(missing)" | Out-File $out -Append -Encoding utf8 }
"--- watcher.log (tail 30) ---" | Out-File $out -Append -Encoding utf8
if (Test-Path 'C:\project\stock\logs\watcher.log') { Get-Content 'C:\project\stock\logs\watcher.log' -Tail 30 | Out-File $out -Append -Encoding utf8 } else { "(missing)" | Out-File $out -Append -Encoding utf8 }
