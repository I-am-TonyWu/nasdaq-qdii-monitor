"""Official-first acquisition; freshness and transmission checks stay separate."""
import re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from . import sources
from .analytics import finite

def parse_nasdaq(html,symbol,expected):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    if symbol not in [n.get_text(' ',strip=True) for n in soup.select('h4')]:
        raise ValueError('Nasdaq指数身份不符')
    text=soup.get_text(' ',strip=True)
    match=re.search(r'DATA AS OF\s+(\d{1,2}/\d{1,2}/\d{4})\s+([\d,]+\.\d+)',text)
    if not match:raise ValueError('Nasdaq观察日期/报价不可确认')
    day=datetime.strptime(match[1],'%m/%d/%Y').date().isoformat()
    if day!=expected:raise ValueError('Nasdaq页面日期不是最近完成交易日')
    cells={}
    for tr in soup.select('table tr'):
        row=tr.find_all(['td','th'],recursive=False)
        if len(row)==2:cells[row[0].get_text(' ',strip=True)]=row[1].get_text(' ',strip=True)
    last=finite(cells.get('Last','').replace(',',''))
    if last is None or abs(last-float(match[2].replace(',','')))>.05:
        raise ValueError('Nasdaq摘要与Last字段不一致')
    # Nasdaq's summary table currently labels the completed-session maximum
    # "Day High"; older pages used "Today's High". Keep the same dated quote
    # and publisher instead of filling a mismatching vendor-close row.
    high=finite((cells.get('Day High') or cells.get("Today's High") or '').replace(',',''))
    return {'date':day,'value':last,'provider':'Nasdaq','price_field':'Last after completed-session cutoff',
            **({'high':high,'high_source':'Nasdaq'} if high is not None and high>=last else {})}

def attach_highs(rows,auxiliary,provider):
    """Use auxiliary highs only when the same-date price-index close agrees."""
    quotes={r['date']:r for r in auxiliary or []}
    result=[]
    for row in rows:
        quote=quotes.get(row['date'],{})
        high=finite(quote.get('high'))
        if not row.get('high') and high is not None and high>=row['value'] and abs(quote['value']-row['value'])<=.05:
            row={**row,'high':high,'high_source':provider,'high_payload_hash':quote.get('payload_hash')}
        result.append(row)
    return result

def _parallel(jobs):
    def one(fn):
        try:return {'rows':fn(),'error':None}
        except Exception as exc:return {'rows':None,'error':type(exc).__name__}
    with ThreadPoolExecutor(max_workers=len(jobs)) as pool:
        futures={key:pool.submit(one,fn) for key,fn in jobs.items()}
        return {key:f.result() for key,f in futures.items()}

def _check(a,b,tolerance,providers):
    left={r['date']:r['value'] for r in a or []};right={r['date']:r['value'] for r in b or []}
    dates=sorted(left.keys()&right.keys())[-20:]
    delta=max((abs(left[d]-right[d]) for d in dates),default=None)
    return {'providers':providers,'type':'shared-publisher-transmission','samples':len(dates),
            'through':dates[-1] if dates else None,'max_difference':delta,'tolerance':tolerance,
            'primary_latest':max(left,default=None),'auxiliary_latest':max(right,default=None),
            'result':'missing' if not dates else 'conflict' if delta>tolerance else 'passed'}

def verification(check,expected):
    if check['result']=='conflict':return 'conflict'
    return 'verified_transmission' if check['result']=='passed' and check['through']==expected else 'official_aux_missing'

