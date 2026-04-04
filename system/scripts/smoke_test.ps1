param(
    [string]$HostName = "127.0.0.1",
    [int]$Port = 8000,
    [int]$StartupTimeoutSec = 30
)

$ErrorActionPreference = "Stop"

function Write-Pass([string]$msg) { Write-Host "[PASS] $msg" -ForegroundColor Green }
function Write-Fail([string]$msg) { Write-Host "[FAIL] $msg" -ForegroundColor Red }
function Write-Info([string]$msg) { Write-Host "[INFO] $msg" -ForegroundColor Cyan }

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "..")
$baseUrl = "http://$HostName`:$Port"

Write-Info "Project root: $projectRoot"
Write-Info "Base URL: $baseUrl"

$speechProcess = $null
$allPassed = $true

try {
    Write-Info "Starting speech server..."
    $speechProcess = Start-Process `
        -FilePath "python" `
        -ArgumentList "scripts/run_speech.py" `
        -WorkingDirectory $projectRoot `
        -PassThru `
        -WindowStyle Hidden

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSec)
    $isReady = $false
    while ((Get-Date) -lt $deadline) {
        try {
            $health = Invoke-RestMethod -Method Get -Uri "$baseUrl/docs" -TimeoutSec 2
            $isReady = $true
            break
        } catch {
            Start-Sleep -Milliseconds 500
        }
    }

    if (-not $isReady) {
        Write-Fail "Speech server did not start within $StartupTimeoutSec seconds."
        Write-Host "Hint: run 'python scripts/run_speech.py' manually to inspect startup errors."
        exit 1
    }
    Write-Pass "Speech server is reachable."

    Write-Info "Testing /speak..."
    $speakPayload = @{
        text = "Smoke test message"
        priority = 5
    } | ConvertTo-Json

    $speakResp = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/speak" `
        -ContentType "application/json" `
        -Body $speakPayload `
        -TimeoutSec 10

    if ($speakResp.accepted -eq $true -and $speakResp.queued -eq $true) {
        Write-Pass "/speak accepted and queued."
    } else {
        $allPassed = $false
        Write-Fail "/speak returned unexpected response: $($speakResp | ConvertTo-Json -Compress)"
    }

    Write-Info "Testing /event..."
    $eventPayload = @{
        source = "smoke_test"
        type = "pipeline_check"
        message = "Event route smoke test"
        priority = 5
        dedupe_key = "smoke_test_pipeline_check"
        cooldown_s = 2
    } | ConvertTo-Json

    $eventResp = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/event" `
        -ContentType "application/json" `
        -Body $eventPayload `
        -TimeoutSec 10

    if ($eventResp.accepted -eq $true -and $eventResp.queued -eq $true) {
        Write-Pass "/event accepted and queued."
    } else {
        $allPassed = $false
        Write-Fail "/event returned unexpected response: $($eventResp | ConvertTo-Json -Compress)"
    }

    # Cooldown behavior check (second immediate event may be blocked)
    Write-Info "Testing cooldown behavior..."
    $eventResp2 = Invoke-RestMethod `
        -Method Post `
        -Uri "$baseUrl/event" `
        -ContentType "application/json" `
        -Body $eventPayload `
        -TimeoutSec 10

    if ($eventResp2.accepted -eq $false -and $eventResp2.reason -eq "cooldown") {
        Write-Pass "Cooldown logic is active."
    } else {
        Write-Info "Cooldown check not strict (acceptable), response: $($eventResp2 | ConvertTo-Json -Compress)"
    }

    if ($allPassed) {
        Write-Host ""
        Write-Pass "Smoke test completed successfully."
        Write-Host "If no sound played, check PIPER model paths/audio device settings."
        exit 0
    } else {
        Write-Host ""
        Write-Fail "Smoke test completed with failures."
        exit 2
    }
}
catch {
    Write-Fail "Smoke test crashed: $($_.Exception.Message)"
    exit 3
}
finally {
    if ($speechProcess -and -not $speechProcess.HasExited) {
        Write-Info "Stopping speech server..."
        Stop-Process -Id $speechProcess.Id -Force
    }
}
