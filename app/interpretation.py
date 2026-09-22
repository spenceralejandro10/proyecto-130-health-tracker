from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import mean
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import settings
from .models import Activity, MetricRecord, NutritionRecord, SleepRecord, StrengthSet
from .timeutils import utc_naive_to_local_date


ENGINE_VERSION = "v3.0"

METRIC_KEYS = (
    "weight_kg",
    "body_fat_pct",
    "muscle_mass_kg",
    "body_water_pct",
    "visceral_fat_index",
    "bone_mass_kg",
)

METRIC_META = {
    "weight_kg": ("Peso", "kg", "kg", "observado"),
    "body_fat_pct": ("Grasa corporal", "%", "puntos", "estimado_por_dispositivo"),
    "fat_mass_est_kg": ("Masa grasa estimada", "kg", "kg", "derivado"),
    "lean_mass_est_kg": ("Masa libre de grasa estimada", "kg", "kg", "derivado"),
    "muscle_mass_kg": ("Masa muscular", "kg", "kg", "estimado_por_dispositivo"),
    "body_water_pct": ("Agua corporal", "%", "puntos", "estimado_por_dispositivo"),
    "water_mass_est_kg": ("Masa de agua estimada", "kg", "kg", "derivado"),
    "visceral_fat_index": ("Grasa visceral", "índice", "puntos", "estimado_por_dispositivo"),
    "sleep_hours": ("Sueño", "h", "h", "observado"),
    "activity_minutes": ("Actividad", "min", "min", "observado"),
}

GUARD_BANDS = {
    "weight_kg": 0.20,
    "body_fat_pct": 0.20,
    "muscle_mass_kg": 0.20,
    "body_water_pct": 0.20,
    "visceral_fat_index": 0.50,
    "fat_mass_est_kg": 0.15,
    "lean_mass_est_kg": 0.15,
    "water_mass_est_kg": 0.20,
    "sleep_hours": 0.25,
    "activity_minutes": 10.0,
}

MET_BY_ACTIVITY = {
    "caminata_manana": 3.5,
    "caminata_noche": 3.0,
    "fuerza_gimnasio": 5.0,
    "funcional_tarde": 6.0,
}


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    rounded = round(float(value), digits)
    text = f"{rounded:.{digits}f}".rstrip("0").rstrip(".")
    return text.replace(".", ",")