def index(key,expected):
    symbol='NDX' if key=='NDX' else 'NDXTMC'
    url=f'https://indexes.nasdaq.com/Index/Overview/{symbol}'
    def official_quote():
        response=sources.fetch_curl(url)
        return [{**parse_nasdaq(response.text,symbol,expected),'payload_hash':response.audit_hash}]
    high_provider='Yahoo Finance' if key=='NDX' else 'Eastmoney'
    result=_parallel({'official':official_quote,
                      'archive':lambda:sources.fred('NASDAQ100' if key=='NDX' else 'NASDAQNDXTMC',expected),
                      'highs':lambda:sources.yahoo('^NDX',expected) if key=='NDX' else sources.eastmoney('251.NDXTMC','NDXTMC',expected)})
    official=result['official']['rows'];archive=result['archive']['rows']
    checks=[_check(official,archive,.05,['Nasdaq','Nasdaq via FRED'])]
    meta={'source_url':url,'checks':checks,'publisher':'Nasdaq',
          'verification_status':verification(checks[0],expected),
          'high_history_provider':high_provider,'high_history_error':result['highs']['error']}
    if official:
        joined={r['date']:{**r,'provider':'Nasdaq via FRED'} for r in archive or []}
        joined.update({r['date']:r for r in official})
        return attach_highs(sorted(joined.values(),key=lambda r:r['date']),result['highs']['rows'],high_provider),'Nasdaq / FRED',meta
    if archive:
        meta['source_url']=f'https://fred.stlouisfed.org/series/{"NASDAQ100" if key=="NDX" else "NASDAQNDXTMC"}'
        if archive[-1]['date']==expected:return attach_highs(archive,result['highs']['rows'],high_provider),'Nasdaq via FRED',meta
    try:
        recent=sources.eastmoney('100.NDX100' if key=='NDX' else '251.NDXTMC','NDX100' if key=='NDX' else 'NDXTMC',expected)
        provider='Eastmoney'
    except Exception:
        if key=='NDXTMC':
            if archive:return archive,'Nasdaq via FRED',meta
            raise ValueError('NDXTMC官源与备源都未取得')
        recent=sources.yahoo('^NDX',expected);provider='Yahoo Finance'
    checks.append(_check(archive,recent,.05,['Nasdaq via FRED',provider]))
    conflict=any(c['result']=='conflict' for c in checks)
    meta.update(verification_status='conflict' if conflict else 'pending_official',source_url=f'https://finance.yahoo.com/quote/%5E{symbol}/' if provider=='Yahoo Finance' else f'https://quote.eastmoney.com/gb/zs{symbol}.html')
    joined={r['date']:{**r,'provider':'Nasdaq via FRED'} for r in archive or []}
    if not conflict:joined.update({r['date']:{**r,'provider':provider} for r in recent})
    return sorted(joined.values(),key=lambda r:r['date']) if joined else recent,provider,meta

def volatility(key,expected):
    result=_parallel({'official':lambda:sources.cboe(key,expected),'vendor':lambda:sources.yahoo('^'+key,expected)})
    official=result['official']['rows'];vendor=result['vendor']['rows']
    check=_check(official,vendor,.02,['Cboe','Yahoo Finance'])
    meta={'checks':[check],'publisher':'Cboe','source_url':f'https://cdn.cboe.com/api/global/us_indices/daily_prices/{key}_History.csv'}
    if official and official[-1]['date']==expected:
        meta['verification_status']=verification(check,expected)
        return official,'Cboe',meta
    if vendor:
        joined={r['date']:{**r,'provider':'Cboe'} for r in official or []}
        for r in vendor:
            if r['date'] not in joined:joined[r['date']]={**r,'provider':'Yahoo Finance'}
        meta.update(verification_status='conflict' if check['result']=='conflict' else 'pending_official',source_url=f'https://finance.yahoo.com/quote/%5E{key}/')
        return sorted(joined.values(),key=lambda r:r['date']),'Cboe / Yahoo Finance',meta
    if official:
        meta['verification_status']='official_aux_missing';return official,'Cboe',meta
    raise ValueError('Cboe与Yahoo均无有效波动率序列')

def yields(key,expected):
    result=_parallel({'official':lambda:sources.treasury(expected,key=='DFII10')[key],
                      'archive':lambda:sources.fred(key,expected)})
    official=result['official']['rows'];archive=result['archive']['rows']
    check=_check(official,archive,.010001,['US Treasury','Federal Reserve via FRED'])
    meta={'checks':[check],'publisher':'US Treasury','source_url':'https://home.treasury.gov/treasury-daily-interest-rate-xml-feed',
          'verification_status':verification(check,expected)}
    if official:
        joined={r['date']:{**r,'provider':'Federal Reserve via FRED'} for r in archive or []} if check['result']!='conflict' else {}
        joined.update({r['date']:{**r,'provider':'US Treasury'} for r in official})
        return sorted(joined.values(),key=lambda r:r['date']),'US Treasury / FRED',meta
    if archive:return archive,'Federal Reserve via FRED',{**meta,'source_url':f'https://fred.stlouisfed.org/series/{key}'}
    raise ValueError('财政部与FRED收益率均读取失败')
