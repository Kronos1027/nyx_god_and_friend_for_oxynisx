param(
    [string]$InstallRoot = (Join-Path $env:LOCALAPPDATA "Programs\Nyx"),
    [switch]$NoShortcut
)

$ErrorActionPreference = "Stop"
$source = $PSScriptRoot
$resolvedTarget = [System.IO.Path]::GetFullPath($InstallRoot)
if (-not (Test-Path (Join-Path $source "Nyx.exe"))) {
    throw "Execute este instalador ao lado de Nyx.exe."
}

$running = Get-CimInstance Win32_Process -Filter "name='Nyx.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.ExecutablePath -and $_.ExecutablePath.StartsWith($resolvedTarget, [StringComparison]::OrdinalIgnoreCase) }
if ($running) { throw "Feche a Nyx antes de instalar ou atualizar." }

New-Item -ItemType Directory -Path $resolvedTarget -Force | Out-Null
Get-ChildItem -LiteralPath $source -Force | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $resolvedTarget -Recurse -Force
}

if (-not $NoShortcut) {
    $startMenu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Nyx"
    New-Item -ItemType Directory -Path $startMenu -Force | Out-Null
    $shortcutPath = Join-Path $startMenu "Nyx.lnk"
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = Join-Path $resolvedTarget "Nyx.exe"
    $shortcut.WorkingDirectory = $resolvedTarget
    $shortcut.Description = "Assistente local Nyx"
    $shortcut.Save()

    $uninstallKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\Nyx"
    New-Item -Path $uninstallKey -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayName -Value "Nyx" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name DisplayVersion -Value "0.1.0" -PropertyType String -Force | Out-Null
    New-ItemProperty -Path $uninstallKey -Name InstallLocation -Value $resolvedTarget -PropertyType String -Force | Out-Null
    $uninstallScript = Join-Path $resolvedTarget "uninstall.ps1"
    $uninstallCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$uninstallScript`""
    New-ItemProperty -Path $uninstallKey -Name UninstallString -Value $uninstallCommand -PropertyType String -Force | Out-Null
}

Write-Output "Nyx instalada em $resolvedTarget"
Write-Output "Memória, lembretes e modelos ficam em %LOCALAPPDATA%\Nyx e não são apagados ao desinstalar."
