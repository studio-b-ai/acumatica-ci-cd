# Bootstrap acumatica-test VM as a GitHub self-hosted runner for Acuminator + validate-publish.
#
# ONE-SHOT USAGE (run this on the VM as Administrator after RDP'ing in):
#
#   # Download the latest script from GCS, then run with the registration token
#   gsutil cp gs://aesthetik-acumatica-sdk/bootstrap-acumatica-test.ps1 C:\bootstrap.ps1
#   powershell -ExecutionPolicy Bypass -File C:\bootstrap.ps1 -RunnerToken "<TOKEN_FROM_GH_API>"
#
# Get the registration token first (from any machine with gh CLI):
#   gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token
#
# Prerequisites (already installed on the VM):
#   - Windows Server 2022
#   - SQL Server 2022
#   - .NET Framework 4.8
#   - Acumatica ERP at C:\Program Files\Acumatica ERP\
#
# What this script installs AND configures:
#   - .NET 8 SDK (for dotnet build)
#   - Git for Windows
#   - GitHub self-hosted runner, registered with labels: self-hosted,windows,acumatica-sdk
#   - Runner as Windows service (auto-start on boot)

param(
    [Parameter(Mandatory=$false)]
    [string]$RunnerToken = "",

    [Parameter(Mandatory=$false)]
    [string]$RunnerName = "acumatica-test",

    [Parameter(Mandatory=$false)]
    [string]$RepoUrl = "https://github.com/studio-b-ai/acumatica-ci-cd"
)

$ErrorActionPreference = "Stop"

Write-Host "=== acumatica-test VM Bootstrap ===" -ForegroundColor Cyan

# --- .NET 8 SDK -------------------------------------------------------
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Host "[1/4] Installing .NET 8 SDK..." -ForegroundColor Yellow
    $installer = "$env:TEMP\dotnet-sdk-installer.exe"
    Invoke-WebRequest -Uri "https://aka.ms/dotnet/8.0/dotnet-sdk-win-x64.exe" -OutFile $installer
    Start-Process -FilePath $installer -ArgumentList "/install", "/quiet", "/norestart" -Wait
    Remove-Item $installer
    $env:Path = "C:\Program Files\dotnet;$env:Path"
    Write-Host "    .NET SDK installed: $(dotnet --version)" -ForegroundColor Green
} else {
    Write-Host "[1/4] .NET SDK already installed: $(dotnet --version)" -ForegroundColor Green
}

# --- Git for Windows --------------------------------------------------
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[2/4] Installing Git for Windows..." -ForegroundColor Yellow
    $gitInstaller = "$env:TEMP\Git-installer.exe"
    Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/latest/download/Git-2.47.1-64-bit.exe" -OutFile $gitInstaller
    Start-Process -FilePath $gitInstaller -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
    Remove-Item $gitInstaller
    $env:Path = "C:\Program Files\Git\cmd;$env:Path"
    Write-Host "    Git installed: $(git --version)" -ForegroundColor Green
} else {
    Write-Host "[2/4] Git already installed: $(git --version)" -ForegroundColor Green
}

# --- GitHub Actions Self-Hosted Runner (download) --------------------
$runnerDir = "C:\actions-runner"
if (-not (Test-Path "$runnerDir\config.cmd")) {
    Write-Host "[3/4] Downloading GitHub Actions runner..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $runnerDir | Out-Null
    Set-Location $runnerDir

    $runnerVersion = "2.321.0"
    $runnerZip = "actions-runner-win-x64-$runnerVersion.zip"
    Invoke-WebRequest -Uri "https://github.com/actions/runner/releases/download/v$runnerVersion/$runnerZip" -OutFile $runnerZip
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory("$runnerDir\$runnerZip", $runnerDir)
    Remove-Item "$runnerDir\$runnerZip"
    Write-Host "    Runner downloaded to $runnerDir" -ForegroundColor Green
} else {
    Write-Host "[3/4] GitHub runner already downloaded at $runnerDir" -ForegroundColor Green
}

# --- Runner: configure + install as service ---------------------------
Set-Location $runnerDir

if (-not $RunnerToken) {
    Write-Host ""
    Write-Host "[4/4] SKIPPED -- no -RunnerToken provided" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "To complete setup, re-run this script with a token:" -ForegroundColor Cyan
    Write-Host "   gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token"
    Write-Host "   powershell -ExecutionPolicy Bypass -File bootstrap-acumatica-test.ps1 -RunnerToken `"<TOKEN>`""
    exit 0
}

# Check if already configured
$alreadyConfigured = Test-Path "$runnerDir\.runner"
if ($alreadyConfigured) {
    Write-Host "[4/4] Runner already configured. Removing old config..." -ForegroundColor Yellow
    # Try to stop and remove existing service first
    try { & "$runnerDir\svc.cmd" stop 2>&1 | Out-Null } catch {}
    try { & "$runnerDir\svc.cmd" uninstall 2>&1 | Out-Null } catch {}
    # Unconfigure (requires token -- but since we can't remove interactively, force-delete config)
    Remove-Item "$runnerDir\.runner" -Force -ErrorAction SilentlyContinue
    Remove-Item "$runnerDir\.credentials" -Force -ErrorAction SilentlyContinue
    Remove-Item "$runnerDir\.credentials_rsaparams" -Force -ErrorAction SilentlyContinue
}

Write-Host "[4/4] Configuring runner..." -ForegroundColor Yellow
& "$runnerDir\config.cmd" `
    --url $RepoUrl `
    --token $RunnerToken `
    --name $RunnerName `
    --labels "self-hosted,windows,acumatica-sdk" `
    --work "_work" `
    --unattended `
    --replace

if ($LASTEXITCODE -ne 0) {
    Write-Host "    Runner configuration FAILED with exit code $LASTEXITCODE" -ForegroundColor Red
    exit 1
}

Write-Host "    Runner configured successfully" -ForegroundColor Green

Write-Host "    Installing runner as Windows service..." -ForegroundColor Yellow
& "$runnerDir\svc.cmd" install
& "$runnerDir\svc.cmd" start

Write-Host ""
Write-Host "=== Bootstrap complete ===" -ForegroundColor Green
Write-Host "Runner should now appear at:" -ForegroundColor Cyan
Write-Host "  $RepoUrl/settings/actions/runners"
Write-Host ""
Write-Host "Check status:" -ForegroundColor Cyan
Write-Host "  & `"$runnerDir\svc.cmd`" status"
