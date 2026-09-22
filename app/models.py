from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)


class MetricRecord(Base, TimestampMixin):
    __tablename__ = "metric_records"
    __table_args__ = (UniqueConstraint("source_event_id", name="uq_metric_source_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    captured_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    metric_key: Mapped[str] = mapped_column(String(80), index=True, nullable=False)
    value: Mapped[float | None] = mapped_column(Float)
    unit: Mapped[str] = mapped_column(String(24), nullable=False)
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    origin: Mapped[str] = mapped_column(String(40), nullable=False)
    validation_status: Mapped[str] = mapped_column(String(40), nullable=False)
    confidence: Mapped[float | None] = mapped_column(Float)
    evidence_ref: Mapped[str | None] = mapped_column(Text)
    source_event_id: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)
    rule_version: Mapped[str] = mapped_column(String(32), default="v1")


class Activity(Base, TimestampMixin):
    __tablename__ = "activities"
    __table_args__ = (UniqueConstraint("source_event_id", name="uq_activity_source_event"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    started_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    duration_min: Mapped[float] = mapped_column(Float, nullable=False)
    distance_km: Mapped[float | None] = mapped_column(Float)
    speed_kmh: Mapped[float | None] = mapped_column(Float)
    incline_pct: Mapped[float | None] = mapped_column(Float)
    steps: Mapped[int | None] = mapped_column(Integer)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    device_calories: Mapped[float | None] = mapped_column(Float)
    perceived_exertion: Mapped[int | None] = mapped_column(Integer)
    pain_score: Mapped[int | None] = mapped_column(Integer)
    integrated: Mapped[bool] = mapped_column(Boolean, default=False)
    integration_context: Mapped[str | None] = mapped_column(String(120))
    source: Mapped[str] = mapped_column(String(120), default="user")
    source_event_id: Mapped[str | None] = mapped_column(String(160))
    notes: Mapped[str | None] = mapped_column(Text)


class StrengthSet(Base, TimestampMixin):
    __tablename__ = "strength_sets"

    id: Mapped[int] = mapped_column(primary_key=True)
    performed_at: Mapped[datetime] = mapped_column(DateTime, index=True, nullable=False)
    exercise_name: Mapped[str] = mapped_column(String(120), nullable=False)
    machine_name: Mapped[str | None] = mapped_column(String(120))
    set_number: Mapped[int] = mapped_column(Integer, nullable=False)
    load_kg: Mapped[float] = mapped_column(Float, nullable=False)
    reps: Mapped[int] = mapped_column(Integer, nullable=False)
    rpe: Mapped[int | None] = mapped_column(Integer)
    pain_score: Mapped[int | None] = mapped_column(Integer)
    notes: Mapped[str | None] = mapped_column(Text)


class SleepRecord(Base, TimestampMixin):
    __tablename__ = "sleep_records"
    __table_args__ = (UniqueConstraint("sleep_date", name="uq_sleep_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    sleep_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime)
    duration_min: Mapped[int | None] = mapped_column(Integer)
    awakenings: Mapped[int | None] = mapped_column(Integer)
    resting_hr: Mapped[float | None] = mapped_column(Float)
    energy_score: Mapped[int | None] = mapped_column(Integer)
    fatigue_score: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(120), default="user")
    notes: Mapped[str | None] = mapped_column(Text)


class NutritionRecord(Base, TimestampMixin):
    __tablename__ = "nutrition_records"
    __table_args__ = (UniqueConstraint("nutrition_date", name="uq_nutrition_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    nutrition_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    calories: Mapped[float | None] = mapped_column(Float)
    protein_g: Mapped[float | None] = mapped_column(Float)
    fat_g: Mapped[float | None] = mapped_column(Float)
    carbs_g: Mapped[float | None] = mapped_column(Float)
    hunger_score: Mapped[int | None] = mapped_column(Integer)
    adherence_score: Mapped[int | None] = mapped_column(Integer)
    source: Mapped[str] = mapped_column(String(120), default="user")
    notes: Mapped[str | None] = mapped_column(Text)


class Decision(Base, TimestampMixin):
    __tablename__ = "decisions"

    id: Mapped[int] = mapped_column(primary_key=True)
    variable: Mapped[str] = mapped_column(String(120), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text)
    old_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)
    hypothesis: Mapped[str | None] = mapped_column(Text)
    observation_days: Mapped[int | None] = mapped_column(Integer)
    result: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), default="open")


class Reminder(Base, TimestampMixin):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(180), nullable=False)
    kind: Mapped[str] = mapped_column(String(80), default="activity")
    time_local: Mapped[str] = mapped_column(String(5), nullable=False)
    recurrence: Mapped[str] = mapped_column(String(40), default="daily")
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    snooze_minutes: Mapped[int] = mapped_column(Integer, default=15)
    notes: Mapped[str | None] = mapped_column(Text)


class ReminderEvent(Base, TimestampMixin):
    __tablename__ = "reminder_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    reminder_id: Mapped[int] = mapped_column(ForeignKey("reminders.id"), index=True)
    action: Mapped[str] = mapped_column(String(32), nullable=False)
    event_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    snoozed_until: Mapped[datetime | None] = mapped_column(DateTime)


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    entity_type: Mapped[str] = mapped_column(String(80), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(String(80))
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    before_json: Mapped[str | None] = mapped_column(Text)
    after_json: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    actor: Mapped[str] = mapped_column(String(80), default="api")
