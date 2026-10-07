import json
from datetime import datetime,timezone
import pytest
from app.authoritative import parse_nasdaq,_check,verification
from app.valuation_views import complete_weeks,window_stats,rolling_percentiles,expected_dates
from app.fund_evidence import eligible
from app.fund_metrics import actual_tracking_error,parse_performance

def test_official_index_date_and_identity_are_required():
    html='<h4>NDX</h4><p>DATA AS OF 10/5/2026 31,076.44</p><table><tr><td>Last</td><td>31,076.44</td></tr></table>'
    assert parse_nasdaq(html,'NDX','2026-10-05')['value']==31076.44
    with pytest.raises(ValueError):parse_nasdaq(html,'NDXTMC','2026-10-05')
    with pytest.raises(ValueError):parse_nasdaq(html,'NDX','2026-10-02')

def test_same_date_conflict_and_missing_auxiliary_are_distinct():
    left=[{'date':'2026-10-05','value':20}]
    assert _check(left,[{'date':'2026-10-05','value':20.03}],.02,['Cboe','Yahoo'])['result']=='conflict'
    assert _check(left,[{'date':'2026-10-02','value':20}],.02,['Cboe','Yahoo'])['result']=='missing'

def test_historical_overlap_does_not_verify_new_day_when_auxiliary_lags():
    primary=[{'date':'2026-10-02','value':3.5},{'date':'2026-10-05','value':3.6}]
    auxiliary=primary[:1]
    check=_check(primary,auxiliary,.01,['Treasury','FRED'])
    assert check['result']=='passed' and check['through']=='2026-10-02'
    assert verification(check,'2026-10-05')=='official_aux_missing'

def test_incomplete_week_excluded_but_good_friday_week_includes_thursday():
    rows=[{'date':'2026-04-02','value':10},{'date':'2026-04-06','value':20}]
    assert complete_weeks(rows,'2026-04-02')==rows[:1]
    assert complete_weeks(rows,'2026-04-06')==rows[:1]
    assert '2026-04-03' in expected_dates('2026-03-30','2026-04-02','weekly')

def test_weekly_reference_is_independent_and_four_week_gap_disables_percentile():
    periods=expected_dates('2025-10-05','2026-10-05','weekly')
    rows=[{'date':p,'value':10+i} for i,p in enumerate(periods)]
    official={'history':rows,'frequency':'weekly'}
    reference={**official,'usage_scope':'reference_only'}
    assert window_stats(official,1,'2026-10-05')['percentile'] is None
    assert window_stats(reference,1,'2026-10-05')['percentile'] is not None
    broken={**reference,'history':rows[:20]+rows[24:]}
    assert window_stats(broken,1,'2026-10-05')['percentile'] is None

def test_rolling_percentile_does_not_use_future_observations():
    rows=[{'date':p,'value':i} for i,p in enumerate(expected_dates('2025-01-01','2026-10-05','weekly'))]
    prefix=rolling_percentiles(rows[:70],1,'weekly')
    full=rolling_percentiles(rows,1,'weekly')
    assert prefix==full[:70]

def test_summary_and_rolling_percentile_share_completed_week_boundary():
    periods=expected_dates('2024-01-01','2026-10-05','weekly')
    rows=[{'date':p,'value':i} for i,p in enumerate(periods)]
    item={'history':rows,'frequency':'weekly','usage_scope':'reference_only'}
    assert window_stats(item,1,'2026-10-05')['percentile']==rolling_percentiles(rows,1,'weekly')[-1]['value']

def test_four_missing_weeks_disable_rolling_even_when_coverage_exceeds_95_percent():
    periods=expected_dates('2010-01-01','2026-10-05','weekly')
    rows=[{'date':p,'value':i} for i,p in enumerate(periods) if not 400<=i<404]
    assert rolling_percentiles(rows,10,'weekly')[-1]['value'] is None

def test_user_confirmed_channel_overrides_platform_absence_but_expires():
    c={'verification_basis':'user_confirmation','purchase_confirmed':True,'announcement_verified':True,'status':'limited','daily_limit':200,'minimum':None,'valid_until':'2099-01-01T00:00:00+00:00'}
    assert eligible(c)
    assert not eligible({**c,'valid_until':'2020-01-01T00:00:00+00:00'})
    assert not eligible({**c,'announcement_verified':False})

def test_tracking_target_is_never_presented_as_actual_error():
    assert actual_tracking_error('本报告期内，本基金年化跟踪误差为1.23%。')==1.23
    assert actual_tracking_error('本报告期内，本基金目标年化跟踪误差不超过4%。') is None

def test_observation_dedup_and_reversions_preserve_revision_chain(tmp_path,monkeypatch):
    from app import storage
    from app.source_audit import store_observation
    monkeypatch.setattr(storage,'DB',tmp_path/'test.sqlite3')
    item={'source':'provider','method_id':'test-v1'}
    with storage.connect() as con:
        for i,value in enumerate([10,10,11,10]):
            store_observation(con,'NDX',{'date':'2026-10-05','value':value},item,f'2026-10-06T0{i}:00:00+00:00')
        rows=con.execute('SELECT * FROM series_observations ORDER BY rowid').fetchall()
        assert len(rows)==3 and [r['value'] for r in rows]==[10,11,10]
        assert rows[0]['first_seen_at'].startswith('2026-10-06T00')
        assert json.loads(rows[2]['payload'])['revision_of']==rows[1]['revision_id']

def test_formal_and_reference_ttm_both_persist_without_overwriting(tmp_path,monkeypatch):
    from app import storage
    monkeypatch.setattr(storage,'DB',tmp_path/'test.sqlite3')
    monkeypatch.setattr(storage,'DATA',tmp_path)
    formal={'source':'WSJ / Birinyi','method_id':'wsj-ttm','history':[{'date':'2026-10-02','value':34.68}]}
    reference={'source':'reference','method_id':'ref-ttm','history':[{'date':'2026-10-02','value':30.42}]}
    storage.persist({'generated_at':'2026-10-06T10:00:00+00:00','series':{},'valuation':{'ttm':formal},
        'valuation_references':{'ttm':reference},'funds':[],'issues':[],'market':{}})
    with storage.connect() as con:
        rows=con.execute("SELECT value,provider FROM series_observations WHERE series='valuation:ttm' ORDER BY value").fetchall()
        assert [r['value'] for r in rows]==[30.42,34.68]
        assert [r['provider'] for r in rows]==['reference','WSJ / Birinyi']
