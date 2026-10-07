"""Run the actual EXE against isolated data, ports and temporary scheduler tasks.

No network collection, browser windows, shortcuts, login registry changes or
production scheduled-task changes are made. A final read-only test attaches to
the original project server if it is running.
"""
import ctypes
from ctypes import wintypes
import hashlib
import http.server
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]
EXE = ROOT / 'outputs/releases/NasdaqQDII-0.4.5/NasdaqQDII.exe'
PS = Path(os.environ['WINDIR']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
CHECKS = []
OUTPUT = ROOT / 'outputs/desktop-v045' / ('verify-' + uuid.uuid4().hex[:8])
STATE = OUTPUT / '测试 状态'
HOME = OUTPUT / '测试 数据'
RPC_RESULT = OUTPUT / 'rpc.json'
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def check(name, passed, details=None):
    CHECKS.append({'name': name, 'passed': bool(passed), 'details': details})
    if not passed:
        raise AssertionError(name + ': ' + str(details))
    print('PASS ' + name, flush=True)


def run(args, **kwargs):
    return subprocess.run([str(a) for a in args], capture_output=True, encoding='utf-8',
                          errors='replace', creationflags=subprocess.CREATE_NO_WINDOW,
                          timeout=120, **kwargs)


def rpc(command):
    RPC_RESULT.unlink(missing_ok=True)
    result = run([EXE, '--state-root', STATE, '--command', command,
                  '--result', RPC_RESULT, '--no-browser'])
    if result.returncode or not RPC_RESULT.exists():
        raise RuntimeError('IPC failed: ' + command + '\n' + result.stderr)
    return json.loads(RPC_RESULT.read_text(encoding='utf-8'))


def wait_state(expected, seconds=90):
    until = time.monotonic() + seconds
    state = None
    while time.monotonic() < until:
        try:
            state = rpc('status')
            if state.get('state') == expected:
                return state
            if state.get('state') == 'error' and expected != 'error':
                raise AssertionError(state)
        except RuntimeError:
            pass
        time.sleep(0.8)
    raise TimeoutError(str(state))


def launch(home, port):
    return subprocess.Popen([str(EXE), '--state-root', str(STATE), '--home', str(home),
                             '--port', str(port), '--no-browser', '--no-shortcuts'],
                            creationflags=subprocess.CREATE_NO_WINDOW)


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def get(base, route, method='GET'):
    try:
        with HTTP.open(urllib.request.Request(base + route, method=method), timeout=15) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


def alive(pid):
    api = ctypes.WinDLL('kernel32', use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = api.OpenProcess(0x1000, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        return bool(api.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
    finally:
        api.CloseHandle(handle)


def wait_dead(pid):
    until = time.monotonic() + 15
    while alive(pid) and time.monotonic() < until:
        time.sleep(0.2)
    return not alive(pid)


def ps_quote(value):
    return "'" + str(value).replace("'", "''") + "'"


def test_tasks(payload):
    prefix = 'NasdaqQDII-PackageSmoke-' + uuid.uuid4().hex[:8] + '-'
    script = OUTPUT / 'scheduler-smoke.ps1'
    script.write_text('''
$ErrorActionPreference='Stop'
[Console]::OutputEncoding=New-Object Text.UTF8Encoding($false)
$installer=INSTALLER
$homePath=HOME_PATH
$launcher=LAUNCHER
$prefix=PREFIX
$backupName=$prefix+'Backup';$serveName=$prefix+'Serve'
try {
  & $installer -DataHome $homePath -LauncherPath $launcher -TaskPrefix $prefix -OnlyTask Backup
  & $installer -DataHome $homePath -LauncherPath $launcher -TaskPrefix $prefix -OnlyTask Backup
  & $installer -DataHome $homePath -LauncherPath $launcher -TaskPrefix $prefix -OnlyTask Serve
  & $installer -DataHome $homePath -LauncherPath $launcher -TaskPrefix $prefix -OnlyTask Serve
  $oldXml=Export-ScheduledTask -TaskName $backupName
  $refused=$false
  try {& $installer -DataHome ($homePath+'-other') -LauncherPath $launcher -TaskPrefix $prefix -OnlyTask Backup} catch {$refused=$true}
  if(-not $refused -or $oldXml -ne (Export-ScheduledTask -TaskName $backupName)){throw 'Foreign-home task protection failed.'}
  Start-ScheduledTask -TaskName $backupName
  $deadline=(Get-Date).AddSeconds(60)
  do {Start-Sleep -Milliseconds 700;$info=Get-ScheduledTaskInfo -TaskName $backupName;$task=Get-ScheduledTask -TaskName $backupName} while(((Get-Date)-lt $deadline)-and($info.LastRunTime.Year -lt 2026 -or $task.State -eq 'Running'))
  if($info.LastTaskResult -ne 0){throw ('Scheduled worker result: '+$info.LastTaskResult)}
  if(-not (Get-ChildItem -LiteralPath (Join-Path $homePath 'data/backups') -Filter '*.sqlite3')){throw 'Backup missing.'}
  Write-Output 'SCHEDULER_SMOKE_PASSED'
} finally {
  foreach($name in @($backupName,$serveName)) {
    $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue
    if($task -and $name.StartsWith($prefix)) {if($task.State -eq 'Running'){Stop-ScheduledTask -TaskName $name};Unregister-ScheduledTask -TaskName $name -Confirm:$false}
  }
}
'''.replace('INSTALLER', ps_quote(payload / 'desktop/install-tasks.ps1'))
        .replace('HOME_PATH', ps_quote(HOME)).replace('LAUNCHER', ps_quote(EXE))
        .replace('PREFIX', ps_quote(prefix)), encoding='utf-8-sig')
    result = run([PS, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script])
    (OUTPUT / 'scheduler.txt').write_text(result.stdout + result.stderr, encoding='utf-8')
    check('Real Task Scheduler backup, idempotent repair, foreign-home protection and cleanup',
          result.returncode == 0 and 'SCHEDULER_SMOKE_PASSED' in result.stdout, result.stderr)


def main():
    OUTPUT.mkdir(parents=True)
    HOME.mkdir()
    (HOME / 'data').mkdir()
    shutil.copy2(ROOT / 'data/latest.json', HOME / 'data/latest.json')
    host = None
    try:
        started = time.monotonic()
        result_path = OUTPUT / 'extraction.json'
        result = run([EXE, '--state-root', STATE, '--home', HOME, '--extract-only',
                      '--no-browser', '--no-shortcuts', '--result', result_path])
        check('EXE extracts in a Chinese path with spaces', result.returncode == 0, result.stderr)
        extracted = json.loads(result_path.read_text(encoding='utf-8'))
        payload = Path(extracted['payload'])
        check('Selected data home survives extraction', Path(extracted['home']) == HOME)
        manifest = json.loads((payload / 'payload-manifest.json').read_text(encoding='utf-8'))
        mismatches = [name for name, digest in manifest.items()
                      if hashlib.sha256((payload / name).read_bytes()).hexdigest() != digest]
        check('Every extracted runtime file matches SHA-256', not mismatches, {'files': len(manifest), 'bad': mismatches})
        paths = [p.relative_to(payload).as_posix() for p in payload.rglob('*') if p.is_file()]
        forbidden = [p for p in paths if p.startswith(('data/', 'logs/', 'outputs/')) or
                     Path(p).name in ('latest.json','monitor.sqlite3','config.local.json','manual_channels.json','.env')]
        check('Generic payload excludes data, caches, personal channel confirmations and secrets', not forbidden, forbidden)
        user_path = str(Path.home()).encode('utf-8').lower()
        private_paths = [name for name in paths if any(needle in (payload / name).read_bytes().lower()
                         for needle in (user_path, user_path.replace(b'\\', b'/')))]
        check('No builder personal absolute paths are embedded', not private_paths, private_paths)
        env = dict(os.environ, PATH=str(Path(os.environ['WINDIR']) / 'System32'),
                   PYTHONHOME=str(OUTPUT / 'nonexistent-system-python'), NASDAQ_QDII_HOME=str(HOME))
        result = run([payload / 'python/python.exe', '-B', '-X', 'utf8', '-c',
                      'import sys,akshare,fastapi,curl_cffi,exchange_calendars;from app.storage import connect,latest;'
                      'assert sys.flags.isolated and sys.flags.no_site;'
                      's=latest();\nwith connect() as c:c.execute("INSERT OR IGNORE INTO snapshots VALUES (?,?,?)",'
                      '(s["id"],s["generated_at"],__import__("json").dumps(s)))\nprint("ISOLATED_RUNTIME_OK")'], cwd=payload, env=env)
        check('Runtime works without system Python/PATH and ignores foreign PYTHONHOME',
              result.returncode == 0 and 'ISOLATED_RUNTIME_OK' in result.stdout, result.stderr)
        check('Python and package license notices retained', (payload / 'python/LICENSE.txt').exists() and
              any('licenses/' in name.lower() for name in paths))
        port = free_port()
        host = launch(HOME, port)
        state = wait_state('ready')
        launch_seconds = round(time.monotonic() - started, 2)
        check('Tray starts and owns the packaged service', state['serviceOwned'] and state['trayVisible'] and
              state['hasSnapshot'] and not state['attachedExisting'], {'total_extraction_and_start_seconds': launch_seconds})
        pid = state['servicePid']
        base = state['url'].rstrip('/')
        code, headers, raw = get(base, '/api/health')
        health = json.loads(raw)
        check('Actual HTTP service identifies the isolated data home and version', code == 200 and
              health['version'] == '0.4.5' and health['home_id'] == hashlib.sha256(str(HOME).lower().encode()).hexdigest()[:24])
        code, headers, raw = get(base, '/api/snapshot')
        snapshot = json.loads(raw)
        original = json.loads((HOME / 'data/latest.json').read_text(encoding='utf-8'))
        check('Existing snapshot is displayed through packaged service', code == 200 and snapshot['id'] == original['id'])
        check('Read-only routes and security headers survive packaging', get(base, '/api/snapshot', 'POST')[0] == 405 and
              headers.get('Cache-Control', headers.get('cache-control')) == 'no-store' and
              'default-src' in headers.get('Content-Security-Policy', headers.get('content-security-policy', '')))
        for years in (1,3,5,10,20,0):
            code, _, raw = get(base, f'/api/valuation-view?metric=forward&dataset=publisher&years={years}')
            view = json.loads(raw)
            check(f'Forward PE {years or "all"}-year route uses actual saved history', code == 200 and
                  view.get('value') is not None, {'samples': view.get('samples'), 'keys': list(view)[:8]})
        check('All web assets and program version are bundled', '0.4.5' in get(base, '/')[2].decode() and
              all(get(base, p)[0] == 200 for p in ('/assets/app.js','/assets/style.css','/assets/vendor/chart.umd.js')))
        second = run([EXE, '--state-root', STATE, '--no-browser', '--no-shortcuts'])
        check('Second launch reuses the single instance', second.returncode == 0 and rpc('status')['servicePid'] == pid)
        check('Tray backup request is accepted', rpc('backup')['accepted'])
        deadline = time.monotonic() + 45
        while time.monotonic() < deadline:
            state = rpc('status')
            if state.get('lastTask') == 'backup' and not state['taskBusy']:
                break
            time.sleep(0.6)
        check('Tray backup completes in external data home', state['lastTask'] == 'backup' and state['lastExit'] == 0)
        for file in (HOME / 'data/backups').glob('*.sqlite3'):
            with sqlite3.connect(file) as con:
                check('Backed-up SQLite contains the snapshot and passes integrity check',
                      con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok' and
                      con.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] > 0)
        browser_result = run([Path(os.environ.get('NASDAQ_NODE', str(Path.home() / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe'))),
                              ROOT / 'scripts/verify_desktop_web.cjs', base, OUTPUT / 'browser.json'])
        check('Six packaged pages work on desktop and mobile with synchronized charts', browser_result.returncode == 0,
              browser_result.stdout + browser_result.stderr)
        test_tasks(payload)
        check('Stop request accepted', rpc('stop')['accepted'])
        wait_state('paused')
        check('Stopping tray service terminates owned process', wait_dead(pid))
        rpc('start')
        state = wait_state('ready')
        check('Restart uses a new process and preserves saved data', state['servicePid'] != pid and state['hasSnapshot'])
        pid = state['servicePid']
        rpc('exit')
        host.wait(timeout=20)
        host = None
        check('Exit cleans up the owned service and preserves cache', wait_dead(pid) and (HOME / 'data/latest.json').exists())
        host = launch(HOME, port)
        pid = wait_state('ready')['servicePid']
        host.kill()
        host.wait(timeout=15)
        host = None
        check('Unexpected tray termination cleans up its service through Windows Job', wait_dead(pid))

        class Foreign(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200);self.end_headers();self.wfile.write(b'{"status":"foreign"}')
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('127.0.0.1', port), Foreign)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            host = launch(HOME, port)
            state = wait_state('error')
            check('Foreign port conflict is detected without taking ownership', not state['serviceOwned'] and '占用' in state['detail'])
            rpc('exit');host.wait(timeout=15);host=None
            check('Foreign server survives tray exit', json.loads(get(base, '/api/health')[2])['status'] == 'foreign')
        finally:
            server.shutdown();server.server_close()

        blank = OUTPUT / '空白 数据'
        host = launch(blank, port)
        state = wait_state('ready')
        check('Empty data home reports missing data without fabricated snapshot', not state['hasSnapshot'] and
              get(base, '/api/snapshot')[0] == 503 and not (blank / 'data/latest.json').exists())
        rpc('exit');host.wait(timeout=15);host=None
        try:
            old_health = json.loads(get('http://127.0.0.1:8765', '/api/health')[2])
        except (OSError, urllib.error.URLError):
            old_health = None
        if old_health and old_health.get('status') == 'ok':
            host = launch(ROOT, 8765)
            state = wait_state('ready')
            check('Existing legacy project service is attached and remains unowned',
                  state['attachedExisting'] and not state['serviceOwned'] and state['hasSnapshot'])
            rpc('exit');host.wait(timeout=15);host=None
            check('Original service remains available after tray exit',
                  json.loads(get('http://127.0.0.1:8765', '/api/health')[2]) == old_health)
        (STATE / 'data-home.txt').unlink()
        result = run([EXE, '--state-root', STATE, '--extract-only', '--no-browser',
                      '--no-shortcuts', '--result', result_path])
        inferred = json.loads(result_path.read_text(encoding='utf-8'))
        check('First launch from project release folder discovers original data automatically',
              result.returncode == 0 and Path(inferred.get('home', '')) == ROOT)
    finally:
        if host is not None and host.poll() is None:
            try:
                rpc('exit');host.wait(timeout=15)
            except Exception:
                host.kill();host.wait(timeout=15)
        result = {'checks': CHECKS, 'passed': sum(c['passed'] for c in CHECKS),
                  'failed': sum(not c['passed'] for c in CHECKS), 'exe_sha256': hashlib.sha256(EXE.read_bytes()).hexdigest()}
        (OUTPUT / 'checks.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps({'output': str(OUTPUT), 'passed': result['passed'], 'failed': result['failed']}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
