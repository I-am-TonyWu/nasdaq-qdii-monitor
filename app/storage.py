import hashlib
import json
import os
import sqlite3
from contextlib import contextmanager
from .settings import DATA
from .calendar import now_iso

DB = DATA / 'monitor.sqlite3'

@contextmanager
def connect():
    con=sqlite3.connect(DB, timeout=30)
    con.row_factory=sqlite3.Row
    con.execute('PRAGMA journal_mode=WAL')
    con.executescript('''
      CREATE TABLE IF NOT EXISTS observations (
        series TEXT, observation_date TEXT, collected_at TEXT, value REAL,
        source TEXT, method TEXT, payload TEXT,
        PRIMARY KEY(series, observation_date, collected_at));
      CREATE TABLE IF NOT EXISTS snapshots (
        id TEXT PRIMARY KEY, created_at TEXT, payload TEXT);
      CREATE TABLE IF NOT EXISTS runs (
        id INTEGER PRIMARY KEY, started_at TEXT, finished_at TEXT, kind TEXT, status TEXT, payload TEXT);
      CREATE TABLE IF NOT EXISTS reports (
        report_date TEXT PRIMARY KEY, snapshot_id TEXT, created_at TEXT,
        status TEXT DEFAULT 'preview', sent_at TEXT, error TEXT);
      CREATE TABLE IF NOT EXISTS source_requests (
        id INTEGER PRIMARY KEY,url TEXT,fetched_at TEXT,status INTEGER,payload_hash TEXT,
        etag TEXT,last_modified TEXT,error TEXT);
      CREATE TABLE IF NOT EXISTS series_observations (
        revision_id TEXT PRIMARY KEY,series TEXT,observation_date TEXT,value REAL,
        provider TEXT,method_id TEXT,first_seen_at TEXT,last_seen_at TEXT,payload TEXT);
      CREATE INDEX IF NOT EXISTS series_observation_key ON series_observations(series,observation_date,provider,method_id);
    ''')
    try:
        yield con
        con.commit()
    finally:
        con.close()

def atomic_json(path, payload):
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(payload,ensure_ascii=False,allow_nan=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)

def latest():
    path=DATA/'latest.json'
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else None

def persist(snapshot):
    from .source_audit import store_observation
    encoded=json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
    snapshot['id']=hashlib.sha256(encoded.encode()).hexdigest()[:20]
    encoded=json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
    with connect() as con:
        con.execute('INSERT OR IGNORE INTO snapshots VALUES (?,?,?)',(snapshot['id'],snapshot['generated_at'],encoded))
        for series,item in snapshot['series'].items():
            for row in item.get('history',[]):
                store_observation(con,series,row,item,item['collected_at'])
        for series,item in [*snapshot.get('valuation',{}).items(),*snapshot.get('valuation_references',{}).items(),
                            *[('publisher:'+k,v) for k,v in snapshot.get('valuation_publisher',{}).items()]]:
            for row in item.get('history',[]):
                store_observation(con,'valuation:'+series,row,item,snapshot['generated_at'])
        for fund in ([] if snapshot.get('collection',{}).get('kind')=='retry' else snapshot['funds']):
            for share in fund['shares']:
                con.execute('INSERT OR IGNORE INTO observations VALUES (?,?,?,?,?,?,?)',
                    ('fund:'+share['code'],share.get('nav_date') or snapshot['market']['beijing_date'],snapshot['generated_at'],
                     share.get('nav'),'Eastmoney / Tiantian','channel-share-v1',json.dumps(share,ensure_ascii=False)))
        con.execute('INSERT INTO runs(started_at,finished_at,kind,status,payload) VALUES(?,?,?,?,?)',
                    (snapshot['generated_at'],now_iso(),snapshot.get('collection',{}).get('kind','collection'),
                     'partial' if snapshot.get('update_issues',snapshot['issues']) else 'complete',json.dumps(snapshot['issues'],ensure_ascii=False)))
    atomic_json(DATA/'latest.json',snapshot)
    return snapshot

def history(limit=30):
    with connect() as con:
        rows=con.execute('SELECT id,created_at,payload FROM snapshots ORDER BY created_at DESC LIMIT ?', (min(limit,100),)).fetchall()
        return [{'id':r['id'],'created_at':r['created_at'],'score':json.loads(r['payload'])['score']['value'],
                 'session':json.loads(r['payload'])['market']['expected_us_session'],
                 'issues':len(json.loads(r['payload'])['issues'])} for r in rows]

def get_snapshot(snapshot_id):
    with connect() as con:
        row=con.execute('SELECT payload FROM snapshots WHERE id=?',(snapshot_id,)).fetchone()
        return json.loads(row['payload']) if row else None

def backup():
    dest=DATA/'backups';dest.mkdir(exist_ok=True)
    path=dest/(now_iso().replace(':','-')+'.sqlite3')
    with connect() as source,sqlite3.connect(path) as target:
        source.backup(target)
    return path
