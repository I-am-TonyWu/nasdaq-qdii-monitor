"""Content-addressed public evidence and immutable observation revisions."""
import hashlib,json
from .settings import DATA,ROOT
from .calendar import now_iso
from .storage import connect

def evidence(url,content,status=200,headers=None,error=None):
    content=content or b'';headers=headers or {}
    digest=hashlib.sha256(content).hexdigest() if content else None
    if digest:
        folder=DATA/'source-evidence';folder.mkdir(exist_ok=True)
        try:
            with (folder/(digest+'.bin')).open('xb') as handle:handle.write(content)
        except FileExistsError:pass
    with connect() as con:
        con.execute('INSERT INTO source_requests(url,fetched_at,status,payload_hash,etag,last_modified,error) VALUES(?,?,?,?,?,?,?)',
                    (url,now_iso(),status,digest,headers.get('ETag'),headers.get('Last-Modified'),error))
    return digest

def record_response(response):
    digest=evidence(str(response.url),response.content,response.status_code,response.headers)
    response.audit_hash=digest
    return digest

def registry():
    return json.loads((ROOT/'config'/'source_registry.json').read_text(encoding='utf-8'))

def store_observation(con,series,row,item,collected_at):
    provider=row.get('provider') or item.get('source','unknown')
    method=item.get('method_id') or item.get('method','unknown')
    stable={'series':series,'date':row['date'],'value':row['value'],'provider':provider,'method_id':method}
    digest=hashlib.sha256(json.dumps(stable,sort_keys=True).encode()).hexdigest()
    prior=con.execute('SELECT revision_id,value FROM series_observations WHERE series=? AND observation_date=? AND provider=? AND method_id=? ORDER BY last_seen_at DESC,rowid DESC LIMIT 1',
                      (series,row['date'],provider,method)).fetchone()
    if prior:
        digest=prior['revision_id'] if prior['value']==row['value'] else hashlib.sha256((digest+prior['revision_id']).encode()).hexdigest()
    metadata={**row,'instrument':item.get('instrument',series),'metric':item.get('metric',series),
        'publisher':item.get('publisher','unknown'),'provider':provider,'upstream_group':item.get('upstream_group','unknown'),
        'method_id':method,'frequency':item.get('frequency','daily'),'unit':item.get('unit'),
        'published_at':row.get('published_at'),'known_at':row.get('known_at'),'fetched_at':collected_at,
        'source_url':item.get('source_url'),'usage_scope':item.get('usage_scope','local_research'),
        'verification_status':item.get('verification_status','not_checked'),'payload_hash':row.get('payload_hash'),
        'revision_of':prior['revision_id'] if prior and prior['revision_id']!=digest else None}
    con.execute('INSERT OR IGNORE INTO series_observations(revision_id,series,observation_date,value,provider,method_id,first_seen_at,last_seen_at,payload) VALUES(?,?,?,?,?,?,?,?,?)',
                (digest,series,row['date'],row['value'],provider,method,collected_at,collected_at,json.dumps(metadata,ensure_ascii=False)))
    con.execute('UPDATE series_observations SET last_seen_at=? WHERE revision_id=?',(collected_at,digest))
    if metadata['payload_hash']:
        stored=con.execute('SELECT payload FROM series_observations WHERE revision_id=?',(digest,)).fetchone()
        original=json.loads(stored['payload'])
        if not original.get('payload_hash'):
            original.update(payload_hash=metadata['payload_hash'],evidence_attached_at=collected_at)
            con.execute('UPDATE series_observations SET payload=? WHERE revision_id=?',(json.dumps(original,ensure_ascii=False),digest))
