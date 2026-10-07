from datetime import datetime, timezone
from app.valuation import parse_wsj_pe
from app.fund_products import parse_product, confirm_product
from app.fund_evidence import apply_rule, eligible, summarize
from app.analytics import pair_roc
import pytest

FOOT='Trailing 12 months Forward 12 months Birinyi operating earnings as-reported earnings'
def html_pe(date='10/02/26', header='Estimate^'):
    return f'''<p>Dow Jones Monday Oct 05 2026</p><table><thead><tr><th>P/E RATIO</th></tr>
    <tr><th></th><th>{date}†</th><th>Year ago†</th><th>{header}</th><th>{date}†</th><th>Year ago†</th></tr></thead>
    <tbody><tr><td>NASDAQ 100 Index</td><td>30.12</td><td>99.9</td><td>21.34</td><td>0.5</td><td>0.6</td></tr></tbody></table><p>{FOOT}</p>'''

def test_wsj_uses_index_table_date_and_not_last_year_column():
    row=parse_wsj_pe(html_pe(),'2026-10-05')
    assert row=={'date':'2026-10-02','ttm':30.12,'forward':21.34}
    with pytest.raises(ValueError): parse_wsj_pe(html_pe(header='Dividend'),'2026-10-05')
    with pytest.raises(ValueError): parse_wsj_pe(html_pe(date='10/09/26'),'2026-10-05')

def test_wsj_requires_provider_method_footnotes():
    with pytest.raises(ValueError): parse_wsj_pe(html_pe().replace(FOOT,''),'2026-10-05')

def test_product_not_offered_overrides_misleading_limited_directory():
    html='<title>测试(022525)</title><div class="staticItem">交易状态：限大额</div><div class="staticItem">该基金暂不开放购买</div>'
    product=parse_product(html,'022525')
    c=confirm_product({'status':'limited','daily_limit':1000},product)
    assert c['status']=='not_offered' and c['daily_limit'] is None

def rule(**kw):
    return dict(quota_scope='shared',quota_summary='份额共用额度',codes=['019441','019442'],methods=['普通申购','定期定额投资'],
        effective_date='2026-09-28',health={'verified':True,'checked_at':'2026-10-06T01:00:00+00:00'},
        notice_ids=['test'],official_url='https://example.test',limit_inclusive=False,
        conditions='',status='limited',direct_limit=100,distributor_limit=10,**kw)

def test_exclusive_ceiling_below_minimum_is_not_buyable_and_not_added():
    c=apply_rule({'channel':'天天基金','channel_verified':True,'status':'limited','daily_limit':10,'minimum':10,'currency':'CNY'},rule(),'019441')
    assert not eligible(c)
    assert c['status']=='minimum_conflict'
    c=apply_rule({'channel':'天天基金','channel_verified':True,'status':'limited','daily_limit':10,'minimum':1,'currency':'CNY'},rule(),'019441')
    assert eligible(c)
    fund={'shares':[{'code':'019441','channels':[c]},{'code':'019442','channels':[c]}]}
    summarize(fund)
    assert fund['verified_limits'][0]['value']==10  # two share rows still one shared ceiling
    lower=apply_rule({'channel':'天天基金','channel_verified':True,'status':'limited','daily_limit':5,'minimum':1,'currency':'CNY'},rule(),'019441')
    assert lower['limit_inclusive'] and not lower['announcement_limit_inclusive']

def test_suspension_removes_old_limit():
    r=rule();r['status']='suspended'
    c=apply_rule({'channel':'天天基金','status':'limited','daily_limit':100,'currency':'CNY'},r,'019441')
    assert c['status']=='suspended' and c['daily_limit'] is None

def test_new_notice_on_unwatched_shared_class_invalidates_whole_group(monkeypatch,tmp_path):
    import json
    from app import fund_evidence
    r=rule();r.update(name='shared',codes=['019525','022664'],scope_codes=['019524','019525','022664'])
    (tmp_path/'config').mkdir()
    (tmp_path/'config'/'fund_rules.json').write_text(json.dumps({'rules':[r]}),encoding='utf-8')
    monkeypatch.setattr(fund_evidence,'ROOT',tmp_path)
    monkeypatch.setattr(fund_evidence,'DATA',tmp_path)
    def health(rule,code):
        return {'verified':code!='019524','checked_at':'2026-10-06T01:00:00+00:00',
                'reason':'出现尚未核对的新业务公告' if code=='019524' else None,'new_notices':[]}
    monkeypatch.setattr(fund_evidence,'notice_health',health)
    rules,issues=fund_evidence.load_rules()
    assert len(issues)==1 and not rules['019525']['health']['verified']
    assert not rules['022664']['health']['verified']
    assert '019524' in rules['019525']['health']['share_checks']

def test_five_year_pair_history_keeps_warmup_and_all_dates():
    from datetime import timedelta,date
    left=[{'date':(date(2020,1,1)+timedelta(days=i)).isoformat(),'value':100+i} for i in range(1500)]
    right=[dict(r,value=200) for r in left]
    result=pair_roc(left,right)
    assert len(result['history'])==1465 and result['history'][0]['date']==left[35]['date']
