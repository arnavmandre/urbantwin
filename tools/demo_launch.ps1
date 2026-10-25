# Argus AI local demo launcher - API + Kit streaming + Next.js dashboard.
# Usage:
#   .\tools\demo_launch.ps1
#   .\tools\demo_launch.ps1 -Force          # free ports 8000/3000/49100 first
#   .\tools\demo_launch.ps1 -NoAnalytics    # skip Grafana + run importer
#   .\tools\demo_launch.ps1 -Inspector      # also open a desktop Kit editor on the stage
#   .\tools\demo_launch.ps1 -City pune      # stream the Pune 400 m view
#   .\Start-UrbanTwin.bat                       # double-click from Explorer
param(
    [switch]$Force,
    [switch]$NoBrowser,
    [switch]$NoAnalytics,
    [switch]$Inspector,
    # Kit opens one stage per launch; switching city means relaunching (with -Force).
    [ValidateSet("pune")]
    [string]$City = "pune"
)

$ErrorActionPreference = "Stop"

function Get-ArgusRoot {
    param([string]$ScriptRoot)
    return (Resolve-Path (Join-Path $ScriptRoot "..")).Path
}

# -Force only stops processes this demo would have started. Each port lists
# the process name and a command-line fragment its owner must match; anything
# else (another dev server, the desktop Omniverse editor) is left alone.
$DemoOwners = @{
    8000  = @{ Name = "python"; CommandLike = "*-m api*" }
    3000  = @{ Name = "node";   CommandLike = "*next*" }
    3001  = @{ Name = "node";   CommandLike = "*next*" }
    49100 = @{ Name = "kit";    CommandLike = "*urbantwin_streaming*" }
    47998 = @{ Name = "kit";    CommandLike = "*urbantwin_streaming*" }
}

function Get-ProcessInfo {
    param([int]$ProcessId)
    return Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
}

function Test-ProcessMatches {
    param($Info, [string]$Name, [string]$CommandLike)
    if (-not $Info) { return $false }
    $procName = [System.IO.Path]::GetFileNameWithoutExtension($Info.Name)
    return ($procName -like "$Name*") -and ([string]$Info.CommandLine -like $CommandLike)
}

function Get-PortListenerIds {
    param([int]$Port)
    $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    return @($conns | ForEach-Object { $_.OwningProcess } | Where-Object { $_ } | Sort-Object -Unique)
}

function Stop-ListenersOnPort {
    param([int]$Port)
    $owner = $DemoOwners[$Port]
    foreach ($procId in Get-PortListenerIds -Port $Port) {
        $info = Get-ProcessInfo -ProcessId $procId
        if (Test-ProcessMatches -Info $info -Name $owner.Name -CommandLike $owner.CommandLike) {
            Write-Host ("  Stopping PID {0} ({1}) listening on port {2}" -f $procId, $info.Name, $Port)
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
        } else {
            $label = if ($info) { $info.Name } else { "unknown" }
            Write-Warning ("Port {0} is held by PID {1} ({2}), not a demo process - leaving it running." -f $Port, $procId, $label)
        }
    }
}

function Stop-KitProcesses {
    # Only the headless streaming Kit; a desktop editor session may have unsaved work.
    Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -like "*urbantwin_streaming*" } |
        ForEach-Object {
            Write-Host ("  Stopping streaming Kit PID {0}" -f $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
}

function Stop-EverythingForDemo {
    Write-Host "Force: stopping demo processes on 8000 / 3000 / 3001 / 49100 / 47998..."
    Stop-KitProcesses
    # The run importer holds no port; match it by its command line.
    Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -like "*import_runs.py*--watch*" } |
        ForEach-Object {
            Write-Host ("  Stopping run importer PID {0}" -f $_.ProcessId)
            Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
        }
    foreach ($port in 8000, 3000, 3001, 49100, 47998) {
        Stop-ListenersOnPort -Port $port
    }
    # Second pass: Kit sometimes leaves the signaling port stuck for a moment.
    Start-Sleep -Seconds 2
    Stop-KitProcesses
    Stop-ListenersOnPort -Port 49100
    Write-Host ""
}

