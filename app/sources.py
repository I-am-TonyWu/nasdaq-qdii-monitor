import csv
import io
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import quote, urlencode
import xml.etree.ElementTree as ET
import requests
from .analytics import finite
from .calendar import NY, now_iso
from .settings import CONFIG
from .source_audit import record_response,evidence

TIMEOUT=(8,CONFIG['source_timeout_seconds'])
HEADERS={'User-Agent':'Mozilla/5.0 (compatible; NasdaqLocalMonitor/0.1)', 'Accept':'application/json,text/csv,text/html,*/*'}

def fetch(url, params=None, referer=None):
    headers=dict(HEADERS)
    if referer:
        headers['Referer']=referer
    try:response=requests.get(url,params=params,headers=headers,timeout=TIMEOUT)
    except Exception as exc:
        evidence(url,None,status=0,error=type(exc).__name__)
        raise
    record_response(response)
    response.raise_for_status()
    return response

def fetch_curl(url,params=None):
    from curl_cffi import requests as curl_requests
    try:response=curl_requests.get(url,params=params,impersonate='chrome',timeout=CONFIG['source_timeout_seconds'])
    except Exception as exc:
        evidence(url,None,status=0,error=type(exc).__name__)
        raise
    record_response(response)
    response.raise_for_status()
    return response

def yahoo(symbol, expected, range_='5y', date_zone=NY):
    response=fetch(f'https://query1.finance.yahoo.com/v8/finance/chart/{quote(symbol,safe="")}',
                   {'range':range_,'interval':'1d','events':'splits'})
    payload=response.json()
    result=payload['chart']['result']
    if not result:
        raise ValueError('行情接口未返回序列')
    result=result[0]
    if result['meta']['symbol'].upper()!=symbol.upper():
        raise ValueError('提供商标的身份不符')
    rows=[]
    quotes=result['indicators']['quote'][0]
    for i,(ts,value) in enumerate(zip(result.get('timestamp',[]),quotes['close'])):
        day=datetime.fromtimestamp(ts, date_zone).date().isoformat()
        number=finite(value)
        if number is not None and day<=expected:
            row={'date':day,'value':number,'source_time':datetime.fromtimestamp(ts,timezone.utc).isoformat(),'payload_hash':response.audit_hash}
            high=finite(quotes.get('high',[None]*len(quotes['close']))[i])
            if high is not None and high>=number:
                row.update(high=high,high_source='Yahoo Finance',high_payload_hash=response.audit_hash)
            rows.append(row)
    if not rows:raise ValueError('Yahoo未返回已完成交易日历史')
    return sorted({r['date']:r for r in rows}.values(),key=lambda r:r['date'])

def cboe(symbol, expected):
    url=f'https://cdn.cboe.com/api/global/us_indices/daily_prices/{symbol}_History.csv'
    response=fetch(url);text=response.text
    rows=[]
    for row in csv.DictReader(io.StringIO(text)):
        day=datetime.strptime(row['DATE'],'%m/%d/%Y').date().isoformat()
        value=finite(row['CLOSE'])
        if value is not None and day<=expected:
            rows.append({'date':day,'value':value,'payload_hash':response.audit_hash})
    if not rows:
        raise ValueError('Cboe无有效收盘记录')
    return rows

