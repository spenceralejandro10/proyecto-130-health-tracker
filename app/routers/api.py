from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..config import settings
from ..db import get_db
from ..interpretation import trend_analysis
from ..models import (
    Activity,
    AuditLog,
    Decision,
    MetricRecord,
    NutritionRecord,
    Reminder,
    ReminderEvent,
    SleepRecord,
    StrengthSet,
)
from ..schemas import (
    ActivityCreate,
    DashboardResponse,
    DecisionCreate,
    DecisionResult,
    MetricCreate,
    NutritionCreate,
    ReminderCreate,
    ReminderEventCreate,
    ReminderUpdate,
    SleepCreate,
    StrengthSetCreate,
)
from ..security import require_api_key
from ..services import dashboard, due_reminders, metric_trend
from ..timeutils import to_utc_naive

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


def _columns(obj) -> dict:
    return {c.key: getattr(obj, c.key) for c in inspect(obj).mapper.column_attrs}


def _create(db: Session, obj, entity_type: str, reason: str = "create"):
    db.add(obj)
    try:
        db.flush()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail=f"Registro duplicado o conflicto: {exc.orig}") from exc
    audit(db, entity_type=entity_type, entity_id=obj.id, action="create", after=_columns(obj), reason=reason)
    db.commit()
    db.refresh(obj)
    return _columns(obj)


@router.get("/health")
def health():
    return {"status": "ok", "time": datetime.now(UTC).isoformat()}


@router.post("/metrics", status_code=201)
def create_metric(payload: MetricCreate, db: Session = Depends(get_db)):
    if payload.value is None and payload.validation_status not in {"unavailable", "pending"}:
        raise HTTPException(status_code=422, detail="value solo puede faltar si el estado es unavailable o pending")
    data = payload.model_dump()
    data["captured_at"] = to_utc_naive(data["captured_at"])
    obj = MetricRecord(**data)
    return _create(db, obj, "metric")


