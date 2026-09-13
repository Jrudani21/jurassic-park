# Registers the scheduled tasks that make the Colibri batch tier self-managing.
#
# Two tasks, because they solve two different problems:
#
#   ColibriAttachDisk  -- at logon, attaches E:\wsl-models.vhdx to WSL. A
#                         `wsl --mount` attachment does not survive the WSL VM
#                         stopping (which WSL does on its own idle timeout), and
#                         re-attaching needs administrator rights. Running this
#                         as a task with highest privileges avoids a UAC prompt
#                         every time.
#
#   ColibriIdleRunner  -- at logon, starts the idle watcher, which runs the
#                         inference server only while the machine is unattended
#                         and drains it gracefully when the user returns.
#
# Windows' own "On Idle" trigger is deliberately not used: it requires sustained
# low CPU, and the agent fleet keeps this machine busy, so it would rarely fire.
# The watcher polls input idle time instead.
#
# RUN AS ADMINISTRATOR.

$ErrorActionPreference = 'Stop'

$ScriptDir  = 'E:\Local\projects\jurassic-park\scripts'
$RunnerPath = Join-Path $ScriptDir 'colibri-idle-runner.ps1'
$ModelVhd   = 'E:\wsl-models.vhdx'
$User       = "$env:USERDOMAIN\$env:USERNAME"

if (-not (Test-Path $RunnerPath)) {
    Write-Host "Missing $RunnerPath" -ForegroundColor Red
    exit 1
}

# --- Task 1: attach the model disk at logon -------------------------------

$attachCmd = "wsl --mount --vhd `"$ModelVhd`" --bare"

$a1 = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -WindowStyle Hidden -Command `"$attachCmd`""
$t1 = New-ScheduledTaskTrigger -AtLogOn -User $User
# Highest privileges: the attach needs admin, and this is what keeps it from
# prompting for UAC on every logon.
$p1 = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
$s1 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName 'ColibriAttachDisk' -Action $a1 -Trigger $t1 `
    -Principal $p1 -Settings $s1 -Force `
    -Description 'Attaches the Colibri model VHDX to WSL at logon (attachments do not survive a WSL VM restart).' | Out-Null

Write-Host "Registered ColibriAttachDisk" -ForegroundColor Green

# --- Task 2: the idle watcher ---------------------------------------------

$a2 = New-ScheduledTaskAction -Execute 'powershell.exe' `
        -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$RunnerPath`""
$t2 = New-ScheduledTaskTrigger -AtLogOn -User $User
$p2 = New-ScheduledTaskPrincipal -UserId $User -LogonType Interactive -RunLevel Highest
# No execution time limit: this is a long-lived watcher, not a job that should
# be reaped after a few hours.
$s2 = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
        -DontStopIfGoingOnBatteries -StartWhenAvailable `
        -ExecutionTimeLimit ([TimeSpan]::Zero) `
        -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 5)

Register-ScheduledTask -TaskName 'ColibriIdleRunner' -Action $a2 -Trigger $t2 `
    -Principal $p2 -Settings $s2 -Force `
    -Description 'Runs the Colibri batch inference server only while the machine is unattended (20 min input idle), draining gracefully on return.' | Out-Null

Write-Host "Registered ColibriIdleRunner" -ForegroundColor Green

Write-Host ""
Get-ScheduledTask -TaskName 'Colibri*' |
    Select-Object TaskName, State |
    Format-Table -AutoSize

Write-Host "Start now without waiting for a logon:" -ForegroundColor Cyan
Write-Host "  Start-ScheduledTask -TaskName ColibriIdleRunner"
Write-Host ""
Write-Host "Remove both:" -ForegroundColor Cyan
Write-Host "  Unregister-ScheduledTask -TaskName ColibriAttachDisk,ColibriIdleRunner -Confirm:`$false"
