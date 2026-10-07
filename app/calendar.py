from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import exchange_calendars as xcals
import pandas as pd

CN = ZoneInfo('Asia/Shanghai')
NY = ZoneInfo('America/New_York')

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def market_context(now=None):
    now = now or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    cal = xcals.get_calendar('XNYS')
    local_date = now.astimezone(NY).date()
    sessions = cal.sessions_in_range(str(local_date - timedelta(days=14)), str(local_date))
    eligible = []
    for session in sessions:
        close = cal.session_close(session).to_pydatetime()
        # NDXTMC correction window: 17:15 ET; independent of early exchange close.
        final_at = datetime.combine(session.date(), datetime.min.time(), NY).replace(hour=17, minute=15)
        if final_at.astimezone(timezone.utc) <= now:
            eligible.append((session, close, final_at))
    session, close, final_at = eligible[-1]
    china_day = now.astimezone(CN).date()
    overnight = session.date() == china_day - timedelta(days=1)
    return {
        'expected_us_session': session.date().isoformat(),
        'exchange_close_beijing': close.astimezone(CN).isoformat(),
        'final_window_beijing': final_at.astimezone(CN).isoformat(),
        'beijing_date': china_day.isoformat(),
        'overnight_new_session': overnight,
        'session_note': '最近完成的美国交易日' if not overnight else '昨夜美国交易日',
        'calendar': 'XNYS / America-New_York; NDXTMC final window 17:15 ET',
    }
