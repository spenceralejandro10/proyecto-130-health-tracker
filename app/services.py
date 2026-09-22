from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from statistics import mean

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .interpretation import interpret_body_composition
from .models import Activity, MetricRecord, Reminder, ReminderEvent, SleepRecord
from .timeutils import local_day_bounds_utc, utc_naive_to_local_date


WEIGHT_KEY = "weight_kg"


def _metric_values(db: Session, metric_key: str, since: datetime | None = None) -> list[MetricRecord]:
    stmt = select(MetricRecord).where(
        MetricRecord.metric_key == metric_key,
        MetricRecord.value.is_not(None),
        MetricRecord.validation_status.in_(["confirmed", "estimated"]),
    )
    if since:
        stmt = stmt.where(MetricRecord.captured_at >= since)
    stmt = stmt.where(MetricRecord.captured_at <= datetime.now(UTC).replace(tzinfo=None))
    stmt = stmt.order_by(MetricRecord.captured_at.asc())
    return list(db.scalars(stmt).all())


def project_start(db: Session):
    if settings.project_start_date:
        return settings.project_start_date
    first = db.scalar(
        select(MetricRecord)
        .where(MetricRecord.metric_key == WEIGHT_KEY, MetricRecord.value.is_not(None), MetricRecord.validation_status.in_(["confirmed", "estimated"]))
        .order_by(MetricRecord.captured_at.asc())
        .limit(1)
    )
    return utc_naive_to_local_date(first.captured_at) if first else None


def weight_summary(db: Session) -> dict:
    values = _metric_values(db, WEIGHT_KEY)
    if not values:
        return {"current": None, "baseline": None, "change": None, "moving_avg_7d": None}

    # Una lectura canónica por día local: si hubiera varias, usa la última.
    daily: dict = {}
    for row in values:
        daily[utc_naive_to_local_date(row.captured_at)] = row
    ordered = [daily[k] for k in sorted(daily)]
    latest = ordered[-1]
    baseline = ordered[0]
    latest_day = utc_naive_to_local_date(latest.captured_at)
    since_day = latest_day - timedelta(days=6)
    recent = [float(r.value) for r in ordered if utc_naive_to_local_date(r.captured_at) >= since_day and r.value is not None]
    return {
        "current": round(float(latest.value), 2),
        "baseline": round(float(baseline.value), 2),
        "change": round(float(latest.value - baseline.value), 2),
        "moving_avg_7d": round(float(mean(recent)), 2) if recent else None,
    }


def metric_trend(db: Session, metric_key: str, days: int) -> list[dict]:
    since = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=days)
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
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    today = now.date()
    today_start, _ = local_day_bounds_utc(today)
    candidates = []
    for reminder in reminders:
        latest_event = db.scalar(
            select(ReminderEvent)
            .where(ReminderEvent.reminder_id == reminder.id, ReminderEvent.event_at >= today_start)
            .order_by(ReminderEvent.event_at.desc())
            .limit(1)
        )
        if latest_event and latest_event.action == "snooze" and latest_event.snoozed_until:
            due_local = latest_event.snoozed_until.replace(tzinfo=UTC).astimezone(settings.timezone)
            candidates.append((due_local, reminder, "snoozed" if latest_event.snoozed_until > now_utc else "snooze_due"))
            continue

        hour, minute = map(int, reminder.time_local.split(":"))
        due = datetime.combine(today, time(hour, minute), tzinfo=settings.timezone)
        if latest_event and latest_event.action in {"done", "dismiss"}:
            due += timedelta(days=1)
        elif due < now:
            due += timedelta(days=1)
        candidates.append((due, reminder, "scheduled"))
    due, reminder, state = min(candidates, key=lambda x: x[0])
    return {"id": reminder.id, "title": reminder.title, "kind": reminder.kind, "time_local": due.strftime("%H:%M"), "due_at": due.isoformat(), "state": state}


def due_reminders(db: Session, tolerance_minutes: int = 10) -> list[dict]:
    now = datetime.now(settings.timezone)
    now_utc = datetime.now(UTC).replace(tzinfo=None)
    reminders = db.scalars(select(Reminder).where(Reminder.active.is_(True))).all()
    result = []
    today_start, _ = local_day_bounds_utc(now.date())
    for reminder in reminders:
        latest = db.scalar(
            select(ReminderEvent)
            .where(ReminderEvent.reminder_id == reminder.id, ReminderEvent.event_at >= today_start)
            .order_by(ReminderEvent.event_at.desc())
            .limit(1)
        )
        if latest and latest.action in {"done", "dismiss"}:
            continue
        if latest and latest.action == "snooze" and latest.snoozed_until:
            if now_utc < latest.snoozed_until:
                continue
            result.append({"id": reminder.id, "title": reminder.title, "kind": reminder.kind, "reason": "snooze_due"})
            continue

        hour, minute = map(int, reminder.time_local.split(":"))
        due = datetime.combine(now.date(), time(hour, minute), tzinfo=settings.timezone)
        if abs((now - due).total_seconds()) <= tolerance_minutes * 60:
            result.append({"id": reminder.id, "title": reminder.title, "kind": reminder.kind, "reason": "scheduled_due"})
    return result


def composition_summary(db: Session) -> dict:
    keys = ["body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index", "bone_mass_kg"]
    out = {}
    for key in keys:
        rows = _metric_values(db, key)
        if not rows:
            out[key] = {"value": None, "unit": None, "origin": None, "validation_status": "unavailable", "captured_at": None, "personal_trend": "insufficient", "reference_status": "not_configured"}
            continue
        first, latest = rows[0], rows[-1]
        if first.value is None or latest.value is None or len(rows) < 2:
            trend = "insufficient"
        else:
            delta = float(latest.value - first.value)
            trend = "stable" if abs(delta) < 1e-9 else ("increasing" if delta > 0 else "decreasing")
        out[key] = {
            "value": float(latest.value) if latest.value is not None else None,
            "unit": latest.unit,
            "origin": latest.origin,
            "validation_status": latest.validation_status,
            "captured_at": latest.captured_at,
            "personal_trend": trend,
            "reference_status": "not_configured",
        }
    return out


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
        "composition": composition_summary(db),
        "interpretation": interpret_body_composition(db),
    }
