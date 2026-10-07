import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path(os.environ.get('NASDAQ_QDII_HOME', str(ROOT))).expanduser().resolve()
DATA = HOME / 'data'
DATA.mkdir(parents=True, exist_ok=True)
CONFIG = {
    'port': 8765,
    'public_url': '',
    'worker_url': '',
    'worker_token_env': 'NASDAQ_MAIL_TOKEN',
    'source_timeout_seconds': 20,
    'channel_valid_hours': 24,
}
local = HOME / 'config.local.json'
if local.exists():
    CONFIG.update(json.loads(local.read_text(encoding='utf-8-sig')))

WATCHLIST = '''040046 014978 000834 008971 016452 016453 021000
022525 019524 019525 022664 019736 019737 019547 019548 019441 019442
012752 023422 539001 019172 019173 015299 015300 016055 016057
024237 016532 016533 021838 160213 018043 018044 270042 006479
021778 012870 161130 017091 017093 019118 018966 018967 021773'''.split()