@router.get("/metrics")
def list_metrics(
    metric_key: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    stmt = select(MetricRecord)
    if metric_key:
        stmt = stmt.where(MetricRecord.metric_key == metric_key)
    stmt = stmt.order_by(MetricRecord.captured_at.desc()).limit(limit)
    return [_columns(x) for x in db.scalars(stmt).all()]


@router.get("/trends/{metric_key}")
def trend(metric_key: str, days: int = Query(default=7, ge=1, le=365), db: Session = Depends(get_db)):
    return {"metric_key": metric_key, "days": days, "points": metric_trend(db, metric_key, days)}


@router.get("/project-series")
def project_series(days: int = Query(default=132, ge=7, le=365), db: Session = Depends(get_db)):
    """Serie unificada para el tablero ejecutivo.

    Devuelve datos crudos/estimados con unidades explícitas. La normalización
    visual se realiza en el cliente para poder comparar escalas distintas sin
    fingir que kg, %, horas y minutos son la misma magnitud.
    """
    start = datetime.now(settings.timezone).date() - timedelta(days=days - 1)
    metric_keys = ["weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index"]
    metrics = {}
    for key in metric_keys:
        metrics[key] = metric_trend(db, key, days)

    activities = db.scalars(select(Activity).order_by(Activity.started_at.asc())).all()
    activity_by_day = {}
    integrated_by_day = {}
    for row in activities:
        local_day = row.started_at.replace(tzinfo=UTC).astimezone(settings.timezone).date()
        day = local_day.isoformat()
        if local_day < start:
            continue
        activity_by_day[day] = round(activity_by_day.get(day, 0) + float(row.duration_min), 1)
        if row.integrated:
            integrated_by_day[day] = round(integrated_by_day.get(day, 0) + float(row.duration_min), 1)

    sleeps = db.scalars(select(SleepRecord).order_by(SleepRecord.sleep_date.asc())).all()
    sleep_by_day = {
        row.sleep_date.isoformat(): round(row.duration_min / 60, 2)
        for row in sleeps if row.duration_min is not None and row.sleep_date >= start
    }

    return {
        "days": days,
        "goal_weight_kg": settings.goal_weight_kg,
        "metrics": metrics,
        "activity_minutes": activity_by_day,
        "integrated_minutes": integrated_by_day,
        "sleep_hours": sleep_by_day,
        "analysis": trend_analysis(db, days),
        "note": "Las series usan unidades distintas. El gráfico las normaliza contra su propia línea base y conserva los valores reales en etiquetas.",
    }


@router.post("/activities", status_code=201)
def create_activity(payload: ActivityCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["started_at"] = to_utc_naive(data["started_at"])
    obj = Activity(**data)
    return _create(db, obj, "activity")


@router.get("/activities")
def list_activities(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    return [_columns(x) for x in db.scalars(select(Activity).order_by(Activity.started_at.desc()).limit(limit)).all()]


@router.post("/strength", status_code=201)
def create_strength(payload: StrengthSetCreate, db: Session = Depends(get_db)):
    data = payload.model_dump()
    data["performed_at"] = to_utc_naive(data["performed_at"])
    obj = StrengthSet(**data)
    return _create(db, obj, "strength_set")


@router.get("/strength")
def list_strength(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(StrengthSet).order_by(StrengthSet.performed_at.desc()).limit(limit)).all()
    return [_columns(x) for x in rows]


@router.get("/strength/last/{exercise_name}")
def last_strength(exercise_name: str, db: Session = Depends(get_db)):
    obj = db.scalar(
        select(StrengthSet)
        .where(StrengthSet.exercise_name == exercise_name)
        .order_by(StrengthSet.performed_at.desc(), StrengthSet.set_number.desc())
        .limit(1)
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Sin series previas")
    return _columns(obj)


@router.post("/sleep", status_code=201)
def create_sleep(payload: SleepCreate, db: Session = Depends(get_db)):
    if payload.duration_min is None and payload.started_at and payload.ended_at:
        duration = int((payload.ended_at - payload.started_at).total_seconds() / 60)
        payload = payload.model_copy(update={"duration_min": max(duration, 0)})
    data = payload.model_dump()
    data["started_at"] = to_utc_naive(data["started_at"])
    data["ended_at"] = to_utc_naive(data["ended_at"])
    obj = SleepRecord(**data)
    return _create(db, obj, "sleep")


@router.get("/sleep")
def list_sleep(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(SleepRecord).order_by(SleepRecord.sleep_date.desc()).limit(limit)).all()
    return [_columns(x) for x in rows]


@router.post("/nutrition", status_code=201)
def create_nutrition(payload: NutritionCreate, db: Session = Depends(get_db)):
    obj = NutritionRecord(**payload.model_dump())
    return _create(db, obj, "nutrition")


@router.get("/nutrition")
def list_nutrition(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(NutritionRecord).order_by(NutritionRecord.nutrition_date.desc()).limit(limit)).all()
    return [_columns(x) for x in rows]


@router.post("/decisions", status_code=201)
def create_decision(payload: DecisionCreate, db: Session = Depends(get_db)):
    obj = Decision(**payload.model_dump())
    return _create(db, obj, "decision")


@router.get("/decisions")
def list_decisions(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(Decision).order_by(Decision.created_at.desc()).limit(limit)).all()
    return [_columns(x) for x in rows]


@router.patch("/decisions/{decision_id}/result")
def set_decision_result(decision_id: int, payload: DecisionResult, db: Session = Depends(get_db)):
    obj = db.get(Decision, decision_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Decisión no encontrada")
    before = _columns(obj)
    obj.result = payload.result
    obj.status = payload.status
    audit(db, entity_type="decision", entity_id=obj.id, action="evaluate", before=before, after=_columns(obj))
    db.commit()
    return _columns(obj)


@router.post("/reminders", status_code=201)
def create_reminder(payload: ReminderCreate, db: Session = Depends(get_db)):
    obj = Reminder(**payload.model_dump())
    return _create(db, obj, "reminder")


@router.get("/reminders")
def list_reminders(db: Session = Depends(get_db)):
    return [_columns(x) for x in db.scalars(select(Reminder).order_by(Reminder.time_local)).all()]


@router.patch("/reminders/{reminder_id}")
def update_reminder(reminder_id: int, payload: ReminderUpdate, db: Session = Depends(get_db)):
    obj = db.get(Reminder, reminder_id)
    if not obj:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")
    before = _columns(obj)
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(obj, key, value)
    audit(db, entity_type="reminder", entity_id=obj.id, action="update", before=before, after=_columns(obj))
    db.commit()
    db.refresh(obj)
    return _columns(obj)


@router.get("/reminders/due")
def get_due_reminders(db: Session = Depends(get_db)):
    return due_reminders(db)


@router.post("/reminders/{reminder_id}/event", status_code=201)
def reminder_event(reminder_id: int, payload: ReminderEventCreate, db: Session = Depends(get_db)):
    reminder = db.get(Reminder, reminder_id)
    if not reminder:
        raise HTTPException(status_code=404, detail="Recordatorio no encontrado")
    snoozed_until = None
    if payload.action == "snooze":
        snoozed_until = datetime.now(UTC).replace(tzinfo=None) + timedelta(minutes=reminder.snooze_minutes)
    obj = ReminderEvent(reminder_id=reminder_id, action=payload.action.value, snoozed_until=snoozed_until)
    return _create(db, obj, "reminder_event")


@router.get("/dashboard", response_model=DashboardResponse)
def get_dashboard(db: Session = Depends(get_db)):
    return dashboard(db)


@router.get("/audit")
def list_audit(limit: int = Query(100, ge=1, le=1000), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.occurred_at.desc()).limit(limit)).all()
    return [_columns(x) for x in rows]


@router.get("/export")
def export_all(db: Session = Depends(get_db)):
    table_map = {
        "metrics": MetricRecord,
        "activities": Activity,
        "strength": StrengthSet,
        "sleep": SleepRecord,
        "nutrition": NutritionRecord,
        "decisions": Decision,
        "reminders": Reminder,
        "reminder_events": ReminderEvent,
        "audit": AuditLog,
    }
    data = {}
    for name, model in table_map.items():
        data[name] = [_columns(x) for x in db.scalars(select(model)).all()]
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "schema_version": "v1",
        "data": data,
    }
