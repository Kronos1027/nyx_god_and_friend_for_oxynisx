$ErrorActionPreference = 'Stop'
try {
    $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 2
    return
} catch { }
$env:OLLAMA_MODELS = 'E:\OllamaModelos'
$env:OLLAMA_HOST = '127.0.0.1:11434'
$env:OLLAMA_MAX_LOADED_MODELS = '1'
$env:OLLAMA_NUM_PARALLEL = '1'
$env:OLLAMA_MAX_QUEUE = '4'
$env:OLLAMA_FLASH_ATTENTION = '1'
$env:OLLAMA_KV_CACHE_TYPE = 'q8_0'
$env:OLLAMA_CONTEXT_LENGTH = '65536'
$env:OLLAMA_NO_CLOUD = '1'
$process = Start-Process -FilePath 'E:\Ollama\ollama.exe' -ArgumentList 'serve' -WindowStyle Hidden -RedirectStandardOutput (Join-Path $PSScriptRoot 'ollama.stdout.log') -RedirectStandardError (Join-Path $PSScriptRoot 'ollama.stderr.log') -PassThru
for ($attempt = 0; $attempt -lt 40; $attempt++) {
    if ($process.HasExited) { throw 'Ollama terminou; consulte ollama.stderr.log.' }
    try {
        $null = Invoke-RestMethod -Uri 'http://127.0.0.1:11434/api/version' -TimeoutSec 1
        return
    } catch { Start-Sleep -Milliseconds 250 }
}
throw 'Ollama ainda não respondeu. Consulte o log antes de tentar novamente.'
