$ErrorActionPreference = 'Stop'
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/show' -Method Post -ContentType 'application/json' -Body '{"model":"nyx-coder:9b"}' -TimeoutSec 10
} catch {
    if (-not $_.Exception.Response -or [int]$_.Exception.Response.StatusCode -ne 404) { throw }
    # Recreate only the alias; require the existing base model, never download silently.
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/show' -Method Post -ContentType 'application/json' -Body '{"model":"qwen3.5:9b"}' -TimeoutSec 10
    & 'E:\Ollama\ollama.exe' create nyx-coder:9b -f (Join-Path $PSScriptRoot 'Modelfile')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao restaurar a configuração nyx-coder:9b.' }
}
