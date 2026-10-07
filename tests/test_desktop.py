"""Exercise external data homes and the real bundled worker entry contract."""
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def python(code, home):
    env = dict(os.environ, NASDAQ_QDII_HOME=str(home))
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c', code], cwd=ROOT,
                            env=env, capture_output=True, text=True, encoding='utf-8', timeout=30)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def worker(home, command, *args, windowless=False):
    exe = Path(sys.executable).with_name('pythonw.exe') if windowless else sys.executable
    return subprocess.run([str(exe), '-B', '-X', 'utf8', '-m', 'app.desktop_worker',
                           '--home', str(home), command, *args], cwd=ROOT,
                          capture_output=True, text=True, encoding='utf-8', timeout=30)


def test_separate_data_home_keeps_bundled_assets_and_reads_local_config(tmp_path):
    home = tmp_path / '外部 数据'
    home.mkdir()
    (home / 'config.local.json').write_text('{"port": 18765}', encoding='utf-8')
    result = python('from app.settings import HOME,ROOT,DATA,CONFIG;import json;'
                    'print(json.dumps([str(HOME),str(ROOT),str(DATA),CONFIG["port"]]))', home)
    assert result == [str(home.resolve()), str(ROOT), str(home / 'data'), 18765]
    assert (home / 'data').is_dir()


def test_worker_status_and_consistent_backup_are_in_selected_home(tmp_path):
    result = worker(tmp_path, 'status')
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)['has_snapshot'] is False
    result = worker(tmp_path, 'backup')
    assert result.returncode == 0, result.stderr
    backup = Path(result.stdout.strip())
    assert backup.parent == tmp_path / 'data' / 'backups'
    with sqlite3.connect(backup) as con:
        assert con.execute('PRAGMA integrity_check').fetchone()[0] == 'ok'
        assert con.execute('SELECT COUNT(*) FROM snapshots').fetchone()[0] == 0


def test_windowless_worker_writes_log_to_selected_home(tmp_path):
    # Redirected pipes provide valid handles even for pythonw. Model the missing
    # standard streams of Task Scheduler explicitly; native scheduling is also
    # exercised by scripts/verify_desktop.py with the built pythonw executable.
    result = subprocess.run([sys.executable, '-B', '-X', 'utf8', '-c',
                             'import sys;sys.stdout=sys.stderr=None;'
                             'from app.desktop_worker import main;'
                             f'sys.argv=["worker","--home",{str(tmp_path)!r},"status"];main()'],
                            cwd=ROOT, capture_output=True, timeout=30)
    assert result.returncode == 0
    assert json.loads((tmp_path / 'logs' / 'scheduled.log').read_text(encoding='utf-8'))['has_snapshot'] is False


@pytest.mark.parametrize('port', ['0', '1023', '65536'])
def test_worker_rejects_invalid_ports(tmp_path, port):
    result = worker(tmp_path, 'serve', '--port', port)
    assert result.returncode == 2 and 'port must be' in result.stderr


def test_worker_does_not_expose_email_send(tmp_path):
    result = worker(tmp_path, 'send')
    assert result.returncode == 2 and 'invalid choice' in result.stderr


def test_health_identifies_home_and_blank_home_is_not_filled(tmp_path):
    result = python('from app.main import health,snapshot;from fastapi import HTTPException;import json;'
                    'h=health();\ntry:snapshot()\nexcept HTTPException as e:code=e.status_code\n'
                    'print(json.dumps({"health":h,"snapshot":code}))', tmp_path)
    assert result['health']['application'] == 'nasdaq-qdii-monitor'
    assert result['health']['home_id'] == hashlib.sha256(str(tmp_path.resolve()).lower().encode()).hexdigest()[:24]
    assert result['health']['has_snapshot'] is False
    assert result['health']['version'] == '0.4.5'
    assert result['snapshot'] == 503


def test_existing_personal_channel_confirmation_is_external_and_keeps_time(tmp_path):
    config = tmp_path / 'config'
    config.mkdir()
    # Synthetic input: the public test suite must not read personal confirmations.
    source = {'channels': [{'code': '019118', 'channel': '合成测试渠道',
                           'channel_kind': 'distributor', 'currency': 'CNY',
                           'daily_limit': 100, 'confirmed_at': '2026-10-06T01:00:00+00:00'}]}
    (config / 'manual_channels.json').write_text(json.dumps(source), encoding='utf-8')
    claim = source['channels'][0]
    result = python('from app import fund_evidence;import json;'
                    f'code={claim["code"]!r};'
                    'r=json.loads((fund_evidence.ROOT/"config"/"fund_rules.json").read_text(encoding="utf-8"))["rules"];'
                    'r=next(x for x in r if code in x["codes"]);r["health"]={"verified":True,"checked_at":"test"};'
                    'print(json.dumps(fund_evidence.manual_channels(code,r)))', tmp_path)
    assert result and result[0]['channel'] == claim['channel']
    assert result[0]['checked_at'] == claim['confirmed_at']
    assert result[0]['verification_basis'] == 'user_confirmation'
