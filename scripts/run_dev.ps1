param(
    [switch]$NoReload,
    [string]$EnvFile,
    [switch]$ValidateOnly
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
if (-not $EnvFile) { $EnvFile = Join-Path $repo ".env" }

function Import-DotEnv {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) { return }
    foreach ($line in [IO.File]::ReadLines((Resolve-Path -LiteralPath $Path))) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        if ($trimmed -notmatch '^(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)$') {
            throw "Invalid environment entry in the configured env file."
        }

        $name = $Matches[1]
        $value = $Matches[2].Trim()
        if ($value.StartsWith("'")) {
            if ($value -notmatch "^'([^']*)'\s*(?:#.*)?$") { throw "Invalid quoted environment value." }
            $value = $Matches[1]
        }
        elseif ($value.StartsWith('"')) {
            if ($value -notmatch '^"((?:\\.|[^"])*)"\s*(?:#.*)?$') { throw "Invalid quoted environment value." }
            $value = $Matches[1]
        }
        else {
            $value = ($value -replace '\s+#.*$', '').TrimEnd()
        }

        if ($null -eq [Environment]::GetEnvironmentVariable($name, "Process")) {
            [Environment]::SetEnvironmentVariable($name, $value, "Process")
        }
    }
}

function Stop-ProcessTree {
    param([int]$RootProcessId)

    $children = @(Get-CimInstance Win32_Process -Filter "ParentProcessId=$RootProcessId" -ErrorAction SilentlyContinue)
    foreach ($child in $children) {
        try { Stop-ProcessTree -RootProcessId $child.ProcessId }
        catch { }
    }
    try { Stop-Process -Id $RootProcessId -Force -ErrorAction SilentlyContinue }
    catch { }
}

Import-DotEnv -Path $EnvFile

$backendPython = Join-Path $repo "backend\.venv\Scripts\python.exe"
$uiPython = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $backendPython -PathType Leaf)) { throw "Backend environment is missing." }
if (-not (Test-Path -LiteralPath $uiPython -PathType Leaf)) { throw "UI environment is missing." }
if ([string]::IsNullOrWhiteSpace($env:DATABASE_URL)) { throw "DATABASE_URL is required. This launcher never creates or migrates a database." }
if ([string]::IsNullOrWhiteSpace($env:SUPABASE_URL)) { throw "SUPABASE_URL is required." }
if ([string]::IsNullOrWhiteSpace($env:SUPABASE_PUBLISHABLE_KEY)) { throw "SUPABASE_PUBLISHABLE_KEY is required." }
if ([string]::IsNullOrWhiteSpace($env:SESSION_SECRET) -or $env:SESSION_SECRET.Length -lt 32) { throw "SESSION_SECRET must contain at least 32 characters." }

if ($ValidateOnly) {
    Write-Host "Development launcher configuration is valid."
    exit 0
}

$logDirectory = Join-Path $repo ".dev-logs"
New-Item -ItemType Directory -Force -Path $logDirectory | Out-Null
$reloadArgs = if ($NoReload) { @() } else { @("--reload") }
$backend = $null
$ui = $null

try {
    $backend = Start-Process -FilePath $backendPython -WorkingDirectory (Join-Path $repo "backend") -PassThru -RedirectStandardOutput (Join-Path $logDirectory "backend.stdout.log") -RedirectStandardError (Join-Path $logDirectory "backend.stderr.log") -ArgumentList (@("-m", "uvicorn", "app.main:app", "--port", "8000") + $reloadArgs)
    $ui = Start-Process -FilePath $uiPython -WorkingDirectory $repo -PassThru -RedirectStandardOutput (Join-Path $logDirectory "ui.stdout.log") -RedirectStandardError (Join-Path $logDirectory "ui.stderr.log") -ArgumentList (@("-m", "uvicorn", "app.main:app", "--port", "8001") + $reloadArgs)

    Write-Host "Backend: http://127.0.0.1:8000/docs"
    Write-Host "Namak UI: http://127.0.0.1:8001"
    Write-Host "Service logs: $logDirectory"
    Write-Host "Press Ctrl+C to stop both service process trees."
    while (-not $backend.HasExited -and -not $ui.HasExited) {
        Start-Sleep -Milliseconds 250
        $backend.Refresh()
        $ui.Refresh()
    }
    if ($backend.HasExited) { throw "Backend exited. Check backend.stderr.log." }
    if ($ui.HasExited) { throw "UI exited. Check ui.stderr.log." }
}
finally {
    if ($backend) { Stop-ProcessTree -RootProcessId $backend.Id }
    if ($ui) { Stop-ProcessTree -RootProcessId $ui.Id }
}