def eastmoney(secid, code, expected):
    from curl_cffi.requests.exceptions import ConnectionError as CurlConnectionError, Timeout as CurlTimeout
    # Browser-compatible TLS transport for this public endpoint; bounded HTTP timeout.
    params={'secid':secid,'klt':101,'fqt':0,'lmt':1300,'end':'20500101',
            'fields1':'f1,f2,f3,f4,f5,f6','fields2':'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61'}
    url='https://push2his.eastmoney.com/api/qt/stock/kline/get?'+urlencode(params,safe=',')
    # This endpoint occasionally disconnects before returning any response.
    # Retry transport failures once; HTTP rejection, invalid identity and
    # malformed quotes still fail immediately and remain visible in the audit.
    try:response=fetch_curl(url)
    except (CurlConnectionError,CurlTimeout):response=fetch_curl(url)
    response.raise_for_status()
    payload=response.json()
    data=payload.get('data')
    if not data or data.get('code')!=code:
        raise ValueError('东方财富标的映射校验失败')
    rows=[]
    for kline in data.get('klines',[]):
        fields=kline.split(',')
        day=fields[0];value=finite(fields[2])
        datetime.strptime(day,'%Y-%m-%d')
        if day<=expected and value is not None:
            high=finite(fields[3])
            row={'date':day,'value':value,'payload_hash':response.audit_hash}
            if high is not None and high>=value:
                row.update(high=high,high_source='Eastmoney',high_payload_hash=response.audit_hash)
            rows.append(row)
    if not rows:
        raise ValueError('东方财富无已完成交易日历史')
    return rows

def fred(symbol, expected):
    start=(datetime.fromisoformat(expected)-timedelta(days=1850)).date().isoformat()
    from curl_cffi import requests as curl_requests
    response=fetch_curl('https://fred.stlouisfed.org/graph/fredgraph.csv',params={'id':symbol,'cosd':start})
    response.raise_for_status()
    rows=[]
    for row in csv.DictReader(io.StringIO(response.text)):
        day=row.get('observation_date') or row.get('DATE')
        value=finite(row.get(symbol))
        if day and day<=expected and value is not None:
            rows.append({'date':day,'value':value,'payload_hash':response.audit_hash})
    if not rows:
        raise ValueError('FRED未返回有效记录')
    return rows

def treasury(expected, real=False):
    kind='daily_treasury_real_yield_curve' if real else 'daily_treasury_yield_curve'
    # XML feed from the publishing agency, avoiding API-key dependencies.
    response=fetch('https://home.treasury.gov/resource-center/data-chart-center/interest-rates/pages/xml',
                   {'data':kind,'field_tdr_date_value':expected[:4]})
    root=ET.fromstring(response.content)
    result={'DFII10':[]} if real else {'DGS2':[],'DGS10':[]}
    for entry in root.iter():
        if entry.tag.split('}')[-1]!='properties':
            continue
        values={child.tag.split('}')[-1]:child.text for child in entry}
        day=(values.get('NEW_DATE') or '')[:10]
        if not day or day>expected:
            continue
        for key,field in ({'DFII10':'TC_10YEAR'} if real else {'DGS2':'BC_2YEAR','DGS10':'BC_10YEAR'}).items():
            value=finite(values.get(field))
            if value is not None:
                result[key].append({'date':day,'value':value,'payload_hash':response.audit_hash})
    if not any(result.values()):
        raise ValueError('美国财政部XML无有效收益率')
    return result

def cnn(expected):
    response=fetch('https://production.dataviz.cnn.io/index/fearandgreed/graphdata',referer='https://www.cnn.com/');payload=response.json()
    obj=payload['fear_and_greed']
    ts=datetime.fromisoformat(obj['timestamp'].replace('Z','+00:00'))
    day=ts.astimezone(NY).date().isoformat()
    value=finite(obj['score'])
    rows=[]
    # Historical daily labels are midnight UTC, not an intraday NY timestamp.
    for point in payload.get('fear_and_greed_historical',{}).get('data',[]):
        historical_day=datetime.fromtimestamp(float(point['x'])/1000,timezone.utc).date().isoformat()
        historical_value=finite(point.get('y'))
        if historical_day<=expected and historical_value is not None and 0<=historical_value<=100:
            rows.append({'date':historical_day,'value':historical_value,'payload_hash':response.audit_hash})
    if day<=expected and value is not None and 0<=value<=100:
        rows.append({'date':day,'value':value,'source_time':ts.isoformat(),'payload_hash':response.audit_hash})
    if not rows:
        raise ValueError('FGI没有已完成交易日的历史记录')
    return sorted({r['date']:r for r in rows}.values(),key=lambda r:r['date'])

