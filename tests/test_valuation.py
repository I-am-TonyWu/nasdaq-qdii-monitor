import csv
from app import valuation
from app.valuation import REQUIRED

def write_rows(tmp_path, kind, rows):
    with (tmp_path/f'pe_{kind}.csv').open('w',encoding='utf-8',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=REQUIRED)
        writer.writeheader();writer.writerows(rows)

def observation(day,value,**overrides):
    return {'date':day,'value':value,'known_at':day+'T20:00:00+00:00','source_url':'https://example.test/valuation',
            'instrument':'NDX','earnings_period':'NTM','earnings_basis':'GAAP','loss_treatment':'excluded',
            'aggregation':'harmonic weighted','method_id':'audit-fixture-v1','frequency':'monthly',**overrides}

def test_forward_never_accepts_ttm(tmp_path,monkeypatch):
    monkeypatch.setattr(valuation,'DATA',tmp_path)
    write_rows(tmp_path,'forward',[observation('2026-09-30',20,earnings_period='TTM')])
    import pytest
    with pytest.raises(ValueError,match='不能以TTM替代'):
        valuation.load_valuation('forward','2026-10-02')

def test_future_known_at_not_used_and_samples_not_filled(tmp_path,monkeypatch):
    monkeypatch.setattr(valuation,'DATA',tmp_path)
    write_rows(tmp_path,'forward',[observation('2026-08-31',20),observation('2026-09-30',10,known_at='2099-10-01T00:00:00+00:00')])
    result=valuation.load_valuation('forward','2026-10-02')
    assert result['value']==20
    assert result['samples']==1
    assert result['score_ready'] is False

def test_changed_method_does_not_mix_history(tmp_path,monkeypatch):
    monkeypatch.setattr(valuation,'DATA',tmp_path)
    write_rows(tmp_path,'forward',[observation('2026-08-31',20),observation('2026-09-30',10,method_id='audit-fixture-v2')])
    result=valuation.load_valuation('forward','2026-10-02')
    assert result['samples']==1
    assert result['percentile'] is None
