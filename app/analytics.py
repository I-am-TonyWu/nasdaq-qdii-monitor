"""Deterministic analytics; no missing-value substitution or weight renormalization."""
from datetime import date, timedelta
from math import isfinite, sqrt
from statistics import mean

METHOD = 'forward-only-50-30-20-v1'

def finite(value):
    try:
        return float(value) if isfinite(float(value)) else None
    except (TypeError, ValueError):
        return None

def percentile(values, current):
    values = [x for x in values if finite(x) is not None]
    if not values or current is None:
        return None
    # Mid-rank ECDF, including the current observation.
    return 100 * (sum(x < current for x in values) + .5 * sum(x == current for x in values)) / len(values)

def rsi_wilder(values, period):
    if len(values) < period + 1:
        return None
    diffs = [b-a for a, b in zip(values, values[1:])]
    gain = mean(max(d, 0) for d in diffs[:period])
    loss = mean(max(-d, 0) for d in diffs[:period])
    for change in diffs[period:]:
        gain = (gain*(period-1) + max(change, 0))/period
        loss = (loss*(period-1) + max(-change, 0))/period
    if loss == 0:
        return 50.0 if gain == 0 else 100.0
    return 100 - 100/(1+gain/loss)

def technical(rows):
    if not rows:
        return {'status': 'missing'}
    values = [r['value'] for r in rows]
    last = values[-1]
    cutoff=(date.fromisoformat(rows[-1]['date'])-timedelta(weeks=52)).isoformat()
    window=[r for r in rows if cutoff<=r['date']<=rows[-1]['date']]
    import exchange_calendars as xcals
    expected={s.date().isoformat() for s in xcals.get_calendar('XNYS').sessions_in_range(cutoff,rows[-1]['date'])}
    valid=[r for r in window if finite(r.get('high')) is not None and r['high']>=r['value']]
    complete=bool(expected) and expected<={r['date'] for r in valid}
    peak=max(valid,key=lambda r:r['high']) if complete else None
    return {
        'status': 'available', 'date': rows[-1]['date'],
        'rsi': {str(p): rsi_wilder(values, p) for p in (6,14,24)},
        'ma200_distance': (last / mean(values[-200:]) - 1)*100 if len(values) >= 200 else None,
        'drawdown_52w': (last/peak['high']-1)*100 if peak else None,
        'high_52w': peak['high'] if peak else None,'high_52w_date':peak['date'] if peak else None,
        'high_52w_source':peak.get('high_source') if peak else None,
        'drawdown_reason':None if peak else '近52周盘中高点历史未齐',
        'drawdown_method':'completed-session close / max daily HIGH over 52 calendar weeks - 1',
        'samples': len(values),
        'method': 'Wilder; first n changes SMA seed; flat=50; zero loss=100; daily close',
    }

def pair_roc(left, right, periods=(20,35,60)):
    rmap = {r['date']:r['value'] for r in right if r['value']>0}
    ratios = [{'date':r['date'],'value':r['value']/rmap[r['date']]} for r in left if r['date'] in rmap]
    series = []
    for i,row in enumerate(ratios):
        if i>=35:
            series.append({'date':row['date'],'value':100*(row['value']/ratios[i-35]['value']-1)})
    return {
        'status': 'available' if series else 'missing',
        'date': ratios[-1]['date'] if ratios else None,
        'ratio': ratios[-1]['value'] if ratios else None,
        'roc': {str(p):100*(ratios[-1]['value']/ratios[-p-1]['value']-1) if len(ratios)>p else None for p in periods},
        'history': series, 'samples':len(ratios),
        'method': 'same-date price ratio; ROC(35), daily, no smoothing, no dividend reinvestment; price-index points / ETF USD price for index pairs',
    }

def changes(rows, yield_series=False):
    if not rows:
        return {}
    values = [r['value'] for r in rows]
    return {str(n): (values[-1]-values[-n-1])*100 if yield_series and len(values)>n else (values[-1]/values[-n-1]-1)*100 if len(values)>n and values[-n-1] else None for n in (1,5,20)}

def correlations(left, right, yield_series=False):
    def returns(rows, levels=False):
        return {b['date']: (b['value']-a['value']) if levels else b['value']/a['value']-1
                for a,b in zip(rows, rows[1:]) if a['value'] != 0}
    lm,rm=returns(left, yield_series),returns(right)
    dates=sorted(lm.keys() & rm.keys())
    result={}
    for window in (60,120):
        if len(dates)<window:
            result[str(window)]=None
            continue
        x=[lm[d] for d in dates[-window:]]; y=[rm[d] for d in dates[-window:]]
        mx,my=mean(x),mean(y)
        denom=sqrt(sum((a-mx)**2 for a in x)*sum((b-my)**2 for b in y))
        result[str(window)]=sum((a-mx)*(b-my) for a,b in zip(x,y))/denom if denom else None
    return result

def score_forward(snapshot):
    """The selected source is explicit; unavailable publisher data cannot switch method."""
    if snapshot.get('score_forward_dataset')=='publisher':
        return snapshot.get('valuation_publisher',{}).get('forward',{'score_ready':False,'reason':'源站前瞻PE分位未取得'})
    return snapshot.get('valuation',{}).get('forward',{})

def score(forward, vxn, fgi):
    components=[]
    for key,name,weight,item,invert in (
        ('forward','前瞻PE',.5,forward,True),('vxn','VXN',.3,vxn,False),('fgi','CNN FGI',.2,fgi,True)):
        raw=item.get('percentile') if key!='fgi' else item.get('value')
        raw=finite(raw)
        ready=item.get('score_ready',False) and raw is not None and 0<=raw<=100
        points=100-raw if invert and ready else raw if ready else None
        components.append({'key':key,'name':name,'weight':weight,'raw_value':item.get('value'),
                           'percentile':item.get('percentile'),'date':item.get('date'),
                           'source':item.get('source'),'source_url':item.get('source_url'),
                           'percentile_window':item.get('percentile_window'),'percentile_origin':item.get('percentile_origin','local_computed'),
                           'points':points,'contribution':points*weight if ready else None,
                           'reason':None if ready else item.get('reason','数据缺失或过期')})
    reasons=[f"{c['name']}：{c['reason']}" for c in components if c['points'] is None]
    value=sum(c['contribution'] for c in components) if not reasons else None
    return {'value':value,'band':None if value is None else 'caution' if value<30 else 'fear' if value>=70 else 'normal',
            'status':'available' if not reasons else 'unavailable','reasons':reasons,
            'components':components,'method_version':'forward-publisher-5y-50-30-20-v2' if forward.get('percentile_origin')=='publisher_reported' else METHOD,
            'note':'初始规则，尚未回测；TTM、VIX、ROC、黄金、利率、汇率不计分'}
