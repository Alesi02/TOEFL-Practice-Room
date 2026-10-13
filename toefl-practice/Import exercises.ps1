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
if (Test-Path -LiteralPath (Join-Path $PSScriptRoot 'models\whisper-base.en\model.bin')) {
    & $taskPythonPath (Join-Path $PSScriptRoot 'convert_audio.py')
    if ($LASTEXITCODE -ne 0) { throw 'Audio conversion failed. Saved progress can be resumed by running Import exercises.cmd again.' }
    & $taskPythonPath (Join-Path $PSScriptRoot 'import_resources.py')
    if ($LASTEXITCODE -ne 0) { throw 'Converted exercise import failed.' }
} else {
    Write-Host 'For automatic recording conversion, install the grading models, then run this importer again.'
}
powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'synthesize_prompts.ps1')
if ($LASTEXITCODE -ne 0) { throw 'Printed-script audio conversion failed. Install an English Windows speech voice and retry.' }
& $taskPythonPath (Join-Path $PSScriptRoot 'prepare_audio.py')
if ($LASTEXITCODE -ne 0) { throw 'Some audio could not be cached. Check your connection and retry.' }
Write-Host 'Import complete. Restart the app to load the updated exercises.'
