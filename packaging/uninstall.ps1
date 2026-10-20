param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\Nyx")
)

$ErrorActionPreference = "Stop"
$resolvedTarget = [System.IO.Path]::GetFullPath($InstallRoot)
$defaultTarget = [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs\Nyx"))
if ($resolvedTarget -ne $defaultTarget -and -not $PSBoundParameters.ContainsKey("InstallRoot")) {
    throw "Pasta de instalação não corresponde ao destino padrão."
}
if (-not (Test-Path -LiteralPath $resolvedTarget -PathType Container)) {
    throw "A pasta de instalação não existe: $resolvedTarget"
}

$running = Get-CimInstance Win32_Process -Filter "name='Nyx.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($resolvedTarget, [StringComparison]::OrdinalIgnoreCase) }
if ($running) { throw "Feche a Nyx antes de desinstalar." }

if ($resolvedTarget -eq $defaultTarget) {
    $resolvedParent = [System.IO.Path]::GetFullPath((Split-Path -Parent $resolvedTarget))
    if ($resolvedParent -ne [System.IO.Path]::GetFullPath((Join-Path $env:LOCALAPPDATA "Programs"))) {
        throw "Destino de desinstalação inválido."
    }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
    Remove-Item -LiteralPath (Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Nyx") -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Nyx" -Recurse -Force -ErrorAction SilentlyContinue
} else {
    # Explicit test/custom installations are only removed when Nyx.exe is present.
    if (-not (Test-Path -LiteralPath (Join-Path $resolvedTarget "Nyx.exe") -PathType Leaf)) {
        throw "Destino personalizado não contém Nyx.exe; nenhum arquivo foi removido."
    }
    Remove-Item -LiteralPath $resolvedTarget -Recurse -Force
}

Write-Output "Nyx removida. Os dados em %LOCALAPPDATA%\Nyx foram preservados."
