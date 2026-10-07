"""Isolated valuation histories and calendar-checked daily/weekly display windows."""
import bisect,json,re
from collections import deque
from functools import lru_cache
from datetime import date,timedelta
import exchange_calendars as xcals
from .analytics import finite,percentile
from .calendar import now_iso
from .sources import fetch_curl
from .settings import DATA
from .storage import atomic_json

YEARS=(1,3,5,10,20)

def subtract_years(day,years):
    d=date.fromisoformat(day)
    try:return d.replace(year=d.year-years).isoformat()
    except ValueError:return d.replace(year=d.year-years,day=28).isoformat()

def week_ending(day):
    d=date.fromisoformat(day);return (d+timedelta(days=4-d.weekday())).isoformat()

@lru_cache(maxsize=1)
def sessions():
    cal=xcals.get_calendar('XNYS',start='1990-01-01',end='2030-12-31')
    return [s.date().isoformat() for s in cal.sessions]

def expected_dates(start,end,frequency):
    days=sessions();selected=days[bisect.bisect_left(days,start):bisect.bisect_right(days,end)]
    return sorted({week_ending(d) for d in selected if week_last_sessions().get(week_ending(d),week_ending(d))<=end}) if frequency=='weekly' else selected

@lru_cache(maxsize=1)
def week_last_sessions():
    result={}
    for day in sessions():result[week_ending(day)]=day
    return result

def complete_weeks(rows,expected):
    result={}
    for r in rows:
        if week_last_sessions().get(week_ending(r['date']),week_ending(r['date']))<=expected:
            result[week_ending(r['date'])]=r
    return sorted(result.values(),key=lambda r:r['date'])

def parse_guchacha(html,expected):
    from bs4 import BeautifulSoup
    soup=BeautifulSoup(html,'html.parser');node=soup.select_one('#__NUXT_DATA__')
    if not node:raise ValueError('参考历史数据节点缺失')
    nodes=json.loads(node.get_text());memo={}
    def resolve(i):
        if i<0:return None
        if i in memo:return memo[i]
        value=nodes[i]
        if isinstance(value,dict):
            result={};memo[i]=result;result.update({k:resolve(v) for k,v in value.items()});return result
        if isinstance(value,list):
            if value and isinstance(value[0],str) and value[0] in ('ShallowReactive','Reactive','Ref','ShallowRef'):
                result=resolve(value[1]);memo[i]=result;return result
            result=[];memo[i]=result;result.extend(resolve(v) for v in value);return result
        memo[i]=value;return value
    root=nodes[nodes[0][1]] if isinstance(nodes[0],list) else nodes[0]
    payloads=resolve(root['data']).values()
    candidates=[p for p in payloads if isinstance(p,dict) and p.get('index',{}).get('code')=='NDX' and p.get('series')]
    if len(candidates)!=1:raise ValueError('参考估值NDX唯一数据未找到')
    payload=candidates[0];result={}
    for kind,field in [('ttm','pe_ttm'),('pb','pb')]:
        rows=[]
        for p in payload['series'][field]:
            value=finite(p.get('v'));day=p.get('d');date.fromisoformat(day)
            if value is not None and value>0 and day<=expected:rows.append({'date':day,'value':value,'known_at':None,'provider':'股叉叉'})
        completed=complete_weeks(rows,expected)
        result[kind]={'instrument':'NDX','metric':field,'kind':kind,'history':completed,
            'value':completed[-1]['value'] if completed else None,'date':completed[-1]['date'] if completed else None,
            'latest_uncompleted':rows[-1] if rows and rows[-1] not in completed else None,
            'frequency':'weekly','source':'股叉叉周频参考','source_url':'https://guchacha.com/index-valuation/NDX',
            'method_id':f'guchacha-NDX-mcw-{field}-v1','earnings_basis':'index mcw; detailed method not_disclosed',
            'usage_scope':'reference_only','verification_status':'method_not_verified','score_ready':False,
            'reason':'周频参考；底层方法与自动同步用途待核验，不参与正式评分','fetched_at':now_iso(),'status':'reference'}
    return result

def collect_references(expected):
    path=DATA/'valuation_references.json';issues=[]
    if path.exists():
        cached=json.loads(path.read_text(encoding='utf-8'))
        if cached and all(i.get('payload_hash') and i.get('status')=='reference' and i.get('fetched_at','')[:10]==now_iso()[:10] for i in cached.values()):
            return cached,issues
    try:
        response=fetch_curl('https://guchacha.com/index-valuation/NDX')
        result=parse_guchacha(response.text,expected)
        for item in result.values():
            item['payload_hash']=response.audit_hash
            for row in item['history']:row['payload_hash']=response.audit_hash
        atomic_json(path,result)
    except Exception as exc:
        result=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        issues.append({'source':'估值参考','item':'TTM / PB','message':type(exc).__name__+'：周频参考读取失败'})
        for item in result.values():item['status']='stale'
    return result,issues

