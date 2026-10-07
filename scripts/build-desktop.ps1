param([string]$PythonPath='')
$ErrorActionPreference='Stop'
$root=Split-Path -Parent $PSScriptRoot
if(-not $PythonPath){$PythonPath=Join-Path $root '.venv\Scripts\python.exe'}
if(-not(Test-Path -LiteralPath $PythonPath)){throw '请先准备项目虚拟环境，或用-PythonPath指定构建用Python。'}
& $PythonPath -X utf8 (Join-Path $PSScriptRoot 'build_desktop.py')
if($LASTEXITCODE -ne 0){throw '程序构建失败。'}
