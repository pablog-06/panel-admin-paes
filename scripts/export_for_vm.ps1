param(
    [switch]$IncludeLogs,
    [switch]$IncludeBackups
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$DataDb = Join-Path $ProjectRoot "data\admin_paes.sqlite"
$ExportsDir = Join-Path $ProjectRoot "exports"
$StageDir = Join-Path $ExportsDir "vm_export_stage"
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ZipPath = Join-Path $ExportsDir "panel_paes_vm_data_$Timestamp.zip"

if (-not (Test-Path $DataDb)) {
    throw "No existe data/admin_paes.sqlite. Abre la app local primero o verifica la ruta."
}

New-Item -ItemType Directory -Force -Path $ExportsDir | Out-Null
if (Test-Path $StageDir) {
    Remove-Item -LiteralPath $StageDir -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $StageDir | Out-Null

New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "data") | Out-Null
Copy-Item -LiteralPath $DataDb -Destination (Join-Path $StageDir "data\admin_paes.sqlite") -Force

$ImageAssets = Join-Path $ProjectRoot "assets\synced_trello_images"
$FileAssets = Join-Path $ProjectRoot "assets\synced_trello_files"
if (Test-Path $ImageAssets) {
    New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "assets") | Out-Null
    Copy-Item -LiteralPath $ImageAssets -Destination (Join-Path $StageDir "assets\synced_trello_images") -Recurse -Force
}
if (Test-Path $FileAssets) {
    New-Item -ItemType Directory -Force -Path (Join-Path $StageDir "assets") | Out-Null
    Copy-Item -LiteralPath $FileAssets -Destination (Join-Path $StageDir "assets\synced_trello_files") -Recurse -Force
}

if ($IncludeLogs) {
    $Logs = Join-Path $ProjectRoot "data\logs"
    if (Test-Path $Logs) {
        Copy-Item -LiteralPath $Logs -Destination (Join-Path $StageDir "data\logs") -Recurse -Force
    }
}

if ($IncludeBackups) {
    $Backups = Join-Path $ProjectRoot "data\backups"
    if (Test-Path $Backups) {
        Copy-Item -LiteralPath $Backups -Destination (Join-Path $StageDir "data\backups") -Recurse -Force
    }
}

Compress-Archive -Path (Join-Path $StageDir "*") -DestinationPath $ZipPath -Force
Remove-Item -LiteralPath $StageDir -Recurse -Force

Write-Host "Export creado:" -ForegroundColor Green
Write-Host $ZipPath
Write-Host "No incluye .streamlit/secrets.toml." -ForegroundColor Yellow
