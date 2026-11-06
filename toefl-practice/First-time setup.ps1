$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'python_path.ps1')
$taskPythonPath = Get-ToeflPython
$taskDependencies = Join-Path $PSScriptRoot '.deps'

Write-Host 'First-time setup: keep this window open until setup finishes.'
Write-Host 'Internet access is required. The grading models are large, so downloading can take a while.'
Write-Host 'Step 1 of 3: installing app dependencies...'
& $taskPythonPath -m pip --disable-pip-version-check install --upgrade --no-warn-script-location --target $taskDependencies -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the message above, then run First-time setup.cmd again.' }

Write-Host 'Step 2 of 3: checking the installed dependencies...'
& $taskPythonPath -c 'import sys; sys.path.insert(0, sys.argv[1]); from faster_whisper import WhisperModel; import av' $taskDependencies
if ($LASTEXITCODE -ne 0) { throw 'The installed dependencies could not be loaded. Run First-time setup.cmd again to repair the installation.' }

Write-Host 'Step 3 of 3: downloading the grading models and CPU engine...'
& $taskPythonPath (Join-Path $PSScriptRoot 'setup_models.py')
if ($LASTEXITCODE -ne 0) { throw 'Model setup failed. Check your connection, then run First-time setup.cmd again. Completed downloads will be reused.' }

Write-Host ''
Write-Host 'Setup complete. Double-click Start TOEFL.cmd to open the app.'
Write-Host 'For later sessions, use Start TOEFL.cmd. You do not need to run setup each time.'
