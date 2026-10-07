"""Published fund return and actual report tracking error, without target substitution."""
import json,re
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor,as_completed
from .analytics import finite
from .calendar import CN,now_iso
from .sources import fetch_curl
from .settings import DATA
from .storage import atomic_json

def parse_performance(text,code):
    identity=re.search(r'var\s+fS_code\s*=\s*[\"\'](\d+)',text)
    value=re.search(r'var\s+syl_1n\s*=\s*[\"\']([^\"\']*)',text)
    trend=re.search(r'var\s+Data_netWorthTrend\s*=\s*(\[.*?\])\s*;',text,re.S)
    if not identity or identity[1]!=code or not value or not trend:raise ValueError('收益标的/时间字段不符')
    rows=json.loads(trend[1])
    if not rows:raise ValueError('净值日期缺失')
    day=datetime.fromtimestamp(rows[-1]['x']/1000,CN).date().isoformat()
    return {'one_year_return':finite(value[1]),'return_date':day,
        'return_method':'天天基金公布的近一年区间收益；复权细节未披露',
        'return_source':f'https://fund.eastmoney.com/pingzhongdata/{code}.js','return_checked_at':now_iso()}

def actual_tracking_error(text):
    compact=re.sub(r'\s+','',text)
    for match in re.finditer(r'(?:年化跟踪误差|跟踪误差年化)(?:为|是|约|[:：])?(\d+(?:\.\d+)?)%',compact):
        context=compact[max(0,match.start()-100):match.end()+20]
        if re.search('报告期|本期',context) and not re.search('目标|力争|不超过|原则上|控制在|正常市场',context):
            return float(match[1])
    return None

def collect_metrics(codes,rules):
    path=DATA/'fund_metrics.json'
    cached=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
    result={};issues=[]
    def performance(code):
        return parse_performance(fetch_curl(f'https://fund.eastmoney.com/pingzhongdata/{code}.js').text,code)
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs={pool.submit(performance,c):c for c in codes}
        for f in as_completed(jobs):
            code=jobs[f]
            try:result[code]=f.result()
            except Exception:
                result[code]={**cached.get(code,{}),'return_fetch_status':'failed'}
                issues.append({'source':'基金收益','item':code,'message':'近一年收益读取失败，保留有日期记录'})
    # One underlying fund report may cover all its classes; never use its tracking target.
    reports={}
    for code in codes:
        checks=rules[code]['health'].get('share_checks',{})
        report=checks.get(code,{}).get('latest_report')
        if report:reports.setdefault(report['ID'],{'codes':[],'report':report})['codes'].append(code)
    def report_metric(ident):
        r=fetch_curl('https://np-cnotice-stock.eastmoney.com/api/content/ann',{'art_code':ident,'client_source':'web','page_index':1})
        text=r.json()['data']['notice_content']
        return actual_tracking_error(text)
    pending={ident:group for ident,group in reports.items() if any(cached.get(c,{}).get('tracking_report_id')!=ident for c in group['codes'])}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(report_metric,ident):ident for ident in pending}
        for f in as_completed(jobs):
            ident=jobs[f]
            try:value=f.result()
            except Exception:value=None
            for code in pending[ident]['codes']:
                result[code].update(tracking_error=value,tracking_report_id=ident,
                    tracking_date='2026-06-30',tracking_source=f'https://pdf.dfcfw.com/pdf/H2_{ident}_1.pdf',
                    tracking_reason='未取得报告期实际年化跟踪误差' if value is None else '管理人中期报告实际年化跟踪误差')
    for ident,group in reports.items():
        if ident not in pending:
            for code in group['codes']:
                result[code].update({k:v for k,v in cached.get(code,{}).items() if k.startswith('tracking_')})
    atomic_json(path,result)
    return result,issues
