from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import APP_TIMEZONE

_TZ = ZoneInfo(APP_TIMEZONE)


def now_local() -> datetime:
    """Current time in the app's timezone, as a naive datetime.

    Kickoff times are stored naive (exactly as typed into the browser's
    datetime-local input, which is app-local wall-clock time), so "now" must
    be evaluated in the same zone and stripped of tzinfo to compare cleanly.
    """
    return datetime.now(_TZ).replace(tzinfo=None)
