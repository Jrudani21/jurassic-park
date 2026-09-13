# Runs the Colibri batch engine overnight, and yields the GPU on demand.
#
# Why not presence detection, which this script originally used:
#
# This machine has no usable "user is here" signal. It is headless and normally
# locked (LogonUI present), it is driven remotely through agents rather than a
# keyboard, and the agent fleet keeps CPU busy around the clock. Measured
# directly: `GetLastInputInfo` and `query user` both reported ~36 minutes idle
# while the user was actively working, because their keystrokes land on a client
# device and only API calls reach this host. Input idle therefore reads "idle"
# permanently, and an idle-gated server would simply never stop.
#
# Windows' own "On Idle" task trigger fails for the related reason that it wants
# sustained sub-10% CPU, which the fleet prevents.
#
# What is left is a fixed window, which needs no detection to be correct, plus a
# GPU check so the engine gets out of the way of anything that actually wants the
# card (Ollama's local tier being the case that matters here).

[CmdletBinding()]
param(
    [int]$StartHour      = 1,    # window opens (local time, 24h)
    [int]$EndHour        = 8,    # window closes
    [int]$PollSeconds    = 60,
    [int]$DrainSeconds   = 300,  # grace for an in-flight generation
    [int]$YieldFreeMB    = 1500, # stop if free VRAM falls below this
    [int]$Port           = 8080,
    [string]$ModelDir    = '/models/mimo-v2.5',
    [string]$ModelVhd    = 'E:\wsl-models.vhdx',
    [string]$LogPath     = 'E:\Local\projects\jurassic-park\logs\colibri-idle.log'
)

$ErrorActionPreference = 'Continue'

New-Item -ItemType Directory -Force -Path (Split-Path $LogPath) | Out-Null

function Write-Log {
    param([string]$Message)
    $line = "{0}  {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
    Add-Content -Path $LogPath -Value $line -Encoding utf8
    Write-Host $line
}

function Test-InWindow {
    $h = (Get-Date).Hour
    # A window that wraps midnight (e.g. 22 -> 6) needs the inverted test.
    if ($StartHour -le $EndHour) { return ($h -ge $StartHour -and $h -lt $EndHour) }
    return ($h -ge $StartHour -or $h -lt $EndHour)
}

function Get-GpuFreeMB {
    # Reports free VRAM as nvidia-smi sees it. While our own engine is resident
    # its ~4.7 GB counts as used, so this is only meaningful as a "someone else
    # arrived" signal when compared against the engine's own footprint.
    try {
        $out = & nvidia-smi --query-gpu=memory.free --format=csv,noheader,nounits 2>$null
        if ($LASTEXITCODE -eq 0 -and $out) { return [int]($out -split "`n")[0].Trim() }
    } catch { }
    return -1   # unknown: treated as "do not block"
}

function Test-GpuContended {
    # Asks Ollama directly whether it currently has a model resident.
    #
    # Two cheaper-looking signals were tried and do not work on this box:
    #
    #   Per-process VRAM -- `nvidia-smi --query-compute-apps=used_memory` reports
    #   [N/A] for every process under the WDDM driver model, and the engine runs
    #   inside WSL so it never appears in that list anyway.
    #
    #   Free-VRAM headroom -- with the engine resident (~4.7 GB) plus the desktop
    #   (~2.4 GB), free VRAM on this 8 GB card measures 449 MB. There is no
    #   headroom left in which to observe someone else arriving, so a
    #   drop-below-baseline test can never fire.
    #
    # Ollama's own /api/ps is unambiguous and cheap: a non-empty models array
    # means it holds the card. A non-responding Ollama is treated as no
    # contention rather than as a reason to stay off.
    #
    # Returns an object, not an array. `return ,@($bool, $text)` was tried and is
    # actively dangerous here: the extra wrapping made $c[0] the inner array
    # rather than the boolean, and a two-element array is always truthy, so the
    # not-contended case would have read as contended and the engine would never
    # have started at all.
    try {
        $r = Invoke-RestMethod -Uri 'http://localhost:11434/api/ps' `
                -TimeoutSec 4 -ErrorAction Stop
        if ($r.models -and $r.models.Count -gt 0) {
            return [pscustomobject]@{
                Contended = $true
                Models    = ($r.models | ForEach-Object { $_.name }) -join ','
            }
        }
    } catch { }
    return [pscustomobject]@{ Contended = $false; Models = '' }
}

function Test-DiskAttached {
    $out = wsl -d Ubuntu -- bash -c "mountpoint -q /models && echo yes || echo no" 2>$null
    return ($out -match 'yes')
}

function Connect-ModelDisk {
    # Checked every cycle rather than assumed: a `wsl --mount` attachment does
    # not survive the WSL VM stopping, and WSL stops it on its own idle timeout.
    # fstab remounts an attached disk but cannot attach one.
    if (Test-DiskAttached) { return $true }

    Write-Log "model disk not mounted; attaching $ModelVhd"
    wsl --mount --vhd $ModelVhd --bare 2>&1 | Out-Null
    Start-Sleep -Seconds 3
    wsl -d Ubuntu -- bash -c "mountpoint -q /models || sudo mount LABEL=wslmodels /models" 2>&1 | Out-Null

    if (Test-DiskAttached) { Write-Log "model disk mounted"; return $true }
    Write-Log "ERROR: could not mount model disk (--mount needs elevation)"
    return $false
}

function Test-ServerUp {
    try {
        $null = Invoke-WebRequest -Uri "http://localhost:$Port/v1/models" `
                    -TimeoutSec 5 -UseBasicParsing -ErrorAction Stop
        return $true
    } catch { return $false }
}

