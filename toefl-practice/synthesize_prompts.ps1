$ErrorActionPreference = 'Stop'
$taskAppRoot = $PSScriptRoot
$taskProjectRoot = Split-Path -Parent $taskAppRoot
$taskSpeechCache = [IO.Path]::GetFullPath((Join-Path $taskAppRoot 'cache\synthesized'))
New-Item -ItemType Directory -Path $taskSpeechCache -Force | Out-Null
$taskSynthesizer = New-Object -ComObject SAPI.SpVoice
$taskVoice = $taskSynthesizer.GetVoices() | Where-Object { $_.GetAttribute('Language') -match '(^|;)409(;|$)' } | Select-Object -First 1
if (-not $taskVoice) { throw 'Install an English Windows speech voice to create audio from printed scripts.' }
$taskSynthesizer.Voice = $taskVoice
$taskManifest = Get-Content -LiteralPath (Join-Path $taskAppRoot 'data\speech-manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
try {
    foreach ($taskPrompt in $taskManifest) {
        $taskOutputPath = [IO.Path]::GetFullPath((Join-Path $taskProjectRoot $taskPrompt.path))
        if (-not $taskOutputPath.StartsWith($taskSpeechCache + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Invalid synthesized prompt path' }
        if ((Test-Path -LiteralPath $taskOutputPath) -and (Get-Item -LiteralPath $taskOutputPath).Length -gt 1000) { continue }
        $taskFileStream = New-Object -ComObject SAPI.SpFileStream
        try {
            $taskFileStream.Open($taskOutputPath,3,$false)
            $taskSynthesizer.AudioOutputStream = $taskFileStream
            $null = $taskSynthesizer.Speak([string]$taskPrompt.text)
        } finally { $taskFileStream.Close() }
    }
} finally { $null = [Runtime.InteropServices.Marshal]::ReleaseComObject($taskSynthesizer) }
Write-Output 'Printed source scripts have been converted to clearly labeled practice audio.'