function Wait-HttpJson {
    param(
        [string]$Url,
        [int]$MaxSeconds = 90
    )
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            return Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 5
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    return $null
}

function Wait-TcpPort {
    param(
        [string]$HostName = "127.0.0.1",
        [int]$Port,
        [int]$MaxSeconds = 120
    )
    $deadline = (Get-Date).AddSeconds($MaxSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $client = New-Object System.Net.Sockets.TcpClient
            $iar = $client.BeginConnect($HostName, $Port, $null, $null)
            $ok = $iar.AsyncWaitHandle.WaitOne(1000, $false)
            if ($ok -and $client.Connected) {
                $client.EndConnect($iar)
                $client.Close()
                return $true
            }
            $client.Close()
        } catch {
            # keep waiting
        }
        Start-Sleep -Seconds 2
    }
    return $false
}

function Start-DemoWindow {
    param(
        [string]$Title,
        [string]$ScriptPath
    )
    $argList = "-NoExit -NoProfile -ExecutionPolicy Bypass -File `"$ScriptPath`""
    Start-Process -FilePath "powershell.exe" -ArgumentList $argList | Out-Null
    Write-Host ("Started: {0}" -f $Title)
}

function Resolve-DashboardUrl {
    # Kit's Python debugger binds 127.0.0.1:3000, so the dashboard is pinned to
    # $DashboardPort. Only accept a listener that is this repo's Next process.
    param([string]$FrontendDir)
    foreach ($port in @($DashboardPort)) {
        foreach ($procId in Get-PortListenerIds -Port $port) {
            $info = Get-ProcessInfo -ProcessId $procId
            if (Test-ProcessMatches -Info $info -Name "node" -CommandLike ("*{0}*" -f $FrontendDir)) {
                return "http://127.0.0.1:$port"
            }
        }
    }
    return $null
}

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$ArgusRoot = Get-ArgusRoot -ScriptRoot $ScriptRoot
$LogDir = Join-Path $ScriptRoot "demo_logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$ApiLog = Join-Path $LogDir ("api-{0}.log" -f $Stamp)
$FrontendLog = Join-Path $LogDir ("frontend-{0}.log" -f $Stamp)
$KitLog = Join-Path $LogDir ("kit-{0}.log" -f $Stamp)
$DashboardPort = 3001
$KitBat = "C:\Users\arnav\omniverse\kit-app-template\launch_urbantwin_streaming.bat"
$KitRoot = "C:\Users\arnav\omniverse\kit-app-template"
$InspectorBat = Join-Path $KitRoot "launch_urbantwin_inspector.bat"

$ApiScript = Join-Path $LogDir ("start-api-{0}.ps1" -f $Stamp)
$FrontendScript = Join-Path $LogDir ("start-frontend-{0}.ps1" -f $Stamp)
$KitScript = Join-Path $LogDir ("start-kit-{0}.ps1" -f $Stamp)
$ImporterLog = Join-Path $LogDir ("importer-{0}.log" -f $Stamp)
$ImporterScript = Join-Path $LogDir ("start-importer-{0}.ps1" -f $Stamp)
$AnalyticsUrl = $null

# The WindowsApps "python" is a Microsoft Store alias stub that only prints "Python was not found".
# Shells started by some apps put it ahead of the real install on PATH, so skip it explicitly.
$PythonExe = (Get-Command python -All -ErrorAction SilentlyContinue |
    Where-Object { $_.Source -notlike "*\WindowsApps\*" } | Select-Object -First 1).Source
if (-not $PythonExe) { $PythonExe = "python" }
$Py = "& '{0}'" -f $PythonExe

# Kit stage per city (integration/cities.py holds the same paths for the API).
$StageRel = "cities\pune\main_view_400m.usda"
$StagePath = Join-Path $ArgusRoot $StageRel

Write-Host "Argus AI - demo launch"
Write-Host ("  Argus root: {0}" -f $ArgusRoot)
Write-Host ("  City:       {0}  (stage {1})" -f $City, $StageRel)
Write-Host ("  Logs:       {0}" -f $LogDir)
Write-Host ""

# Pune's animated layers are generated, not committed (cities/pune/.gitignore); build them once.
if ($City -eq "pune" -and -not (Test-Path -LiteralPath $StagePath)) {
    Write-Host "Preparing Pune (first launch, ~15 s): pune_sim.py then pune_view.py ..."
    Push-Location (Join-Path $ArgusRoot "cities\pune")
    try {
        & $PythonExe pune_sim.py
        if ($LASTEXITCODE -eq 0) { & $PythonExe pune_view.py }
        if ($LASTEXITCODE -ne 0) { throw "Pune preparation failed (exit $LASTEXITCODE) - see output above." }
    } finally {
        Pop-Location
    }
    Write-Host ""
}
Write-Host "NOTE: Omniverse Kit streaming starts with --no-window."
Write-Host "      You will NOT see a normal Omniverse editor. Look for a console"
Write-Host "      titled 'Argus AI Kit Streaming' and a Live viewport in Chrome/Edge."
Write-Host ""

if (-not (Test-Path -LiteralPath (Join-Path $ArgusRoot "api\server.py"))) {
    throw "api\server.py not found under $ArgusRoot - run this from the Argus repo."
}

$FrontendDir = Join-Path $ArgusRoot "frontend"
if (-not (Test-Path -LiteralPath (Join-Path $FrontendDir "package.json"))) {
    throw "frontend\package.json not found under $ArgusRoot."
}

if ($Force) {
    Stop-EverythingForDemo
} else {
    # Soft check: warn if Kit/signaling already running (common cause of
    # "Failed to start the primary stream server" / NVST_R_INTERNAL_ERROR).
    $existingKit = Get-Process -Name kit -ErrorAction SilentlyContinue
    $sigBusy = Get-NetTCPConnection -LocalPort 49100 -State Listen -ErrorAction SilentlyContinue
    if ($existingKit -or $sigBusy) {
        Write-Warning "Kit or port 49100 is already in use."
        Write-Warning "That usually breaks WebRTC with: Failed to start the primary stream server."
        Write-Warning "Re-run with: Start-UrbanTwin.bat -Force (stops only the streaming Kit and"
        Write-Warning "demo API/Next processes; a desktop Omniverse editor must be closed by hand)."
        Write-Host ""
    }
}

$apiLines = @(
    ("Set-Location -LiteralPath '{0}'" -f $ArgusRoot)
    '$Host.UI.RawUI.WindowTitle = ''Argus AI API (:8000)'''
    # Tells /api/stream/config which city Kit shows; the TCP probe cannot ask Kit.
    ("`$env:URBANTWIN_STREAM_CITY = '{0}'" -f $City)
    ("{0} -m api --host 127.0.0.1 --port 8000 2>&1 | Tee-Object -FilePath '{1}'" -f $Py, $ApiLog)
)
$apiLines | Set-Content -LiteralPath $ApiScript -Encoding ASCII

