from datetime import UTC, date, datetime, time

from .config import settings


def to_utc_naive(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=settings.timezone)
    return value.astimezone(UTC).replace(tzinfo=None)


def utc_naive_to_local_date(value: datetime) -> date:
    return value.replace(tzinfo=UTC).astimezone(settings.timezone).date()


def local_day_bounds_utc(day: date) -> tuple[datetime, datetime]:
    start = datetime.combine(day, time.min, tzinfo=settings.timezone).astimezone(UTC).replace(tzinfo=None)
    end = datetime.combine(day.fromordinal(day.toordinal() + 1), time.min, tzinfo=settings.timezone).astimezone(UTC).replace(tzinfo=None)
    return start, end
