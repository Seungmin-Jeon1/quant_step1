@echo off
cd /d "%~dp0"

if not exist output mkdir output

echo ==== %date% %time% ==== >> output\scheduled_run_log.txt
py .\run_all_reports.py >> output\scheduled_run_log.txt 2>&1
echo ExitCode=%ERRORLEVEL% >> output\scheduled_run_log.txt
echo. >> output\scheduled_run_log.txt

exit /b %ERRORLEVEL%
