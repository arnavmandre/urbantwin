@echo off
setlocal
REM UrbanTwin Phase 13 — local streaming Kit launch (no main app window).
REM Argus stage: phase9/scene/main.usda
REM Connect with NVIDIA web-viewer-sample (stream only) after this starts.

REM Use forward slashes for Kit settings args (avoids escape issues).
set "STAGE=C:/Users/arnav/Argus/phase9/scene/main.usda"
REM Argus demo_launch.ps1 -City sets URBANTWIN_STAGE (e.g. the Pune view); unset keeps London.
if defined URBANTWIN_STAGE set "STAGE=%URBANTWIN_STAGE%"
if not exist "%STAGE%" (
  echo ERROR: Stage not found: %STAGE%
  echo Update STAGE in this script, or set URBANTWIN_STAGE, if your Argus checkout lives elsewhere.
  exit /b 1
)

cd /d "%~dp0"
echo Launching urbantwin_streaming.kit with:
echo   stage = %STAGE%
echo   flags = --no-window
echo   extensions = urbantwin.stage_autoload, urbantwin.view_commands
REM kit_base_editor ignores auto_load_usd alone (USD Viewer setup handles it).
REM Enable our source extension to open phase9/scene/main.usda after startup.
REM tickRate is forced here because the saved user config persists 120, and a
REM persisted value beats the .kit file; only the command line outranks it.
REM AUTO_RELOAD: an Argus run rewrites the stage's USD layers on disk. Without
REM these, omni.kit.usd.layers only posts "Base USD files have been changed,
REM please fetch changes" and waits for a click on FETCH.
set "AUTO_RELOAD=--/persistent/ext/omni.kit.usd.layers/auto_reload_sublayers=true --/persistent/ext/omni.kit.widget.stage/auto_reload_non_sublayers=true"
REM FIT: let the browser ask for its own aspect ratio (within the 1280x720
REM budget) so the stream fills the dashboard instead of being letterboxed.
REM app.livestream.allowResize in the .kit file does not enable this; the
REM livestream plugin reads primaryStream/allowDynamicResize (default false).
set "FIT=--/exts/omni.kit.livestream.app/primaryStream/allowDynamicResize=true"
call .\repo.bat launch -n urbantwin_streaming.kit -- --no-window --/app/auto_load_usd=%STAGE% --ext-folder "%~dp0source\extensions" --enable urbantwin.stage_autoload --enable urbantwin.view_commands --/persistent/app/viewport/defaults/tickRate=30 %AUTO_RELOAD% %FIT%
endlocal
