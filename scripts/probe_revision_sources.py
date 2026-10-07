"""Bounded read-only source investigation; raw responses stay in ignored data/."""
import json, sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import requests
from curl_cffi import requests as curl

out = Path(__file__).resolve().parents[1] / 'data' / 'revision-audit'
out.mkdir(parents=True, exist_ok=True)
base = 'https://siblisresearch.supabase.co/functions/v1/free-data-api/v1'
urls = {
    'wsj': 'https://www.wsj.com/market-data/stocks/peyields',
    'vxn3': 'https://query1.finance.yahoo.com/v8/finance/chart/%5EVXN?interval=1d&range=3y',
    'vxn5': 'https://query1.finance.yahoo.com/v8/finance/chart/%5EVXN?interval=1d&range=5y',
    'vix5': 'https://query1.finance.yahoo.com/v8/finance/chart/%5EVIX?interval=1d&range=5y',
    'siblis-dates': base + '/dates',
    'siblis-forward': base + '/NDX/pe-forward',
    'notices': 'https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=30&page_index=1&ann_type=3&stock_list=019736',
    'fund-page': 'https://fundf10.eastmoney.com/jjgg_019736_1.html',
}
def probe(item):
    name, url = item
    r = curl.get(url, impersonate='chrome', timeout=20)
    (out / (name + '.txt')).write_text(r.text, encoding='utf-8')
    detail = {'name': name, 'status': r.status_code, 'bytes': len(r.content)}
    try:
        j = r.json()
        if name.startswith('vx'):
            result = j.get('chart', {}).get('result') or []
            detail.update(error=j.get('chart', {}).get('error'), samples=len(result[0].get('timestamp', [])) if result else 0)
        elif name == 'notices':
            detail['sample'] = j.get('data', {}).get('list', [])[:2]
        else:
            detail['sample'] = str(j)[:600]
    except ValueError:
        pass
    return detail
with ThreadPoolExecutor(max_workers=6) as pool:
    jobs = {pool.submit(probe, item): item[0] for item in urls.items()}
    for job in as_completed(jobs):
        try: print(json.dumps(job.result(), ensure_ascii=False), flush=True)
        except Exception as e: print(json.dumps({'name':jobs[job], 'error':type(e).__name__}), flush=True)
