<#
.SYNOPSIS
    Respalda la memoria episodica local antes de un git pull / merge.

.DESCRIPTION
    storage/episodic_memory.json ahora esta versionado en el repositorio
    (PR de retoma). Eso significa que un `git pull` puede sobrescribir o
    bloquear tu archivo local, que contiene tus episodios reales.

    Este script:
      1. Copia storage/episodic_memory.json a storage/episodic_memory.backup.json
      2. Guarda ademas una copia con fecha en storage/backups/
      3. Muestra una advertencia con los pasos siguientes recomendados

    No borra nada. No toca git. Solo copia. Es seguro correrlo varias veces.

.EXAMPLE
    .\scripts\backup_memory.ps1
    .\scripts\backup_memory.ps1 -Verbose
#>
[CmdletBinding()]
param(
    [string]$Origen  = "storage\episodic_memory.json",
    [string]$Destino = "storage\episodic_memory.backup.json",
    [string]$CarpetaHistorial = "storage\backups"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "=== Respaldo de memoria episodica ===" -ForegroundColor Cyan

if (-not (Test-Path $Origen)) {
    Write-Host "[i] No existe '$Origen'. No hay nada que respaldar." -ForegroundColor Yellow
    Write-Host "    (Es normal si todavia no has conversado con Lautaro en esta maquina.)"
    exit 0
}

# 1) Respaldo fijo (el que menciona el README)
Copy-Item $Origen $Destino -Force
Write-Host "[ok] Copia creada: $Destino" -ForegroundColor Green

# 2) Respaldo con fecha, para no pisar respaldos anteriores
if (-not (Test-Path $CarpetaHistorial)) {
    New-Item -ItemType Directory -Path $CarpetaHistorial | Out-Null
}
$sello   = Get-Date -Format "yyyyMMdd-HHmmss"
$fechado = Join-Path $CarpetaHistorial "episodic_memory.$sello.json"
Copy-Item $Origen $fechado -Force
Write-Host "[ok] Copia fechada:  $fechado" -ForegroundColor Green

# 3) Dato util: cuantos episodios se respaldaron
try {
    $datos = Get-Content $Origen -Raw -Encoding UTF8 | ConvertFrom-Json
    $n = @($datos.episodes).Count
    Write-Host "[i] Episodios respaldados: $n"
} catch {
    Write-Host "[!] El JSON no se pudo leer ($($_.Exception.Message))." -ForegroundColor Yellow
    Write-Host "    El respaldo se hizo igual: se copio el archivo tal cual."
}

Write-Host ""
Write-Host "ADVERTENCIA" -ForegroundColor Yellow
Write-Host "  storage/episodic_memory.json esta versionado en git." -ForegroundColor Yellow
Write-Host "  Un 'git pull' o un merge puede sobrescribir tus episodios locales." -ForegroundColor Yellow
Write-Host ""
Write-Host "Siguiente paso recomendado (una sola vez por maquina):"
Write-Host "  git update-index --skip-worktree storage/episodic_memory.json" -ForegroundColor Cyan
Write-Host ""
Write-Host "Para revertirlo cuando quieras volver a versionar el archivo:"
Write-Host "  git update-index --no-skip-worktree storage/episodic_memory.json" -ForegroundColor Cyan
Write-Host ""
