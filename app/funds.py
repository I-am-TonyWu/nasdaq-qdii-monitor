import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from .analytics import finite
from .calendar import now_iso
from .settings import DATA, WATCHLIST, CONFIG
from .sources import fund_profile, purchase_table, fund_nav
from .storage import atomic_json
from .fund_evidence import load_rules, apply_rule, direct_channel, summarize, manual_channels
from .fund_products import collect_products, confirm_product
from .fund_metrics import collect_metrics

def normalize_channel(code, row, checked_at, currency):
    raw=str(row.get('申购状态','未知')) if row else '未知'
    limit=finite(row.get('日累计限定金额')) if row else None
    # These values are third-party sentinels, never remaining capacity.
    sentinel=limit is not None and limit>=1e9
    state='suspended' if '暂停' in raw else 'limited' if '限' in raw else 'open' if '开放' in raw else 'unknown'
    if state=='limited' and (limit is None or limit<=0):
        limit=None
    return {'channel':'天天基金','method':'普通申购','status':state,'raw_status':raw,
            'minimum':finite(row.get('购买起点')) if row else None,
            'daily_limit':None if sentinel or state=='suspended' else limit,'single_limit':None,
            'limit_kind':'sentinel_no_known_limit' if sentinel else 'known' if limit is not None else 'unknown',
            'currency':currency,'fee_percent':finite(row.get('手续费')) if row else None,
            'checked_at':checked_at,'valid_until':(datetime.fromisoformat(checked_at)+timedelta(hours=CONFIG['channel_valid_hours'])).isoformat(),
            'effective_date':None,'evidence':f'https://fundf10.eastmoney.com/jjfl_{code}.html',
            'status_evidence':'https://fund.eastmoney.com/Fund_sgzt_bzdm.html',
            'conditions':'平台当前公开快照；跨渠道、A/C、定投合并累计规则待公告核对',
            'channel_verified':bool(row),'entry_url':f'https://fund.eastmoney.com/{code}.html',
            'reason':None if row else '该份额无当前可读渠道记录'}

def collect_funds(refresh_profiles=False):
    cache_path=DATA/'fund_profiles.json'
    profiles=json.loads(cache_path.read_text(encoding='utf-8')) if cache_path.exists() else {}
    issues=[]
    need=[code for code in WATCHLIST if code not in profiles or refresh_profiles]
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs={pool.submit(fund_profile,code):code for code in need}
        for job in as_completed(jobs):
            code=jobs[job]
            try:
                profiles[code]=job.result()
            except Exception as exc:
                issues.append({'source':'fund-profile','item':code,'message':type(exc).__name__+': 基金资料采集失败'})
    atomic_json(cache_path,profiles)
    navs={}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(fund_nav,code):code for code in WATCHLIST}
        for job in as_completed(jobs):
            code=jobs[job]
            try:
                navs[code]=job.result()
            except Exception:
                issues.append({'source':'fund-nav','item':code,'message':'完整净值归属日读取失败，未推断年份'})
    checked_at=now_iso()
    rules,rule_issues=load_rules()
    issues.extend(rule_issues)
    products,product_issues=collect_products(WATCHLIST)
    issues.extend(product_issues)
    metrics,metric_issues=collect_metrics(WATCHLIST,rules)
    issues.extend(metric_issues)
    try:
        table=purchase_table()
    except Exception as exc:
        table={}
        issues.append({'source':'Tiantian / AKShare','item':'fund-channels','message':type(exc).__name__+': 渠道状态采集失败'})
    groups={}
    for code in WATCHLIST:
        share=dict(profiles.get(code,{'code':code,'name':f'基金 {code}','group_key':code,'company':'待核验',
            'target':'待确认','currency':'待核验','share_class':'待核验','kind':'待核验',
            'profile_source':f'https://fundf10.eastmoney.com/jbgk_{code}.html','identity_status':'基本资料缺失','fees':{}}))
        row=table.get(code)
        if row and share['name']==f'基金 {code}':
            share['name']=str(row.get('基金简称',share['name']))
        share.update(navs.get(code,{'nav':finite(row.get('最新净值/万份收益')) if row else None,
                                   'nav_date':None,'nav_date_label':str(row.get('最新净值/万份收益-报告时间')) if row else None}))
        rule=rules[code]
        share['currency']=rule['currency']
        share['company_url']=rule['official_url']
        share['quota_summary']=rule['quota_summary']
        share.update(metrics.get(code,{}))
        base=normalize_channel(code,row,checked_at,share['currency'])
        share['channels']=[apply_rule(confirm_product(base,products.get(code)),rule,code),
                          apply_rule(confirm_product(base,products.get(code),dca=True),rule,code),
                          apply_rule(direct_channel(rule,checked_at),rule,code)]
        for channel in share['channels']:
            channel['channel_kind']='distributor' if channel['channel']=='天天基金' else 'direct'
        share['channels'].extend(manual_channels(code,rule))
        key=share['group_key']+'|'+share['kind']
        if key not in groups:
            groups[key]={'id':code,'name':share['group_key'],'company':share['company'],
                'target':share['target'],'kind':share['kind'],'identity_status':share['identity_status'],'shares':[]}
        groups[key]['shares'].append(share)
    funds=list(groups.values())
    for fund in funds:
        summarize(fund)
        fund['quota_summary']=fund['shares'][0]['quota_summary']
        fund['checked_at']=checked_at
    funds.sort(key=lambda f:(-bool(f['open_channels']),-f['has_sentinel'],-max((l['value'] for l in f['max_limits'] if l['currency']=='CNY'),default=0),f['name']))
    assert sorted(s['code'] for f in funds for s in f['shares'])==sorted(WATCHLIST)
    return funds,issues
