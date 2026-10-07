"""Read-time expiry overlay: a frozen cache never remains fresh forever."""
from copy import deepcopy
from datetime import datetime, timezone, date
from .calendar import market_context
from .analytics import score,score_forward
from .fund_evidence import summarize

def for_display(snapshot, now=None):
    now=now or datetime.now(timezone.utc)
    out=deepcopy(snapshot)
    current=market_context(now)
    expected=current['expected_us_session']
    out['current_market']=current
    for item in out['series'].values():
        if item.get('status')=='fresh' and item.get('date')!=expected:
            item['status']='stale'
            item['score_ready']=False
            item['reason']='缓存早于最新完成交易日'
    for valuation in out['valuation'].values():
        if valuation.get('date'):
            age=(date.fromisoformat(expected)-date.fromisoformat(valuation['date'])).days
            maximum={'daily':7,'weekly':10,'monthly':45,'quarterly':120}.get(valuation.get('frequency'),0)
            if age>maximum:
                valuation.update(status='stale',score_ready=False,reason='估值记录已过期')
    for valuation in out.get('valuation_publisher',{}).values():
        if valuation.get('date') and valuation['date']!=expected:
            valuation.update(status='stale',score_ready=False,reason=valuation.get('reason') or '源站读数早于最近完成交易日')
    for fund in out['funds']:
        active=[]
        for share in fund['shares']:
            for channel in share['channels']:
                expiry=channel.get('valid_until')
                if expiry and datetime.fromisoformat(expiry)<now:
                    channel['original_status']=channel['status']
                    channel['status']='expired'
                    channel['reason']='渠道核验超过有效期，请查看原站'
                if channel['status'] in ('open','limited'):
                    active.append(channel)
        summarize(fund)
    out['funds'].sort(key=lambda f:(-bool(f['open_channels']),-f['has_sentinel'],-max((l['value'] for l in f['max_limits'] if l['currency']=='CNY'),default=0),f['name']))
    out['score']=score(score_forward(out),out['series'].get('VXN',{}),out['series'].get('FGI',{}))
    for key,t in out.get('technicals',{}).items():
        t['source_status']=out['series'].get(key,{}).get('status','missing')
    if 'NDX' in out.get('technicals',{}):out['technical']=out['technicals']['NDX']
    out['fresh_count']=sum(i['status']=='fresh' for i in out['series'].values())
    out['cache_status']='current' if snapshot['market']['expected_us_session']==expected else 'stale'
    from .quality import refresh_quality
    return refresh_quality(out,expected)
