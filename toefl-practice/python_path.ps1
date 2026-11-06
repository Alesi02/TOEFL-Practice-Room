function Get-ToeflPython {
    $taskPythonCandidates = @(
        (Join-Path $PSScriptRoot '.runtime\python.exe'),
        (Join-Path $PSScriptRoot '.runtime\Scripts\python.exe')
    )
    $taskPythonLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($taskPythonLauncher) {
        try {
            $taskLaunchedPython = & $taskPythonLauncher.Source -3.12 -c 'import sys; print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $taskLaunchedPython) {
                $taskPythonCandidates += [string]$taskLaunchedPython
            }
        } catch { }
    }
    foreach ($taskCommandName in @('python3.12', 'python')) {
        $taskPythonCommand = Get-Command $taskCommandName -ErrorAction SilentlyContinue
        if ($taskPythonCommand -and $taskPythonCommand.Source -notlike '*\Microsoft\WindowsApps\*') {
            $taskPythonCandidates += $taskPythonCommand.Source
        }
    }
    if ($env:LOCALAPPDATA) {
        $taskPythonCandidates += Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'
    }
    if ($env:ProgramFiles) {
        $taskPythonCandidates += Join-Path $env:ProgramFiles 'Python312\python.exe'
    }
    # Retain support for installations that already use the bundled local runtime.
    $taskPythonCandidates += Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
    foreach ($taskPythonCandidate in ($taskPythonCandidates | Select-Object -Unique)) {
        if (-not (Test-Path -LiteralPath $taskPythonCandidate -PathType Leaf)) { continue }
        try {
            $taskResolvedPython = & $taskPythonCandidate -I -c 'import struct, sys; sys.exit(1) if sys.version_info[:2] != (3, 12) or struct.calcsize(chr(80)) != 8 else print(sys.executable)' 2>$null
            if ($LASTEXITCODE -eq 0 -and $taskResolvedPython) { return [string]$taskResolvedPython }
        } catch { }
    }
    throw 'Python 3.12 (64-bit) was not found. Install it from python.org with the Python launcher enabled, then run First-time setup.cmd again.'
}
