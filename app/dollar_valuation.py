"""Parse the public page's JSON data for this local, attributed display."""
import json
import re
from datetime import date, datetime, timezone
from .analytics import finite
from .calendar import now_iso
from .settings import DATA
from .storage import atomic_json

URL='https://dollarliquidity.com/en/valuation/nasdaq-100-forward-pe'
SOURCE='Dollar Liquidity (dollarliquidity.com)'
METHOD='DollarLiquidity-NDX-blended-forward-12m-v1'

def parse_forward(html,expected):
    from bs4 import BeautifulSoup
    from .valuation_views import sessions
    # Next.js Flight supplies JSON and JSON references, never executable data.
    chunks=[]
    for tag in BeautifulSoup(html,'html.parser').find_all('script'):
        text=tag.get_text().strip()
        match=re.fullmatch(r'self\.__next_f\.push\((.*)\);?',text,re.S)
        if match:
            packet=json.loads(match[1])
            if isinstance(packet,list) and len(packet)==2 and packet[0]==1 and isinstance(packet[1],str):chunks.append(packet[1])
    records={}
    for line in ''.join(chunks).splitlines():
        match=re.match(r'^([0-9a-f]+):([\[{].*)$',line)
        if match:
            try:records[match[1]]=json.loads(match[2])
            except json.JSONDecodeError:continue
    candidates=[v[3] for v in records.values() if isinstance(v,list) and len(v)==4 and isinstance(v[3],dict)
                and v[3].get('seriesId')=='ndx100-forward-pe' and v[3].get('slug')=='nasdaq-100-forward-pe']
    if len(candidates)!=1:raise ValueError('Dollar Liquidity NDX前瞻PE唯一数据未找到')
    props=candidates[0]
    def resolve(value,seen=frozenset()):
        if not isinstance(value,str):return value
        if value in seen or len(seen)>32:raise ValueError('估值JSON引用循环')
        match=re.fullmatch(r'\$([0-9a-f]+):props:([A-Za-z0-9_:]+)',value)
        if not match:raise ValueError('估值JSON引用不符')
        root=records.get(match[1])
        if not isinstance(root,list) or len(root)!=4:raise ValueError('估值JSON引用根缺失')
        result=root[3]
        for key in match[2].split(':'):
            result=result[int(key)] if isinstance(result,list) else result[key]
        return resolve(result,seen|{value})
    def point(value):
        p=resolve(value)
        day=p['date'];date.fromisoformat(day)
        pe=finite(p.get('pe'))
        if pe is None or pe<=0:raise ValueError('Forward PE不是有效正数')
        return {'date':day,'value':pe}
    stats=props['stats'];latest=point(stats['latest'])
    if stats['lastDate']!=latest['date'] or latest['date']>expected:raise ValueError('原站读数日期不符或交易日尚未完成')
    rows={}
    for field in ('historyPoints','recentPoints'):
        for value in props[field]:
            p=point(value)
            if p['date']>expected:continue
            if p['date'] in rows and rows[p['date']]['value']!=p['value']:raise ValueError('原站同日估值存在冲突')
            rows[p['date']]=p
    if rows.get(latest['date'])!=latest:raise ValueError('原站摘要与历史尾值不一致')
    calendar=set(sessions())
    history=sorted([p for p in rows.values() if p['date'] in calendar],key=lambda p:p['date'])
    if not history or history[-1]!=latest:raise ValueError('原站最新值不是已完成美国交易日')
    p5=finite(stats.get('percentile5y'))
    if p5 is not None and not 0<=p5<=100:raise ValueError('原站分位范围不符')
    current=latest['date']==expected
    return {'instrument':'NDX','kind':'forward','metric':'forward','value':latest['value'],'date':latest['date'],
            'history':history,'frequency':'daily','source':SOURCE,'publisher':SOURCE,'source_url':URL,
            'method_id':METHOD,'earnings_period':'NTM','earnings_basis':'blended forward 12-month consensus estimates',
            'usage_scope':'local_display_only','redistribution':'display_only_not_redistributable',
            'license_url':'https://dollarliquidity.com/en/license','verification_status':'publisher_single_source',
            'percentile':p5,'percentile_window':'5年','percentile_origin':'publisher_reported',
            'percentile_algorithm':'publisher_published_statistic','percentile_date':latest['date'],
            'score_ready':current and p5 is not None,'status':'available' if current else 'stale',
            'reason':'源站尚未更新至最近完成交易日' if not current else '源站5年分位未发布' if p5 is None else None,
            'history_reason':'本站取得长历史图表采样；未取得全量历史日线，仅影响本站重算与历史分位曲线',
            'publisher_summary':{'percentile_5y':p5,'percentile_full':finite(stats.get('percentileFull')),
                'median_5y':finite(stats.get('median5y')),'minimum_5y':finite(stats.get('low5y')),
                'maximum_5y':finite(stats.get('high5y')),'reported_samples':stats.get('count'),
                'downloaded_samples':len(history),'omitted_non_session_points':len(rows)-len(history),
                'history_sample_points':len(props['historyPoints']),'recent_points':len(props['recentPoints'])}}

