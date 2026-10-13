$ErrorActionPreference = 'Stop'
$taskPythonPath = Join-Path $PSScriptRoot '.runtime\python.exe'
if (-not (Test-Path -LiteralPath $taskPythonPath)) {
    $taskPythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}
if (-not (Test-Path -LiteralPath $taskPythonPath)) {
    $taskPythonPath = (Get-Command python -ErrorAction Stop).Source
}
& $taskPythonPath (Join-Path $PSScriptRoot 'import_resources.py')
if ($LASTEXITCODE -ne 0) { throw 'Exercise import failed. Check that the supported files are present.' }
& $taskPythonPath (Join-Path $PSScriptRoot 'prepare_audio.py')
if ($LASTEXITCODE -ne 0) { throw 'Some audio could not be cached. Check your connection and retry.' }
Write-Host 'Import complete. Restart the app to load the updated exercises.'
