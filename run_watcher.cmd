@echo off
REM Stock Watcher launcher with safe tracing

set "STOCK_DIR=C:\project\stock"
set "PYTHON_EXE=C:\project\ikawa-blog\.venv\Scripts\python.exe"
set "PLAYWRIGHT_BROWSERS_PATH=C:\Users\yoshi\AppData\Local\ms-playwright"
set "PYTHONIOENCODING=utf-8"

set "LOGDIR=%STOCK_DIR%\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%" 2>nul
set "LOGFILE=%LOGDIR%\watcher.log"
set "DIAGFILE=%LOGDIR%\diag.log"

>>"%DIAGFILE%" echo [step1] vars set
>>"%DIAGFILE%" echo ===== %DATE% %TIME% probe =====
>>"%DIAGFILE%" 2>&1 whoami
>>"%DIAGFILE%" 2>&1 cd
if exist "%PYTHON_EXE%" (>>"%DIAGFILE%" echo PYTHON_EXE=YES) else (>>"%DIAGFILE%" echo PYTHON_EXE=NO)
if exist "%STOCK_DIR%\watcher.py" (>>"%DIAGFILE%" echo WATCHER=YES) else (>>"%DIAGFILE%" echo WATCHER=NO)

>>"%DIAGFILE%" echo [step2] about to cd
cd /d "%STOCK_DIR%"
>>"%DIAGFILE%" echo [step3] cd done errorlevel=%ERRORLEVEL%
>>"%DIAGFILE%" 2>&1 cd

>>"%DIAGFILE%" echo [step4] about to write to LOGFILE
>>"%LOGFILE%" echo.
>>"%DIAGFILE%" echo [step5] first echo done errorlevel=%ERRORLEVEL%

>>"%LOGFILE%" echo ===== START %DATE% %TIME% =====
>>"%DIAGFILE%" echo [step6] start marker written errorlevel=%ERRORLEVEL%

>>"%DIAGFILE%" echo [step7] about to run python
>>"%LOGFILE%" 2>&1 "%PYTHON_EXE%" -u watcher.py
set "EC=%ERRORLEVEL%"
>>"%DIAGFILE%" echo [step8] python finished exit=%EC%

>>"%LOGFILE%" echo ===== END %DATE% %TIME% (exit=%EC%) =====
exit /b %EC%
