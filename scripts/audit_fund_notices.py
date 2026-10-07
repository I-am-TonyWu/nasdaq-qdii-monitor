"""Download current issuer announcements for human review (never infer quota)."""
import io, json, re, sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from curl_cffi import requests
from bs4 import BeautifulSoup
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.settings import DATA
out = DATA/'revision-audit'
profiles = json.loads((DATA/'fund_profiles.json').read_text(encoding='utf-8'))
groups = {}
for code, p in profiles.items(): groups.setdefault(p['group_key'], []).append(code)

def get_notices(codes):
    code = codes[0]
    r = requests.get('https://api.fund.eastmoney.com/f10/JJGG',
        params={'fundcode':code,'pageIndex':1,'pageSize':150,'type':0},
        headers={'Referer':f'https://fundf10.eastmoney.com/jjgg_{code}.html'},
        impersonate='chrome', timeout=20)
    r.raise_for_status()
    j = r.json()
    (out/f'notices-{code}.json').write_text(json.dumps(j,ensure_ascii=False,indent=2),encoding='utf-8')
    relevant=[n for n in j.get('Data',[]) if re.search('申购|定投|定期定额|规模上限',n['TITLE'])]
    print(json.dumps({'code':code,'name':profiles[code]['group_key'],'count':len(j.get('Data',[])),
        'notices':[{k:n.get(k) for k in ('ID','TITLE','PUBLISHDATEDesc')} for n in relevant[:6]]},ensure_ascii=False),flush=True)
    return code,relevant[:6]

def download(item):
    code,n = item
    ident = n['ID']; url = 'https://np-cnotice-stock.eastmoney.com/api/content/ann'
    r = requests.get(url, params={'art_code':ident,'client_source':'web','page_index':1}, impersonate='chrome',timeout=20)
    r.raise_for_status()
    payload = r.json()['data']
    text = payload.get('notice_content','')
    (out/f'{ident}.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding='utf-8')
    (out/f'{ident}.txt').write_text(text,encoding='utf-8')
    # Structured issuer text includes tables and footnotes, without navigation.
    return {'code':code,'id':ident,'bytes':len(text)}
items=[]
with ThreadPoolExecutor(max_workers=6) as pool:
    for f in as_completed([pool.submit(get_notices,codes) for codes in groups.values()]):
        try:
            code,ns=f.result(); items.extend((code,n) for n in ns)
        except Exception as e: print(type(e).__name__,flush=True)
with ThreadPoolExecutor(max_workers=6) as pool:
    for f in as_completed([pool.submit(download,item) for item in items]):
        try: f.result()
        except Exception as e: print(type(e).__name__,flush=True)
