param(
    [string]$Python = "python",
    [string]$TargetTriple = "x86_64-pc-windows-msvc"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDirectory = Join-Path $ProjectRoot "build\sidecar"
$BinaryDirectory = Join-Path $ProjectRoot "src-tauri\binaries"

$PythonVersion = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect Python interpreter: $Python"
}
if ($PythonVersion -ne "3.12") {
    throw "Qingwu release sidecar must be built with Python 3.12; got $PythonVersion from $Python"
}

& $Python -m PyInstaller --noconfirm --clean --onefile --name qingwu-sidecar `
    --distpath $DistDirectory `
    --workpath (Join-Path $ProjectRoot "build\pyinstaller") `
    --specpath (Join-Path $ProjectRoot "build") `
    --paths (Join-Path $ProjectRoot "python") `
    --add-data "$(Join-Path $ProjectRoot 'templates');templates" `
    --add-data "$(Join-Path $ProjectRoot 'schemas');schemas" `
    (Join-Path $ProjectRoot "scripts\sidecar_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

New-Item -ItemType Directory -Force -Path $BinaryDirectory | Out-Null
$Source = Join-Path $DistDirectory "qingwu-sidecar.exe"
$Destination = Join-Path $BinaryDirectory "qingwu-sidecar-$TargetTriple.exe"
Copy-Item -LiteralPath $Source -Destination $Destination -Force
Write-Host "Sidecar ready: $Destination"
