$ErrorActionPreference='Stop'
$projectRoot=Split-Path -Parent $PSScriptRoot
foreach($name in @('Serve','Collect','Retry','Freeze','ReportPreview','Funds','Backup','Weekly')){
    $taskName='NasdaqQDII-Local-'+$name
    $task=Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
    if($task -and $task.Actions[0].WorkingDirectory -eq $projectRoot){
        Stop-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
        Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
    }
}
