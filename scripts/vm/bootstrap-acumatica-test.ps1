# Bootstrap acumatica-test VM as a persistent dev + GitHub self-hosted runner.
#
# ONE-SHOT USAGE (run this on the VM as Administrator after RDP'ing in):
#
#   gsutil cp gs://aesthetik-acumatica-sdk/bootstrap-acumatica-test.ps1 C:\bootstrap.ps1
#   powershell -ExecutionPolicy Bypass -File C:\bootstrap.ps1 -RunnerToken "<TOKEN>"
#
# Get the registration token first (from any machine with gh CLI):
#   gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token
#
# Prerequisites (already on the VM):
#   - Windows Server 2022
#   - SQL Server 2022
#   - .NET Framework 4.8
#   - Acumatica ERP at C:\Program Files\Acumatica ERP\
#
# This script installs (all idempotent - safe to re-run):
#
#   Build tools:
#     [1] .NET 8 SDK               -- dotnet build
#     [2] Git for Windows          -- source control
#     [3] Python 3.11              -- deploy.py, verify.py, pytest, playwright
#
#   Dev tools (manual debugging on the VM):
#     [4] GitHub CLI (gh)          -- PRs, runs, secrets
#     [5] VS Code                  -- IDE
#     [6] SSMS                     -- SQL Server Management Studio
#     [7] Google Chrome            -- Playwright default browser
#
#   CI infrastructure:
#     [8] GitHub Actions runner    -- self-hosted, registered as Windows service
#
# Switches:
#   -SkipDevTools   skip sections 4-7 (only install build tools + runner)
#   -SkipRunner     skip section 8 (only install tools, no runner registration)

param(
    [Parameter(Mandatory=$false)]
    [string]$RunnerToken = "",

    [Parameter(Mandatory=$false)]
    [string]$RunnerName = "acumatica-test",

    [Parameter(Mandatory=$false)]
    [string]$RepoUrl = "https://github.com/studio-b-ai/acumatica-ci-cd",

    [switch]$SkipDevTools,
    [switch]$SkipRunner
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"  # Speeds up Invoke-WebRequest

# PowerShell 5.1 defaults to TLS 1.0/1.1 which GitHub/Python/Microsoft all dropped.
# Force TLS 1.2 for every HTTPS request made by this session.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

Write-Host "=== acumatica-test VM Bootstrap ===" -ForegroundColor Cyan
Write-Host ""

function Write-Step {
    param([string]$Num, [string]$Msg, [string]$Color = "Yellow")
    Write-Host "[$Num] $Msg" -ForegroundColor $Color
}

function Write-Done {
    param([string]$Msg)
    Write-Host "    $Msg" -ForegroundColor Green
}

function Write-Skip {
    param([string]$Msg)
    Write-Host "    $Msg" -ForegroundColor DarkGray
}

function Write-Fail {
    param([string]$Msg)
    Write-Host "    $Msg" -ForegroundColor Red
}

function Download-File {
    param(
        [string]$Uri,
        [string]$OutFile,
        [int]$MaxRetries = 3
    )
    $attempt = 0
    while ($attempt -lt $MaxRetries) {
        $attempt++
        try {
            Invoke-WebRequest -Uri $Uri -OutFile $OutFile -UseBasicParsing -TimeoutSec 120
            return
        } catch {
            if ($attempt -ge $MaxRetries) { throw }
            Write-Host "    Download attempt $attempt failed: $($_.Exception.Message). Retrying..." -ForegroundColor DarkYellow
            Start-Sleep -Seconds (5 * $attempt)
        }
    }
}

# ======================================================================
# [1] .NET 8 SDK
# ======================================================================
try {
    if (-not (Get-Command dotnet -ErrorAction SilentlyContinue)) {
        Write-Step "1/8" "Installing .NET 8 SDK..."
        $installer = "$env:TEMP\dotnet-sdk-installer.exe"
        Download-File "https://aka.ms/dotnet/8.0/dotnet-sdk-win-x64.exe" $installer
        Start-Process -FilePath $installer -ArgumentList "/install", "/quiet", "/norestart" -Wait
        Remove-Item $installer
        $env:Path = "C:\Program Files\dotnet;$env:Path"
        Write-Done ".NET SDK installed: $(dotnet --version)"
    } else {
        Write-Step "1/8" ".NET SDK already installed: $(dotnet --version)" "Green"
    }
} catch {
    Write-Fail ".NET SDK install failed: $_"
}

# ======================================================================
# [2] Git for Windows
# ======================================================================
try {
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Write-Step "2/8" "Installing Git for Windows..."
        $gitInstaller = "$env:TEMP\Git-installer.exe"
        Download-File "https://github.com/git-for-windows/git/releases/download/v2.47.1.windows.1/Git-2.47.1-64-bit.exe" $gitInstaller
        Start-Process -FilePath $gitInstaller -ArgumentList "/VERYSILENT", "/NORESTART" -Wait
        Remove-Item $gitInstaller
        $env:Path = "C:\Program Files\Git\cmd;$env:Path"
        Write-Done "Git installed: $(git --version)"
    } else {
        Write-Step "2/8" "Git already installed: $(git --version)" "Green"
    }
} catch {
    Write-Fail "Git install failed: $_"
}

