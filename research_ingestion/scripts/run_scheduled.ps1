param(
    [Parameter(Mandatory = $true)]
    [string]$PythonExe,
    [Parameter(Mandatory = $true)]
    [string]$OmniRouteExe,
    [int]$OmniRoutePort = 20128,
    [int]$StartupTimeoutSeconds = 90
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

function Test-LocalPort {
    param([int]$Port)
    $client = [System.Net.Sockets.TcpClient]::new()
    try {
        $pending = $client.BeginConnect("127.0.0.1", $Port, $null, $null)
        if (-not $pending.AsyncWaitHandle.WaitOne(1000)) {
            return $false
        }
        $client.EndConnect($pending)
        return $true
    }
    catch {
        return $false
    }
    finally {
        $client.Dispose()
    }
}

if (-not (Test-LocalPort -Port $OmniRoutePort)) {
    Write-Output "OmniRoute is not listening on port $OmniRoutePort; starting its background daemon."
    $arguments = @("serve", "--daemon", "--no-open", "--no-tray", "--port", "$OmniRoutePort")
    # OmniRoute's Windows launcher stays attached to the server even with
    # --daemon, so do not wait for the launcher process to exit. Readiness is
    # determined by the bounded localhost port check below.
    Start-Process -FilePath $OmniRouteExe -ArgumentList $arguments `
        -WorkingDirectory $ProjectRoot -WindowStyle Hidden | Out-Null

    $deadline = (Get-Date).AddSeconds($StartupTimeoutSeconds)
    while ((Get-Date) -lt $deadline -and -not (Test-LocalPort -Port $OmniRoutePort)) {
        Start-Sleep -Seconds 1
    }
}

if (Test-LocalPort -Port $OmniRoutePort) {
    Write-Output "OmniRoute preflight passed on 127.0.0.1:$OmniRoutePort."
}
else {
    Write-Warning "OmniRoute did not become ready; the pipeline will use its documented deterministic fallback."
}

Push-Location $ProjectRoot
try {
    & $PythonExe -m research_ingestion.cli run --catch-up
    $pipelineExitCode = $LASTEXITCODE
    if ($pipelineExitCode -ne 0) {
        exit $pipelineExitCode
    }

    Write-Output "Importing manually downloaded PDFs from the configured inbox."
    & $PythonExe -m research_ingestion.cli import-pdfs
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "PDF inbox import failed with exit code $LASTEXITCODE."
    }

    # Repository indexes can lag a new DOI. Retry a bounded set of ages using
    # only OpenAlex/Unpaywall; do not repeatedly revisit blocked publisher or
    # SSRN landing pages.
    foreach ($ageDays in @(1, 3, 7, 14)) {
        $retryDate = (Get-Date).Date.AddDays(-$ageDays).ToString("yyyy-MM-dd")
        $manifest = Join-Path $ProjectRoot "data\accepted\$retryDate.json"
        if (-not (Test-Path $manifest)) {
            continue
        }
        Write-Output "Retrying public PDF resolution for $retryDate (age $ageDays days)."
        & $PythonExe -m research_ingestion.cli resolve-pdfs --from $retryDate --to $retryDate --resolver-only
        if ($LASTEXITCODE -ne 0) {
            Write-Warning "Public PDF retry failed for $retryDate with exit code $LASTEXITCODE."
        }
    }
    exit 0
}
finally {
    Pop-Location
}
