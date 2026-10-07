from concurrent.futures import ThreadPoolExecutor, as_completed
from copy import deepcopy
from datetime import date,timedelta,datetime,timezone,time
from zoneinfo import ZoneInfo
from . import sources
from .analytics import technical,pair_roc,changes,correlations,percentile,score
from .calendar import market_context,now_iso
from .funds import collect_funds
from .storage import latest,persist
from .source_audit import registry
from .settings import WATCHLIST
from .valuation_views import collect_references,window_stats
from .valuation import load_valuation, refresh_public_valuations

SPECS={
 'NDX':('纳斯达克100','^NDX','points','Yahoo Finance','https://finance.yahoo.com/quote/%5ENDX/','daily close; price index'),
 'NDXTMC':('纳斯达克100科技市值加权','NDXTMC','points','Eastmoney / FRED','https://quote.eastmoney.com/gb/zsNDXTMC.html','NDXTMC price index; provider daily close'),
 'QQQ':('Invesco QQQ','QQQ','USD','Yahoo Finance','https://finance.yahoo.com/quote/QQQ/','provider close; split adjusted; no dividend reinvestment'),
 'VTV':('价值股ETF VTV','VTV','USD','Yahoo Finance','https://finance.yahoo.com/quote/VTV/','provider close; split adjusted; no dividend reinvestment'),
 'CGDV':('主动ETF CGDV','CGDV','USD','Yahoo Finance','https://finance.yahoo.com/quote/CGDV/','provider close; no history before inception'),
 'KO':('可口可乐 KO','KO','USD','Yahoo Finance','https://finance.yahoo.com/quote/KO/','provider close; split adjusted; no dividend reinvestment'),
 'BRKA':('伯克希尔哈撒韦 A','BRK-A','USD','Yahoo Finance','https://finance.yahoo.com/quote/BRK-A/','Class A equity; provider close; no dividend reinvestment'),
 'RUT':('罗素2000指数','^RUT','points','Yahoo Finance','https://finance.yahoo.com/quote/%5ERUT/','Russell 2000 price index; provider daily close'),
 'VXN':('纳指波动率 VXN','VXN','points','Cboe','https://www.cboe.com/us/indices/dashboard/vxn/','Cboe daily CLOSE'),
 'VIX':('标普波动率 VIX','VIX','points','Cboe','https://www.cboe.com/tradable-products/vix/vix-historical-data','Cboe daily CLOSE'),
 'FGI':('CNN Fear & Greed','FGI','0-100','CNN','https://www.cnn.com/markets/fear-and-greed','CNN actual FGI; no proxy'),
 'GOLD':('黄金期货（现货代理）','GC=F','USD/oz','Yahoo Finance','https://finance.yahoo.com/quote/GC=F/','continuous front-month futures; roll affects changes; not spot'),
 'DGS2':('美债2年名义收益率','DGS2','%','FRED / US Treasury','https://fred.stlouisfed.org/series/DGS2','constant maturity yield'),
 'DGS10':('美债10年名义收益率','DGS10','%','FRED / US Treasury','https://fred.stlouisfed.org/series/DGS10','constant maturity yield'),
 'DFII10':('美债10年实际收益率','DFII10','%','FRED / US Treasury','https://fred.stlouisfed.org/series/DFII10','inflation-indexed constant maturity yield'),
}

def acquire(key,expected):
    from . import authoritative
    if key in ('NDX','NDXTMC'):return authoritative.index(key,expected)
    if key in ('VXN','VIX'):return authoritative.volatility(key,expected)
    if key in ('DGS2','DGS10','DFII10'):return authoritative.yields(key,expected)
    if key=='FGI':return sources.cnn(expected),'CNN',{'verification_status':'official_single_source','checks':[]}
    return sources.yahoo(SPECS[key][1],expected,range_='10y' if key in ('QQQ','VTV','CGDV','KO','BRKA','RUT') else '5y'),'Yahoo Finance',{'verification_status':'distributor_only','checks':[]}