# ======================================================================
# [3] Python 3.11
# ======================================================================
try {
    if (-not (Get-Command python -ErrorAction SilentlyContinue)) {
        Write-Step "3/8" "Installing Python 3.11..."
        $pyInstaller = "$env:TEMP\python-installer.exe"
        Download-File "https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe" $pyInstaller
        # Install for all users, add to PATH, include pip
        Start-Process -FilePath $pyInstaller -ArgumentList "/quiet", "InstallAllUsers=1", "PrependPath=1", "Include_pip=1", "Include_test=0" -Wait
        Remove-Item $pyInstaller
        # Add to current session PATH
        $env:Path = "C:\Program Files\Python311;C:\Program Files\Python311\Scripts;$env:Path"
        Write-Done "Python installed: $(python --version)"
    } else {
        Write-Step "3/8" "Python already installed: $(python --version)" "Green"
    }
} catch {
    Write-Fail "Python install failed: $_"
}

# ======================================================================
# Dev tools (skip with -SkipDevTools)
# ======================================================================
if ($SkipDevTools) {
    Write-Host ""
    Write-Host "Skipping dev tools (sections 4-7) -- -SkipDevTools flag set" -ForegroundColor DarkGray
    Write-Host ""
} else {

# ======================================================================
# [4] GitHub CLI (gh)
# ======================================================================
try {
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Step "4/8" "Installing GitHub CLI..."
        $ghInstaller = "$env:TEMP\gh-installer.msi"
        Download-File "https://github.com/cli/cli/releases/download/v2.65.0/gh_2.65.0_windows_amd64.msi" $ghInstaller
        Start-Process -FilePath msiexec.exe -ArgumentList "/i", $ghInstaller, "/quiet", "/norestart" -Wait
        Remove-Item $ghInstaller
        $env:Path = "C:\Program Files\GitHub CLI;$env:Path"
        Write-Done "GitHub CLI installed: $(gh --version | Select-Object -First 1)"
    } else {
        Write-Step "4/8" "GitHub CLI already installed: $(gh --version | Select-Object -First 1)" "Green"
    }
} catch {
    Write-Fail "GitHub CLI install failed: $_"
}

