param(
    [ValidateRange(3,10)][int]$Runs = 3,
    [string[]]$Categories = @('all'),
    [string]$Model = 'qwen3.5:4b',
    [ValidateSet('conservative','normal','game','focus')][string]$Profile = 'conservative'
)
$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $false
$nyxRepoRoot = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$nyxPython = Join-Path $nyxRepoRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $nyxPython)) { throw 'Crie o ambiente .venv com as dependências da Nyx antes de executar.' }
$nyxStamp = Get-Date -Format 'yyyy-MM-dd_HH-mm-ss'
$nyxEvidence = Join-Path $nyxRepoRoot "docs\evidence\bench_${nyxStamp}_M0.json"
$nyxGate = Join-Path $nyxRepoRoot "docs\evidence\gate_${nyxStamp}_M0.json"
$nyxCodes = [ordered]@{}
Push-Location -LiteralPath $nyxRepoRoot
try {
    & $nyxPython -m ruff check src tests tools bench
    $nyxCodes.ruff = $LASTEXITCODE
    & $nyxPython -m pytest -q -m 'not windows_live' --junitxml=build/diagnostic/m0-unit.xml
    $nyxCodes.unit = $LASTEXITCODE
    if ($nyxCodes.ruff -eq 0 -and $nyxCodes.unit -eq 0) {
        & $nyxPython -m pytest -q -m windows_live --junitxml=build/diagnostic/m0-windows-live.xml
        $nyxCodes.windows_live = $LASTEXITCODE
        & $nyxPython tools/run_bench.py --runs $Runs --categories @Categories --model $Model --profile $Profile --output $nyxEvidence
        $nyxCodes.bench = $LASTEXITCODE
    }
    $nyxReport = [ordered]@{ milestone='M0'; runs=$Runs; categories=$Categories; model=$Model; profile=$Profile;
        exit_codes=$nyxCodes; evidence=[System.IO.Path]::GetFileName($nyxEvidence);
        note='Nenhum marco é concluído por testes verdes isolados; confira cobertura bloqueada e verificadores no relatório.' }
    $nyxReport | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $nyxGate -Encoding utf8
} finally { Pop-Location }
if ($nyxCodes.Count -ne 4 -or @($nyxCodes.Values | Where-Object { $_ -ne 0 }).Count -gt 0) { exit 1 }
exit 0