def collect(refresh_profiles=False, funds_only=False, *, retry_keys=None,
            refresh_publisher=True, refresh_valuations=True):
    context=market_context();expected=context['expected_us_session'];source_registry=registry()
    previous=deepcopy(latest() or {})
    targeted=retry_keys is not None
    series=previous.get('series',{}) if targeted else {}
    issues=previous.get('issues',[]) if targeted else []
    started=now_iso()
    with ThreadPoolExecutor(max_workers=8) as pool:
        keys=retry_keys if targeted else SPECS
        jobs={pool.submit(acquire,key,expected):key for key in keys} if not funds_only else {}
        fund_job=None if targeted else pool.submit(collect_funds,refresh_profiles)
        for job in as_completed(jobs):
            key=jobs[job];name,symbol,unit,source,url,method=SPECS[key]
            error=None;meta={}
            try:
                rows,source,meta=job.result()
                if not rows:
                    raise ValueError('无有效观测')
                collected_at=now_iso()
            except Exception as exc:
                error=f'{type(exc).__name__}：当前采集失败'
                old=previous.get('series',{}).get(key,{})
                rows=old.get('history',[])
                collected_at=old.get('collected_at',started)
                source=old.get('source',source)
                # Cached values retain their verification state; a failed refresh cannot erase a conflict.
                meta=deepcopy(old)
            day=rows[-1]['date'] if rows else None
            if source=='US Treasury':
                url='https://home.treasury.gov/treasury-daily-interest-rate-xml-feed'
            elif source=='Eastmoney':
                url='https://quote.eastmoney.com/gb/zsNDX100.html' if key=='NDX' else 'https://quote.eastmoney.com/gb/zsNDXTMC.html'
            elif source=='Yahoo Finance' and key in ('VXN','VIX'):
                url=f'https://finance.yahoo.com/quote/%5E{key}/'
                method='Yahoo Cboe index daily close; 5y chart history; actual 3y ECDF for VXN'
            elif key=='NDXTMC' and source.startswith('Nasdaq via FRED'):
                url='https://fred.stlouisfed.org/series/NASDAQNDXTMC'
                method='NDXTMC daily price index; Nasdaq via FRED history; official Nasdaq latest quote checked separately'
            state='missing' if not rows else 'stale' if day!=expected or error else 'fresh'
            item={'key':key,'name':name,'symbol':symbol,'unit':unit,'source':source,'source_url':url,
                'method':method,**source_registry.get(key,{}),**meta,'provider':source,'status':state,'value':rows[-1]['value'] if rows else None,'date':day,
                'collected_at':collected_at,'source_time':rows[-1].get('source_time') if rows else None,
                'published_at':None,'finality':'提供商日线值，终值修正待连续观测' if key in ('NDX','NDXTMC','QQQ') else '日频已发布观测',
                'history':rows,'changes':changes(rows,key in ('DGS2','DGS10','DFII10')),'error':error,
                'usage_scope':'local_research','redistribution':'公开再展示许可待核验'}
            if meta.get('verification_status')=='conflict':
                item['changes']={str(n):None for n in (1,5,20)}
                issues.append({'source':source,'item':key,'message':'同口径信源存在未解释冲突，衍生计算停用'})
            if meta.get('verification_status')=='pending_official':
                issues.append({'source':source,'item':key,'message':'最新分发器值待官方新日核对'})
            if state!='fresh':
                issues.append({'source':source,'item':key,'message':error or ('没有有效数据' if not day else f'最新观察日 {day}，预期 {expected}')})
            series[key]=item
        if fund_job:
            funds,fund_issues=fund_job.result()
            issues.extend(fund_issues)
        else:
            funds=previous.get('funds',[])
    if funds_only:
        series={k:v for k,v in previous.get('series',{}).items() if k in SPECS}
        for key,item in series.items():
            if item.get('date')!=expected and item.get('status')=='fresh':
                item['status']='stale'
            if item['status']!='fresh':
                issues.append({'source':item['source'],'item':key,'message':'沿用缓存；详见实际观察日'})
    valuations=previous.get('valuation',{}) if not refresh_valuations else {}
    if refresh_valuations:
        issues=[i for i in issues if i.get('item') not in ('PE采集','PE历史','TTM / PB')]
        issues.extend(refresh_public_valuations(expected))
        for kind in ('forward','ttm'):
            try:
                valuations[kind]=load_valuation(kind,expected)
            except Exception as exc:
                valuations[kind]={'value':None,'date':None,'percentile':None,'score_ready':False,'status':'missing',
                                  'reason':type(exc).__name__+'：估值导入口径验证失败','history':[],'windows':{},'samples':0}
    vxn=series.get('VXN',{})
    if refresh_valuations:
        references,reference_issues=collect_references(expected)
        issues.extend(reference_issues)
    else:
        references=previous.get('valuation_references',{})
    from .dollar_valuation import collect_forward
    if refresh_publisher:
        publisher_forward,publisher_issues=collect_forward(expected)
        issues.extend(publisher_issues)
    else:
        publisher_forward=previous.get('valuation_publisher',{}).get('forward',{})
    cutoff=date.fromisoformat(expected)-timedelta(days=round(365.25*3))
    samples=[r for r in vxn.get('history',[]) if r['date']>=cutoff.isoformat()]
    vxn_window=window_stats(vxn,3,expected)
    enough=vxn_window['available']
    vxn['percentile']=vxn_window['percentile']
    vxn['percentile_samples']=len(samples);vxn['percentile_window']='3年';vxn['percentile_algorithm']='midrank-ECDF'
    vxn['score_ready']=enough and vxn.get('status')=='fresh' and vxn.get('verification_status') not in ('conflict','pending_official')
    vxn['reason']='VXN待官源核对或存在冲突' if vxn.get('verification_status') in ('conflict','pending_official') else 'VXN数据过期/采集失败' if vxn.get('status')!='fresh' else '近3年真实样本不足' if not enough else None
    fgi=series.get('FGI',{})
    fgi['score_ready']=fgi.get('status')=='fresh'
    fgi['reason']='FGI缺失、过期或采集失败' if not fgi['score_ready'] else None
    ndx=series.get('NDX',{});qqq=series.get('QQQ',{})
    technicals={}
    for key in ('NDX','NDXTMC','QQQ'):
        item=series.get(key,{})
        technicals[key]={**technical(item.get('history',[]) if item.get('verification_status')!='conflict' else []),
                         'instrument':key,'source_status':item.get('status')}
        if technicals[key].get('drawdown_reason'):
            issues.append({'source':item.get('high_history_provider',item.get('source','')),'item':key+' 52周回撤',
                           'message':technicals[key]['drawdown_reason']+'；不以最高收盘价代替盘中高点'})
    technical_state=technicals['NDX']
    pairs={key:pair_roc(series.get(key,{}).get('history',[]),qqq.get('history',[])) for key in ('VTV','CGDV','KO','BRKA','RUT')}
    for key,item in pairs.items():
        item['source_status']='fresh' if series.get(key,{}).get('status')=='fresh' and qqq.get('status')=='fresh' else 'stale'
    for key in ('GOLD','DGS2','DGS10','DFII10'):
        if key in series:
            series[key]['qqq_correlation']=correlations(series[key].get('history',[]) if series[key].get('verification_status')!='conflict' else [],qqq.get('history',[]),key in ('DGS2','DGS10','DFII10'))
    snapshot={'version':'0.4.3','generated_at':started,'market':context,'series':series,'valuation':valuations,'valuation_references':references,
              'valuation_publisher':{'forward':publisher_forward},
              'score_forward_dataset':'publisher',
              'technical':technical_state,'technicals':technicals,'pairs':pairs,'score':score(publisher_forward,vxn,fgi),'funds':funds,
              'watchlist_count':len(WATCHLIST),'issues':issues,'source_count':len(series),
              'fresh_count':sum(i.get('status')=='fresh' for i in series.values()),
              'collection':{'kind':'retry' if targeted else 'funds' if funds_only else 'collection',
                            'targets':list(keys) if targeted else ['funds'] if funds_only else list(SPECS)},
              'deployment':{'mode':'本机初版','public_ready':False,'mail_ready':False}}
    from .presentation import for_display
    return persist(for_display(snapshot))


