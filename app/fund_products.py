"""Read actual Tiantian product controls, not just the purchase-status directory."""
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from .analytics import finite
from .calendar import now_iso
from .settings import CONFIG

def parse_product(html, code):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser')
    if not soup.title or f'({code})' not in soup.title.get_text():
        raise ValueError('渠道产品代码不符')
    state=next((n for n in soup.select('.staticItem') if '交易状态' in n.get_text()),None)
    if state is None: raise ValueError('渠道产品交易状态不可读')
    text=state.get_text(' ',strip=True)
    blocked=any('该基金暂不开放购买' in n.get_text() for n in soup.select('.staticItem'))
    status='not_offered' if blocked else 'suspended' if '暂停申购' in text else 'limited' if '限大额' in text else 'open' if '开放申购' in text else 'unknown'
    match=re.search(r'单日累计购买上限\s*([\d,.]+)\s*元',text)
    cap=finite(match[1].replace(',','')) if match else None
    money=soup.select_one('#moneyAmountTxt')
    minimum=finite(money.get('data-minsg')) if money else None
    dca=soup.select_one('a#FixedInvestment')
    dca_text=dca.get_text(' ',strip=True) if dca else ''
    dca_link=dca.get('href','') if dca else ''
    dca_min=re.search(r'([\d.]+)元起投',dca_text)
    dca_ok=bool(dca and f'fc={code}' in dca_link and not re.search('停止|暂停',dca_text) and status in ('open','limited'))
    return {'status':status,'raw_status':text,'daily_limit':cap,'minimum':minimum,
            'dca_offered':dca_ok,'dca_minimum':finite(dca_min[1]) if dca_min else None,
            'dca_entry':dca_link if dca_ok else None,'checked_at':now_iso(),
            'evidence':f'https://fund.eastmoney.com/{code}.html'}

def collect_products(codes):
    from curl_cffi import requests
    def get(code):
        r=requests.get(f'https://fund.eastmoney.com/{code}.html',impersonate='chrome',timeout=CONFIG['source_timeout_seconds'])
        from .source_audit import record_response
        record_response(r)
        r.raise_for_status();return parse_product(r.text,code)
    results={};issues=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs={pool.submit(get,c):c for c in codes}
        for f in as_completed(jobs):
            code=jobs[f]
            try: results[code]=f.result()
            except Exception:
                issues.append({'source':'天天产品页','item':code,'message':'实际购买入口读取失败，未认定有额度'})
    return results,issues

def confirm_product(channel, product, dca=False):
    c=dict(channel)
    if not product:
        c.update(channel_verified=False,reason='实际产品购买入口读取失败，不能仅凭总表确认可买')
        return c
    c.update(checked_at=product['checked_at'],status_evidence=product['evidence'],
             entry_url=product['dca_entry'] if dca else product['evidence'],
             channel_verified=True,raw_product_status=product['raw_status'])
    if dca:
        c.update(method='定期定额投资',minimum=product['dca_minimum'])
        if not product['dca_offered']:
            c.update(status='not_offered',daily_limit=None,reason='当前产品页没有可用定投入口')
    else:
        c.update(status=product['status'],minimum=product['minimum'])
    if product['daily_limit'] is not None:
        c['daily_limit']=product['daily_limit'];c['limit_kind']='known'
    if c['status'] in ('suspended','not_offered'):
        c['daily_limit']=None;c['limit_kind']=c['status']
    return c
