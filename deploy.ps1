# ELLIE Trading -- Deploy Script
# Usage:
#   .\deploy.ps1           -- build frontend + deploy everything + restart
#   .\deploy.ps1 -Backend  -- deploy api.py only (no build)
#   .\deploy.ps1 -Frontend -- build + deploy frontend only

param(
    [switch]$Backend,
    [switch]$Frontend
)

$KEY    = "C:\Users\humes\.ssh\id_ed25519"
$SERVER = "root@159.89.139.43"
$APP    = "/home/ellie/app"
$SSH    = "ssh -i $KEY -o StrictHostKeyChecking=no $SERVER"

$deployAll      = (-not $Backend) -and (-not $Frontend)
$deployBackend  = $deployAll -or $Backend
$deployFrontend = $deployAll -or $Frontend

Write-Host ""
Write-Host "ELLIE Deploy" -ForegroundColor Cyan

# 1. Build frontend
if ($deployFrontend) {
    Write-Host ""
    Write-Host "Building frontend..." -ForegroundColor Yellow
    Push-Location "$PSScriptRoot\web"
    npx vite build
    $buildExit = $LASTEXITCODE
    Pop-Location
    if ($buildExit -ne 0) {
        Write-Host "Build failed -- aborting." -ForegroundColor Red
        exit 1
    }
    Write-Host "Build complete." -ForegroundColor Green
}

# 2. Upload api.py
if ($deployBackend) {
    Write-Host ""
    Write-Host "Uploading api.py..." -ForegroundColor Yellow
    scp -i $KEY -o StrictHostKeyChecking=no "$PSScriptRoot\api.py" "${SERVER}:${APP}/api.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "api.py upload failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "api.py uploaded." -ForegroundColor Green
}

# 3. Upload frontend dist + fix permissions
if ($deployFrontend) {
    Write-Host ""
    Write-Host "Uploading frontend..." -ForegroundColor Yellow
    scp -i $KEY -o StrictHostKeyChecking=no -r "$PSScriptRoot\web\dist\*" "${SERVER}:${APP}/web/dist/"
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Frontend upload failed." -ForegroundColor Red
        exit 1
    }
    Write-Host "Fixing permissions..." -ForegroundColor Yellow
    $fixCmd = "chmod 755 $APP/web/dist/assets; chmod 644 $APP/web/dist/assets/*; chmod 644 $APP/web/dist/index.html"
    ssh -i $KEY -o StrictHostKeyChecking=no $SERVER $fixCmd
    Write-Host "Frontend uploaded." -ForegroundColor Green
}

# 4. Restart service
Write-Host ""
Write-Host "Restarting ellie service..." -ForegroundColor Yellow
$restartCmd = "systemctl restart ellie; sleep 3; systemctl is-active ellie"
ssh -i $KEY -o StrictHostKeyChecking=no $SERVER $restartCmd
if ($LASTEXITCODE -ne 0) {
    Write-Host "Service restart failed -- check logs on server." -ForegroundColor Red
    exit 1
}
Write-Host "Service restarted and running." -ForegroundColor Green

Write-Host ""
Write-Host "Deploy complete!" -ForegroundColor Cyan
Write-Host ""