def fund_nav(code):
    payload=fetch('https://api.fund.eastmoney.com/f10/lsjz',
                  {'fundCode':code,'pageIndex':1,'pageSize':1},'https://fundf10.eastmoney.com/').json()
    row=payload['Data']['LSJZList'][0]
    day=row['FSRQ']
    datetime.strptime(day,'%Y-%m-%d')
    return {'nav':finite(row['DWJZ']),'nav_date':day,'nav_source':f'https://fundf10.eastmoney.com/jjjz_{code}.html',
            'nav_checked_at':now_iso()}

def fund_profile(code):
    from bs4 import BeautifulSoup
    url=f'https://fundf10.eastmoney.com/jbgk_{code}.html'
    response=fetch(url)
    response.encoding='utf-8'
    soup=BeautifulSoup(response.text,'html.parser')
    fields={}
    for tr in soup.select('table.info tr'):
        cells=tr.find_all(['th','td'],recursive=False)
        for i in range(0,len(cells)-1,2):
            fields[cells[i].get_text(strip=True)]=cells[i+1].get_text(' ',strip=True)
    if not fields.get('基金全称'):
        raise ValueError('基金基本资料字段不可读')
    company=None
    for td in soup.find_all('td'):
        if td.get_text(' ',strip=True)==fields.get('基金管理人'):
            anchor=td.find('a',href=True)
            company=anchor['href'] if anchor else None
            break
    name=fields.get('基金简称') or fields['基金全称']
    fullname=fields['基金全称']
    currency='USD' if '美元' in name or '美元' in fullname else 'CNY' if '人民币' in name or '人民币' in fullname else '待核验'
    share_class_match=re.search(r'([A-Z])(?:类|人民币|美元|（|\(|$)',name)
    target='NDXTMC' if '纳斯达克科技市值加权' in fields.get('业绩比较基准','') or '纳斯达克100科技市值加权' in fields.get('业绩比较基准','') else 'NDX100' if '纳斯达克100' in fields.get('业绩比较基准','') else '待确认'
    # Keep ETF, feeder, LOF and non-index vehicles distinct. Exact legal full name groups only.
    legal_name=fullname
    for suffix in ('人民币A类','人民币C类','美元现汇A类','美元现汇C类','A类','C类'):
        if legal_name.endswith(suffix):
            legal_name=legal_name[:-len(suffix)].rstrip('（(')
            break
    kind='ETF联接' if '联接' in fullname else 'ETF' if 'ETF' in name or '交易型开放式' in fullname else 'LOF' if 'LOF' in fullname.upper() else '普通开放式'
    return {'code':code,'name':name,'full_name':fullname,'group_key':legal_name,
            'company':fields.get('基金管理人','待核验'),'company_url':company,
            'target':target,'benchmark':fields.get('业绩比较基准','待核验'),
            'kind':kind,'currency':currency,'share_class':share_class_match.group(1) if share_class_match else '待核验',
            'fees':{k:fields.get(k) for k in ('管理费率','托管费率','销售服务费率')},
            'inception':fields.get('成立日期/规模','待核验'),
            'profile_source':url,'profile_checked_at':now_iso(),
            'identity_status':'第三方资料映射，管理人合同待复核',
            'one_year_return':None,'return_reason':'尚未接入同口径分红再投资收益',
            'tracking_error':None,'tracking_reason':'尚未取得正式报告实际跟踪误差'}

def purchase_table():
    import subprocess
    import sys
    import tempfile
    import json
    from pathlib import Path
    # Upstream AKShare has no HTTP timeout here. Bound the entire child process.
    with tempfile.TemporaryDirectory() as directory:
        path=Path(directory)/'purchase.json'
        code="import akshare as ak,sys;ak.fund_purchase_em().to_json(sys.argv[1],orient='records',force_ascii=False)"
        subprocess.run([sys.executable,'-X','utf8','-c',code,str(path)],timeout=75,check=True,capture_output=True)
        records=json.loads(path.read_text(encoding='utf-8'))
    if not records or '基金代码' not in records[0]:
        raise ValueError('天天基金返回空表或字段变化')
    return {str(row['基金代码']).zfill(6):row for row in records}
