@echo off
setlocal
REM UrbanTwin inspector: a second, ordinary Kit editor window on the same Argus
REM stage, for checking the scene by hand while the headless streaming Kit
REM serves the browser. Independent of the stream: its own camera and
REM selection, no livestream, and browser view commands do not reach it.
REM Both instances reload the stage's layers when an Argus run rewrites them.
REM
REM Two RTX instances share one GPU; expect the stream's frame rate to drop
REM while this window is open.

set "STAGE=C:/Users/arnav/Argus/phase9/scene/main.usda"
REM Argus demo_launch.ps1 -City sets URBANTWIN_STAGE (e.g. the Pune view); unset keeps London.
if defined URBANTWIN_STAGE set "STAGE=%URBANTWIN_STAGE%"
if not exist "%STAGE%" (
  echo ERROR: Stage not found: %STAGE%
  echo Update STAGE in this script, or set URBANTWIN_STAGE, if your Argus checkout lives elsewhere.
  exit /b 1
)

cd /d "%~dp0"
echo Launching urbantwin.kit (inspector, full editor UI) with:
echo   stage = %STAGE%
REM cleanView=false keeps Stage / Property / Layer panels for inspection.
set "AUTO_RELOAD=--/persistent/ext/omni.kit.usd.layers/auto_reload_sublayers=true --/persistent/ext/omni.kit.widget.stage/auto_reload_non_sublayers=true"
call .\repo.bat launch -n urbantwin.kit -- --/app/auto_load_usd=%STAGE% --ext-folder "%~dp0source\extensions" --enable urbantwin.stage_autoload --/exts/urbantwin.stage_autoload/cleanView=false %AUTO_RELOAD%
endlocal
