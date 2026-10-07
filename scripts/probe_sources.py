"""Bounded, credential-free source reachability audit."""
import concurrent.futures
import json
import pathlib
import urllib.request

SOURCES = {
    'catalog': 'https://raw.githubusercontent.com/zhouminghan/qdii-tracker/main/config/funds.json',
    'tracker_source': 'https://raw.githubusercontent.com/zhouminghan/qdii-tracker/main/scripts/sources/eastmoney.py',
    'purchase_source': 'https://raw.githubusercontent.com/akfamily/akshare/main/akshare/fund/fund_purchase_em.py',
    'yahoo_ndx': 'https://query1.finance.yahoo.com/v8/finance/chart/%5ENDX?range=5y&interval=1d',
    'yahoo_qqq': 'https://query1.finance.yahoo.com/v8/finance/chart/QQQ?range=5y&interval=1d',
    'cboe_vxn': 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VXN_History.csv',
    'cboe_vix': 'https://cdn.cboe.com/api/global/us_indices/daily_prices/VIX_History.csv',
    'fred_ndxtmc': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=NASDAQNDXTMC',
    'fred_yields': 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS2,DGS10,DFII10',
    'cnn': 'https://production.dataviz.cnn.io/index/fearandgreed/graphdata',
    'fund_017093': 'https://fundf10.eastmoney.com/jbgk_017093.html',
    'eastmoney_ndxtmc': 'https://push2his.eastmoney.com/api/qt/stock/kline/get?secid=100.NDXTMC&klt=101&fqt=0&lmt=400&end=20500101&fields1=f1,f2,f3,f4,f5,f6&fields2=f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
}

def probe(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://www.cnn.com/' if name == 'cnn' else url})
        with urllib.request.urlopen(req, timeout=18) as response:
            raw = response.read(8_000_000)
        target = pathlib.Path('vendor-cache')
        target.mkdir(exist_ok=True)
        (target / (name + '.txt')).write_bytes(raw)
        return {'name': name, 'ok': True, 'bytes': len(raw), 'sample': raw[:140].decode('utf-8', errors='replace')}
    except Exception as exc:
        return {'name': name, 'ok': False, 'error': str(exc)[:200]}

if __name__ == '__main__':
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for result in pool.map(probe, SOURCES.items()):
            print(json.dumps(result, ensure_ascii=False))
