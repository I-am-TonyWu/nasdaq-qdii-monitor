import json
from copy import deepcopy
import pytest
from app.dollar_valuation import parse_forward
from app.valuation_views import view,expected_dates

def page(props=None,percentile5y=18):
    props=props or {'seriesId':'ndx100-forward-pe','slug':'nasdaq-100-forward-pe',
        'recentPoints':[{'date':'2026-10-02','pe':21.74},{'date':'2026-10-04','pe':21.74},{'date':'2026-10-05','pe':21.85}],
        'historyPoints':[{'date':'2006-07-24','pe':20.33},'$ab:props:recentPoints:0','$ab:props:recentPoints:2'],
        'stats':{'latest':'$ab:props:recentPoints:2','lastDate':'2026-10-05','percentile5y':percentile5y,'count':5279}}
    flight='ab:'+json.dumps(['$','$L23',None,props])+'\n'
    return '<script>self.__next_f.push('+json.dumps([1,flight])+');</script>'

def test_json_reference_resolution_keeps_real_dates_and_separates_reported_count():
    item=parse_forward(page(),'2026-10-05')
    assert item['value']==21.85 and item['date']=='2026-10-05'
    assert [r['date'] for r in item['history']]==['2006-07-24','2026-10-02','2026-10-05']
    assert item['publisher_summary']['reported_samples']==5279
    assert item['publisher_summary']['downloaded_samples']==3
    assert item['publisher_summary']['omitted_non_session_points']==1
    assert item['score_ready'] and item['percentile']==18
    assert item['percentile_window']=='5年' and item['percentile_origin']=='publisher_reported'

def test_uncompleted_session_and_wrong_index_cannot_be_imported():
    with pytest.raises(ValueError):parse_forward(page(),'2026-10-02')
    with pytest.raises(ValueError):parse_forward(page().replace('ndx100-forward-pe','spx-forward-pe'),'2026-10-05')

def test_conflicting_duplicate_and_missing_json_reference_fail_closed():
    with pytest.raises(ValueError):parse_forward(page().replace('20.33','21.1').replace('2006-07-24','2026-10-05'),'2026-10-05')
    with pytest.raises((ValueError,KeyError)):parse_forward(page().replace('$ab:props:recentPoints:0','$cd:props:recentPoints:0'),'2026-10-05')

def test_sampled_old_history_cannot_make_five_year_percentile_or_override_official():
    rows=[{'date':d,'value':20+i/100} for i,d in enumerate(expected_dates('2023-10-05','2026-10-05','daily'))]
    official={'value':23.87,'history':[{'date':'2026-10-02','value':23.87}],'frequency':'weekly'}
    publisher={'value':rows[-1]['value'],'history':rows,'frequency':'daily','source':'Dollar Liquidity','publisher_summary':{'percentile_5y':18}}
    snapshot={'market':{'expected_us_session':'2026-10-05'},'series':{},'valuation':{'forward':official},'valuation_publisher':{'forward':publisher}}
    original=deepcopy(snapshot)
    one=view(snapshot,'forward','publisher',1);five=view(snapshot,'forward','publisher',5)
    assert one['stats']['percentile'] is not None
    assert five['stats']['percentile'] is None and all(r['value'] is None for r in five['percentile_history'])
    assert five['publisher_summary']['percentile_5y']==18
    assert view(snapshot,'forward','official',5)['value']==23.87
    assert snapshot==original

def test_score_uses_current_published_five_year_percentile_not_full_history_or_wsj():
    from app.analytics import score,score_forward
    item=parse_forward(page(),'2026-10-05')
    item['publisher_summary']['percentile_full']=66
    snapshot={'score_forward_dataset':'publisher','valuation_publisher':{'forward':item},
              'valuation':{'forward':{'percentile':90,'score_ready':True}}}
    result=score(score_forward(snapshot),{'percentile':57.24734042553192,'score_ready':True},
                 {'value':43.7142857142857,'score_ready':True})
    assert result['value']==pytest.approx(69.43134498480243)
    assert result['band']=='normal'
    assert result['components'][0]['percentile']==18
    assert result['components'][0]['raw_value']==21.85
    assert result['method_version']=='forward-publisher-5y-50-30-20-v2'

def test_missing_published_five_year_percentile_cannot_substitute_other_windows():
    item=parse_forward(page(percentile5y=None),'2026-10-05')
    assert item['percentile'] is None and not item['score_ready']
    assert item['reason']=='源站5年分位未发布'
    zero=parse_forward(page(percentile5y=0),'2026-10-05')
    assert zero['score_ready'] and zero['percentile']==0

def test_published_summary_is_displayed_only_for_its_own_window():
    item=parse_forward(page(),'2026-10-05');item['publisher_summary']['percentile_full']=66
    s={'market':{'expected_us_session':'2026-10-05'},'series':{},'valuation':{},'valuation_publisher':{'forward':item}}
    assert view(s,'forward','publisher',5)['reported_percentile']['value']==18
    assert view(s,'forward','publisher',0)['reported_percentile']['value']==66
    assert view(s,'forward','publisher',20)['reported_percentile'] is None
    assert '本站取得图表采样' in view(s,'forward','publisher',20)['reason']

def test_expired_source_disables_score_and_does_not_fall_back_to_wsj():
    from datetime import datetime,timezone
    from app.presentation import for_display
    from app.storage import latest
    s=latest();s['score_forward_dataset']='publisher'
    s['valuation_publisher']['forward']=parse_forward(page(),'2026-10-05')
    s['valuation']['forward'].update(score_ready=True,percentile=10)
    for key in ('VXN','FGI'):s['series'][key].update(date='2026-10-06',status='fresh',score_ready=True)
    displayed=for_display(s,datetime(2026,10,7,12,tzinfo=timezone.utc))
    assert displayed['score']['value'] is None
    assert displayed['valuation_publisher']['forward']['status']=='stale'
    assert displayed['score']['components'][0]['source'].startswith('Dollar Liquidity')
    assert s['valuation_publisher']['forward']['score_ready']

def test_failed_collection_marks_cached_source_stale_without_extending_date(tmp_path,monkeypatch):
    from app import dollar_valuation,sources
    cache=parse_forward(page(),'2026-10-05');cache['fetched_at']='2026-10-06T00:00:00+00:00'
    (tmp_path/'pe_dollarliquidity_forward.json').write_text(json.dumps(cache),encoding='utf-8')
    monkeypatch.setattr(dollar_valuation,'DATA',tmp_path)
    def fail(url):raise TimeoutError()
    monkeypatch.setattr(sources,'fetch_curl',fail)
    item,issues=dollar_valuation.collect_forward('2026-10-06')
    assert item['status']=='stale' and item['date']=='2026-10-05'
    assert item['fetched_at']==cache['fetched_at'] and not item['score_ready'] and issues
