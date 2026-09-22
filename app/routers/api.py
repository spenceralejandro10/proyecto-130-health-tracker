from __future__ import annotations

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..audit import audit
from ..db import get_db
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
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


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


@router.post("/nutrition", status_code=201)
def create_nutrition(payload: NutritionCreate, db: Session = Depends(get_db)):
    obj = NutritionRecord(**payload.model_dump())
    return _create(db, obj, "nutrition")


@router.post("/decisions", status_code=201)
def create_decision(payload: DecisionCreate, db: Session = Depends(get_db)):
    obj = Decision(**payload.model_dump())
    return _create(db, obj, "decision")


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
        snoozed_until = datetime.utcnow() + timedelta(minutes=reminder.snooze_minutes)
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
        "exported_at": datetime.utcnow().isoformat(),
        "schema_version": "v1",
        "data": data,
    }
