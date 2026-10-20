# Native Nyx launcher. Ollama startup and paths are owned by the Python app.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$Host.UI.RawUI.WindowTitle = 'Nyx Desktop'
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
$nyxPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'

Push-Location -LiteralPath $PSScriptRoot
try {
    Write-Host 'Iniciando Nyx Desktop' -ForegroundColor Cyan
    if (-not (Test-Path -LiteralPath $nyxPython)) {
        if (Get-Command uv -ErrorAction SilentlyContinue) {
            uv venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel criar o ambiente Python.' }
            uv pip install --python $nyxPython -r requirements.txt -r requirements-windows.txt
        } else {
            python -m venv .venv
            if ($LASTEXITCODE -ne 0) { throw 'Nao foi possivel criar o ambiente Python.' }
            & $nyxPython -m pip install -r requirements.txt -r requirements-windows.txt
        }
        if ($LASTEXITCODE -ne 0) { throw 'A instalacao das dependencias falhou.' }
    }
    Write-Host 'Os caminhos e limites do Ollama sao lidos pela Nyx; configure-os em Personalizar.' -ForegroundColor DarkGray
    & $nyxPython (Join-Path $PSScriptRoot 'src\main.py') @args
    $nyxExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $nyxExitCode
