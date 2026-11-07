param(
    [ValidateSet('Setup', 'StartDb', 'InitDb', 'Check', 'Cached', 'Agent', 'All', 'StopDb')]
    [string]$Action = 'Check',
    [ValidateSet('demo', 'competition')][string]$Profile = 'demo',
    [string]$SqlIds = 'sql_1',
    [ValidateRange(1, 10000)][int]$Limit = 1,
    [ValidateRange(1, 30)][int]$Workers = 1
)
$ErrorActionPreference = 'Stop'
$env:PYTHONIOENCODING = 'utf-8'
$env:PYTHONUTF8 = '1'
$env:TGAC_PROFILE = $Profile
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new()
$projectPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
$composeFile = Join-Path $PSScriptRoot 'compose.yaml'

function Assert-LastCommand {
    if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE). See output above." }
}
function Start-ProjectDatabase {
    & docker compose -f $composeFile up -d --wait --wait-timeout 240
    Assert-LastCommand
}
if ($Action -eq 'Setup') {
    if (-not (Test-Path -LiteralPath $projectPython)) {
        & py -3.12 -m venv (Join-Path $PSScriptRoot '.venv')
        Assert-LastCommand
    }
    & $projectPython -m pip install -r (Join-Path $PSScriptRoot 'requirements-lock.txt')
    Assert-LastCommand
    exit 0
}
if ($Action -eq 'StartDb') { Start-ProjectDatabase; exit 0 }
if ($Action -eq 'StopDb') {
    & docker compose -f $composeFile stop
    Assert-LastCommand
    exit 0
}
if (-not (Test-Path -LiteralPath $projectPython)) { throw 'Run .\run.ps1 -Action Setup first.' }
switch ($Action) {
    'InitDb' {
        Start-ProjectDatabase
        & $projectPython (Join-Path $PSScriptRoot 'reset_and_init_db.py') --mode init
    }
    'Check' { & $projectPython (Join-Path $PSScriptRoot 'check_environment.py') }
    'Cached' {
        & $projectPython (Join-Path $PSScriptRoot 'main.py') --cache_only --max_workers $Workers
    }
    'Agent' {
        & $projectPython (Join-Path $PSScriptRoot 'main.py') --ignore_cache --rerun_ids $SqlIds --limit $Limit --max_workers $Workers --output_file (Join-Path $PSScriptRoot "output\$Profile\agent_result.json")
    }
    'All' { & $projectPython (Join-Path $PSScriptRoot 'main.py') --max_workers $Workers }
}
Assert-LastCommand