function Start-Engine {
    if (-not (Connect-ModelDisk)) { return $false }

    Write-Log "starting engine on port $Port"
    # setsid --fork, not a bare `&`. WSL tears down the session when the last
    # wsl.exe client exits, which reaps a merely backgrounded child: verified
    # once as exit 0 with no process and no log file ever written. </dev/null
    # keeps it off a stdin that is about to disappear.
    $cmd = "cd ~/peng-mimo/c && COLI_CUDA=1 CUDA_DENSE=1 CUDA_ATTN=1 PILOT=1 " +
           "setsid --fork nohup python3 openai_server.py --model $ModelDir " +
           "--port $Port > ~/colibri-server.log 2>&1 < /dev/null"
    wsl -d Ubuntu -- bash -c $cmd 2>&1 | Out-Null

    for ($i = 0; $i -lt 40; $i++) {
        Start-Sleep -Seconds 10
        if (Test-ServerUp) { Write-Log "engine ready after $(($i+1)*10)s"; return $true }
    }
    Write-Log "ERROR: engine not ready within 400s"
    return $false
}

function Stop-Engine {
    param([switch]$Drain, [string]$Reason = 'stopping')

    if ($Drain) {
        # SIGTERM lets an in-flight generation finish. At ~0.16 tok/s a
        # discarded request can be several minutes of compute.
        Write-Log "$Reason -- draining (up to ${DrainSeconds}s)"
        wsl -d Ubuntu -- bash -c "pkill -TERM -f '[o]penai_server'" 2>&1 | Out-Null

        $waited = 0
        while ($waited -lt $DrainSeconds) {
            Start-Sleep -Seconds 5
            $waited += 5
            # Bracketed pattern: a bare `pgrep -f openai_server.py` also matches
            # the bash -c command line carrying that text, so it would report the
            # process alive forever and the drain would never complete.
            $alive = wsl -d Ubuntu -- bash -c "pgrep -f '[o]penai_server' >/dev/null && echo yes || echo no" 2>$null
            if ($alive -match 'no') { Write-Log "drained cleanly after ${waited}s"; return }
        }
        Write-Log "drain window elapsed; forcing stop"
    }

    wsl -d Ubuntu -- bash -c "pkill -KILL -f '[o]penai_server'" 2>&1 | Out-Null
    Write-Log "engine stopped"
}

# ---------------------------------------------------------------------------

$running = $false

Write-Log "watcher started (window ${StartHour}:00-${EndHour}:00, yields to Ollama)"

try {
    while ($true) {
        $inWindow = Test-InWindow

        if (-not $running) {
            if ($inWindow) {
                $c = Test-GpuContended
                $free = Get-GpuFreeMB
                if ($c.Contended) {
                    Write-Log "in window but Ollama holds the GPU ($($c.Models)); holding off"
                } elseif ($free -ge 0 -and $free -lt $YieldFreeMB) {
                    Write-Log "in window but only ${free}MB VRAM free; holding off"
                } else {
                    Write-Log "window open (${free}MB VRAM free) -- starting"
                    $running = Start-Engine
                    if ($running) {
                        Start-Sleep -Seconds 10
                        Write-Log "running; free VRAM $(Get-GpuFreeMB)MB"
                    } else {
                        Start-Sleep -Seconds 600
                    }
                }
            }
        }
        else {
            if (-not $inWindow) {
                Stop-Engine -Drain -Reason 'window closed'
                $running = $false
            }
            elseif (-not (Test-ServerUp)) {
                Write-Log "engine died unexpectedly; see ~/colibri-server.log"
                $running = $false
            }
            else {
                # Yield the moment Ollama loads a model. It is the fleet's
                # latency-sensitive local tier; this is the batch tier and can
                # always wait.
                $c = Test-GpuContended
                if ($c.Contended) {
                    Stop-Engine -Drain -Reason "Ollama took the GPU ($($c.Models))"
                    $running = $false
                    Start-Sleep -Seconds 900   # do not immediately retake the card
                }
            }
        }

        Start-Sleep -Seconds $PollSeconds
    }
}
finally {
    if ($running) { Stop-Engine }
    Write-Log "watcher exiting"
}
