"""Reviewed issuer rules + live notice monitoring; uncertainty never becomes capacity."""
import json, re, os
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from .settings import ROOT, DATA, CONFIG
from .calendar import now_iso
from .storage import atomic_json

def is_business_notice(title):
    return bool(re.search('申购|定投|定期定额|规模上限',title) and
                re.search('暂停|恢复|限制|调整|取消|上限',title) and
                not re.search('费率|优惠|增加|招募|募集|节假日|非交易日',title))

def notice_health(rule, code):
    from curl_cffi import requests
    r=requests.get('https://api.fund.eastmoney.com/f10/JJGG',
        params={'fundcode':code,'pageIndex':1,'pageSize':100,'type':0},
        headers={'Referer':f'https://fundf10.eastmoney.com/jjgg_{code}.html'},
        impersonate='chrome',timeout=CONFIG['source_timeout_seconds'])
    r.raise_for_status(); payload=r.json()
    from .source_audit import record_response
    record_response(r)
    if payload.get('ErrCode')!=0 or not payload.get('Data'):
        raise ValueError('公告列表为空或不可读')
    notices=[n for n in payload['Data'] if is_business_notice(n['TITLE'])]
    new=[n for n in notices if n['ID'] not in rule.get('reviewed_notice_ids',rule['notice_ids']) and
         n['PUBLISHDATEDesc']>=rule.get('reviewed_through','2026-10-06')]
    return {'checked_at':now_iso(),'verified':not new,'new_notices':new,
            'reason':'出现尚未核对的新业务公告' if new else None,
            'list_url':f'https://fundf10.eastmoney.com/jjgg_{code}.html',
            'latest_report':next((n for n in payload['Data'] if re.search(r'2026.*中期报告$',n['TITLE'])),None)}

