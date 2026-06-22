@echo off
REM Stock Radar Bot launcher (background / no console window via SYSTEM session 0)
REM 出力は logs\radar_bot.log に追記。常駐ループ(radar_bot.py)を起動する。

set "STOCK_DIR=C:\project\stock"
set "PYTHON_EXE=C:\project\ikawa-blog\.venv\Scripts\python.exe"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

cd /d "%STOCK_DIR%"
if not exist "%STOCK_DIR%\logs" mkdir "%STOCK_DIR%\logs"
set "LOGFILE=%STOCK_DIR%\logs\radar_bot.log"

>>"%LOGFILE%" 2>&1 echo ===== START %DATE% %TIME% =====
>>"%LOGFILE%" 2>&1 "%PYTHON_EXE%" -u radar_bot.py
>>"%LOGFILE%" 2>&1 echo ===== END %DATE% %TIME% (exit=%ERRORLEVEL%) =====
