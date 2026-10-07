[CmdletBinding(SupportsShouldProcess=$true)]
param(
    [switch]$WakeToRun,
    [ValidateSet('Serve','Collect','Retry','Freeze','ReportPreview','Funds','Backup','Weekly')]
    [string[]]$OnlyTask=@()
)
$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
$pythonPath=Join-Path $projectRoot '.venv\Scripts\python.exe'
if(-not(Test-Path -LiteralPath $pythonPath)){throw '请先安装项目依赖。'}
$pythonWindowless=Join-Path $projectRoot '.venv\Scripts\pythonw.exe'
if(Test-Path -LiteralPath $pythonWindowless){$pythonPath=$pythonWindowless}
if((Get-TimeZone).BaseUtcOffset.TotalHours -ne 8){throw '这些本机任务使用北京时间；设备时区必须为UTC+8。其他时区请使用带显式时区的任务XML。'}
$userIdentity=[System.Security.Principal.WindowsIdentity]::GetCurrent().Name
$principal=New-ScheduledTaskPrincipal -UserId $userIdentity -LogonType Interactive -RunLevel Limited
$shortSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -WakeToRun:$WakeToRun
$serverSettings=New-ScheduledTaskSettingsSet -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
$retryTimes=@()
for($retryAt=[datetime]::Today.AddHours(7).AddMinutes(15);$retryAt -le [datetime]::Today.AddHours(17).AddMinutes(15);$retryAt=$retryAt.AddMinutes(30)){
    $retryTimes+=$retryAt.ToString('HH:mm')
}
$jobs=@(
    @{Name='Serve';Command='serve';Times=@();Logon=$true},
    @{Name='Collect';Command='collect';Times=@('06:30','06:45','12:30');Logon=$true},
    @{Name='Retry';Command='retry';Times=$retryTimes;Logon=$false},
    @{Name='Freeze';Command='freeze';Times=@('06:55');Logon=$false},
    @{Name='ReportPreview';Command='report';Times=@('07:00');Logon=$false},
    @{Name='Funds';Command='funds';Times=@('09:10','14:30','20:30');Logon=$false},
    @{Name='Backup';Command='backup';Times=@('07:10');Logon=$false},
    @{Name='Weekly';Command='weekly';Times=@('12:30');Logon=$false;Weekly=$true}
)
if($OnlyTask.Count){$jobs=@($jobs | Where-Object {$_.Name -in $OnlyTask})}
foreach($job in $jobs){
    $taskName='NasdaqQDII-Local-'+$job.Name
    $existing=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if($existing -and $existing.Actions[0].WorkingDirectory -ne $projectRoot){throw "同名任务属于其他目录：$taskName。"}
    if($job.Name -eq 'Serve' -and $existing -and $existing.State -eq 'Running'){
        Write-Output '本机网页服务正在运行，保留当前 Serve 任务；其他选定任务继续登记。'
        continue
    }
    $action=New-ScheduledTaskAction -Execute $pythonPath -Argument "-X utf8 -m app.cli $($job.Command)" -WorkingDirectory $projectRoot
    $triggers=@()
    foreach($time in $job.Times){$triggers+=if($job.Weekly){New-ScheduledTaskTrigger -Weekly -DaysOfWeek Saturday -At $time}else{New-ScheduledTaskTrigger -Daily -At $time}}
    if($job.Logon){$triggers+=New-ScheduledTaskTrigger -AtLogOn -User $userIdentity}
    $settings=if($job.Name -eq 'Serve'){$serverSettings}else{$shortSettings}
    $description=if($job.Name -eq 'Retry'){'北京时间07:15至17:15每30分钟检查并补采未完成的数据；已完整数据跳过，不重复采集基金。'}else{'纳斯达克与QDII本机初版；07:00仅生成预览，未启用发信。'}
    if($PSCmdlet.ShouldProcess($taskName,'登记本机任务')){
        Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $triggers -Settings $settings -Principal $principal -Description $description -Force | Select-Object TaskName,State
    }
}
if($WhatIfPreference){Write-Output '仅预览任务登记，未修改任务计划程序。'}else{Write-Output '选定任务已处理。使用当前用户会话，可锁屏运行；未登录执行、硬件唤醒和重启恢复仍需验证。邮件未启用。'}
