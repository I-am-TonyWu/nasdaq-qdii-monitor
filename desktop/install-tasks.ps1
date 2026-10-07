[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [Parameter(Mandatory=$true)][string]$DataHome,
    [Parameter(Mandatory=$true)][string]$LauncherPath,
    [ValidatePattern('^NasdaqQDII-(Local-|PackageSmoke-[A-Za-z0-9_-]+-)$')]
    [string]$TaskPrefix='NasdaqQDII-Local-',
    [ValidateSet('Serve','Collect','Retry','Freeze','ReportPreview','Funds','Backup','Weekly')]
    [string[]]$OnlyTask=@()
)
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object System.Text.UTF8Encoding($false)
$runtimeRoot=[IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$dataRoot=[IO.Path]::GetFullPath($DataHome)
$launcher=[IO.Path]::GetFullPath($LauncherPath)
$pythonPath=Join-Path $runtimeRoot 'python\pythonw.exe'
if(-not(Test-Path -LiteralPath $pythonPath)){throw '程序运行环境不存在。'}
if(-not(Test-Path -LiteralPath $launcher)){throw '程序启动文件不存在。'}
if((Get-TimeZone).BaseUtcOffset.TotalHours -ne 8){throw '自动任务按北京时间执行；设备时区需要设为UTC+8。'}
$identity=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal=New-ScheduledTaskPrincipal -UserId $identity -LogonType Interactive -RunLevel Limited
$short=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$long=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
$retryTimes=@();for($at=[datetime]::Today.AddHours(7).AddMinutes(15);$at -le [datetime]::Today.AddHours(17).AddMinutes(15);$at=$at.AddMinutes(30)){$retryTimes+=$at.ToString('HH:mm')}
$jobs=@(
    @{Name='Serve';Command='serve';Times=@();Logon=$true},
    @{Name='Collect';Command='collect';Times=@('06:30','06:45','12:30');Logon=$true},
    @{Name='Retry';Command='retry';Times=$retryTimes},
    @{Name='Freeze';Command='freeze';Times=@('06:55')},
    @{Name='ReportPreview';Command='report';Times=@('07:00')},
    @{Name='Funds';Command='funds';Times=@('09:10','14:30','20:30')},
    @{Name='Backup';Command='backup';Times=@('07:10')},
    @{Name='Weekly';Command='weekly';Times=@('12:30');Weekly=$true}
)
if($OnlyTask.Count){$jobs=@($jobs | Where-Object {$_.Name -in $OnlyTask})}
$stateRoot=Split-Path -Parent (Split-Path -Parent $launcher)
$ownedReleases=[IO.Path]::GetFullPath((Join-Path $stateRoot 'releases'))+[IO.Path]::DirectorySeparatorChar
# Preflight every selected task before changing any task.
foreach($job in $jobs){
    $name=$TaskPrefix+$job.Name
    $existing=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if($existing){
        $work=[IO.Path]::GetFullPath($existing.Actions[0].WorkingDirectory)
        $ownedLauncher=($job.Name -eq 'Serve') -and ($existing.Actions[0].Execute -eq $launcher) -and ($work -eq (Split-Path -Parent $launcher))
        $owned=$ownedLauncher -or ($work -eq $dataRoot) -or $work.StartsWith($ownedReleases,[StringComparison]::OrdinalIgnoreCase) -or ($work -eq $runtimeRoot)
        if(-not $owned){throw "同名任务属于其他目录，未修改：$name"}
        if(-not $ownedLauncher -and $work -ne $dataRoot -and $existing.Actions[0].Arguments -notlike "*--home `"$dataRoot`"*"){throw "同名程序任务使用另一数据目录，未修改：$name"}
    }
}
$backupRoot=Join-Path $dataRoot ('logs\task-backups\'+(Get-Date -Format 'yyyyMMdd-HHmmss'))
foreach($job in $jobs){
    $name=$TaskPrefix+$job.Name
    $existing=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if($job.Name -eq 'Serve' -and $existing -and $existing.State -eq 'Running'){
        Write-Output '原服务正在运行，保留当前启动任务；其他选定任务继续登记。';continue
    }
    $action=if($job.Name -eq 'Serve'){
        New-ScheduledTaskAction -Execute $launcher -Argument '--autostart' -WorkingDirectory (Split-Path -Parent $launcher)
    }else{
        New-ScheduledTaskAction -Execute $pythonPath -Argument "-B -X utf8 -m app.desktop_worker --home `"$dataRoot`" $($job.Command)" -WorkingDirectory $runtimeRoot
    }
    $triggers=@();foreach($time in $job.Times){$triggers+=if($job.Weekly){New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At $time}else{New-ScheduledTaskTrigger -Daily -At $time}}
    if($job.Logon){$triggers+=New-ScheduledTaskTrigger -AtLogOn -User $identity}
    if($PSCmdlet.ShouldProcess($name,'登记程序版自动任务')){
        if($existing){
            New-Item -ItemType Directory -Path $backupRoot -Force | Out-Null
            [IO.File]::WriteAllText((Join-Path $backupRoot ($name+'.xml')),(Export-ScheduledTask -TaskName $name),(New-Object Text.UTF8Encoding($true)))
        }
        Register-ScheduledTask -TaskName $name -Action $action -Trigger $triggers -Settings $(if($job.Name -eq 'Serve'){$long}else{$short}) -Principal $principal -Description '纳指观察程序版；北京时间；当前用户登录会话；邮件仅预览。' -Force | Select-Object TaskName,State
    }
}
if($WhatIfPreference){Write-Output '仅预览，未修改任务。'}else{Write-Output '选定任务已配置。原任务XML备份在数据目录logs/task-backups中。'}
