# Booking eSIM - SERVER rejimi (eski kompyuter uchun, 24/7)
# Windows'ga kirganda o'zi ishga tushadi (server_setup.bat sozlaydi).
# - internet kelishini kutadi
# - Cloudflare tunnel + botni ishga tushiradi
# - bot yiqilsa qayta yoqadi; tunnel o'lsa yoki Mini App ochilmay qolsa hammasini qayta ishga tushiradi
# - hamma narsani server.log fayliga yozadi
$ErrorActionPreference = "Continue"
Set-Location -Path $PSScriptRoot
$Host.UI.RawUI.WindowTitle = "Booking eSIM SERVER"
$LogFile = Join-Path $PSScriptRoot "server.log"

function Log($msg) {
    $line = "{0:yyyy-MM-dd HH:mm:ss}  {1}" -f (Get-Date), $msg
    Write-Host $line
    try {
        if ((Test-Path $LogFile) -and ((Get-Item $LogFile).Length -gt 5MB)) {
            Move-Item $LogFile "$LogFile.old" -Force
        }
        Add-Content -Path $LogFile -Value $line
    } catch {}
}

function Stop-Pid($file) {
    $f = Join-Path $PSScriptRoot $file
    if (Test-Path $f) {
        $old = Get-Content $f -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($old -and ([int]$old -ne $PID)) { Stop-Process -Id ([int]$old) -Force -ErrorAction SilentlyContinue }
        Remove-Item $f -Force -ErrorAction SilentlyContinue
    }
}

function Test-Internet {
    try {
        $c = New-Object System.Net.Sockets.TcpClient
        $ok = $c.ConnectAsync("api.telegram.org", 443).Wait(8000)
        $c.Close()
        return $ok
    } catch { return $false }
}

function Wait-Internet {
    $warned = $false
    while (-not (Test-Internet)) {
        if (-not $warned) { Log "Internet yo'q - kutilmoqda..."; $warned = $true }
        Start-Sleep -Seconds 15
    }
    if ($warned) { Log "Internet keldi." }
}

function Test-MiniApp($url) {
    try {
        $r = Invoke-WebRequest -Uri "$url/" -UseBasicParsing -TimeoutSec 20
        return ($r.StatusCode -eq 200)
    } catch { return $false }
}

# --- eski nusxalarni yopish ---
Stop-Pid "server.pid"
Stop-Pid "bot.pid"
Stop-Pid "cloudflared.pid"
Set-Content -Path (Join-Path $PSScriptRoot "server.pid") -Value $PID

$python = (Get-Command python -ErrorAction SilentlyContinue).Source
$cf = (Get-Command cloudflared -ErrorAction SilentlyContinue).Source
if (-not $cf -and (Test-Path "$env:ProgramFiles (x86)\cloudflared\cloudflared.exe")) { $cf = "$env:ProgramFiles (x86)\cloudflared\cloudflared.exe" }
if (-not $python -or -not $cf) {
    Log "XATO: python yoki cloudflared topilmadi. SERVER.md dagi 2-qadamni bajaring."
    Start-Sleep -Seconds 600
    exit 1
}

Log "=== Server ishga tushdi ==="
Wait-Internet
Log "Kutubxonalar tekshirilmoqda..."
& $python -m pip install -q -r requirements.txt --disable-pip-version-check 2>&1 | Out-Null
& $python -m playwright install chromium 2>&1 | Out-Null

while ($true) {
    Wait-Internet

    # --- 1) Cloudflare tunnel ---
    $cfLog = Join-Path $PSScriptRoot "cloudflared.log"
    Remove-Item $cfLog, "$cfLog.out" -Force -ErrorAction SilentlyContinue
    $tunnel = Start-Process -FilePath $cf -ArgumentList "tunnel --url http://localhost:8080" `
        -RedirectStandardError $cfLog -RedirectStandardOutput "$cfLog.out" -WindowStyle Hidden -PassThru
    Set-Content -Path (Join-Path $PSScriptRoot "cloudflared.pid") -Value $tunnel.Id
    $url = $null
    for ($i = 0; $i -lt 60 -and -not $tunnel.HasExited; $i++) {
        Start-Sleep -Seconds 1
        $m = Select-String -Path $cfLog -Pattern "https://[a-z0-9-]+\.trycloudflare\.com" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($m) { $url = $m.Matches[0].Value; break }
    }
    if (-not $url) {
        Log "Tunnel manzili olinmadi - 30 soniyadan keyin qayta urinish."
        Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 30
        continue
    }
    Log "Tunnel: $url"
    & $python update_env.py $url | Out-Null

    # --- 2) Bot ---
    $bot = Start-Process -FilePath $python -ArgumentList "main.py" -NoNewWindow -PassThru
    $null = $bot.Handle
    Log "Bot ishga tushdi (PID $($bot.Id))."

    # --- 3) Kuzatuv ---
    $fails = 0
    $tick = 0
    while ($true) {
        Start-Sleep -Seconds 20
        $tick++
        if ($tunnel.HasExited) { Log "Tunnel to'xtab qoldi - hammasi qayta ishga tushiriladi."; break }
        if ($bot.HasExited) {
            Log "Bot to'xtadi (kod $($bot.ExitCode)) - 10 soniyadan keyin qayta yoqiladi."
            Start-Sleep -Seconds 10
            Wait-Internet
            $bot = Start-Process -FilePath $python -ArgumentList "main.py" -NoNewWindow -PassThru
            $null = $bot.Handle
            Log "Bot qayta ishga tushdi (PID $($bot.Id))."
            continue
        }
        if ($tick % 15 -eq 0) {   # ~5 daqiqada bir Mini App ochilishini tekshirish
            if (Test-MiniApp $url) { $fails = 0 }
            else {
                $fails++
                Log "Mini App ochilmadi ($fails/3)."
                if ($fails -ge 3) { Log "Tunnel ishlamayapti - yangi tunnel ochiladi."; break }
            }
        }
    }

    # --- hammasini yopib, qaytadan ---
    Stop-Process -Id $bot.Id -Force -ErrorAction SilentlyContinue
    Stop-Process -Id $tunnel.Id -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
}