# ======================================================================
# [5] VS Code
# ======================================================================
try {
    $vscodeExe = "C:\Program Files\Microsoft VS Code\Code.exe"
    if (-not (Test-Path $vscodeExe)) {
        Write-Step "5/8" "Installing VS Code..."
        $vscodeInstaller = "$env:TEMP\vscode-installer.exe"
        Download-File "https://aka.ms/win32-x64-system-stable" $vscodeInstaller
        # Silent install, add to PATH, don't launch after install
        Start-Process -FilePath $vscodeInstaller -ArgumentList "/VERYSILENT", "/NORESTART", "/MERGETASKS=!runcode,addcontextmenufiles,addcontextmenufolders,addtopath" -Wait
        Remove-Item $vscodeInstaller
        Write-Done "VS Code installed"
    } else {
        Write-Step "5/8" "VS Code already installed" "Green"
    }
} catch {
    Write-Fail "VS Code install failed: $_"
}

# ======================================================================
# [6] SSMS (SQL Server Management Studio)
# ======================================================================
try {
    $ssmsExe = "C:\Program Files (x86)\Microsoft SQL Server Management Studio 20\Common7\IDE\Ssms.exe"
    $ssmsExe19 = "C:\Program Files (x86)\Microsoft SQL Server Management Studio 19\Common7\IDE\Ssms.exe"
    if ((Test-Path $ssmsExe) -or (Test-Path $ssmsExe19)) {
        Write-Step "6/8" "SSMS already installed" "Green"
    } else {
        Write-Step "6/8" "Installing SSMS (this takes 5-10 min)..."
        $ssmsInstaller = "$env:TEMP\SSMS-Setup.exe"
        Download-File "https://aka.ms/ssmsfullsetup" $ssmsInstaller
        Start-Process -FilePath $ssmsInstaller -ArgumentList "/install", "/quiet", "/norestart" -Wait
        Remove-Item $ssmsInstaller
        Write-Done "SSMS installed"
    }
} catch {
    Write-Fail "SSMS install failed: $_"
}

# ======================================================================
# [7] Google Chrome
# ======================================================================
try {
    $chromeExe = "C:\Program Files\Google\Chrome\Application\chrome.exe"
    if (Test-Path $chromeExe) {
        Write-Step "7/8" "Chrome already installed" "Green"
    } else {
        Write-Step "7/8" "Installing Google Chrome..."
        $chromeInstaller = "$env:TEMP\chrome-installer.exe"
        Download-File "https://dl.google.com/chrome/install/latest/chrome_installer.exe" $chromeInstaller
        Start-Process -FilePath $chromeInstaller -ArgumentList "/silent", "/install" -Wait
        Remove-Item $chromeInstaller
        Write-Done "Chrome installed"
    }
} catch {
    Write-Fail "Chrome install failed: $_"
}

} # end !SkipDevTools