def window_stats(item,years,expected):
    rows=item.get('history',[]);frequency=item.get('frequency','daily')
    if frequency=='weekly':rows=complete_weeks(rows,expected)
    end=expected
    if frequency=='weekly':
        completed=[day for day in week_last_sessions().values() if day<=expected]
        end=max(completed,default=expected)
    start=subtract_years(end,years) if years else (rows[0]['date'] if rows else end)
    selected=[r for r in rows if start<=r['date']<=end]
    periods=expected_dates(start,end,frequency)
    observed={week_ending(r['date']) if frequency=='weekly' else r['date'] for r in selected}
    coverage=len(observed&set(periods))/len(periods) if periods else 0
    streak=gap=0
    for p in periods:
        streak=0 if p in observed else streak+1;gap=max(gap,streak)
    is_reference=item.get('usage_scope')=='reference_only'
    daily_required=bool(years and years<=5 and frequency!='daily' and not is_reference)
    valid=bool(selected) and len(selected)>=20 and coverage>=.95 and gap<(4 if frequency=='weekly' else 20) and not daily_required
    if item.get('verification_status')=='conflict':valid=False
    values=[r['value'] for r in selected];current=selected[-1]['value'] if selected else None
    return {'years':years,'start':start,'end':selected[-1]['date'] if selected else None,'samples':len(selected),
        'frequency':frequency,'coverage_ratio':coverage,'max_missing_periods':gap,'available':valid,
        'percentile':percentile(values,current) if valid else None,'minimum':min(values) if values else None,
        'maximum':max(values) if values else None,'change':(current/values[0]-1)*100 if len(values)>1 else None,
        'reason':'短周期正式日频历史不足' if daily_required else '历史覆盖或样本不足' if not valid else '周样本参考分位' if is_reference else None}

def rolling_percentiles(rows,years,frequency):
    ordered=[];left=0;result=[];days=[r['date'] for r in rows];gaps=deque()
    calendar_days=sessions();calendar_periods=sorted({week_ending(d) for d in calendar_days}) if frequency=='weekly' else calendar_days
    positions=[bisect.bisect_left(calendar_periods,week_ending(d) if frequency=='weekly' else d) for d in days]
    for index,row in enumerate(rows):
        cutoff=subtract_years(row['date'],years) if years else days[0]
        while left<index and days[left]<cutoff:
            ordered.pop(bisect.bisect_left(ordered,rows[left]['value']));left+=1
        bisect.insort(ordered,row['value'])
        if index:
            gap=positions[index]-positions[index-1]-1
            while gaps and gaps[-1][1]<=gap:gaps.pop()
            gaps.append((index,gap))
        while gaps and gaps[0][0]<=left:gaps.popleft()
        cutoff_position=bisect.bisect_left(calendar_periods,cutoff)
        wanted=positions[index]-cutoff_position+1
        max_gap=max(positions[left]-cutoff_position,gaps[0][1] if gaps else 0)
        enough=len(ordered)>=20 and (not years or wanted>0 and len(ordered)/wanted>=.95) and max_gap<(4 if frequency=='weekly' else 20)
        value=100*(bisect.bisect_left(ordered,row['value'])+.5*(bisect.bisect_right(ordered,row['value'])-bisect.bisect_left(ordered,row['value'])))/len(ordered) if enough else None
        result.append({'date':row['date'],'value':value})
    return result

def view(snapshot,metric,dataset,years):
    expected=snapshot.get('current_market',snapshot['market'])['expected_us_session']
    if metric in ('ttm','forward','pb'):
        if dataset=='publisher':item=snapshot.get('valuation_publisher',{}).get(metric,{})
        elif dataset=='reference':item=snapshot.get('valuation_references',{}).get(metric,{})
        else:item=snapshot['valuation'].get(metric,{})
    else:item=snapshot['series'].get(metric,{})
    if not item:item={'history':[],'frequency':'daily','status':'missing','reason':'该指标的此类历史尚未取得'}
    item=dict(item);rows=item.get('history',[])
    if item.get('frequency')=='weekly':rows=complete_weeks(rows,expected)
    windows={str(y):window_stats(item,y,expected) for y in YEARS}
    stats=window_stats(item,years,expected)
    cutoff=stats['start'];shown=[r for r in rows if r['date']>=cutoff]
    rolling=rolling_percentiles(rows,years,item.get('frequency','daily'))
    rolling=[r for r in rolling if r['date']>=cutoff]
    if not stats['available']:rolling=[{**r,'value':None} for r in rolling]
    published=item.get('publisher_summary') or {}
    reported_percentile=None
    if dataset=='publisher':
        if not stats['available']:
            stats['reason']='本站取得图表采样，未重算此区间分位'
        p=finite(published.get('percentile_5y' if years==5 else 'percentile_full')) if years in (0,5) else None
        if p is not None:
            reported_percentile={'value':p,'years':years,'date':item.get('date'),'origin':'publisher_reported'}
    return {'metric':metric,'dataset':dataset,'years':years,'source':item.get('source') or 'WSJ / Birinyi',
        'frequency':item.get('frequency','daily'),'reference':item.get('usage_scope')=='reference_only',
        'value':shown[-1]['value'] if shown else None,'date':shown[-1]['date'] if shown else None,
        'history':shown,'percentile_history':rolling,'stats':stats,'windows':windows,
        'reason':stats['reason'] or item.get('reason'),'status':item.get('status'),'source_url':item.get('source_url'),
        'publisher_summary':item.get('publisher_summary'),'fetched_at':item.get('fetched_at'),
        'reported_percentile':reported_percentile}

def archive_weekly(snapshot):
    expected=snapshot['market']['expected_us_session'];items={}
    for key,item in {**snapshot['series'],**{'valuation:'+k:v for k,v in snapshot.get('valuation_references',{}).items()}}.items():
        rows=complete_weeks(item.get('history',[]),expected)
        if rows:items[key]={'observations':[{**r,'week_ending':week_ending(r['date'])} for r in rows],
            'publisher':item.get('publisher'),'provider':item.get('source'),'method_id':item.get('method_id'),
            'usage_scope':item.get('usage_scope'),'frequency':'weekly_view'}
    week=max((r['week_ending'] for i in items.values() for r in i['observations']),default=None)
    if not week:raise ValueError('没有已完成交易周')
    folder=DATA/'weekly';folder.mkdir(exist_ok=True)
    path=folder/f'{week}-{snapshot["id"]}.json'
    if not path.exists():atomic_json(path,{'week_ending':week,'snapshot_id':snapshot['id'],'archived_at':now_iso(),'series':items})
    return path
