$ErrorActionPreference = 'Stop'
$taskPythonPath = Join-Path $PSScriptRoot '.runtime\python.exe'
if (-not (Test-Path -LiteralPath $taskPythonPath)) {
    $taskPythonPath = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
}
if (-not (Test-Path -LiteralPath $taskPythonPath)) {
    $taskPythonPath = (Get-Command python -ErrorAction Stop).Source
}
& $taskPythonPath (Join-Path $PSScriptRoot 'setup_models.py')
if ($LASTEXITCODE -ne 0) { throw 'Model setup failed. Check the message above and retry.' }
Write-Host 'Offline grading is ready. Open Start TOEFL.cmd to practise.'