Start-DemoWindow -Title "Python API (:8000)" -ScriptPath $ApiScript

$kitStarted = Test-Path -LiteralPath $KitBat
if ($kitStarted) {
    # Keep a visible console (/k style via -NoExit). Old Start-Process cmd /c
    # flashed closed, so Kit looked like it never started even when it did.
    $kitLines = @(
        ("Set-Location -LiteralPath '{0}'" -f $KitRoot)
        '$Host.UI.RawUI.WindowTitle = ''Argus AI Kit Streaming (headless)'''
        'Write-Host "Starting launch_urbantwin_streaming.bat ..."'
        'Write-Host "This is headless (--no-window). No Omniverse editor UI will appear."'
        'Write-Host "Wait until this window shows Kit ready / livestream, then check the dashboard Live chip."'
        'Write-Host ""'
        # Read by launch_urbantwin_streaming.bat; the stage is always the Pune view.
        ("`$env:URBANTWIN_STAGE = '{0}'" -f ($StagePath -replace '\\', '/'))
        # explicit .\ path: cmd ignores the current folder when NoDefaultCurrentDirectoryInExePath is set
        ("cmd.exe /c `".\launch_urbantwin_streaming.bat`" 2>&1 | Tee-Object -FilePath '{0}'" -f $KitLog)
        'Write-Host ""'
        'Write-Host "Kit process exited. If the stream never came online, scroll up or open:"'
        ("Write-Host '  {0}'" -f $KitLog)
    )
    $kitLines | Set-Content -LiteralPath $KitScript -Encoding ASCII
    Start-DemoWindow -Title "Kit streaming" -ScriptPath $KitScript
    Write-Host "Started Kit streaming in a visible console (headless render)."
} else {
    Write-Warning ("Kit launcher not found at {0} - start Kit manually for stream online." -f $KitBat)
}

# Inspector: an ordinary Kit editor window on the same stage, separate from the
# stream. -Force never stops it (it may hold unsaved work), so do not open a
# second one if it is already running.
if ($Inspector) {
    $inspectorRunning = Get-CimInstance Win32_Process -Filter "Name='kit.exe'" -ErrorAction SilentlyContinue |
        Where-Object { [string]$_.CommandLine -like "*urbantwin.kit*" }
    if ($inspectorRunning) {
        Write-Host "Inspector Kit already running - leaving it open."
    } elseif (Test-Path -LiteralPath $InspectorBat) {
        $env:URBANTWIN_STAGE = $StagePath -replace '\\', '/'  # inherited by the inspector's cmd.exe
        Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"$InspectorBat`"" -WorkingDirectory $KitRoot | Out-Null
        Write-Host "Started: Inspector Kit (desktop editor window; shares the GPU with the stream)"
    } else {
        Write-Warning ("Inspector launcher not found at {0}." -f $InspectorBat)
    }
}

# Analytics (optional): PostgreSQL + Grafana in Docker, plus an importer that
# copies finished runs into the database. Skipped, with a warning, when Docker
# is not running; the 3D demo does not depend on it.
if (-not $NoAnalytics) {
    # docker writes progress to stderr; under "Stop", Windows PowerShell turns
    # that into a terminating error, so judge success by exit code alone.
    $savedPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    $dockerUp = $false
    $composeOk = $false
    try {
        & docker info --format "{{.ServerVersion}}" *> $null
        $dockerUp = ($LASTEXITCODE -eq 0)
        if ($dockerUp) {
            & docker compose -f (Join-Path $ArgusRoot "analytics\docker-compose.yml") up -d *> $null
            $composeOk = ($LASTEXITCODE -eq 0)
        }
    } catch {
        $dockerUp = $false
    } finally {
        $ErrorActionPreference = $savedPreference
    }
    if ($dockerUp) {
        if ($composeOk) {
            $importerLines = @(
                ("Set-Location -LiteralPath '{0}'" -f $ArgusRoot)
                '$Host.UI.RawUI.WindowTitle = ''Argus AI run importer (Grafana)'''
                ("{0} analytics\import_runs.py --watch 2>&1 | Tee-Object -FilePath '{1}'" -f $Py, $ImporterLog)
            )
            $importerLines | Set-Content -LiteralPath $ImporterScript -Encoding ASCII
            Start-DemoWindow -Title "Run importer (Grafana)" -ScriptPath $ImporterScript
            $AnalyticsUrl = "http://localhost:3300"
        } else {
            Write-Warning "docker compose up failed for analytics\docker-compose.yml - continuing without Grafana."
        }
    } else {
        Write-Warning "Docker is not running - continuing without Grafana analytics (no Analytics link)."
    }
}

$feLines = @(
    ("Set-Location -LiteralPath '{0}'" -f $FrontendDir)
    '$env:URBANTWIN_API_BASE = ''http://127.0.0.1:8000'''
    $(if ($AnalyticsUrl) { "`$env:URBANTWIN_GRAFANA_URL = '$AnalyticsUrl'" } else { '# analytics not running' })
    '$Host.UI.RawUI.WindowTitle = ''UrbanTwin AI Dashboard'''
    ("npm run dev -- -p {1} 2>&1 | Tee-Object -FilePath '{0}'" -f $FrontendLog, $DashboardPort)
)
$feLines | Set-Content -LiteralPath $FrontendScript -Encoding ASCII

Start-DemoWindow -Title "Next.js frontend" -ScriptPath $FrontendScript
Write-Host ""

Write-Host "Waiting for API health (up to 90s)..."
$health = Wait-HttpJson -Url "http://127.0.0.1:8000/api/health" -MaxSeconds 90
if (-not $health) {
    Write-Warning ("API health did not respond in time. Check {0}" -f $ApiLog)
} else {
    Write-Host ("  mode: {0}, omniverse_stream: {1}" -f $health.mode, $health.omniverse_stream)
}

if (-not $kitStarted) {
    Write-Host "Skipping Kit signaling wait (Kit was not started by this script)."
} elseif (Wait-TcpPort -Port 49100 -MaxSeconds 120) {
    Write-Host "  Kit signaling port is open."
} else {
    Write-Warning "Kit signaling port 49100 never opened."
    Write-Warning ("Check the 'Argus AI Kit Streaming' window and {0}" -f $KitLog)
    Write-Warning "You can still use the dashboard; the viewport will stay offline until Kit is up."
}

Write-Host "Waiting for stream config..."
$stream = Wait-HttpJson -Url "http://127.0.0.1:8000/api/stream/config" -MaxSeconds 30
if ($stream) {
    Write-Host ("  stream status: {0}" -f $stream.status)
} else {
    Write-Warning "Stream config not reachable yet."
}

Write-Host "Waiting for dashboard (up to 60s)..."
$dashboard = $null
$deadline = (Get-Date).AddSeconds(60)
while ((Get-Date) -lt $deadline) {
    $dashboard = Resolve-DashboardUrl -FrontendDir $FrontendDir
    if ($dashboard) {
        try {
            $null = Invoke-WebRequest -Uri $dashboard -UseBasicParsing -TimeoutSec 3
            break
        } catch {
            $dashboard = $null
        }
    }
    Start-Sleep -Seconds 2
}
if (-not $dashboard) {
    $dashboard = "http://127.0.0.1:$DashboardPort"
    Write-Warning ("Dashboard not confirmed yet - check the 'UrbanTwin AI Dashboard' window or {0}; port {1} may be held by another program." -f $FrontendLog, $DashboardPort)
}

Write-Host ""
Write-Host "Ready URLs:"
Write-Host ("  Dashboard:  {0}" -f $dashboard)
Write-Host "  API health: http://127.0.0.1:8000/api/health"
Write-Host "  Stream cfg: http://127.0.0.1:8000/api/stream/config"
Write-Host "  Kit signal: tcp://127.0.0.1:49100 (headless streaming host)"
if ($AnalyticsUrl) {
    Write-Host ("  Grafana:    {0}/d/argus-observatory (read-only; admin login to edit)" -f $AnalyticsUrl)
    Write-Host ("  Importer log: {0}" -f $ImporterLog)
}
Write-Host ""
Write-Host "Omniverse tip: there is no editor window. Use Chrome/Edge; wait for viewport = Live."
Write-Host "Smoke test:  python tools\demo_smoke.py"
Write-Host "Runbook:     docs\DEMO_RUNBOOK.md"
Write-Host ("API log:     {0}" -f $ApiLog)
Write-Host ("Kit log:     {0}" -f $KitLog)
Write-Host ("Frontend log: {0}" -f $FrontendLog)

if (-not $NoBrowser) {
    try {
        Start-Process $dashboard | Out-Null
        Write-Host ""
        Write-Host ("Opened browser: {0}" -f $dashboard)
        Write-Host "Use Chrome or Edge for the Omniverse stream."
    } catch {
        Write-Warning "Could not open a browser automatically."
    }
}
