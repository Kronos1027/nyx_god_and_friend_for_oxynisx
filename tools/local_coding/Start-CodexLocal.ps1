param([string]$Project = 'E:\projeto\Nova pasta')
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Start-LocalServer.ps1')
& (Join-Path $PSScriptRoot 'Ensure-CoderModel.ps1')
$previousCodexHome = $env:CODEX_HOME
try {
    $env:CODEX_HOME = Join-Path $PSScriptRoot 'codex-home'
    & codex --no-daemon --oss --local-provider ollama --model nyx-coder:9b -c 'model_reasoning_effort="none"' -c 'model_catalog_json="E:/projeto/local-coding/codex-home/models.json"' -C $Project
} finally {
    $env:CODEX_HOME = $previousCodexHome
}