def collect_forward(expected):
    from .sources import fetch_curl
    path=DATA/'pe_dollarliquidity_forward.json'
    try:
        response=fetch_curl(URL)
        item=parse_forward(response.content.decode('utf-8'),expected)
        if item['date']<expected:
            # The public HTML is CDN-cached for six hours. A successful HTTP
            # response can therefore contain yesterday's complete JSON even
            # after the publisher has updated. Retry once with a bounded,
            # half-hour public cache key; the actual JSON date must still pass
            # all parsing/session checks. Never infer a date from this key.
            try:
                refresh_at=datetime.now(timezone.utc)
                refreshed=fetch_curl(URL,params={'asof':expected,
                    'refresh_slot':refresh_at.strftime('%Y%m%d%H')+'-'+str(refresh_at.minute//30)})
                candidate=parse_forward(refreshed.content.decode('utf-8'),expected)
                if candidate['date']>=item['date']:
                    response,item=refreshed,candidate
            except Exception as exc:
                item['refresh_error']=type(exc).__name__
        item['http_cache']={'request_url':str(response.url),
            'age_seconds':response.headers.get('Age'),
            'cache_status':response.headers.get('CF-Cache-Status')}
        cached=json.loads(path.read_text(encoding='utf-8')) if path.exists() else None
        if cached and cached.get('date','')>item['date']:
            # A valid but older CDN response must not replace a newer complete
            # local observation. Mark this attempt unverified without changing
            # the preserved payload's date, fetched_at, hash or historical rows.
            refresh_error=item.get('refresh_error')
            reason=f"上游返回旧缓存（{item['date']}），保留本地较新数据（{cached['date']}）；"
            reason+=f'补查失败：{refresh_error}' if refresh_error else '补查仍未取得较新数据'
            cached.update(status='stale',score_ready=False,reason=reason)
            if refresh_error:cached['refresh_error']=refresh_error
            return cached,[{'source':SOURCE,'item':'Forward PE直接采集','message':reason}]
        item.update(fetched_at=now_iso(),payload_hash=response.audit_hash)
        for row in item['history']:row.update(payload_hash=response.audit_hash,known_at=item['fetched_at'])
        atomic_json(path,item)
        return item,([] if item['status']=='available' else [{'source':SOURCE,'item':'Forward PE直接采集','message':item['reason']}])
    except Exception as exc:
        cached=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'history':[],'source':SOURCE,'source_url':URL}
        cached.update(status='stale' if cached['history'] else 'missing',score_ready=False,
                      reason=type(exc).__name__+'：本次源站抓取失败，保留原日期')
        return cached,[{'source':SOURCE,'item':'Forward PE直接采集','message':cached['reason']}]
