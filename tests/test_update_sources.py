"""Regression coverage for the morning quote/high acquisition fixes."""
from types import SimpleNamespace

import pytest
from curl_cffi.requests.exceptions import ConnectionError, HTTPError, Timeout

from app import sources
from app.authoritative import parse_nasdaq


def nasdaq_page(high_label='Day High', high='31,142.25', last='31,102.40'):
    return f'''<h4>NDX</h4><div>DATA AS OF 10/06/2026 31,102.40</div>
    <table><tr><td>Last</td><td>{last}</td></tr>
    <tr><td>{high_label}</td><td>{high}</td></tr></table>'''


@pytest.mark.parametrize('label', ['Day High', "Today's High"])
def test_nasdaq_current_and_legacy_high_labels_keep_the_dated_close(label):
    row = parse_nasdaq(nasdaq_page(label), 'NDX', '2026-10-06')
    assert row['date'] == '2026-10-06'
    assert row['value'] == pytest.approx(31102.40)
    assert row['high'] == pytest.approx(31142.25)
    assert row['high_source'] == 'Nasdaq'


def test_nasdaq_high_does_not_bypass_close_or_date_validation():
    with pytest.raises(ValueError, match='Last'):
        parse_nasdaq(nasdaq_page(last='31,000.00'), 'NDX', '2026-10-06')
    with pytest.raises(ValueError, match='日期'):
        parse_nasdaq(nasdaq_page(), 'NDX', '2026-10-07')
    row = parse_nasdaq(nasdaq_page(high='31,000.00'), 'NDX', '2026-10-06')
    assert 'high' not in row


def eastmoney_response(code='NDXTMC'):
    # Real API field order: date, open, close, high, low, volume, amount,
    # amplitude, percentage change, absolute change, turnover.
    payload = {'rc': 0, 'data': {'code': code, 'name': 'NASDAQ 100 Technology',
        'klines': [
            '2026-10-05,100,101,103,99,1000,100000,4,1,1,0',
            '2026-10-06,101,102,104,100,1200,120000,4,1,1,0',
            '2026-10-07,102,103,105,101,1400,140000,4,1,1,0',
        ]}}
    return SimpleNamespace(json=lambda: payload, raise_for_status=lambda: None,
                           audit_hash='http-payload-sha256')


@pytest.mark.parametrize('transport_error', [ConnectionError, Timeout])
def test_eastmoney_transport_retry_recovers_valid_quotes(monkeypatch, transport_error):
    urls = []

    def fetch(url):
        urls.append(url)
        if len(urls) == 1:
            raise transport_error('temporary network failure')
        return eastmoney_response()

    monkeypatch.setattr(sources, 'fetch_curl', fetch)
    rows = sources.eastmoney('251.NDXTMC', 'NDXTMC', '2026-10-06')
    assert len(urls) == 2 and urls[0] == urls[1]
    assert 'secid=251.NDXTMC' in urls[0]
    assert [r['date'] for r in rows] == ['2026-10-05', '2026-10-06']
    assert rows[-1]['value'] == 102 and rows[-1]['high'] == 104
    assert rows[-1]['high_source'] == 'Eastmoney'
    assert rows[-1]['high_payload_hash'] == 'http-payload-sha256'


@pytest.mark.parametrize('transport_error', [ConnectionError, Timeout])
def test_eastmoney_persistent_transport_failure_stops_after_two_requests(monkeypatch, transport_error):
    calls = []

    def fetch(url):
        calls.append(url)
        raise transport_error('still disconnected')

    monkeypatch.setattr(sources, 'fetch_curl', fetch)
    with pytest.raises(transport_error, match='still disconnected'):
        sources.eastmoney('251.NDXTMC', 'NDXTMC', '2026-10-06')
    assert len(calls) == 2


@pytest.mark.parametrize('error', [HTTPError('HTTP 403'), ValueError('invalid JSON')])
def test_eastmoney_non_transport_failure_is_not_retried(monkeypatch, error):
    calls = []

    def fetch(url):
        calls.append(url)
        raise error

    monkeypatch.setattr(sources, 'fetch_curl', fetch)
    with pytest.raises(type(error)):
        sources.eastmoney('251.NDXTMC', 'NDXTMC', '2026-10-06')
    assert len(calls) == 1


def test_eastmoney_identity_mismatch_is_not_retried(monkeypatch):
    calls = []

    def fetch(url):
        calls.append(url)
        return eastmoney_response(code='NDX100')

    monkeypatch.setattr(sources, 'fetch_curl', fetch)
    with pytest.raises(ValueError, match='映射'):
        sources.eastmoney('251.NDXTMC', 'NDXTMC', '2026-10-06')
    assert len(calls) == 1
