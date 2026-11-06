"""Wall-clock schedules produce unique local-date slots across DST folds."""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from .security import clock_minutes


def due_slots(settings, previous, now):
    settings.require_schedule()
    zone = ZoneInfo(settings.timezone)
    previous = max(previous, now - 2 * 86400)
    first = datetime.fromtimestamp(previous, zone).date()
    last = datetime.fromtimestamp(now, zone).date()
    result = []
    day = first
    while day <= last:
        for clock in settings.briefs:
            h, m = map(int, clock.split(":"))
            local = datetime(day.year, day.month, day.day, h, m, tzinfo=zone, fold=0)
            stamp = local.timestamp()
            # A nonexistent wall time rolls forward across the gap; a repeated time uses fold=0 once.
            if previous < stamp <= now:
                result.append((stamp, f"{settings.timezone}:{day.isoformat()}:{clock}"))
        day += timedelta(days=1)
    return sorted(result)


def quiet(settings, now, category):
    if not settings.quiet_start or category in settings.quiet_bypass:
        return False
    local = datetime.fromtimestamp(now, ZoneInfo(settings.timezone))
    current = local.hour * 60 + local.minute
    start, end = clock_minutes(settings.quiet_start), clock_minutes(settings.quiet_end)
    return start <= current < end if start < end else (current >= start or current < end)
