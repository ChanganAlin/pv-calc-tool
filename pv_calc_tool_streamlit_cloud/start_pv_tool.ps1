$ErrorActionPreference = "Stop"

$Project = "C:\Users\jyb99\Documents\Codex\2026-07-09\files-mentioned-by-the-user-python\pv_calc_tool"
$Python = "C:\Users\jyb99\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$Url = "http://127.0.0.1:8501"

Set-Location $Project
$env:STREAMLIT_BROWSER_GATHER_USAGE_STATS = "false"

$running = Get-NetTCPConnection -LocalPort 8501 -State Listen -ErrorAction SilentlyContinue
if ($running) {
    foreach ($conn in $running) {
        try {
            Stop-Process -Id $conn.OwningProcess -Force -ErrorAction SilentlyContinue
        } catch {
        }
    }
    Start-Sleep -Seconds 2
}

Start-Process -FilePath $Python `
    -ArgumentList @("-m", "streamlit", "run", "app.py", "--server.port", "8501", "--server.headless", "true", "--browser.gatherUsageStats", "false") `
    -WorkingDirectory $Project `
    -WindowStyle Minimized

$ready = $false
for ($i = 0; $i -lt 30; $i++) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 2
        if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
            $ready = $true
            break
        }
    } catch {
        Start-Sleep -Seconds 1
    }
}

if ($ready) {
    Start-Process $Url
} else {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show("PV calculator startup timed out. Please open $Url later, or ask Codex to debug the launcher.", "Startup failed")
}
