param([switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$taskAppDirectory = $PSScriptRoot
$taskRuntimePython = Join-Path $taskAppDirectory '.runtime\python.exe'
if (-not (Test-Path -LiteralPath $taskRuntimePython)) {
    $taskRuntimePython = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}
if (-not (Test-Path -LiteralPath $taskRuntimePython)) {
    $taskRuntimePython = (Get-Command python -ErrorAction Stop).Source
}
$taskServerAddress = 'http://127.0.0.1:8765'
try {
    $taskExistingServer = Invoke-RestMethod -Uri "$taskServerAddress/api/health" -TimeoutSec 2
} catch {
    $taskExistingServer = $null
}
if (-not $taskExistingServer.ok) {
    $taskServerScript = Join-Path $taskAppDirectory 'server.py'
    Start-Process -FilePath $taskRuntimePython -ArgumentList ('"' + $taskServerScript + '"') -WorkingDirectory $taskAppDirectory -WindowStyle Hidden -RedirectStandardOutput (Join-Path $taskAppDirectory 'data\server.log') -RedirectStandardError (Join-Path $taskAppDirectory 'data\server-error.log')
    for ($taskAttempt = 0; $taskAttempt -lt 40; $taskAttempt++) {
        Start-Sleep -Milliseconds 250
        try {
            $taskHealth = Invoke-RestMethod -Uri "$taskServerAddress/api/health" -TimeoutSec 1
            if ($taskHealth.ok) { break }
        } catch { }
    }
}
if (-not $taskExistingServer.ok -and -not $taskHealth.ok) {
    throw 'The app did not start. Check data\server-error.log in the app folder.'
}
if (-not $NoBrowser) { Start-Process $taskServerAddress }