def retry_delayed(now=None, force=False):
    """Recheck late providers and incomplete highs, without renewing fund evidence."""
    from .presentation import for_display
    now=now or datetime.now(timezone.utc)
    if not force and not time(7,15)<=now.astimezone(ZoneInfo('Asia/Shanghai')).time().replace(tzinfo=None)<=time(17,30):
        return {'status':'skipped','reason':'北京时间补采时段07:15–17:30之外','targets':[]}
    previous=latest()
    if not previous:
        return {'status':'skipped','reason':'初始快照尚未建立，请先完整采集','targets':[]}
    current=for_display(previous,now)
    targets=[]
    for key in SPECS:
        item=current.get('series',{}).get(key,{})
        if (item.get('status')!='fresh'
            or item.get('verification_status') in ('conflict','pending_official')
            or current.get('technicals',{}).get(key,{}).get('drawdown_reason')):
            targets.append(key)
    publisher=current.get('valuation_publisher',{}).get('forward',{})
    retry_publisher=not publisher.get('score_ready')
    retry_valuations=(any(i.get('status') in ('missing','stale') for i in current.get('valuation',{}).values())
                      or any(i.get('item') in ('PE采集','PE历史','TTM / PB') for i in current.get('update_issues',[])))
    all_targets=targets+(['Forward PE'] if retry_publisher else [])+(['估值参照'] if retry_valuations else [])
    if not all_targets:
        return {'status':'current','snapshot':previous['id'],'targets':[],
                'reason':'数据已完整，跳过网络采集','quality_counts':current['quality_counts']}
    snapshot=collect(retry_keys=targets,refresh_publisher=retry_publisher,refresh_valuations=retry_valuations)
    result={'status':'partial' if snapshot['update_issues'] else 'complete','snapshot':snapshot['id'],
            'targets':all_targets,'quality_counts':snapshot['quality_counts'],'score':snapshot['score']['value'],
            'session':snapshot['market']['expected_us_session']}
    return result

def refresh_forward_display():
    """Update only this source; preserve other instruments' acquisition times."""
    from .dollar_valuation import collect_forward,SOURCE
    snapshot=latest()
    if not snapshot:raise ValueError('请先采集初始快照')
    expected=market_context()['expected_us_session']
    item,issues=collect_forward(expected)
    snapshot.pop('id',None)
    snapshot.update(version='0.4.3',generated_at=now_iso(),valuation_publisher={'forward':item},score_forward_dataset='publisher')
    snapshot['issues']=[i for i in snapshot['issues'] if i.get('source')!=SOURCE]+issues
    from .presentation import for_display
    return persist(for_display(snapshot))
