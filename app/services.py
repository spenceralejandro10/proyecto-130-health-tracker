from __future__ import annotations

from datetime import datetime, time, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Activity, MetricRecord, Reminder, ReminderEvent, SleepRecord
from .timeutils import local_day_bounds_utc, utc_naive_to_local_date


WEIGHT_KEY = "weight_kg"


def _metric_values(db: Session, metric_key: str, since: datetime | None = None) -> list[MetricRecord]:
    stmt = select(MetricRecord).where(
        MetricRecord.metric_key == metric_key,
        MetricRecord.value.is_not(None),
        MetricRecord.validation_status != "discarded",
    )
    if since:
        stmt = stmt.where(MetricRecord.captured_at >= since)
    stmt = stmt.order_by(MetricRecord.captured_at.asc())
    return list(db.scalars(stmt).all())


def project_start(db: Session):
    if settings.project_start_date:
        return settings.project_start_date
    first = db.scalar(
        select(MetricRecord)
        .where(MetricRecord.metric_key == WEIGHT_KEY, MetricRecord.value.is_not(None))
        .order_by(MetricRecord.captured_at.asc())
        .limit(1)
    )
    return utc_naive_to_local_date(first.captured_at) if first else None


def weight_summary(db: Session) -> dict:
    values = _metric_values(db, WEIGHT_KEY)
    if not values:
        return {"current": None, "baseline": None, "change": None, "moving_avg_7d": None}
    latest = values[-1]
    baseline = values[0]
    since = latest.captured_at - timedelta(days=6)
    recent = [r.value for r in values if r.captured_at >= since and r.value is not None]
    return {
        "current": round(float(latest.value), 2),
        "baseline": round(float(baseline.value), 2),
        "change": round(float(latest.value - baseline.value), 2),
        "moving_avg_7d": round(float(mean(recent)), 2) if recent else None,
    }


def metric_trend(db: Session, metric_key: str, days: int) -> list[dict]:
    since = datetime.utcnow() - timedelta(days=days)
    return [
        {"captured_at": row.captured_at, "value": float(row.value)}
        for row in _metric_values(db, metric_key, since)
        if row.value is not None
    ]


def _today_bounds() -> tuple[datetime, datetime]:
    return local_day_bounds_utc(datetime.now(settings.timezone).date())


def activity_today(db: Session) -> dict:
    start, end = _today_bounds()
    rows = db.scalars(select(Activity).where(Activity.started_at >= start, Activity.started_at < end)).all()
    total = sum(float(r.duration_min) for r in rows)
    integrated = sum(float(r.duration_min) for r in rows if r.integrated)
    max_pain = max((r.pain_score or 0 for r in rows), default=0)
    return {"total": round(total, 1), "integrated": round(integrated, 1), "max_pain": max_pain}


def latest_sleep(db: Session) -> SleepRecord | None:
    return db.scalar(select(SleepRecord).order_by(SleepRecord.sleep_date.desc()).limit(1))


def next_reminder(db: Session) -> dict | None:
    reminders = db.scalars(select(Reminder).where(Reminder.active.is_(True))).all()
    if not reminders:
        return None
    now = datetime.now(settings.timezone)
    today = now.date()
    candidates = []
    for reminder in reminders:
        hour, minute = map(int, reminder.time_local.split(":"))
        due = datetime.combine(today, time(hour, minute), tzinfo=settings.timezone)
        if due < now:
            due += timedelta(days=1)
        candidates.append((due, reminder))
    due, reminder = min(candidates, key=lambda x: x[0])
    return {"id": reminder.id, "title": reminder.title, "kind": reminder.kind, "time_local": reminder.time_local, "due_at": due.isoformat()}


def due_reminders(db: Session, tolerance_minutes: int = 10) -> list[dict]:
    now = datetime.now(settings.timezone)
    reminders = db.scalars(select(Reminder).where(Reminder.active.is_(True))).all()
    result = []
    for reminder in reminders:
        hour, minute = map(int, reminder.time_local.split(":"))
        due = datetime.combine(now.date(), time(hour, minute), tzinfo=settings.timezone)
        if abs((now - due).total_seconds()) > tolerance_minutes * 60:
            continue
        today_start, _ = local_day_bounds_utc(now.date())
        already = db.scalar(
            select(ReminderEvent)
            .where(ReminderEvent.reminder_id == reminder.id, ReminderEvent.event_at >= today_start)
            .order_by(ReminderEvent.event_at.desc())
            .limit(1)
        )
        if already and already.action in {"done", "dismiss"}:
            continue
        if already and already.action == "snooze" and already.snoozed_until:
            if datetime.utcnow() < already.snoozed_until:
                continue
        result.append({"id": reminder.id, "title": reminder.title, "kind": reminder.kind})
    return result


def dashboard(db: Session) -> dict:
    start = project_start(db)
    today = datetime.now(settings.timezone).date()
    if start:
        elapsed = (today - start).days
        day_number = max(1, elapsed + 1)
        days_remaining = max(0, settings.project_length_days - day_number)
    else:
        day_number = None
        days_remaining = None

    weights = weight_summary(db)
    activity = activity_today(db)
    sleep = latest_sleep(db)
    sleep_hours = round(sleep.duration_min / 60, 1) if sleep and sleep.duration_min is not None else None

    alerts: list[str] = []
    if activity["max_pain"] >= 5:
        alerts.append("Hay dolor relevante registrado hoy; revisar recuperación antes de progresar carga.")
    if sleep_hours is not None and sleep_hours < 6:
        alerts.append("El sueño reciente fue corto; no escalar carga automáticamente.")
    if sleep and sleep.fatigue_score is not None and sleep.fatigue_score >= 8:
        alerts.append("Fatiga alta registrada; revisar recuperación antes de añadir volumen.")

    last_two = _metric_values(db, WEIGHT_KEY)[-2:]
    if len(last_two) == 2 and all(r.value is not None for r in last_two):
        delta = abs(float(last_two[-1].value - last_two[-2].value))
        hours = max((last_two[-1].captured_at - last_two[-2].captured_at).total_seconds() / 3600, 1)
        if hours <= 36 and delta >= 2:
            alerts.append("Cambio de peso atípico en corto plazo: verificar contexto y posible influencia de fluidos.")

    if not start:
        message = "Inicio pendiente: registra la primera medición matutina para abrir el Día 1."
        quality = "insufficient"
    elif alerts:
        message = "Hay señales que requieren revisión antes de ajustar el plan."
        quality = "attention"
    elif weights["current"] is None:
        message = "Datos insuficientes para interpretar la tendencia corporal."
        quality = "insufficient"
    else:
        message = "Estado actualizado. Usar tendencias y contexto; no reaccionar a una lectura aislada."
        quality = "ok"

    return {
        "project_started": start is not None,
        "day_number": day_number,
        "days_remaining": days_remaining,
        "current_weight_kg": weights["current"],
        "baseline_weight_kg": weights["baseline"],
        "change_from_baseline_kg": weights["change"],
        "moving_avg_7d_kg": weights["moving_avg_7d"],
        "goal_weight_kg": settings.goal_weight_kg,
        "activity_minutes_today": activity["total"],
        "integrated_minutes_today": activity["integrated"],
        "latest_sleep_hours": sleep_hours,
        "next_reminder": next_reminder(db),
        "operational_message": message,
        "alerts": alerts,
        "data_quality": quality,
    }
