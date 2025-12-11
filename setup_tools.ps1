# Script de Configuracion y Limpieza
# Ejecutar una vez para organizar el proyecto

$ErrorActionPreference = "Stop"

$baseDir = Get-Location
$cookiesDir = Join-Path $baseDir "cookies"
$dataDir = Join-Path $baseDir "data"
$downloadsDir = Join-Path $baseDir "downloads"
$toolsDir = Join-Path $baseDir "tools"

Write-Host "Creating folders..." -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path $cookiesDir | Out-Null
New-Item -ItemType Directory -Force -Path $dataDir | Out-Null
New-Item -ItemType Directory -Force -Path $downloadsDir | Out-Null
New-Item -ItemType Directory -Force -Path $toolsDir | Out-Null

# --- 1. Move Cookies ---
Write-Host "Moving cookies..." -ForegroundColor Yellow
$cookieFiles = @(
    "cookies.txt", "cookies_facebook.txt", "cookies_instagram.txt", "cookies_jav.txt",
    "cookies_pornhub.txt", "cookies_tiktok.txt", "cookies_twitter.txt", 
    "cookies_x.txt", "cookies_xvideos.txt", "vimeo_cookies.txt", "dropbox_cookies.txt"
)

foreach ($file in $cookieFiles) {
    if (Test-Path $file) {
        Move-Item -Path $file -Destination $cookiesDir -Force
        Write-Host "   Moved: $file"
    }
}

# --- 2. Move Data (JSON and Session) ---
Write-Host "Moving data and session..." -ForegroundColor Yellow
$dataFiles = @("descargas.json", "hashtags.json", "mi_bot_pro.session", "mi_bot_pro.session-journal")

foreach ($file in $dataFiles) {
    if (Test-Path $file) {
        Move-Item -Path $file -Destination $dataDir -Force
        Write-Host "   Moved: $file"
    }
}

# --- 3. Clean up downloads ---
Write-Host "Moving loose video files..." -ForegroundColor Yellow
Get-ChildItem -File | Where-Object { $_.Extension -match "\.(mp4|mkv|webm|mp3|jpg|png)$" } | ForEach-Object {
    if ($_.Name -match "^dl_" -or $_.Name -match "^t_") {
        Move-Item -Path $_.FullName -Destination $downloadsDir -Force
        Write-Host "   Moved: $($_.Name)"
    }
}

# --- 4. Download Aria2c ---
$aria2Path = Join-Path $toolsDir "aria"+"2c.exe"
if (-not (Test-Path $aria2Path)) {
    Write-Host "Downloading aria2c (High speed engine)..." -ForegroundColor Green
    
    $url = "https://github.com/aria2/aria2/releases/download/release-1.37.0/aria2-1.37.0-win-64bit-build1.zip"
    $zipPath = Join-Path $toolsDir "aria"+"2.zip"
    
    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Invoke-WebRequest -Uri $url -OutFile $zipPath
        
        Write-Host "Extracting aria2c..."
        Expand-Archive -Path $zipPath -DestinationPath $toolsDir -Force
        
        # Move exe to root of tools
        $extractedFolder = Join-Path $toolsDir "aria"+"2-1.37.0-win-64bit-build1"
        $exeSource = Join-Path $extractedFolder "aria"+"2c.exe"
        
        if (Test-Path $exeSource) {
            Move-Item -Path $exeSource -Destination $toolsDir -Force
            Write-Host "Aria2c installed correctly."
        } else {
            Write-Host "Error: exe not found in zip." -ForegroundColor Red
        }
        
        # Cleanup
        Remove-Item -Path $zipPath -Force
        Remove-Item -Path $extractedFolder -Recurse -Force
    } catch {
        Write-Host "Error downloading Aria2: $_" -ForegroundColor Red
    }
} else {
    Write-Host "Aria2 is already installed." -ForegroundColor Green
}

Write-Host "`nOrganization and Setup Completed!" -ForegroundColor Cyan
Write-Host "You can now start the bot normally."
