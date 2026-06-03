@echo off
REM 管理者として実行してください（右クリック → 管理者として実行）
REM SYSTEM 実行のスケジュールタスク StockWatcher を XML から登録します

setlocal
cd /d "%~dp0"

REM 管理者権限チェック
net session >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 管理者権限が必要です。右クリック→「管理者として実行」してください。
    echo.
    pause
    exit /b 1
)

echo タスク StockWatcher を登録します...
schtasks /Create /TN "StockWatcher" /XML "%~dp0watcher_task.xml" /F
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 登録失敗
    pause
    exit /b 1
)

echo.
echo [OK] 登録完了。タスクを今すぐ開始しますか？
echo.
choice /C YN /M "Yを押すと即時開始 / Nを押すとスキップ"
if %ERRORLEVEL% EQU 1 (
    schtasks /Run /TN "StockWatcher"
    echo.
    echo タスクを開始しました。logs\watcher.log を確認してください。
)

echo.
echo 状態確認:
schtasks /Query /TN "StockWatcher" /V /FO LIST | findstr /R "TaskName Status Last"
echo.
pause