def _signed(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    rounded = round(float(value), digits)
    return f"{'+' if rounded > 0 else ''}{_fmt(rounded, digits)}"


def _direction(delta: float | None, band: float) -> str:
    if delta is None:
        return "sin_comparacion"
    if abs(delta) < 1e-9:
        return "estable"
    return "subio" if delta > 0 else "bajo"


def _usable_metrics(db: Session) -> list[MetricRecord]:
    stmt = (
        select(MetricRecord)
        .where(
            MetricRecord.metric_key.in_(METRIC_KEYS),
            MetricRecord.value.is_not(None),
            MetricRecord.validation_status.in_(["confirmed", "estimated"]),
        )
        .order_by(MetricRecord.captured_at.asc(), MetricRecord.id.asc())
    )
    return list(db.scalars(stmt).all())


def _snapshots(db: Session, since: date | None = None) -> list[dict[str, Any]]:
    by_day: dict[date, dict[str, MetricRecord]] = defaultdict(dict)
    today = datetime.now(settings.timezone).date()

    for row in _usable_metrics(db):
        day = utc_naive_to_local_date(row.captured_at)
        if day > today:
            continue
        if since and day < since:
            continue
        by_day[day][row.metric_key] = row

    snapshots: list[dict[str, Any]] = []
    for day in sorted(by_day):
        rows = by_day[day]
        values = {key: float(row.value) for key, row in rows.items() if row.value is not None}
        times = [row.captured_at for row in rows.values()]
        snapshot: dict[str, Any] = {
            "date": day,
            "values": values,
            "rows": rows,
            "measurement_span_min": (
                (max(times) - min(times)).total_seconds() / 60 if len(times) >= 2 else 0.0
            ),
        }

        weight = values.get("weight_kg")
        fat_pct = values.get("body_fat_pct")
        water_pct = values.get("body_water_pct")

        if weight is not None and fat_pct is not None:
            fat_mass = weight * fat_pct / 100
            snapshot["fat_mass_est_kg"] = fat_mass
            snapshot["lean_mass_est_kg"] = weight - fat_mass

        if weight is not None and water_pct is not None:
            snapshot["water_mass_est_kg"] = weight * water_pct / 100

        snapshots.append(snapshot)

    return snapshots


def _value(snapshot: dict[str, Any], key: str) -> float | None:
    raw = snapshot.get(key, snapshot.get("values", {}).get(key))
    return None if raw is None else float(raw)


def _delta(current: dict[str, Any], previous: dict[str, Any], key: str) -> float | None:
    a = _value(current, key)
    b = _value(previous, key)
    if a is None or b is None:
        return None
    return a - b


def _metric_observation(
    key: str,
    current: dict[str, Any],
    previous: dict[str, Any],
    baseline: dict[str, Any],
) -> dict[str, Any] | None:
    current_value = _value(current, key)
    if current_value is None:
        return None

    previous_value = _value(previous, key)
    baseline_value = _value(baseline, key)
    label, unit, delta_unit, kind = METRIC_META[key]
    delta = None if previous_value is None else current_value - previous_value
    delta_baseline = None if baseline_value is None else current_value - baseline_value

    return {
        "key": key,
        "label": label,
        "kind": kind,
        "unit": unit,
        "delta_unit": delta_unit,
        "current": _round(current_value),
        "previous": _round(previous_value),
        "baseline": _round(baseline_value),
        "delta": _round(delta),
        "delta_baseline": _round(delta_baseline),
        "direction": _direction(delta, GUARD_BANDS.get(key, 0.0)),
    }


def _direct_metric_message(obs: dict[str, Any]) -> str:
    label = obs["label"]
    unit = obs["unit"]
    delta_unit = obs["delta_unit"]
    current = _fmt(obs["current"])
    previous = _fmt(obs["previous"])

    if obs["delta"] is None:
        return f"{label}: {current} {unit}. Primera lectura disponible."

    delta = float(obs["delta"])
    if obs["direction"] == "estable":
        if abs(delta) < 0.005:
            return f"{label} no cambió: {previous} {unit} → {current} {unit}."
        return (
            f"{label} se mantuvo prácticamente estable: "
            f"{previous} {unit} → {current} {unit} ({_signed(delta)} {delta_unit})."
        )

    verb = "subió" if delta > 0 else "bajó"
    if obs["key"] in {"body_fat_pct", "body_water_pct"}:
        return f"{label} {verb}: {previous}% → {current}%."
    if obs["key"] == "visceral_fat_index":
        return f"{label} {verb}: {previous} → {current}."
    return f"{label} {verb} {_fmt(abs(delta))} {delta_unit}: {previous} {unit} → {current} {unit}."


def _metric_messages(observations: list[dict[str, Any]]) -> dict[str, str]:
    result = {obs["key"]: _direct_metric_message(obs) for obs in observations}
    by_key = {obs["key"]: obs for obs in observations}

    fat = by_key.get("fat_mass_est_kg")
    if fat and fat.get("previous") is not None:
        result["body_fat_pct"] = (
            result.get("body_fat_pct", "")
            + f" Masa grasa estimada: {_fmt(fat['previous'])} kg → {_fmt(fat['current'])} kg."
        ).strip()

    water = by_key.get("water_mass_est_kg")
    if water and water.get("previous") is not None:
        result["body_water_pct"] = (
            result.get("body_water_pct", "")
            + f" Agua corporal estimada: {_fmt(water['previous'])} kg → {_fmt(water['current'])} kg."
        ).strip()

    return result


def _activity_met(row: Activity) -> float:
    if row.speed_kmh is not None:
        speed = float(row.speed_kmh)
        if speed >= 6.5:
            return 5.0
        if speed >= 5.5:
            return 4.3
        if speed >= 4.5:
            return 3.5
        if speed > 0:
            return 2.8
    return MET_BY_ACTIVITY.get(row.activity_type, 4.0)


def _activity_energy(row: Activity, weight_kg: float) -> tuple[float, str]:
    if row.device_calories is not None:
        return float(row.device_calories), "dispositivo"
    met = _activity_met(row)
    kcal = met * 3.5 * weight_kg / 200 * float(row.duration_min)
    return kcal, "estimado"


def _energy_state(
    db: Session,
    current: dict[str, Any],
    previous: dict[str, Any] | None,
    day_override: date | None = None,
) -> dict[str, Any]:
    day = day_override or current["date"]
    weight = _value(current, "weight_kg")
    lean = _value(current, "lean_mass_est_kg")

    resting = 370 + 21.6 * lean if lean is not None else None
    previous_resting = None
    if previous is not None:
        prev_lean = _value(previous, "lean_mass_est_kg")
        if prev_lean is not None:
            previous_resting = 370 + 21.6 * prev_lean

    rows = [
        row
        for row in db.scalars(select(Activity).order_by(Activity.started_at.asc())).all()
        if utc_naive_to_local_date(row.started_at) == day
    ]
    activity_minutes = sum(float(row.duration_min) for row in rows) if rows else None
    activity_kcal = None
    device_kcal = 0.0
    estimated_kcal = 0.0
    if rows and weight is not None:
        for row in rows:
            kcal, source = _activity_energy(row, weight)
            if source == "dispositivo":
                device_kcal += kcal
            else:
                estimated_kcal += kcal
        activity_kcal = device_kcal + estimated_kcal

    nutrition = db.scalar(
        select(NutritionRecord)
        .where(NutritionRecord.nutrition_date == day)
        .order_by(NutritionRecord.id.desc())
        .limit(1)
    )
    intake_kcal = float(nutrition.calories) if nutrition and nutrition.calories is not None else None

    accounted_expenditure = None
    if resting is not None:
        accounted_expenditure = resting + (activity_kcal or 0.0)

    partial_balance = None
    if intake_kcal is not None and accounted_expenditure is not None:
        partial_balance = intake_kcal - accounted_expenditure

    return {
        "date": day.isoformat(),
        "resting_kcal_day": _round(resting, 0),
        "resting_change_kcal_day": _round(
            None if resting is None or previous_resting is None else resting - previous_resting,
            0,
        ),
        "lean_mass_est_kg": _round(lean),
        "activity_minutes": _round(activity_minutes, 0),
        "activity_kcal": _round(activity_kcal, 0),
        "activity_kcal_device": _round(device_kcal, 0) if rows else None,
        "activity_kcal_estimated": _round(estimated_kcal, 0) if rows else None,
        "intake_kcal": _round(intake_kcal, 0),
        "accounted_expenditure_kcal": _round(accounted_expenditure, 0),
        "partial_balance_kcal": _round(partial_balance, 0),
    }


def _energy_message(energy: dict[str, Any]) -> str:
    resting = energy.get("resting_kcal_day")
    if resting is None:
        return "No se pudo calcular el gasto en reposo porque falta grasa corporal o peso."

    parts = [f"Gasto en reposo estimado: {_fmt(resting, 0)} kcal/día"]
    change = energy.get("resting_change_kcal_day")
    if change is not None:
        parts.append(f"cambió {_signed(change, 0)} kcal/día desde la medición anterior")

    activity_kcal = energy.get("activity_kcal")
    activity_minutes = energy.get("activity_minutes")
    if activity_kcal is not None:
        parts.append(
            f"actividad registrada: {_fmt(activity_minutes, 0)} min ≈ {_fmt(activity_kcal, 0)} kcal"
        )

    intake = energy.get("intake_kcal")
    balance = energy.get("partial_balance_kcal")
    if intake is not None:
        parts.append(f"ingesta registrada: {_fmt(intake, 0)} kcal")
    if balance is not None:
        label = "déficit parcial" if balance < 0 else "superávit parcial"
        parts.append(f"{label}: {_fmt(abs(balance), 0)} kcal")

    return ". ".join(parts) + "."


def _context_state(db: Session, day: date) -> dict[str, Any]:
    sleep = db.scalar(
        select(SleepRecord)
        .where(SleepRecord.sleep_date <= day, SleepRecord.duration_min.is_not(None))
        .order_by(SleepRecord.sleep_date.desc())
        .limit(1)
    )

    nutrition = db.scalar(
        select(NutritionRecord)
        .where(NutritionRecord.nutrition_date == day)
        .order_by(NutritionRecord.id.desc())
        .limit(1)
    )

    strength_rows = [
        row
        for row in db.scalars(select(StrengthSet).order_by(StrengthSet.performed_at.asc())).all()
        if utc_naive_to_local_date(row.performed_at) == day
    ]

    sleep_hours = float(sleep.duration_min) / 60 if sleep and sleep.duration_min is not None else None
    strength_volume = sum(float(row.load_kg) * int(row.reps) for row in strength_rows) if strength_rows else None

    return {
        "sleep_date": sleep.sleep_date.isoformat() if sleep else None,
        "sleep_hours": _round(sleep_hours, 1),
        "resting_hr": _round(float(sleep.resting_hr), 0) if sleep and sleep.resting_hr is not None else None,
        "fatigue_score": sleep.fatigue_score if sleep else None,
        "nutrition_date": nutrition.nutrition_date.isoformat() if nutrition else None,
        "protein_g": _round(float(nutrition.protein_g), 0) if nutrition and nutrition.protein_g is not None else None,
        "carbs_g": _round(float(nutrition.carbs_g), 0) if nutrition and nutrition.carbs_g is not None else None,
        "fat_g": _round(float(nutrition.fat_g), 0) if nutrition and nutrition.fat_g is not None else None,
        "strength_sets": len(strength_rows) if strength_rows else None,
        "strength_volume_kg_reps": _round(strength_volume, 0),
    }


def _connected_findings(
    current: dict[str, Any],
    observations: list[dict[str, Any]],
    energy: dict[str, Any],
    context: dict[str, Any],
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    weight = _value(current, "weight_kg")
    lean = energy.get("lean_mass_est_kg")
    resting = energy.get("resting_kcal_day")
    resting_change = energy.get("resting_change_kcal_day")

    if lean is not None and resting is not None:
        change_text = (
            f" ({_signed(resting_change, 0)} kcal/día frente a la medición anterior)"
            if resting_change is not None else ""
        )
        findings.append({
            "code": "composition_to_resting",
            "label": "Composición corporal → gasto en reposo",
            "explanation": (
                f"Masa libre de grasa estimada {_fmt(lean, 1)} kg → "
                f"TMB estimada {_fmt(resting, 0)} kcal/día{change_text}."
            ),
        })

    activity_kcal = energy.get("activity_kcal")
    activity_minutes = energy.get("activity_minutes")
    accounted = energy.get("accounted_expenditure_kcal")
    if weight is not None and activity_kcal is not None:
        findings.append({
            "code": "weight_activity_to_expenditure",
            "label": "Peso + actividad → gasto contabilizado",
            "explanation": (
                f"Con {_fmt(weight, 1)} kg y {_fmt(activity_minutes, 0)} min de actividad registrada, "
                f"la actividad aporta ≈{_fmt(activity_kcal, 0)} kcal; "
                f"reposo + actividad = ≈{_fmt(accounted, 0)} kcal."
            ),
        })

    intake = energy.get("intake_kcal")
    balance = energy.get("partial_balance_kcal")
    if intake is not None and accounted is not None and balance is not None:
        balance_word = "déficit" if balance < 0 else "superávit" if balance > 0 else "balance neutro"
        findings.append({
            "code": "intake_expenditure_balance",
            "label": "Ingesta + gasto → balance parcial",
            "explanation": (
                f"Ingesta {_fmt(intake, 0)} kcal − gasto contabilizado {_fmt(accounted, 0)} kcal = "
                f"{balance_word} de {_fmt(abs(balance), 0)} kcal."
            ),
        })

    muscle_obs = next((item for item in observations if item["key"] == "muscle_mass_kg"), None)
    if muscle_obs and muscle_obs.get("delta") is not None:
        parts = [_direct_metric_message(muscle_obs)]
        if context.get("strength_sets") is not None:
            parts.append(
                f"Fuerza del día: {context['strength_sets']} series, "
                f"{_fmt(context.get('strength_volume_kg_reps'), 0)} kg·rep."
            )
        if context.get("protein_g") is not None:
            parts.append(f"Proteína registrada: {_fmt(context['protein_g'], 0)} g.")
        if len(parts) > 1:
            findings.append({
                "code": "muscle_strength_nutrition",
                "label": "Músculo + fuerza + nutrición",
                "explanation": " ".join(parts),
            })

    if context.get("sleep_hours") is not None:
        parts = [f"Sueño: {_fmt(context['sleep_hours'], 1)} h."]
        if context.get("resting_hr") is not None:
            parts.append(f"FC en reposo: {_fmt(context['resting_hr'], 0)} lpm.")
        if context.get("fatigue_score") is not None:
            parts.append(f"Fatiga registrada: {context['fatigue_score']}/10.")
        findings.append({
            "code": "recovery_state",
            "label": "Recuperación registrada",
            "explanation": " ".join(parts),
        })

    return findings


def _confidence(current: dict[str, Any], previous: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    core = ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct")
    paired = sum(1 for key in core if _value(current, key) is not None and _value(previous, key) is not None)
    gap_days = (current["date"] - previous["date"]).days
    recent_count = sum(1 for item in snapshots if (current["date"] - item["date"]).days <= 7)
    level = "alta" if paired >= 4 and recent_count >= 5 and 1 <= gap_days <= 3 else "media" if paired >= 3 else "baja"
    return {
        "level": level,
        "variables_compared": paired,
        "recent_measurements": recent_count,
        "gap_days": gap_days,
    }


def _integrated_findings(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, str]]:
    weight = _delta(current, previous, "weight_kg")
    fat_mass = _delta(current, previous, "fat_mass_est_kg")
    water_mass = _delta(current, previous, "water_mass_est_kg")
    muscle = _delta(current, previous, "muscle_mass_kg")
    fat_pct = _delta(current, previous, "body_fat_pct")
    water_pct = _delta(current, previous, "body_water_pct")
    visceral = _delta(current, previous, "visceral_fat_index")

    findings: list[dict[str, str]] = []
    if weight is None:
        return findings

    if weight > GUARD_BANDS["weight_kg"]:
        if fat_mass is not None and fat_mass <= GUARD_BANDS["fat_mass_est_kg"] and water_mass is not None and water_mass > GUARD_BANDS["water_mass_est_kg"]:
            findings.append({
                "code": "weight_up_water_up_fat_not_up",
                "label": "El peso subió, pero la grasa estimada no subió",
                "confidence": "media",
                "explanation": (
                    f"Peso {_signed(weight)} kg; agua estimada {_signed(water_mass)} kg; "
                    f"grasa estimada {_signed(fat_mass)} kg. El aumento de peso coincidió con más agua estimada, no con más grasa estimada."
                ),
            })
        elif fat_mass is not None and fat_mass > GUARD_BANDS["fat_mass_est_kg"]:
            findings.append({
                "code": "weight_up_fat_up",
                "label": "El peso y la grasa estimada subieron",
                "confidence": "media",
                "explanation": f"Peso {_signed(weight)} kg; grasa estimada {_signed(fat_mass)} kg.",
            })
        else:
            findings.append({
                "code": "weight_up_mixed",
                "label": "El peso subió",
                "confidence": "baja",
                "explanation": f"Peso {_signed(weight)} kg. Los demás componentes no muestran un cambio dominante.",
            })

    elif weight < -GUARD_BANDS["weight_kg"]:
        if fat_mass is not None and fat_mass < -GUARD_BANDS["fat_mass_est_kg"] and (water_mass is None or abs(water_mass) <= GUARD_BANDS["water_mass_est_kg"]):
            findings.append({
                "code": "weight_down_fat_down",
                "label": "El peso y la grasa estimada bajaron",
                "confidence": "media",
                "explanation": f"Peso {_signed(weight)} kg; grasa estimada {_signed(fat_mass)} kg.",
            })
        elif water_mass is not None and water_mass < -GUARD_BANDS["water_mass_est_kg"] and (fat_mass is None or abs(fat_mass) <= GUARD_BANDS["fat_mass_est_kg"]):
            findings.append({
                "code": "weight_down_water_down",
                "label": "El peso bajó y el mayor cambio medido fue agua",
                "confidence": "media",
                "explanation": f"Peso {_signed(weight)} kg; agua estimada {_signed(water_mass)} kg; grasa estimada {_signed(fat_mass)} kg.",
            })
        else:
            findings.append({
                "code": "weight_down_mixed",
                "label": "El peso bajó",
                "confidence": "baja",
                "explanation": (
                    f"Peso {_signed(weight)} kg"
                    + (f"; grasa estimada {_signed(fat_mass)} kg" if fat_mass is not None else "")
                    + (f"; agua estimada {_signed(water_mass)} kg" if water_mass is not None else "")
                    + "."
                ),
            })
    else:
        findings.append({
            "code": "weight_stable",
            "label": "El peso se mantuvo estable",
            "confidence": "media",
            "explanation": f"Peso {_signed(weight)} kg frente a la medición anterior.",
        })

    if fat_pct is not None and abs(fat_pct) > GUARD_BANDS["body_fat_pct"]:
        findings.append({
            "code": "fat_pct_change",
            "label": f"La grasa corporal {'subió' if fat_pct > 0 else 'bajó'}",
            "confidence": "media",
            "explanation": (
                f"Grasa corporal: {_fmt(_value(previous, 'body_fat_pct'))}% → "
                f"{_fmt(_value(current, 'body_fat_pct'))}%."
            ),
        })

    if water_pct is not None and abs(water_pct) > GUARD_BANDS["body_water_pct"]:
        findings.append({
            "code": "water_pct_change",
            "label": f"El agua corporal {'subió' if water_pct > 0 else 'bajó'}",
            "confidence": "media",
            "explanation": (
                f"Agua corporal: {_fmt(_value(previous, 'body_water_pct'))}% → "
                f"{_fmt(_value(current, 'body_water_pct'))}%."
            ),
        })

    if muscle is not None and abs(muscle) > GUARD_BANDS["muscle_mass_kg"]:
        findings.append({
            "code": "muscle_change",
            "label": f"La masa muscular estimada {'subió' if muscle > 0 else 'bajó'}",
            "confidence": "media",
            "explanation": f"Masa muscular estimada {_signed(muscle)} kg.",
        })

    if visceral is not None and abs(visceral) > GUARD_BANDS["visceral_fat_index"]:
        findings.append({
            "code": "visceral_change",
            "label": f"La grasa visceral estimada {'subió' if visceral > 0 else 'bajó'}",
            "confidence": "media",
            "explanation": (
                f"Grasa visceral: {_fmt(_value(previous, 'visceral_fat_index'))} → "
                f"{_fmt(_value(current, 'visceral_fat_index'))}."
            ),
        })

    return findings


def _state_summary(observations: list[dict[str, Any]], findings: list[dict[str, str]], energy: dict[str, Any]) -> str:
    changed = [obs for obs in observations if obs["delta"] is not None and obs["key"] in {
        "weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index"
    }]
    direct = " ".join(_direct_metric_message(obs) for obs in changed)
    interpretation = findings[0]["explanation"] if findings else ""
    energy_text = _energy_message(energy)
    return " ".join(x for x in (direct, interpretation, energy_text) if x)


def _context_findings(db: Session) -> list[str]:
    findings: list[str] = []
    today = datetime.now(settings.timezone).date()

    sleep = db.scalar(
        select(SleepRecord)
        .where(SleepRecord.sleep_date <= today, SleepRecord.duration_min.is_not(None))
        .order_by(SleepRecord.sleep_date.desc())
        .limit(1)
    )
    if sleep and sleep.duration_min is not None:
        findings.append(f"Sueño: {_fmt(float(sleep.duration_min) / 60, 1)} h ({sleep.sleep_date.isoformat()}).")

    activity_by_day: dict[date, float] = defaultdict(float)
    for row in db.scalars(select(Activity).order_by(Activity.started_at.asc())).all():
        day = utc_naive_to_local_date(row.started_at)
        if day <= today:
            activity_by_day[day] += float(row.duration_min)
    if activity_by_day:
        day = max(activity_by_day)
        findings.append(f"Actividad: {_fmt(activity_by_day[day], 0)} min ({day.isoformat()}).")

    nutrition = db.scalar(
        select(NutritionRecord)
        .where(NutritionRecord.nutrition_date <= today)
        .order_by(NutritionRecord.nutrition_date.desc())
        .limit(1)
    )
    if nutrition:
        parts = []
        if nutrition.calories is not None:
            parts.append(f"{_fmt(float(nutrition.calories), 0)} kcal")
        if nutrition.protein_g is not None:
            parts.append(f"{_fmt(float(nutrition.protein_g), 0)} g proteína")
        if parts:
            findings.append(f"Nutrición: {', '.join(parts)} ({nutrition.nutrition_date.isoformat()}).")

    return findings


def _series_summary(key: str, points: list[tuple[date, float]], days: int) -> dict[str, Any]:
    label, unit, delta_unit, _ = METRIC_META[key]
    first_day, first = points[0]
    last_day, last = points[-1]
    previous = points[-2][1] if len(points) >= 2 else None
    delta_latest = None if previous is None else last - previous
    delta_period = last - first
    values = [value for _, value in points]

    if len(points) == 1:
        headline = f"{label}: {_fmt(last)} {unit}. Un registro en el período."
    else:
        verb = "subió" if delta_period > 0 else "bajó" if delta_period < 0 else "no cambió"
        if key in {"body_fat_pct", "body_water_pct"}:
            headline = f"{label} {verb}: {_fmt(first)}% → {_fmt(last)}%."
        elif key == "visceral_fat_index":
            headline = f"{label} {verb}: {_fmt(first)} → {_fmt(last)}."
        else:
            amount = "" if delta_period == 0 else f" {_fmt(abs(delta_period))} {delta_unit}"
            headline = (
                f"{label} {verb}{amount}: {_fmt(first)} {unit} → {_fmt(last)} {unit}. "
                f"Último cambio: {_signed(delta_latest)} {delta_unit}."
            )

    return {
        "key": key,
        "label": label,
        "unit": unit,
        "delta_unit": delta_unit,
        "sample_count": len(points),
        "first_date": first_day.isoformat(),
        "last_date": last_day.isoformat(),
        "first": _round(first),
        "current": _round(last),
        "previous": _round(previous),
        "delta_latest": _round(delta_latest),
        "delta_period": _round(delta_period),
        "average": _round(mean(values)),
        "minimum": _round(min(values)),
        "maximum": _round(max(values)),
        "direction_latest": _direction(delta_latest, GUARD_BANDS.get(key, 0.0)),
        "headline": headline,
    }


def energy_history(db: Session, days: int) -> list[dict[str, Any]]:
    today = datetime.now(settings.timezone).date()
    start = today - timedelta(days=days - 1)
    snapshots = [item for item in _snapshots(db) if "weight_kg" in item["values"]]
    if not snapshots:
        return []

    rows: list[dict[str, Any]] = []
    previous_body: dict[str, Any] | None = None
    for offset in range(days):
        day = start + timedelta(days=offset)
        available = [item for item in snapshots if item["date"] <= day]
        if not available:
            continue
        body = available[-1]
        body_index = snapshots.index(body)
        previous_body = snapshots[body_index - 1] if body_index > 0 else None
        state = _energy_state(db, body, previous_body, day_override=day)
        rows.append({
            "date": day.isoformat(),
            "weight_kg": _round(_value(body, "weight_kg")),
            "resting_kcal": state.get("resting_kcal_day"),
            "activity_kcal": state.get("activity_kcal"),
            "activity_minutes": state.get("activity_minutes"),
            "accounted_expenditure_kcal": state.get("accounted_expenditure_kcal"),
            "intake_kcal": state.get("intake_kcal"),
            "balance_kcal": state.get("partial_balance_kcal"),
        })
    return rows


def trend_analysis(db: Session, days: int) -> dict[str, Any]:
    start = datetime.now(settings.timezone).date() - timedelta(days=days - 1)
    today = datetime.now(settings.timezone).date()
    summaries: dict[str, dict[str, Any]] = {}

    snapshots = _snapshots(db, start)
    for key in ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index"):
        points = [(item["date"], float(item["values"][key])) for item in snapshots if key in item["values"]]
        if points:
            summaries[key] = _series_summary(key, points, days)

    sleeps = list(
        db.scalars(
            select(SleepRecord)
            .where(
                SleepRecord.sleep_date >= start,
                SleepRecord.sleep_date <= today,
                SleepRecord.duration_min.is_not(None),
            )
            .order_by(SleepRecord.sleep_date.asc())
        ).all()
    )
    sleep_points = [(row.sleep_date, float(row.duration_min) / 60) for row in sleeps]
    if sleep_points:
        summaries["sleep_hours"] = _series_summary("sleep_hours", sleep_points, days)

    activity_by_day: dict[date, float] = defaultdict(float)
    for row in db.scalars(select(Activity).order_by(Activity.started_at.asc())).all():
        local_day = utc_naive_to_local_date(row.started_at)
        if start <= local_day <= today:
            activity_by_day[local_day] += float(row.duration_min)
    activity_points = [(day, activity_by_day[day]) for day in sorted(activity_by_day)]
    if activity_points:
        summaries["activity_minutes"] = _series_summary("activity_minutes", activity_points, days)

    findings: list[str] = []
    weighted = [item for item in snapshots if "weight_kg" in item["values"]]
    if len(weighted) >= 2:
        period_findings = _integrated_findings(weighted[-1], weighted[0])
        findings.extend(f"{item['label']}. {item['explanation']}" for item in period_findings[:4])

    for key in ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index"):
        item = summaries.get(key)
        if item and item["sample_count"] >= 2:
            findings.append(item["headline"])

    if "sleep_hours" in summaries:
        findings.append(summaries["sleep_hours"]["headline"])
    if "activity_minutes" in summaries:
        findings.append(summaries["activity_minutes"]["headline"])

    return {
        "days": days,
        "from_date": start.isoformat(),
        "to_date": today.isoformat(),
        "metric_summaries": summaries,
        "findings": findings,
    }


def interpret_body_composition(db: Session) -> dict[str, Any]:
    snapshots = _snapshots(db)
    weighted = [item for item in snapshots if "weight_kg" in item["values"]]

    if not weighted:
        return {
            "engine_version": ENGINE_VERSION,
            "status": "insufficient",
            "as_of": None,
            "compared_with": None,
            "confidence": {"level": "baja", "variables_compared": 0, "recent_measurements": 0, "gap_days": None},
            "headline": "Sin peso registrado.",
            "summary": "No hay datos corporales suficientes para calcular cambios.",
            "observations": [],
            "metric_messages": {},
            "hypotheses": [],
            "context_findings": _context_findings(db),
            "energy": {},
            "context_state": {},
            "connections": [],
            "limits": [],
            "decision_note": "0 variables comparadas.",
        }

    current = weighted[-1]
    baseline = weighted[0]
    previous_candidates = [item for item in weighted[:-1] if item["date"] < current["date"]]
    previous = previous_candidates[-1] if previous_candidates else None

    keys = (
        "weight_kg",
        "body_fat_pct",
        "fat_mass_est_kg",
        "lean_mass_est_kg",
        "muscle_mass_kg",
        "body_water_pct",
        "water_mass_est_kg",
        "visceral_fat_index",
    )
    empty = {"values": {}}
    observations = [
        obs
        for key in keys
        if (obs := _metric_observation(key, current, previous or empty, baseline))
    ]

    energy = _energy_state(db, current, previous)
    context_state = _context_state(db, current["date"])
    connections = _connected_findings(current, observations, energy, context_state)

    if previous is None:
        return {
            "engine_version": ENGINE_VERSION,
            "status": "baseline",
            "as_of": current["date"].isoformat(),
            "compared_with": None,
            "confidence": {"level": "baja", "variables_compared": 0, "recent_measurements": 1, "gap_days": None},
            "headline": f"Estado inicial registrado: {_fmt(_value(current, 'weight_kg'))} kg.",
            "summary": _energy_message(energy),
            "observations": observations,
            "metric_messages": _metric_messages(observations),
            "hypotheses": [],
            "context_findings": _context_findings(db),
            "energy": energy,
            "context_state": context_state,
            "connections": connections,
            "limits": [],
            "decision_note": f"{len(observations)} valores integrados en el estado inicial.",
        }

    findings = _integrated_findings(current, previous)
    confidence = _confidence(current, previous, snapshots)
    weight_delta = _delta(current, previous, "weight_kg") or 0.0

    if abs(weight_delta) < 1e-9:
        headline = f"Peso sin cambio: {_fmt(_value(previous, 'weight_kg'))} → {_fmt(_value(current, 'weight_kg'))} kg."
    elif weight_delta > 0:
        headline = f"Peso subió {_fmt(abs(weight_delta))} kg: {_fmt(_value(previous, 'weight_kg'))} → {_fmt(_value(current, 'weight_kg'))} kg."
    else:
        headline = f"Peso bajó {_fmt(abs(weight_delta))} kg: {_fmt(_value(previous, 'weight_kg'))} → {_fmt(_value(current, 'weight_kg'))} kg."

    return {
        "engine_version": ENGINE_VERSION,
        "status": "ready",
        "as_of": current["date"].isoformat(),
        "compared_with": previous["date"].isoformat(),
        "confidence": confidence,
        "headline": headline,
        "summary": _state_summary(observations, findings, energy),
        "observations": observations,
        "metric_messages": _metric_messages(observations),
        "hypotheses": findings,
        "context_findings": _context_findings(db),
        "energy": energy,
        "context_state": context_state,
        "connections": connections,
        "limits": [
            "TMB calculada con masa libre de grasa estimada: 370 + 21,6 × masa libre de grasa (kg).",
            "Calorías de actividad usan el dato del dispositivo cuando existe; si no, se estiman con MET, peso y duración.",
            "El balance mostrado es parcial: ingesta registrada menos TMB y actividad registrada.",
        ],
        "decision_note": (
            f"{confidence['variables_compared']} variables corporales principales cruzadas; "
            f"{confidence['recent_measurements']} mediciones recientes usadas para contexto."
        ),
    }
