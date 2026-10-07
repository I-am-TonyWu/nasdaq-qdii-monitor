import json
from datetime import date,datetime,timedelta,timezone
from app.analytics import rsi_wilder,pair_roc,percentile,score,technical
from app.calendar import market_context
from app.funds import normalize_channel
from app.settings import WATCHLIST
from app.presentation import for_display
from app.storage import latest

def test_watchlist_retains_original_and_adds_two_A_classes():
    assert len(WATCHLIST)==len(set(WATCHLIST))==44
    assert {'017093','017091','019524','019525','022664'}<=set(WATCHLIST)

def test_wilder_rsi_reference():
    values=[44.34,44.09,44.15,43.61,44.33,44.83,45.10,45.42,45.84,46.08,45.89,46.03,45.61,46.28,46.28]
    assert abs(rsi_wilder(values,14)-70.464135021097)<1e-8
    assert rsi_wilder([10]*25,14)==50
    assert rsi_wilder(list(range(30)),14)==100
    assert rsi_wilder(list(range(30,0,-1)),14)==0

def test_pair_uses_matching_days_and_exact_35_interval():
    left=[{'date':str(i).zfill(3),'value':100+i} for i in range(40)]
    right=[{'date':str(i).zfill(3),'value':100} for i in range(40) if i!=2]
    result=pair_roc(left,right)
    assert result['samples']==39
    assert abs(result['roc']['35']-100*(139/104-1))<1e-8
    assert result['date']=='039'

def test_missing_pe_or_fgi_cannot_score():
    ready={'value':20,'percentile':80,'score_ready':True,'date':'2026-10-02'}
    assert score({},ready,ready)['value'] is None
    assert score(ready,ready,{})['value'] is None
    assert score(ready,ready,{'value':10,'score_ready':True})['value']==52

def test_percentile_handles_ties():
    assert percentile([1,2,2,3],2)==50
    assert percentile([],2) is None

def test_calendar_dst_and_holiday():
    summer=market_context(datetime(2026,7,8,23,tzinfo=timezone.utc))
    winter=market_context(datetime(2026,1,8,23,tzinfo=timezone.utc))
    assert summer['final_window_beijing'][11:16]=='05:15'
    assert winter['final_window_beijing'][11:16]=='06:15'
    holiday=market_context(datetime(2026,9,8,0,tzinfo=timezone.utc))
    assert holiday['expected_us_session']=='2026-09-04'
    assert holiday['overnight_new_session'] is False

def test_early_close_still_waits_for_ndxtmc_revision_window():
    s=market_context(datetime(2026,11,27,20,tzinfo=timezone.utc))
    assert s['expected_us_session']=='2026-11-25'

def test_sentinel_not_a_real_amount():
    c=normalize_channel('017093',{'申购状态':'开放申购','日累计限定金额':1e11,'购买起点':10},'2026-10-06T00:00:00+00:00','CNY')
    assert c['daily_limit'] is None
    assert c['limit_kind']=='sentinel_no_known_limit'
    c=normalize_channel('017093',None,'2026-10-06T00:00:00+00:00','CNY')
    assert c['status']=='unknown'

def test_cache_expires_on_read():
    s=latest()
    assert s is not None
    displayed=for_display(s,datetime(2026,11,1,0,tzinfo=timezone.utc))
    assert displayed['fresh_count']==0
    assert displayed['score']['value'] is None
    assert all(c['status'] not in ('open','limited') for f in displayed['funds'] for share in f['shares'] for c in share['channels'])
    assert all(not f['max_limits'] for f in displayed['funds'])
    assert s['series']['NDX']['status']!='stale'

def test_snapshot_has_exact_code_coverage_and_nonzero_technical():
    s=latest()
    assert sorted(share['code'] for fund in s['funds'] for share in fund['shares'])==sorted(WATCHLIST)
    assert 0<=s['technical']['rsi']['14']<=100
    assert s['pairs']['VTV']['roc']['35'] is not None
