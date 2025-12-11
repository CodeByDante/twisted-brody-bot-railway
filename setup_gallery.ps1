$ErrorActionPreference = "Stop"
$baseDir = Get-Location
$toolsDir = Join-Path $baseDir "tools"

# Asegurar que tools existe
if (-not (Test-Path $toolsDir)) { New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null }

$exePath = Join-Path $toolsDir "gallery-dl.exe"
$url = "https://github.com/mikf/gallery-dl/releases/download/v1.26.9/gallery-dl.exe" 

Write-Host "🚀 Descargando gallery-dl..." -ForegroundColor Cyan

try {
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    Invoke-WebRequest -Uri $url -OutFile $exePath
    Write-Host "✅ gallery-dl.exe instalado en $toolsDir" -ForegroundColor Green
} catch {
    Write-Host "❌ Error descargando: $_" -ForegroundColor Red
}
