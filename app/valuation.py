import csv
from datetime import datetime, date, timedelta, timezone
from .analytics import finite, percentile
from .settings import DATA, CONFIG
from .calendar import now_iso
from .storage import atomic_json
import re

WSJ_URL='https://www.wsj.com/market-data/stocks/peyields'

def parse_wsj_pe(html, expected):
    """Read the NDX table's own date, never the Dow Jones table or download date."""
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    text=soup.get_text(' ',strip=True)
    if not all(s in text.lower() for s in ('trailing 12 months','forward 12 months','operating earnings','as-reported earnings','birinyi')):
        raise ValueError('WSJ口径脚注缺失或变化')
    matches=[]
    for table in soup.find_all('table'):
        for tr in table.select('tbody tr'):
            cells=[c.get_text(' ',strip=True) for c in tr.find_all(['th','td'],recursive=False)]
            if cells and cells[0].upper()=='NASDAQ 100 INDEX':
                heads=table.select('thead tr')
                if len(heads)!=2 or len(cells)!=6:
                    raise ValueError('WSJ估值表结构变化')
                headers=[c.get_text(' ',strip=True) for c in heads[1].find_all(['th','td'],recursive=False)]
                if len(headers)!=6 or headers[2].lower().rstrip('†')!='year ago' or not headers[3].startswith('Estimate'):
                    raise ValueError('WSJ当前值/去年值/预测值列不符')
                match=re.fullmatch(r'(\d{2}/\d{2}/\d{2})†?',headers[1])
                if not match or headers[1]!=headers[4]:
                    raise ValueError('WSJ纳指表观察日期不可确认')
                day=datetime.strptime(match[1],'%m/%d/%y').date().isoformat()
                if day>expected:
                    raise ValueError('WSJ观察日期晚于最新完成交易日')
                values={kind:finite(cells[index].replace(',','')) for kind,index in (('ttm',1),('forward',3))}
                if any(v is None or v<=0 for v in values.values()):
                    raise ValueError('WSJ估值非有效正数')
                matches.append({'date':day,**values})
    if len(matches)!=1:
        raise ValueError('WSJ纳斯达克100唯一记录未找到')
    return matches[0]

def refresh_public_valuations(expected):
    from curl_cffi import requests
    issues=[]
    try:
        from .sources import fetch_curl
        r=fetch_curl(WSJ_URL)
        r.raise_for_status()
        observed=parse_wsj_pe(r.text,expected)
        known=now_iso()
        for kind in ('forward','ttm'):
            path=DATA/f'pe_wsj_{kind}.csv'
            records=[]
            if path.exists():
                with path.open(encoding='utf-8',newline='') as handle:
                    records=list(csv.DictReader(handle))
            record={'date':observed['date'],'value':observed[kind],'known_at':known,'source_url':WSJ_URL,
                    'instrument':'NDX','earnings_period':'NTM' if kind=='forward' else 'TTM',
                    'earnings_basis':'operating' if kind=='forward' else 'as-reported',
                    'loss_treatment':'not_disclosed','aggregation':'not_disclosed',
                    'method_id':f'WSJ-Birinyi-NDX-{kind}-v1','frequency':'weekly','payload_hash':r.audit_hash}
            changed=False
            if not records or records[-1]['date']!=record['date'] or finite(records[-1]['value'])!=record['value']:
                records.append(record)
                changed=True
            elif not records[-1].get('payload_hash'):
                # Attach newly acquired evidence without rewriting the original known_at.
                records[-1]['payload_hash']=record['payload_hash']
                changed=True
            if changed:
                temp=path.with_suffix('.tmp')
                with temp.open('w',encoding='utf-8',newline='') as handle:
                    writer=csv.DictWriter(handle,fieldnames=(*REQUIRED,'payload_hash'))
                    writer.writeheader(); writer.writerows(records)
                temp.replace(path)
    except Exception as exc:
        issues.append({'source':'WSJ / Birinyi','item':'PE采集','message':type(exc).__name__+'：本次读取失败，保留有日期的历史记录'})
    # Siblis is a separate provider/method. Free sparse month-ends cannot complete WSJ's history.
    try:
        url='https://siblisresearch.supabase.co/functions/v1/free-data-api/v1/NDX/pe-forward'
        r=fetch_curl(url); r.raise_for_status()
        j=r.json()
        if j.get('ticker')!='NDX' or j.get('ratio')!='pe-forward':
            raise ValueError('Siblis估值身份不符')
        rows=[{'date':p['trading_day (EOD)'],'value':finite(p['value'])} for p in j['data']]
        rows=sorted([p for p in rows if p['date']<=expected and p['value'] is not None],key=lambda p:p['date'])
        atomic_json(DATA/'pe_siblis_reference.json',{'provider':'Siblis Research','history':rows,'source_url':url,
            'checked_at':now_iso(),'score_ready':False,'reason':'免费历史稀疏，且与WSJ盈利口径不同，独立参照'})
    except Exception:
        issues.append({'source':'Siblis','item':'PE历史','message':'独立历史参照读取失败'})
    return issues

