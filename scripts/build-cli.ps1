param(
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$DistDirectory = Join-Path $ProjectRoot "release"

$PythonVersion = (& $Python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')").Trim()
if ($LASTEXITCODE -ne 0) {
    throw "Unable to inspect Python interpreter: $Python"
}
if ($PythonVersion -ne "3.12") {
    throw "Qingwu release CLI must be built with Python 3.12; got $PythonVersion from $Python"
}

& $Python -m PyInstaller --noconfirm --clean --onefile --name qingwu `
    --distpath $DistDirectory `
    --workpath (Join-Path $ProjectRoot "build\pyinstaller-cli") `
    --specpath (Join-Path $ProjectRoot "build") `
    --paths (Join-Path $ProjectRoot "python") `
    --add-data "$(Join-Path $ProjectRoot 'templates');templates" `
    --add-data "$(Join-Path $ProjectRoot 'schemas');schemas" `
    (Join-Path $ProjectRoot "scripts\cli_entry.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Write-Host "CLI ready: $(Join-Path $DistDirectory 'qingwu.exe')"
