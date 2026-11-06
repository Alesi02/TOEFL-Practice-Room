$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python_path.ps1')
$taskPythonPath = Get-ToeflPython
& $taskPythonPath (Join-Path $PSScriptRoot 'setup_models.py')
if ($LASTEXITCODE -ne 0) { throw 'Model setup failed. Check the message above and retry.' }
Write-Host 'Offline grading is ready. Open Start TOEFL.cmd to practise.'
