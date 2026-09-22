from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from .enums import DataOrigin, ReminderAction, ValidationStatus


class MetricCreate(BaseModel):
    captured_at: datetime
    metric_key: str
    value: float | None = None
    unit: str
    source: str
    origin: DataOrigin
    validation_status: ValidationStatus = ValidationStatus.CONFIRMED
    confidence: float | None = Field(default=None, ge=0, le=1)
    evidence_ref: str | None = None
    source_event_id: str | None = None
    notes: str | None = None

    @field_validator("metric_key", "unit", "source")
    @classmethod
    def non_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("no puede estar vacío")
        return value.strip()


class ActivityCreate(BaseModel):
    started_at: datetime
    activity_type: str
    duration_min: float = Field(gt=0, le=1440)
    distance_km: float | None = Field(default=None, ge=0)
    speed_kmh: float | None = Field(default=None, ge=0)
    incline_pct: float | None = None
    steps: int | None = Field(default=None, ge=0)
    avg_hr: float | None = Field(default=None, ge=0)
    device_calories: float | None = Field(default=None, ge=0)
    perceived_exertion: int | None = Field(default=None, ge=1, le=10)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    integrated: bool = False
    integration_context: str | None = None
    source: str = "user"
    source_event_id: str | None = None
    notes: str | None = None


class StrengthSetCreate(BaseModel):
    performed_at: datetime
    exercise_name: str
    machine_name: str | None = None
    set_number: int = Field(ge=1, le=100)
    load_kg: float = Field(ge=0)
    reps: int = Field(ge=1, le=500)
    rpe: int | None = Field(default=None, ge=1, le=10)
    pain_score: int | None = Field(default=None, ge=0, le=10)
    notes: str | None = None


class SleepCreate(BaseModel):
    sleep_date: date
    started_at: datetime | None = None
    ended_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=0, le=1440)
    awakenings: int | None = Field(default=None, ge=0)
    resting_hr: float | None = Field(default=None, ge=0)
    energy_score: int | None = Field(default=None, ge=1, le=10)
    fatigue_score: int | None = Field(default=None, ge=1, le=10)
    source: str = "user"
    notes: str | None = None


class NutritionCreate(BaseModel):
    nutrition_date: date
    calories: float | None = Field(default=None, ge=0)
    protein_g: float | None = Field(default=None, ge=0)
    fat_g: float | None = Field(default=None, ge=0)
    carbs_g: float | None = Field(default=None, ge=0)
    hunger_score: int | None = Field(default=None, ge=1, le=10)
    adherence_score: int | None = Field(default=None, ge=1, le=10)
    source: str = "user"
    notes: str | None = None


class DecisionCreate(BaseModel):
    variable: str
    reason: str
    evidence: str | None = None
    old_value: str | None = None
    new_value: str | None = None
    hypothesis: str | None = None
    observation_days: int | None = Field(default=None, ge=1, le=365)


class DecisionResult(BaseModel):
    result: str
    status: str = "evaluated"


class ReminderCreate(BaseModel):
    title: str
    kind: str = "activity"
    time_local: str = Field(pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$")
    recurrence: Literal["daily"] = "daily"
    active: bool = True
    snooze_minutes: int = Field(default=15, ge=1, le=240)
    notes: str | None = None


class ReminderEventCreate(BaseModel):
    action: ReminderAction


class TrendPoint(BaseModel):
    captured_at: datetime
    value: float


class DashboardResponse(BaseModel):
    project_started: bool
    day_number: int | None
    days_remaining: int | None
    current_weight_kg: float | None
    baseline_weight_kg: float | None
    change_from_baseline_kg: float | None
    moving_avg_7d_kg: float | None
    goal_weight_kg: float
    activity_minutes_today: float
    integrated_minutes_today: float
    latest_sleep_hours: float | None
    next_reminder: dict | None
    operational_message: str
    alerts: list[str]
    data_quality: str
