param(
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$python = Join-Path $repo ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) {
    throw "Ambiente .venv ausente. Instale requirements.txt e requirements-windows.txt primeiro."
}

Push-Location $repo
try {
    & $python -c "import PyInstaller" 2>$null
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller não está instalado neste ambiente. Execute: .venv\Scripts\python.exe -m pip install pyinstaller"
    }

    $pyinstallerArgs = @("--noconfirm", "packaging\Nyx.spec")
    if ($Clean) { $pyinstallerArgs = @("--noconfirm", "--clean", "packaging\Nyx.spec") }
    # PyInstaller writes progress to stderr; with ErrorActionPreference=Stop that
    # would abort the build, so native output is collected instead of thrown.
    $previousPreference = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $python -m PyInstaller @pyinstallerArgs 2>&1 | ForEach-Object { "$_" }
    $buildExitCode = $LASTEXITCODE
    $ErrorActionPreference = $previousPreference
    if ($buildExitCode -ne 0) { throw "PyInstaller terminou com código $buildExitCode" }

    $exe = Join-Path $repo "dist\Nyx\Nyx.exe"
    if (-not (Test-Path $exe)) { throw "Build terminou sem produzir $exe" }
    $reportPath = Join-Path $repo "build\nyx-self-check.json"
    $env:NYX_SELF_CHECK_REPORT = $reportPath
    $checkProcess = Start-Process -FilePath $exe -ArgumentList @("--self-check") -WindowStyle Hidden -Wait -PassThru
    $checkExitCode = $checkProcess.ExitCode
    Remove-Item Env:\NYX_SELF_CHECK_REPORT -ErrorAction SilentlyContinue
    if ($checkExitCode -ne 0 -or -not (Test-Path $reportPath)) {
        throw "Aplicativo empacotado falhou no autoteste ($checkExitCode). Relatório: $reportPath"
    }
    $report = Get-Content -LiteralPath $reportPath -Raw | ConvertFrom-Json
    if (-not $report.ok) { throw "Autoteste incompleto; consulte $reportPath" }

    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "install.ps1") -Destination (Join-Path $repo "dist\Nyx\install.ps1") -Force
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot "uninstall.ps1") -Destination (Join-Path $repo "dist\Nyx\uninstall.ps1") -Force
    $archive = Join-Path $repo "dist\Nyx-0.1.0-windows-x64-portable.zip"
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    Compress-Archive -Path (Join-Path $repo "dist\Nyx\*") -DestinationPath $archive -CompressionLevel Optimal

    $hash = (Get-FileHash -LiteralPath $exe -Algorithm SHA256).Hash.ToLowerInvariant()
    $archiveHash = (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant()
    $checksumFile = "$archive.sha256"
    Set-Content -LiteralPath $checksumFile -Value "$archiveHash  $(Split-Path -Leaf $archive)" -Encoding ascii
    Write-Output "Build pronto: $exe"
    Write-Output "Autoteste do executável: aprovado"
    Write-Output "SHA256: $hash"
    Write-Output "Pacote portátil: $archive"
    Write-Output "SHA256 ZIP: $archiveHash"
    Write-Output "SHA256 file: $checksumFile"
} finally {
    Pop-Location
}
