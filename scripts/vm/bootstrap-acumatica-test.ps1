# Bootstrap acumatica-test VM as a GitHub self-hosted runner for Acuminator + validate-publish.
#
# Run this ONCE on the GCE VM (acumatica-test, 136.115.233.148) as Administrator:
#   powershell -ExecutionPolicy Bypass -File bootstrap-acumatica-test.ps1
#
# Prerequisites (already installed on the VM):
#   - Windows Server 2022
#   - SQL Server 2022
#   - .NET Framework 4.8
#   - Acumatica ERP at C:\Program Files\Acumatica ERP\
#
# What this script installs:
#   - .NET 8 SDK (for dotnet build)
#   - Git for Windows
#   - GitHub self-hosted runner (registered with studio-b-ai/acumatica-ci-cd)
#
# After this script runs, register the runner with a registration token from:
#   gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token

$ErrorActionPreference = "Stop"

Write-Host "=== acumatica-test VM Bootstrap ===" -ForegroundColor Cyan

# ─── .NET 8 SDK ───────────────────────────────────────────────────────
if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
    Write-Host "[1/3] Installing .NET 8 SDK..." -ForegroundColor Yellow
    $installer = "$env:TEMP\dotnet-sdk-installer.exe"
    Invoke-WebRequest -Uri "https://aka.ms/dotnet/8.0/dotnet-sdk-win-x64.exe" -OutFile $installer
    Start-Process -FilePath $installer -ArgumentList "/install", "/quiet", "/norestart" -Wait
    Remove-Item $installer
    $env:Path += ";C:\Program Files\dotnet"
    Write-Host "    .NET SDK installed: $(dotnet --version)" -ForegroundColor Green
} else {
    Write-Host "[1/3] .NET SDK already installed: $(dotnet --version)" -ForegroundColor Green
}

# ─── Git for Windows ──────────────────────────────────────────────────
if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "[2/3] Installing Git for Windows..." -ForegroundColor Yellow
    $gitInstaller = "$env:TEMP\Git-installer.exe"
    Invoke-WebRequest -Uri "https://github.com/git-for-windows/git/releases/latest/download/Git-2.47.1-64-bit.exe" -OutFile $gitInstaller
    Start-Process -FilePath $gitInstaller -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
    Remove-Item $gitInstaller
    $env:Path += ";C:\Program Files\Git\cmd"
    Write-Host "    Git installed: $(git --version)" -ForegroundColor Green
} else {
    Write-Host "[2/3] Git already installed: $(git --version)" -ForegroundColor Green
}

# ─── GitHub Actions Self-Hosted Runner ────────────────────────────────
$runnerDir = "C:\actions-runner"
if (-not (Test-Path "$runnerDir\run.cmd")) {
    Write-Host "[3/3] Downloading GitHub Actions runner..." -ForegroundColor Yellow
    New-Item -ItemType Directory -Force -Path $runnerDir | Out-Null
    Set-Location $runnerDir

    $runnerVersion = "2.321.0"
    $runnerZip = "actions-runner-win-x64-$runnerVersion.zip"
    Invoke-WebRequest -Uri "https://github.com/actions/runner/releases/download/v$runnerVersion/$runnerZip" -OutFile $runnerZip
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [System.IO.Compression.ZipFile]::ExtractToDirectory("$runnerDir\$runnerZip", $runnerDir)
    Remove-Item "$runnerDir\$runnerZip"

    Write-Host "    Runner downloaded to $runnerDir" -ForegroundColor Green
    Write-Host ""
    Write-Host "=== NEXT STEPS ===" -ForegroundColor Cyan
    Write-Host "1. Get a registration token from your Mac:"
    Write-Host "   gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token"
    Write-Host ""
    Write-Host "2. On this VM, configure the runner:"
    Write-Host "   cd C:\actions-runner"
    Write-Host "   .\config.cmd --url https://github.com/studio-b-ai/acumatica-ci-cd --token <TOKEN> --name acumatica-test --labels self-hosted,windows,acumatica-sdk --unattended --replace"
    Write-Host ""
    Write-Host "3. Install as Windows service (so it restarts on reboot):"
    Write-Host "   .\svc.sh install"
    Write-Host "   .\svc.sh start"
    Write-Host ""
    Write-Host "4. Verify the runner appears at:"
    Write-Host "   https://github.com/studio-b-ai/acumatica-ci-cd/settings/actions/runners"
} else {
    Write-Host "[3/3] GitHub runner already downloaded at $runnerDir" -ForegroundColor Green
}

Write-Host ""
Write-Host "Bootstrap complete." -ForegroundColor Green