def load_rules():
    rules=json.loads((ROOT/'config'/'fund_rules.json').read_text(encoding='utf-8'))['rules']
    health={}; issues=[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        jobs={pool.submit(notice_health,r,code):(r,code) for r in rules
              for code in r.get('scope_codes',r['codes'])}
        for f in as_completed(jobs):
            rule,code=jobs[f]
            try: result=f.result()
            except Exception as exc:
                result={'verified':False,'checked_at':None,'reason':'最新公告列表读取失败','new_notices':[]}
            group=health.setdefault(rule['name'],{'verified':True,'checked_at':now_iso(),
                'new_notices':[],'reason':None,'share_checks':{}})
            group['share_checks'][code]=result
            if not result['verified']:
                group['verified']=False
                group['reason']=result['reason']
                group['new_notices'].extend(result['new_notices'])
    for name,result in health.items():
        if not result['verified']:
            issues.append({'source':'管理人公告','item':name,'message':result['reason']})
    atomic_json(DATA/'fund_notice_health.json',health)
    return {code:{**r,**r.get('overrides',{}).get(code,{}),'health':health[r['name']]} for r in rules for code in r['codes']},issues

def apply_rule(channel, rule, code):
    """Preserve raw platform status, then apply issuer suspension and stricter ceiling."""
    channel=dict(channel)
    channel.update(quota_scope=rule['quota_scope'],quota_summary=rule['quota_summary'],
                   scope_codes=rule.get('scope_codes',rule['codes']),combined_methods=rule['methods'],
                   effective_date=rule['effective_date'],announcement_verified=rule['health']['verified'],
                   notice_checked_at=rule['health']['checked_at'],
                   notice_evidence=[f'https://pdf.dfcfw.com/pdf/H2_{i}_1.pdf' for i in rule['notice_ids']],
                   official_url=rule['official_url'],limit_inclusive=rule['limit_inclusive'],
                   announcement_limit_inclusive=rule['limit_inclusive'],scope_basis=rule.get('scope_basis','issuer_notice'),
                   conditions=rule['conditions'] or '每账户单日累计；申购与定投合并，实际受理按各销售机构规定。')
    is_direct=channel['channel']!='天天基金'
    cap=rule['direct_limit'] if is_direct else rule['distributor_limit']
    channel['announcement_limit']=cap
    if rule['status']=='suspended':
        channel['status']='suspended';channel['daily_limit']=None;channel['limit_kind']='suspended'
        channel['reason']='管理人公告暂停，旧申购上限已停用'
    elif channel['status'] in ('open','limited') and cap is not None:
        raw=channel.get('daily_limit')
        channel['platform_limit']=raw
        channel['daily_limit']=min(raw,cap) if raw is not None else cap
        channel['limit_kind']='known';channel['status']='limited'
        # A platform-specific lower ceiling has its own inclusive endpoint.
        if raw is not None and raw<cap: channel['limit_inclusive']=True
    if not rule['health']['verified']:
        channel['reason']=rule['health']['reason']+'；沿用公告仅作历史参考'
        channel['announcement_verified']=False
        if is_direct: channel['status']='unknown'
    if rule['quota_scope']=='unknown':
        channel['reason']=rule['conditions']
    cap=channel.get('daily_limit'); minimum=channel.get('minimum')
    if channel.get('channel_verified') and channel['status'] in ('open','limited') and cap is not None and minimum is not None:
        if minimum>cap or (minimum==cap and channel.get('limit_inclusive') is False):
            channel['status']='minimum_conflict'
            channel['reason']='该渠道起购金额达到或超过公告允许上限，当前没有可用申购区间'
    return channel

def direct_channel(rule, checked_at):
    status='suspended' if rule['status']=='suspended' and rule['health']['verified'] else 'unknown'
    return {'channel':rule['direct_channel'],'method':'普通申购 / 定投','status':status,
            'daily_limit':None,'minimum':None,'single_limit':None,'fee_percent':None,
            'currency':rule['currency'],'checked_at':rule['health']['checked_at'],
            'valid_until':(datetime.fromisoformat(checked_at)+timedelta(hours=CONFIG['channel_valid_hours'])).isoformat(),
            'evidence':rule['official_url'],'entry_url':rule['official_url'],
            'channel_verified':False,'reason':'已核对公告上限；直销具体入口、起购金额及当前受理状态未完成验证'}

def manual_channels(code,rule):
    home=Path(os.environ['NASDAQ_QDII_HOME']).expanduser().resolve() if os.environ.get('NASDAQ_QDII_HOME') else ROOT
    path=home/'config'/'manual_channels.json'
    if not path.exists():return []
    result=[]
    for claim in json.loads(path.read_text(encoding='utf-8'))['channels']:
        if claim['code']!=code:continue
        cap=rule['direct_limit'] if claim['channel_kind']=='direct' else rule['distributor_limit']
        result.append({**claim,'status':'limited','minimum':None,'single_limit':None,'fee_percent':None,
            'checked_at':claim['confirmed_at'],'channel_verified':True,'verification_basis':'user_confirmation',
            'announcement_verified':rule['health']['verified'],'notice_checked_at':rule['health']['checked_at'],
            'quota_scope':rule['quota_scope'],'quota_summary':rule['quota_summary'],
            'scope_codes':rule.get('scope_codes',rule['codes']),'scope_basis':rule.get('scope_basis','issuer_notice'),
            'combined_methods':rule['methods'],'announcement_limit':cap,'announcement_limit_inclusive':rule['limit_inclusive'],
            'limit_inclusive':True,'effective_date':claim['confirmed_at'][:10],
            'official_url':rule['official_url'],'entry_url':None,'evidence':rule['official_url'],
            'notice_evidence':[f'https://pdf.dfcfw.com/pdf/H2_{i}_1.pdf' for i in rule['notice_ids']],
            'conditions':'用户确认该渠道当前可购买；保留原确认时间，自动采集不延长人工确认有效期。',
            'reason':None,'limit_kind':'user_confirmed'})
    return result

def eligible(channel):
    cap=channel.get('daily_limit');minimum=channel.get('minimum')
    if channel.get('verification_basis')=='user_confirmation':
        expiry=channel.get('valid_until')
        return bool(channel.get('purchase_confirmed') and channel.get('announcement_verified') and channel.get('status') in ('open','limited') and cap and cap>0 and
                    expiry and datetime.fromisoformat(expiry)>datetime.now().astimezone())
    return bool(channel.get('status') in ('open','limited') and channel.get('channel_verified') and
                channel.get('announcement_verified') and channel.get('quota_scope') in ('per_share','shared') and
                channel.get('currency') in ('CNY','USD') and cap is not None and cap>0 and minimum is not None and
                (minimum<=cap if channel.get('limit_inclusive',True) else minimum<cap))

def summarize(fund):
    for share in fund['shares']:
        for channel in share['channels']:channel['purchasable']=eligible(channel)
    active=[c for s in fund['shares'] for c in s['channels'] if c['status'] in ('open','limited')]
    confirmed=[{'value':c['daily_limit'],'currency':c['currency'],'code':s['code'],'channel':c['channel'],
                'inclusive':c.get('limit_inclusive',True),'scope':c['quota_scope']}
               for s in fund['shares'] for c in s['channels'] if eligible(c)]
    fund['open_channels']=len(active)
    fund['open_shares']=sum(any(c['status'] in ('open','limited') for c in s['channels']) for s in fund['shares'])
    fund['verified_channels']=len(confirmed)
    fund['verified_shares']=sum(any(eligible(c) for c in s['channels']) for s in fund['shares'])
    fund['verified_limits']=[max([c for c in confirmed if c['currency']==cur],key=lambda c:c['value']) for cur in sorted({c['currency'] for c in confirmed})]
    limits=[{'value':c['daily_limit'],'currency':c['currency']} for c in active if c.get('daily_limit') is not None]
    fund['max_limits']=[max([c for c in limits if c['currency']==cur],key=lambda c:c['value']) for cur in sorted({c['currency'] for c in limits})]
    fund['has_sentinel']=any(c.get('limit_kind')=='sentinel_no_known_limit' for c in active)
    fund['availability_basis']='user_confirmation' if any(eligible(c) and c.get('verification_basis')=='user_confirmation' for s in fund['shares'] for c in s['channels']) else 'public_evidence'
