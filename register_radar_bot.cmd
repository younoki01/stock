@echo off
REM 管理者として実行してください（右クリック → 管理者として実行）
REM SYSTEM 実行の常駐タスク StockRadarBot を XML から登録します（窓は出ません）

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

echo タスク StockRadarBot を登録します...
schtasks /Create /TN "StockRadarBot" /XML "%~dp0radar_bot_task.xml" /F
if %ERRORLEVEL% NEQ 0 (
    echo [ERROR] 登録失敗
    pause
    exit /b 1
)

echo.
echo [OK] 登録完了。今すぐ開始しますか？
choice /C YN /M "Yで即時開始 / Nでスキップ（次回起動時に自動開始）"
if %ERRORLEVEL% EQU 1 (
    schtasks /Run /TN "StockRadarBot"
    echo タスクを開始しました。logs\radar_bot.log を確認してください。
)

echo.
echo 状態確認:
schtasks /Query /TN "StockRadarBot" /V /FO LIST | findstr /R "TaskName Status Last"
echo.
echo 停止/削除するには:  schtasks /End /TN "StockRadarBot"  /  schtasks /Delete /TN "StockRadarBot" /F
echo.
pause
