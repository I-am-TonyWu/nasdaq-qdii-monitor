"""Regression tests for targeted morning retries and read-time quality warnings."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from types import SimpleNamespace

import pytest
import exchange_calendars as xcals

from app import dollar_valuation, pipeline, presentation
from app import sources
from app.analytics import technical
from app.calendar import market_context

NOW = datetime(2026, 10, 7, 2, tzinfo=timezone.utc)  # 10:00 Beijing
DAY = '2026-10-06'
CHECKED_AT = '2026-10-07T00:00:00+00:00'


def snapshot(day=DAY):
    days = xcals.get_calendar('XNYS').sessions_in_range('2023-10-01', day)
    history = [{'date':d.date().isoformat(), 'value':100 + n / 10,
                'high':102 + n / 10, 'high_source':'test'} for n, d in enumerate(days)]
    series = {key:{'key':key, 'date':day, 'value':history[-1]['value'],
                   'status':'fresh', 'source':'test', 'frequency':'daily',
                   'verification_status':'verified_transmission',
                   'history':deepcopy(history), 'collected_at':CHECKED_AT,
                   'score_ready':True, 'percentile':50}
              for key in pipeline.SPECS}
    series['FGI']['value'] = 40
    # A public-evidence quota is intentionally left unchanged by market retries.
    fund = {'name':'测试基金', 'checked_at':CHECKED_AT, 'shares':[{
        'code':'000001', 'channels':[{'channel':'测试直销', 'currency':'CNY',
            'status':'limited', 'daily_limit':100, 'minimum':1,
            'quota_scope':'per_share', 'channel_verified':True,
            'announcement_verified':True, 'checked_at':CHECKED_AT,
            'valid_until':'2026-10-08T00:00:00+00:00'}]}]}
    valuations = {kind:{'source':'WSJ / Birinyi', 'date':'2026-10-02',
        'status':'available', 'frequency':'weekly', 'score_ready':False,
        'reason':'近5年同口径真实样本不足', 'history':[]}
        for kind in ('forward', 'ttm')}
    publisher = {'source':'Dollar Liquidity', 'value':21.85, 'date':day,
        'status':'available', 'score_ready':True, 'percentile':18,
        'percentile_origin':'publisher_reported', 'fetched_at':CHECKED_AT}
    return {'id':'0123456789abcdef0123', 'generated_at':CHECKED_AT,
        'market':{'expected_us_session':day}, 'series':series,
        'funds':[fund], 'valuation':valuations, 'valuation_references':{},
        'valuation_publisher':{'forward':publisher}, 'score_forward_dataset':'publisher',
        'technicals':{key:technical(series[key]['history']) for key in ('NDX','NDXTMC','QQQ')},
        'issues':[]}


def fail_io(*args, **kwargs):
    raise AssertionError('Unexpected upstream or persistence operation')


def collection_io(monkeypatch, previous, *, allow_funds=False, allow_valuations=False):
    """Replace source/storage IO while keeping calendar, analytics and quality real."""
    monkeypatch.setattr(pipeline, 'latest', lambda: previous)
    monkeypatch.setattr(pipeline, 'registry', lambda: {})
    monkeypatch.setattr(pipeline, 'market_context', lambda: market_context(NOW))
    monkeypatch.setattr(pipeline, 'now_iso', lambda: NOW.isoformat())
    monkeypatch.setattr(presentation, 'market_context', lambda now=None: market_context(NOW))
    monkeypatch.setattr(pipeline, 'persist', lambda result: dict(result, id='abcdef0123456789abcd'))
    monkeypatch.setattr(pipeline, 'acquire', fail_io)
    monkeypatch.setattr(pipeline, 'collect_funds',
        (lambda refresh: (deepcopy(previous['funds']), [])) if allow_funds else fail_io)
    monkeypatch.setattr(pipeline, 'refresh_public_valuations',
        (lambda expected: []) if allow_valuations else fail_io)
    monkeypatch.setattr(pipeline, 'load_valuation',
        (lambda kind, expected: deepcopy(previous['valuation'][kind])) if allow_valuations else fail_io)
    monkeypatch.setattr(pipeline, 'collect_references',
        (lambda expected: ({}, [])) if allow_valuations else fail_io)
    monkeypatch.setattr(dollar_valuation, 'collect_forward',
        (lambda expected: (deepcopy(previous['valuation_publisher']['forward']), []))
        if allow_valuations else fail_io)


@pytest.mark.parametrize('verification', ['pending_official', 'conflict'])
def test_funds_only_preserves_market_verification_warnings(monkeypatch, verification):
    previous = snapshot()
    previous['series']['VXN']['verification_status'] = verification
    original = deepcopy(previous)
    collection_io(monkeypatch, previous, allow_funds=True, allow_valuations=True)

    result = pipeline.collect(funds_only=True)

    warning = [i for i in result['update_issues'] if i['item']=='VXN']
    assert len(warning)==1 and warning[0]['kind']=='verification'
    assert result['series']['VXN']['verification_status']==verification
    assert result['score']['value'] is None
    assert result['series']['NDX']['collected_at']==CHECKED_AT
    assert result['series']['VXN']['collected_at']==CHECKED_AT
    assert previous==original


def test_read_time_session_advance_adds_stale_warnings_without_mutating_cache():
    cached = snapshot('2026-10-05')
    cached['issues'] = [{'source':'test','item':'NDX','message':'old warning'}]
    original = deepcopy(cached)

    result = presentation.for_display(cached, NOW)

    assert result['current_market']['expected_us_session']==DAY
    assert result['fresh_count']==0 and result['cache_status']=='stale'
    for key in pipeline.SPECS:
        warnings = [i for i in result['update_issues'] if i['item']==key]
        assert len(warnings)==1 and DAY in warnings[0]['message']
        assert result['series'][key]['status']=='stale'
    assert result['score']['value'] is None
    assert cached==original


def test_wsj_history_gaps_do_not_count_as_pending_updates_or_disable_publisher_score():
    result = presentation.for_display(snapshot(), NOW)

    assert result['quality_counts']=={'updates':0, 'history':2}
    assert result['update_issues']==[]
    assert {i['item'] for i in result['history_limitations']}=={'forward','ttm'}
    assert all(i['kind']=='history' for i in result['history_limitations'])
    assert result['score']['value']==pytest.approx(.5*82 + .3*50 + .2*60)


def test_complete_snapshot_retry_performs_no_io_and_renews_no_evidence(monkeypatch):
    previous = snapshot()
    original = deepcopy(previous)
    monkeypatch.setattr(pipeline, 'latest', lambda: previous)
    monkeypatch.setattr(pipeline, 'collect', fail_io)

    result = pipeline.retry_delayed(NOW)

    assert result['status']=='current' and result['targets']==[]
    assert result['snapshot']==previous['id']
    assert result['quality_counts']=={'updates':0, 'history':2}
    assert previous==original  # timestamps, quota expiry and original snapshot all stay intact


def test_retry_selects_only_unfinished_market_highs_and_publisher(monkeypatch):
    previous = snapshot()
    previous['series']['KO'].update(status='stale', date='2026-10-05')
    previous['series']['VXN']['verification_status']='pending_official'
    previous['technicals']['NDX']['drawdown_reason']='近52周盘中高点历史未齐'
    previous['valuation_publisher']['forward'].update(date='2026-10-05', score_ready=False)
    selected = []
    monkeypatch.setattr(pipeline, 'latest', lambda: previous)

    def collect(**kwargs):
        selected.append(kwargs)
        return {'id':'retry-snapshot', 'update_issues':[],
                'quality_counts':{'updates':0,'history':2},
                'score':{'value':69}, 'market':{'expected_us_session':DAY}}

    monkeypatch.setattr(pipeline, 'collect', collect)
    result = pipeline.retry_delayed(NOW)

    assert selected==[{'retry_keys':['NDX','KO','VXN'],
                      'refresh_publisher':True, 'refresh_valuations':False}]
    assert result['targets']==['NDX','KO','VXN','Forward PE']
    assert result['status']=='complete'


def test_targeted_collect_keeps_fund_expiry_and_unselected_acquisition_times(monkeypatch):
    previous = snapshot()
    previous['series']['KO'].update(status='stale', date='2026-10-05')
    previous['series']['NDX']['history'][-1].pop('high')
    original = deepcopy(previous)
    fresh_rows = deepcopy(previous['series']['QQQ']['history'])
    calls = []
    collection_io(monkeypatch, previous)

    def acquire(key, expected):
        calls.append((key,expected))
        assert key in ('NDX','KO')
        return deepcopy(fresh_rows), 'test', {'verification_status':'verified_transmission'}

    monkeypatch.setattr(pipeline, 'acquire', acquire)
    result = pipeline.collect(retry_keys=['NDX','KO'],
                              refresh_publisher=False, refresh_valuations=False)

    assert sorted(calls)==[('KO',DAY),('NDX',DAY)]
    assert result['technicals']['NDX']['drawdown_reason'] is None
    assert result['series']['KO']['date']==DAY and result['series']['KO']['status']=='fresh'
    assert result['series']['KO']['collected_at']==NOW.isoformat()
    assert result['series']['NDX']['collected_at']==NOW.isoformat()
    assert result['series']['QQQ']['collected_at']==CHECKED_AT
    assert result['series']['VXN']['collected_at']==CHECKED_AT
    assert result['valuation_publisher']['forward']['fetched_at']==CHECKED_AT
    assert result['funds'][0]['checked_at']==CHECKED_AT
    channel=result['funds'][0]['shares'][0]['channels'][0]
    assert channel['checked_at']==CHECKED_AT
    assert channel['valid_until']=='2026-10-08T00:00:00+00:00'
    assert previous==original


@pytest.mark.parametrize('beijing_hour', [7, 18])
def test_retry_outside_morning_window_skips_before_reading_or_collecting(monkeypatch, beijing_hour):
    from zoneinfo import ZoneInfo
    now=datetime(2026,10,7,beijing_hour,tzinfo=ZoneInfo('Asia/Shanghai'))
    monkeypatch.setattr(pipeline, 'latest', fail_io)
    monkeypatch.setattr(pipeline, 'collect', fail_io)

    result = pipeline.retry_delayed(now)

    assert result['status']=='skipped' and result['targets']==[]


def dollar_page(day='2026-10-05', pe=21.85, *, malformed=None):
    """Complete public Flight props, including JSON references and dated tails."""
    props = {'seriesId':'ndx100-forward-pe', 'slug':'nasdaq-100-forward-pe',
        'recentPoints':[{'date':'2026-09-30','pe':21.74},
                        {'date':'2026-10-04','pe':21.74}, {'date':day,'pe':pe}],
        'historyPoints':[{'date':'2006-07-24','pe':20.33},
                         '$ab:props:recentPoints:0', '$ab:props:recentPoints:2'],
        'stats':{'latest':'$ab:props:recentPoints:2', 'lastDate':day,
                 'percentile5y':17 if day==DAY else 18, 'count':5280}}
    if malformed=='identity':
        props['seriesId']='spx-forward-pe'
    elif malformed=='tail':
        props['stats']['latest']={'date':day,'pe':pe+.01}
    flight='ab:'+json.dumps(['$','$L23',None,props])+'\n'
    return '<script>self.__next_f.push('+json.dumps([1,flight])+');</script>'


def dollar_response(day='2026-10-05', pe=21.85, *, malformed=None, cache='HIT'):
    return SimpleNamespace(content=dollar_page(day,pe,malformed=malformed).encode(),
        url=dollar_valuation.URL, headers={'Age':'21600' if cache=='HIT' else '0',
                                        'CF-Cache-Status':cache},
        audit_hash='payload-'+day+('-'+malformed if malformed else ''))


def dollar_http(monkeypatch, tmp_path, responses):
    calls=[]

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return NOW.astimezone(tz) if tz else NOW.replace(tzinfo=None)

    def fetch(url, params=None):
        calls.append((url,deepcopy(params)))
        assert len(calls)<=len(responses), 'Public-page retry exceeded its request bound'
        response=responses[len(calls)-1]
        if isinstance(response,Exception):
            raise response
        return response

    monkeypatch.setattr(dollar_valuation,'DATA',tmp_path)
    monkeypatch.setattr(dollar_valuation,'datetime',FixedDateTime)
    monkeypatch.setattr(dollar_valuation,'now_iso',lambda:NOW.isoformat())
    monkeypatch.setattr(sources,'fetch_curl',fetch)
    return calls


def test_dollar_old_edge_cache_rechecks_public_page_and_accepts_valid_new_tail(monkeypatch,tmp_path):
    calls=dollar_http(monkeypatch,tmp_path,[dollar_response(),
        dollar_response(DAY,21.83,cache='MISS')])

    item,issues=dollar_valuation.collect_forward(DAY)

    assert calls==[(dollar_valuation.URL,None),
        (dollar_valuation.URL,{'asof':DAY,'refresh_slot':'2026100702-0'})]
    assert item['date']==DAY and item['value']==21.83
    assert item['percentile']==17 and item['score_ready'] and issues==[]
    assert item['history'][-1]['date']==DAY and item['history'][-1]['value']==21.83
    assert all(row['payload_hash']=='payload-'+DAY for row in item['history'])
    assert item['http_cache']['cache_status']=='MISS'
    stored=json.loads((tmp_path/'pe_dollarliquidity_forward.json').read_text(encoding='utf-8'))
    assert stored['date']==DAY and stored['payload_hash']=='payload-'+DAY


@pytest.mark.parametrize('fallback', ['still_old','failure','older'])
def test_dollar_edge_recheck_cannot_invent_current_date_or_regress_observation(monkeypatch,tmp_path,fallback):
    from curl_cffi.requests.exceptions import Timeout
    candidate={'still_old':dollar_response(), 'failure':Timeout('edge timed out'),
               'older':dollar_response('2026-10-02',21.74)}[fallback]
    calls=dollar_http(monkeypatch,tmp_path,[dollar_response(),candidate])

    item,issues=dollar_valuation.collect_forward(DAY)

    assert len(calls)==2
    assert item['date']=='2026-10-05' and item['value']==21.85
    assert item['status']=='stale' and not item['score_ready']
    assert len(issues)==1 and issues[0]['item']=='Forward PE直接采集'
    assert item['history'][-1]['date']=='2026-10-05'
    assert item['payload_hash']=='payload-2026-10-05'
    if fallback=='failure':
        assert item['refresh_error']=='Timeout'
    stored=json.loads((tmp_path/'pe_dollarliquidity_forward.json').read_text(encoding='utf-8'))
    assert stored['date']=='2026-10-05' and not stored['score_ready']


def test_dollar_current_public_page_uses_only_one_request(monkeypatch,tmp_path):
    calls=dollar_http(monkeypatch,tmp_path,[dollar_response(DAY,21.83)])

    item,issues=dollar_valuation.collect_forward(DAY)

    assert calls==[(dollar_valuation.URL,None)]
    assert item['score_ready'] and item['date']==DAY and issues==[]


@pytest.mark.parametrize('invalid', ['future','identity','tail'])
def test_dollar_cache_recheck_keeps_full_date_identity_and_tail_validation(monkeypatch,tmp_path,invalid):
    candidate=(dollar_response('2026-10-07',21.83) if invalid=='future'
               else dollar_response(DAY,21.83,malformed=invalid))
    calls=dollar_http(monkeypatch,tmp_path,[dollar_response(),candidate])

    item,issues=dollar_valuation.collect_forward(DAY)

    assert len(calls)==2 and item['refresh_error']=='ValueError'
    assert item['date']=='2026-10-05' and item['value']==21.85
    assert item['status']=='stale' and not item['score_ready'] and issues
    assert item['history'][-1]['date']=='2026-10-05'


def test_dollar_future_first_response_is_rejected_without_new_request_or_cache_overwrite(monkeypatch,tmp_path):
    cache=dollar_valuation.parse_forward(dollar_page(),'2026-10-05')
    cache['fetched_at']=CHECKED_AT
    cache_file=tmp_path/'pe_dollarliquidity_forward.json'
    cache_file.write_text(json.dumps(cache),encoding='utf-8')
    original=cache_file.read_bytes()
    calls=dollar_http(monkeypatch,tmp_path,[dollar_response('2026-10-07',21.83)])

    item,issues=dollar_valuation.collect_forward(DAY)

    assert calls==[(dollar_valuation.URL,None)]
    assert item['date']=='2026-10-05' and item['fetched_at']==CHECKED_AT
    assert item['status']=='stale' and not item['score_ready'] and issues
    assert cache_file.read_bytes()==original


def seed_current_dollar_cache(tmp_path):
    cached=dollar_valuation.parse_forward(dollar_page(DAY,21.83),DAY)
    cached.update(fetched_at=CHECKED_AT,payload_hash='previous-current-payload')
    for row in cached['history']:
        row.update(payload_hash='previous-current-payload',known_at=CHECKED_AT)
    path=tmp_path/'pe_dollarliquidity_forward.json'
    path.write_text(json.dumps(cached),encoding='utf-8')
    return cached,path


@pytest.mark.parametrize('fallback',
    ['still_old','failure','older','future','identity','tail','future_first'])
def test_dollar_old_upstream_cannot_overwrite_newer_local_cache(monkeypatch,tmp_path,fallback):
    from curl_cffi.requests.exceptions import Timeout
    cached,path=seed_current_dollar_cache(tmp_path)
    original=path.read_bytes()
    candidates={'still_old':dollar_response(), 'failure':Timeout('edge timed out'),
        'older':dollar_response('2026-10-02',21.74),
        'future':dollar_response('2026-10-07',21.84),
        'identity':dollar_response(DAY,21.84,malformed='identity'),
        'tail':dollar_response(DAY,21.84,malformed='tail')}
    responses=([dollar_response('2026-10-07',21.84)] if fallback=='future_first'
               else [dollar_response(),candidates[fallback]])
    calls=dollar_http(monkeypatch,tmp_path,responses)
    writes=[]
    monkeypatch.setattr(dollar_valuation,'atomic_json',lambda *args: writes.append(args))

    item,issues=dollar_valuation.collect_forward(DAY)

    assert len(calls)==(1 if fallback=='future_first' else 2)
    assert item['status']=='stale' and not item['score_ready'] and issues
    for key in ('date','value','history','payload_hash','fetched_at'):
        assert item[key]==cached[key]
    assert '保留' in item['reason']
    assert writes==[] and path.read_bytes()==original


def test_dollar_valid_current_retry_can_update_equal_date_cache(monkeypatch,tmp_path):
    cached,path=seed_current_dollar_cache(tmp_path)
    calls=dollar_http(monkeypatch,tmp_path,
        [dollar_response(),dollar_response(DAY,21.84,cache='MISS')])
    writes=[]
    real_atomic_json=dollar_valuation.atomic_json

    def record_write(*args):
        writes.append(args)
        return real_atomic_json(*args)

    monkeypatch.setattr(dollar_valuation,'atomic_json',record_write)
    item,issues=dollar_valuation.collect_forward(DAY)

    assert len(calls)==2 and len(writes)==1
    assert item['date']==cached['date']==DAY and item['value']==21.84
    assert item['score_ready'] and item['status']=='available' and issues==[]
    assert item['fetched_at']==NOW.isoformat() and item['payload_hash']=='payload-'+DAY
    stored=json.loads(path.read_text(encoding='utf-8'))
    assert stored['value']==21.84 and stored['history'][-1]['value']==21.84
    assert stored['payload_hash']==item['payload_hash']


def test_current_official_source_with_missing_optional_aux_does_not_trigger_retry(monkeypatch):
    previous=snapshot()
    for key in ('NDX','VXN'):
        previous['series'][key]['verification_status']='official_aux_missing'
    original=deepcopy(previous)
    monkeypatch.setattr(pipeline,'latest',lambda:previous)
    monkeypatch.setattr(pipeline,'collect',fail_io)

    result=pipeline.retry_delayed(NOW)

    assert result['status']=='current' and result['targets']==[]
    assert result['quality_counts']=={'updates':0,'history':2}
    assert previous==original
