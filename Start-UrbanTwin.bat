@echo off
REM UrbanTwin AI - one-click local demo: API + Omniverse Kit stream (Pune) + dashboard.
REM Double-click this file. It first stops leftover demo servers from a previous
REM launch (only processes this demo starts), then opens the dashboard in your browser.
REM Options: Start-UrbanTwin.bat inspector   (also open a desktop Kit editor)
REM          Start-UrbanTwin.bat noanalytics (skip Grafana / Docker)

setlocal EnableDelayedExpansion
cd /d "%~dp0"

set "EXTRA="
for %%A in (%*) do (
  if /I "%%~A"=="inspector" set "EXTRA=!EXTRA! -Inspector"
  if /I "%%~A"=="noanalytics" set "EXTRA=!EXTRA! -NoAnalytics"
)

echo.
echo  UrbanTwin AI - starting the API, the Omniverse Kit stream and the dashboard...
echo  Kit runs headless: no Omniverse window appears, only its console.
echo  The dashboard opens in your browser when it is ready (use Chrome or Edge).
echo  To shut everything down, close the service windows.
echo.

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\demo_launch.ps1" -City pune -Force !EXTRA!
set "ERR=%ERRORLEVEL%"

echo.
if not "%ERR%"=="0" (
  echo Launch finished with errors. See tools\demo_logs\ and the service windows.
) else (
  echo Launch finished. Keep the service windows open while you use the app.
)
echo.
pause
endlocal
exit /b %ERR%