# ======================================================================
# [8] GitHub Actions Self-Hosted Runner
# ======================================================================
if ($SkipRunner) {
    Write-Host ""
    Write-Host "Skipping runner section -- -SkipRunner flag set" -ForegroundColor DarkGray
} else {

$runnerDir = "C:\actions-runner"

# Download if not present
if (-not (Test-Path "$runnerDir\config.cmd")) {
    Write-Step "8/8" "Downloading GitHub Actions runner..."
    try {
        New-Item -ItemType Directory -Force -Path $runnerDir | Out-Null
        Set-Location $runnerDir

        $runnerVersion = "2.321.0"
        $runnerZip = "actions-runner-win-x64-$runnerVersion.zip"
        Download-File "https://github.com/actions/runner/releases/download/v$runnerVersion/$runnerZip" "$runnerDir\$runnerZip"
        Add-Type -AssemblyName System.IO.Compression.FileSystem
        [System.IO.Compression.ZipFile]::ExtractToDirectory("$runnerDir\$runnerZip", $runnerDir)
        Remove-Item "$runnerDir\$runnerZip"
        Write-Done "Runner downloaded to $runnerDir"
    } catch {
        Write-Fail "Runner download failed: $_"
    }
} else {
    Write-Step "8/8" "GitHub runner already downloaded at $runnerDir" "Green"
}

# Configure + register
Set-Location $runnerDir

if (-not $RunnerToken) {
    Write-Host ""
    Write-Host "Runner NOT configured -- no -RunnerToken provided" -ForegroundColor Yellow
    Write-Host "To complete setup:" -ForegroundColor Cyan
    Write-Host "   gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token"
    Write-Host "   powershell -ExecutionPolicy Bypass -File C:\bootstrap.ps1 -RunnerToken `"<TOKEN>`" -SkipDevTools"
} else {
    # Check if already configured
    $alreadyConfigured = Test-Path "$runnerDir\.runner"
    if ($alreadyConfigured) {
        Write-Host "    Runner already configured. Removing old config..." -ForegroundColor Yellow
        try { & "$runnerDir\svc.cmd" stop 2>&1 | Out-Null } catch {}
        try { & "$runnerDir\svc.cmd" uninstall 2>&1 | Out-Null } catch {}
        Remove-Item "$runnerDir\.runner" -Force -ErrorAction SilentlyContinue
        Remove-Item "$runnerDir\.credentials" -Force -ErrorAction SilentlyContinue
        Remove-Item "$runnerDir\.credentials_rsaparams" -Force -ErrorAction SilentlyContinue
    }

    Write-Host "    Configuring runner..." -ForegroundColor Yellow
    & "$runnerDir\config.cmd" `
        --url $RepoUrl `
        --token $RunnerToken `
        --name $RunnerName `
        --labels "self-hosted,windows,acumatica-sdk" `
        --work "_work" `
        --unattended `
        --replace

    if ($LASTEXITCODE -ne 0) {
        Write-Fail "Runner configuration failed with exit code $LASTEXITCODE"
    } else {
        Write-Done "Runner configured successfully"
        Write-Host "    Installing runner as Windows service..." -ForegroundColor Yellow
        & "$runnerDir\svc.cmd" install
        & "$runnerDir\svc.cmd" start
        Write-Done "Runner service installed and started"
    }
}

} # end !SkipRunner

# ======================================================================
# Summary
# ======================================================================
Write-Host ""
Write-Host "=== Bootstrap complete ===" -ForegroundColor Green
Write-Host ""
Write-Host "Installed tools:" -ForegroundColor Cyan
if (Get-Command dotnet -ErrorAction SilentlyContinue) { Write-Host "  [OK] .NET SDK      : $(dotnet --version)" }
if (Get-Command git -ErrorAction SilentlyContinue)    { Write-Host "  [OK] Git           : $(git --version)" }
if (Get-Command python -ErrorAction SilentlyContinue) { Write-Host "  [OK] Python        : $(python --version)" }
if (Get-Command gh -ErrorAction SilentlyContinue)     { Write-Host "  [OK] GitHub CLI    : $(gh --version | Select-Object -First 1)" }
if (Test-Path "C:\Program Files\Microsoft VS Code\Code.exe")                                    { Write-Host "  [OK] VS Code       : installed" }
if (Test-Path "C:\Program Files (x86)\Microsoft SQL Server Management Studio 20\Common7\IDE\Ssms.exe") { Write-Host "  [OK] SSMS 20       : installed" }
if (Test-Path "C:\Program Files (x86)\Microsoft SQL Server Management Studio 19\Common7\IDE\Ssms.exe") { Write-Host "  [OK] SSMS 19       : installed" }
if (Test-Path "C:\Program Files\Google\Chrome\Application\chrome.exe")                          { Write-Host "  [OK] Chrome        : installed" }
if (Test-Path "C:\actions-runner\.runner")                                                      { Write-Host "  [OK] GH Runner     : registered ($RunnerName)" }
Write-Host ""
Write-Host "Runner status:" -ForegroundColor Cyan
Write-Host "  $RepoUrl/settings/actions/runners"
Write-Host ""
Write-Host "To reset the runner token later:" -ForegroundColor DarkGray
Write-Host "  gh api --method POST repos/studio-b-ai/acumatica-ci-cd/actions/runners/registration-token --jq .token"