REQUIRED=('date','value','known_at','source_url','instrument','earnings_period','earnings_basis','loss_treatment','aggregation','method_id','frequency')

def load_valuation(kind, expected):
    path=DATA/f'pe_wsj_{kind}.csv'
    if not path.exists():
        path=DATA/f'pe_{kind}.csv'
    missing={'value':None,'date':None,'percentile':None,'score_ready':False,'status':'missing',
             'reason':'同口径前瞻PE及真实历史尚未取得' if kind=='forward' else 'TTM PE及同口径历史尚未取得',
             'history':[],'windows':{},'kind':kind,'samples':0}
    if not path.exists():
        return missing
    with path.open(encoding='utf-8-sig',newline='') as handle:
        reader=csv.DictReader(handle)
        if any(field not in (reader.fieldnames or []) for field in REQUIRED):
            return {**missing,'reason':'导入文件缺少估值口径或发布时间字段'}
        records=list(reader)
    rows=[]
    now=datetime.now(timezone.utc)
    for row in records:
        if any(not row.get(field) for field in REQUIRED):
            raise ValueError('估值记录存在空口径字段')
        value=finite(row['value'])
        known=datetime.fromisoformat(row['known_at'].replace('Z','+00:00'))
        if known.tzinfo is None:
            raise ValueError('known_at必须包含时区')
        date.fromisoformat(row['date'])
        if row['date']<=expected and known<=now and value is not None and value>0:
            rows.append({**row,'value':value})
    if not rows:
        return missing
    rows.sort(key=lambda r:(r['date'],r['known_at']))
    current=rows[-1]
    if current['instrument'] not in ('NDX','QQQ_PROXY'):
        raise ValueError('首版评分仅接受NDX或明确标注的QQQ_PROXY估值')
    if kind=='forward' and current['earnings_period'] not in ('NTM','FY0','FY1','FY2'):
        raise ValueError('前瞻盈利期间必须明确，不能以TTM替代')
    if kind=='ttm' and current['earnings_period']!='TTM':
        raise ValueError('TTM参照必须使用TTM盈利期间')
    # Never mix instruments, forecast periods or aggregation methods into a history.
    fields=('instrument','earnings_period','earnings_basis','loss_treatment','aggregation','method_id','frequency')
    rows=[r for r in rows if all(r[f]==current[f] for f in fields)]
    # Latest known revision of each real observation, not forward-filled daily observations.
    rows=sorted({r['date']:r for r in rows}.values(),key=lambda r:r['date'])
    frequency=current['frequency']
    max_age={'daily':7,'weekly':10,'monthly':45,'quarterly':120}.get(frequency)
    result={**missing,**current,'source':'WSJ / Birinyi','publisher':'WSJ / Birinyi','status':'available','kind':kind,'samples':len(rows),'history':rows,'windows':{}}
    today=date.fromisoformat(expected)
    from .valuation_views import window_stats
    for years in (1,3,5,10,20):
        result['windows'][str(years)]={**window_stats(result,years,expected),'algorithm':'midrank-ECDF'}
    result['percentile']=result['windows']['5']['percentile']
    expired=max_age is None or (today-date.fromisoformat(current['date'])).days>max_age
    result['score_ready']=not expired and result['percentile'] is not None
    result['status']='stale' if expired else 'available'
    result['reason']='估值过期或频率未定义' if expired else '近5年同口径真实样本不足' if result['percentile'] is None else None
    return result
