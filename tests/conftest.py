"""Only the four cache-dependent integration checks require a local snapshot.

Unit tests use constructed fixtures. Provider caches and personal data are never
committed; clean public checkouts skip the explicit local integration checks.
"""
import os
from pathlib import Path
import pytest

LOCAL_SNAPSHOT_TESTS = {
    'test_cache_expires_on_read',
    'test_snapshot_has_exact_code_coverage_and_nonzero_technical',
    'test_read_time_expiry_applies_to_every_instrument_technical',
    'test_expired_source_disables_score_and_does_not_fall_back_to_wsj',
}


def pytest_collection_modifyitems(items):
    home = Path(os.environ.get('NASDAQ_QDII_HOME', Path(__file__).resolve().parents[1]))
    if not (home / 'data' / 'latest.json').exists():
        mark = pytest.mark.skip(reason='Requires a locally collected private snapshot; excluded from public repository')
        for item in items:
            if item.name in LOCAL_SNAPSHOT_TESTS:
                item.add_marker(mark)
