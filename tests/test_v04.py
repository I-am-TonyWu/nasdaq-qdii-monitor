from datetime import date,timedelta,datetime,timezone
import pytest
import exchange_calendars as xcals
from app.analytics import technical,score
from app.authoritative import attach_highs
from app.pipeline import SPECS
from app.presentation import for_display
from app.storage import latest

def year_rows():
    end=date(2026,10,5)
    sessions=xcals.get_calendar('XNYS').sessions_in_range(str(end-timedelta(weeks=55)),str(end))
    return [{'date':s.date().isoformat(),'value':100,'high':110,'high_source':'test'} for s in sessions]

def test_drawdown_uses_intraday_high_even_when_latest_close_is_a_record():
    rows=year_rows();rows[-1].update(value=105,high=106)
    t=technical(rows)
    assert t['drawdown_52w']==pytest.approx((105/110-1)*100)
    assert t['high_52w']==110
    # A previous high outside the 52-week calendar window must not carry forward.
    rows[0]['high']=1000
    assert technical(rows)['high_52w']==110

def test_drawdown_is_unavailable_if_one_required_high_is_missing():
    rows=year_rows();del rows[-10]['high']
    t=technical(rows)
    assert t['drawdown_52w'] is None and t['drawdown_reason']

def test_a_true_intraday_high_close_can_still_have_zero_drawdown():
    rows=year_rows();rows[-1].update(value=110,high=110)
    assert technical(rows)['drawdown_52w']==0

def test_auxiliary_high_requires_matching_identity_date_and_close():
    official=[{'date':'2026-10-05','value':100},{'date':'2026-10-02','value':100}]
    aux=[{'date':'2026-10-05','value':99,'high':120},{'date':'2026-10-02','value':100.01,'high':110,'payload_hash':'abc'}]
    result=attach_highs(official,aux,'vendor')
    assert 'high' not in result[0]
    assert result[1]['high']==110 and result[1]['high_payload_hash']=='abc'
    assert all('high' not in r for r in official)

@pytest.mark.parametrize('value,band',[(0,'caution'),(29.99,'caution'),(30,'normal'),(69.99,'normal'),(70,'fear'),(100,'fear')])
def test_score_bands_without_changing_weights(value,band):
    forward={'score_ready':True,'percentile':100-value}
    vxn={'score_ready':True,'percentile':value}
    fgi={'score_ready':True,'value':100-value}
    result=score(forward,vxn,fgi)
    assert result['value']==pytest.approx(value) and result['band']==band
    assert score({},vxn,fgi)['band'] is None

def test_new_instruments_are_class_a_stock_and_small_cap_index():
    assert SPECS['BRKA'][1:3]==('BRK-A','USD')
    assert SPECS['RUT'][1:3]==('^RUT','points')

def test_read_time_expiry_applies_to_every_instrument_technical():
    s=latest();assert set(s['technicals'])=={'NDX','NDXTMC','QQQ'}
    displayed=for_display(s,datetime(2026,11,1,tzinfo=timezone.utc))
    assert all(t['source_status']=='stale' for t in displayed['technicals'].values())
    assert all(t['source_status']=='fresh' for t in s['technicals'].values())
