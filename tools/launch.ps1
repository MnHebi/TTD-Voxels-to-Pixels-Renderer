# SPDX-License-Identifier: GPL-2.0-only
$ErrorActionPreference = 'Stop'
$workshopRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $workshopRoot
$candidates = @(
    $env:WORKSHOP_PYTHON,
    (Join-Path $workshopRoot '.venv/Scripts/python.exe'),
    (Join-Path $env:USERPROFILE '.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe')
)
foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        & $candidate -c 'import PIL,numpy' 2>$null
        if ($LASTEXITCODE -eq 0) {
            & $candidate (Join-Path $workshopRoot 'app.py')
            exit $LASTEXITCODE
        }
    }
}
$launcher = Get-Command py -ErrorAction SilentlyContinue
if ($launcher) {
    & $launcher.Source -3 -c 'import PIL,numpy' 2>$null
    if ($LASTEXITCODE -eq 0) {
        & $launcher.Source -3 (Join-Path $workshopRoot 'app.py')
        exit $LASTEXITCODE
    }
}
Write-Host 'Python 3.10+ with Pillow and NumPy is required.'
Write-Host 'Run: py -3 -m venv .venv'
Write-Host 'Then: .venv\Scripts\python.exe -m pip install -r requirements.txt'
exit 1
