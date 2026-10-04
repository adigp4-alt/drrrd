<#
.SYNOPSIS
    Installs a working game-streaming stack on Windows using winget.

.DESCRIPTION
    Packages are grouped into tiers so you can start small:

      core         OBS, a chat client, Discord - enough to go live tonight
      recommended  core, plus audio routing, clip trimming and a webcam tool
      all          everything, including the heavyweight video editor

    The script never fails the whole run because one package is unavailable:
    each id is checked against the winget catalogue first, anything missing is
    reported at the end, and anything already installed is skipped.

.PARAMETER Tier
    core, recommended (default) or all.

.PARAMETER DryRun
    Print what would happen without installing anything.

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File setup-windows.ps1
    powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -Tier all
    powershell -ExecutionPolicy Bypass -File setup-windows.ps1 -DryRun
#>

[CmdletBinding()]
param(
    [ValidateSet('core', 'recommended', 'all')]
    [string]$Tier = 'recommended',

    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

# PowerShell 7.4+ turns a non-zero exit code from a native command into a
# terminating error when ErrorActionPreference is Stop. We read winget's exit
# codes deliberately - a package that isn't in the catalogue is information,
# not a reason to abandon the run - so opt out where the setting exists.
if (Test-Path Variable:PSNativeCommandUseErrorActionPreference) {
    $PSNativeCommandUseErrorActionPreference = $false
}

$Packages = @(
    @{ Id = 'OBSProject.OBSStudio';        Name = 'OBS Studio';        Tier = 'core';
       Why = 'The broadcast software itself. Free, and what most of Twitch runs on.' }
    @{ Id = 'ChatterinoTeam.Chatterino';   Name = 'Chatterino';        Tier = 'core';
       Why = 'A real chat client. Reading chat in a browser tab will not survive a busy stream.' }
    @{ Id = 'Discord.Discord';             Name = 'Discord';           Tier = 'core';
       Why = 'Where your community lives between streams, and where you talk to other streamers.' }

    @{ Id = 'VB-Audio.Voicemeeter.Banana'; Name = 'Voicemeeter Banana'; Tier = 'recommended';
       Why = 'Splits game / voice chat / music onto separate faders so you can duck one without the others.' }
    @{ Id = 'mifi.losslesscut';            Name = 'LosslessCut';        Tier = 'recommended';
       Why = 'Trims clips out of your VODs in seconds without re-encoding. This is how you get shorts.' }
    @{ Id = 'Elgato.StreamDeck';           Name = 'Elgato Stream Deck'; Tier = 'recommended';
       Why = 'Only needed if you own the hardware, but harmless to have ready.' }
    @{ Id = 'Audacity.Audacity';           Name = 'Audacity';           Tier = 'recommended';
       Why = 'Free audio editor. Use it once to check what your mic actually sounds like.' }

    @{ Id = 'BlackmagicDesign.DaVinciResolve'; Name = 'DaVinci Resolve'; Tier = 'all';
       Why = 'Full video editor for highlight reels. Large download - skip it until you need it.' }
    @{ Id = 'OBSProject.OBSStudio.Pre-release'; Name = 'OBS Studio (beta)'; Tier = 'all';
       Why = 'Optional beta channel. Only if you like living dangerously.' }
)

$TierRank = @{ 'core' = 0; 'recommended' = 1; 'all' = 2 }
$Wanted = $Packages | Where-Object { $TierRank[$_.Tier] -le $TierRank[$Tier] }

function Write-Head($text) {
    Write-Host ''
    Write-Host "  $text" -ForegroundColor Cyan
    Write-Host "  $('-' * 60)" -ForegroundColor DarkGray
}

Write-Head 'Game streaming setup for Windows'

if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
    Write-Host '  winget is not available on this machine.' -ForegroundColor Red
    Write-Host '  Install "App Installer" from the Microsoft Store, reopen PowerShell, run this again.'
    exit 1
}

Write-Host "  Tier: $Tier   Packages: $($Wanted.Count)"
if ($DryRun) { Write-Host '  DRY RUN - nothing will be installed.' -ForegroundColor Yellow }

$installed = @()
$skipped   = @()
$missing   = @()
$failed    = @()

foreach ($pkg in $Wanted) {
    Write-Host ''
    Write-Host "  $($pkg.Name)" -ForegroundColor White
    Write-Host "    $($pkg.Why)" -ForegroundColor DarkGray

    # Already here? winget list exits non-zero when it finds nothing.
    $null = winget list --id $pkg.Id --exact 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Host '    already installed - skipping' -ForegroundColor DarkGreen
        $skipped += $pkg.Name
        continue
    }

    # Does the catalogue actually have this id? Ids do get renamed upstream.
    $null = winget show --id $pkg.Id --exact 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "    not found in the winget catalogue (id: $($pkg.Id))" -ForegroundColor Yellow
        $missing += $pkg.Name
        continue
    }

    if ($DryRun) {
        Write-Host '    would install' -ForegroundColor Yellow
        continue
    }

    Write-Host '    installing...' -ForegroundColor Green
    winget install --id $pkg.Id --exact --silent `
        --accept-package-agreements --accept-source-agreements

    if ($LASTEXITCODE -eq 0) {
        $installed += $pkg.Name
    } else {
        Write-Host "    install returned exit code $LASTEXITCODE" -ForegroundColor Yellow
        $failed += $pkg.Name
    }
}

# Somewhere predictable for local recordings. Always record locally, even when
# the platform stores VODs for you - that copy is yours and it is higher quality.
$recordings = Join-Path $env:USERPROFILE 'Videos\Stream Recordings'
if (-not (Test-Path $recordings)) {
    if ($DryRun) {
        Write-Host ''
        Write-Host "  Would create $recordings" -ForegroundColor Yellow
    } else {
        New-Item -ItemType Directory -Path $recordings -Force | Out-Null
        Write-Host ''
        Write-Host "  Created $recordings"
    }
}

Write-Head 'Summary'
if ($installed) { Write-Host "  Installed:      $($installed -join ', ')" -ForegroundColor Green }
if ($skipped)   { Write-Host "  Already there:  $($skipped -join ', ')" -ForegroundColor DarkGreen }
if ($missing)   { Write-Host "  Not in catalog: $($missing -join ', ')" -ForegroundColor Yellow }
if ($failed)    { Write-Host "  Failed:         $($failed -join ', ')" -ForegroundColor Red }

if ($missing -or $failed) {
    Write-Host ''
    Write-Host '  For anything above, search for it by hand:  winget search "<name>"'
    Write-Host '  or download it from the vendor. Nothing here blocks you going live.'
}

Write-Head 'Next'
Write-Host '  1. Launch OBS once so it creates its config folder, then close it.'
Write-Host '  2. Generate your OBS profile and scenes:'
Write-Host '       python .\make_obs_kit.py --upload-mbps <your upload> --install' -ForegroundColor White
Write-Host '  3. Work through ..\docs\06-go-live-checklist.md before your first stream.'
Write-Host ''
