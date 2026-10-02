"""Monitor findings are stamped in Pacific time; events are UTC.
Use real zone rules instead of a fixed +7h so data that crosses DST is right
(handoff E6). Identical to +7h for everything from April to October 2026."""
import datetime as dt
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
UTC = ZoneInfo("UTC")


def pt_to_utc(date_str, hh, mm, ss=0):
    """'2026-09-18', 16, 51 -> naive UTC datetime."""
    local = dt.datetime.strptime(date_str, "%Y-%m-%d").replace(hour=int(hh), minute=int(mm),
                                                               second=int(ss), tzinfo=PT)
    return local.astimezone(UTC).replace(tzinfo=None)
