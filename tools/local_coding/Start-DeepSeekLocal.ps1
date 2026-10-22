$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot 'Start-LocalServer.ps1')
& (Join-Path $PSScriptRoot 'Ensure-CoderModel.ps1')
$env:NYX_LOCAL_OLLAMA_KEY = 'local-not-a-secret'
Start-Process -FilePath 'E:\projeto\deepsekharnesssla\DeepSeek Harness.exe'
