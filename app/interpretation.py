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


ENGINE_VERSION = "v2.0"
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
    "muscle_mass_kg": ("Masa muscular", "kg", "kg", "estimado_por_dispositivo"),
    "body_water_pct": ("Agua corporal", "%", "puntos", "estimado_por_dispositivo"),
    "water_mass_est_kg": ("Masa de agua estimada", "kg", "kg", "derivado"),
    "visceral_fat_index": ("Grasa visceral", "índice", "puntos", "estimado_por_dispositivo"),
    "sleep_hours": ("Sueño", "h", "h", "observado"),
    "activity_minutes": ("Actividad", "min", "min", "observado"),
}

# Bandas operativas conservadoras para evitar narrar como relevante cualquier
# variación mínima. No representan error clínico certificado del dispositivo.
GUARD_BANDS = {
    "weight_kg": 0.20,
    "body_fat_pct": 0.20,
    "muscle_mass_kg": 0.20,
    "body_water_pct": 0.20,
    "visceral_fat_index": 0.50,
    "fat_mass_est_kg": 0.15,
    "water_mass_est_kg": 0.20,
    "sleep_hours": 0.25,
    "activity_minutes": 10.0,
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
    prefix = "+" if rounded > 0 else ""
    return f"{prefix}{_fmt(rounded, digits)}"


def _direction(delta: float | None, band: float) -> str:
    if delta is None:
        return "sin_comparacion"
    if abs(delta) <= band:
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
        # Última lectura válida de cada indicador en el día = lectura canónica.
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
            snapshot["fat_mass_est_kg"] = weight * fat_pct / 100
        if weight is not None and water_pct is not None:
            snapshot["water_mass_est_kg"] = weight * water_pct / 100
        snapshots.append(snapshot)
    return snapshots


def _value(snapshot: dict[str, Any], key: str) -> float | None:
    raw = snapshot.get(key, snapshot.get("values", {}).get(key))
    return None if raw is None else float(raw)


def _delta(current: dict[str, Any], previous: dict[str, Any], key: str) -> float | None:
    a, b = _value(current, key), _value(previous, key)
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


def _metric_messages(observations: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for obs in observations:
        current = f"{_fmt(obs['current'])} {obs['unit']}"
        if obs["delta"] is None:
            result[obs["key"]] = f"{obs['label']}: {current}. Primera lectura disponible."
            continue
        delta = f"{_signed(obs['delta'])} {obs['delta_unit']}"
        baseline = (
            f"; desde el inicio {_signed(obs['delta_baseline'])} {obs['delta_unit']}"
            if obs["delta_baseline"] is not None
            else ""
        )
        result[obs["key"]] = (
            f"{obs['label']}: {current}. Cambio frente a la medición anterior: {delta}{baseline}."
        )
    return result


def _confidence(current: dict[str, Any], previous: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    core = ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct")
    paired = sum(1 for key in core if _value(current, key) is not None and _value(previous, key) is not None)
    gap_days = (current["date"] - previous["date"]).days
    span_ok = current["measurement_span_min"] <= 180 and previous["measurement_span_min"] <= 180
    recent_count = sum(1 for item in snapshots if (current["date"] - item["date"]).days <= 7)

    if paired >= 4 and span_ok and recent_count >= 5 and 1 <= gap_days <= 3:
        level = "alta"
    elif paired >= 3 and 1 <= gap_days <= 7:
        level = "media"
    else:
        level = "baja"

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

    if abs(weight) <= GUARD_BANDS["weight_kg"]:
        findings.append({
            "code": "weight_stable",
            "label": "Peso sin cambio relevante",
            "confidence": "media",
            "explanation": f"El peso cambió {_signed(weight)} kg frente a la medición anterior.",
        })
    elif weight > 0:
        if water_mass is not None and water_mass > GUARD_BANDS["water_mass_est_kg"] and (
            fat_mass is None or fat_mass <= GUARD_BANDS["fat_mass_est_kg"]
        ):
            fat_text = (
                f" y la masa grasa estimada cambió {_signed(fat_mass)} kg"
                if fat_mass is not None else ""
            )
            findings.append({
                "code": "fluid_compatible_gain",
                "label": "El aumento de peso coincide principalmente con más agua estimada",
                "confidence": "media",
                "explanation": (
                    f"Peso {_signed(weight)} kg; masa de agua estimada {_signed(water_mass)} kg{fat_text}. "
                    "En esta comparación no aparece una subida clara de grasa estimada que explique el aumento de peso."
                ),
            })
        elif fat_mass is not None and fat_mass > GUARD_BANDS["fat_mass_est_kg"]:
            findings.append({
                "code": "fat_compatible_gain",
                "label": "El aumento de peso coincide con una subida de grasa estimada",
                "confidence": "baja",
                "explanation": (
                    f"Peso {_signed(weight)} kg y masa grasa estimada {_signed(fat_mass)} kg. "
                    "La señal existe en esta lectura, pero todavía no constituye una tendencia confirmada."
                ),
            })
    else:
        if fat_mass is not None and fat_mass < -GUARD_BANDS["fat_mass_est_kg"] and (
            water_mass is None or abs(water_mass) <= GUARD_BANDS["water_mass_est_kg"]
        ):
            findings.append({
                "code": "fat_compatible_loss",
                "label": "La bajada de peso coincide con una reducción de grasa estimada",
                "confidence": "media",
                "explanation": (
                    f"Peso {_signed(weight)} kg; masa grasa estimada {_signed(fat_mass)} kg"
                    + (f"; masa de agua estimada {_signed(water_mass)} kg." if water_mass is not None else ".")
                ),
            })
        elif water_mass is not None and water_mass < -GUARD_BANDS["water_mass_est_kg"] and (
            fat_mass is None or abs(fat_mass) <= GUARD_BANDS["fat_mass_est_kg"]
        ):
            findings.append({
                "code": "fluid_compatible_loss",
                "label": "La bajada de peso coincide principalmente con menos agua estimada",
                "confidence": "media",
                "explanation": (
                    f"Peso {_signed(weight)} kg; masa de agua estimada {_signed(water_mass)} kg"
                    + (f"; masa grasa estimada {_signed(fat_mass)} kg." if fat_mass is not None else ".")
                ),
            })

    if muscle is not None and water_mass is not None:
        if muscle > GUARD_BANDS["muscle_mass_kg"] and water_mass > GUARD_BANDS["water_mass_est_kg"]:
            findings.append({
                "code": "muscle_water_up",
                "label": "Músculo estimado y agua estimada subieron al mismo tiempo",
                "confidence": "media",
                "explanation": f"Masa muscular estimada {_signed(muscle)} kg y masa de agua estimada {_signed(water_mass)} kg.",
            })
        elif muscle < -GUARD_BANDS["muscle_mass_kg"] and water_mass < -GUARD_BANDS["water_mass_est_kg"]:
            findings.append({
                "code": "muscle_water_down",
                "label": "Músculo estimado y agua estimada bajaron al mismo tiempo",
                "confidence": "media",
                "explanation": f"Masa muscular estimada {_signed(muscle)} kg y masa de agua estimada {_signed(water_mass)} kg.",
            })

    if fat_pct is not None and water_pct is not None:
        if fat_pct < -GUARD_BANDS["body_fat_pct"] and water_pct > GUARD_BANDS["body_water_pct"]:
            findings.append({
                "code": "fat_down_water_up",
                "label": "Grasa estimada bajó mientras el agua estimada subió",
                "confidence": "media",
                "explanation": f"Grasa corporal {_signed(fat_pct)} puntos y agua corporal {_signed(water_pct)} puntos.",
            })
        elif fat_pct > GUARD_BANDS["body_fat_pct"] and water_pct < -GUARD_BANDS["body_water_pct"]:
            findings.append({
                "code": "fat_up_water_down",
                "label": "Grasa estimada subió mientras el agua estimada bajó",
                "confidence": "media",
                "explanation": f"Grasa corporal {_signed(fat_pct)} puntos y agua corporal {_signed(water_pct)} puntos.",
            })

    if visceral is not None and abs(visceral) > GUARD_BANDS["visceral_fat_index"]:
        findings.append({
            "code": "visceral_change",
            "label": "También cambió el índice de grasa visceral estimado",
            "confidence": "baja",
            "explanation": f"Índice de grasa visceral: {_signed(visceral)} puntos frente a la medición anterior.",
        })

    if not findings:
        parts = [f"peso {_signed(weight)} kg"]
        if fat_mass is not None:
            parts.append(f"masa grasa estimada {_signed(fat_mass)} kg")
        if water_mass is not None:
            parts.append(f"masa de agua estimada {_signed(water_mass)} kg")
        if muscle is not None:
            parts.append(f"músculo estimado {_signed(muscle)} kg")
        findings.append({
            "code": "mixed_change",
            "label": "Cambio corporal mixto",
            "confidence": "baja",
            "explanation": "En la comparación actual: " + ", ".join(parts) + ". No aparece un componente dominante.",
        })
    return findings


def _context_findings(db: Session) -> list[str]:
    findings: list[str] = []

    sleeps = list(db.scalars(select(SleepRecord).where(SleepRecord.duration_min.is_not(None)).order_by(SleepRecord.sleep_date.asc())).all())
    if sleeps:
        latest = sleeps[-1]
        latest_h = float(latest.duration_min) / 60
        if len(sleeps) >= 2:
            previous_h = float(sleeps[-2].duration_min) / 60
            findings.append(
                f"Sueño: {_fmt(latest_h, 1)} h en el último registro ({_signed(latest_h - previous_h, 1)} h frente al anterior)."
            )
        else:
            findings.append(f"Sueño: {_fmt(latest_h, 1)} h en el último registro.")

    activity_by_day: dict[date, float] = defaultdict(float)
    for row in db.scalars(select(Activity).order_by(Activity.started_at.asc())).all():
        activity_by_day[utc_naive_to_local_date(row.started_at)] += float(row.duration_min)
    activity_days = sorted(activity_by_day)
    if activity_days:
        latest_day = activity_days[-1]
        latest_min = activity_by_day[latest_day]
        if len(activity_days) >= 2:
            previous_min = activity_by_day[activity_days[-2]]
            findings.append(
                f"Actividad: {_fmt(latest_min, 0)} min en el último día con registro ({_signed(latest_min - previous_min, 0)} min frente al día anterior con datos)."
            )
        else:
            findings.append(f"Actividad: {_fmt(latest_min, 0)} min en el último día con registro.")

    nutrition = list(db.scalars(select(NutritionRecord).order_by(NutritionRecord.nutrition_date.asc())).all())
    if nutrition:
        latest = nutrition[-1]
        parts = []
        if latest.calories is not None:
            parts.append(f"{_fmt(latest.calories, 0)} kcal")
        if latest.protein_g is not None:
            parts.append(f"{_fmt(latest.protein_g, 0)} g de proteína")
        if latest.carbs_g is not None:
            parts.append(f"{_fmt(latest.carbs_g, 0)} g de carbohidratos")
        if parts:
            findings.append(f"Nutrición ({latest.nutrition_date.isoformat()}): " + ", ".join(parts) + ".")

    strength_by_day: dict[date, dict[str, float]] = defaultdict(lambda: {"sets": 0.0, "volume": 0.0})
    for row in db.scalars(select(StrengthSet).order_by(StrengthSet.performed_at.asc())).all():
        day = utc_naive_to_local_date(row.performed_at)
        strength_by_day[day]["sets"] += 1
        strength_by_day[day]["volume"] += float(row.load_kg) * int(row.reps)
    strength_days = sorted(strength_by_day)
    if strength_days:
        day = strength_days[-1]
        values = strength_by_day[day]
        findings.append(
            f"Fuerza ({day.isoformat()}): {_fmt(values['sets'], 0)} series registradas y {_fmt(values['volume'], 0)} kg·repetición de volumen externo."
        )

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
        headline = f"{label}: {_fmt(last)} {unit}. Un registro disponible en el período."
    else:
        headline = (
            f"{label}: {_fmt(last)} {unit}. Último cambio {_signed(delta_latest)} {delta_unit}; "
            f"cambio en {days} días {_signed(delta_period)} {delta_unit}."
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


def trend_analysis(db: Session, days: int) -> dict[str, Any]:
    start = datetime.now(settings.timezone).date() - timedelta(days=days - 1)
    summaries: dict[str, dict[str, Any]] = {}

    snapshots = _snapshots(db, start)
    for key in ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index"):
        points = [(item["date"], float(item["values"][key])) for item in snapshots if key in item["values"]]
        if points:
            summaries[key] = _series_summary(key, points, days)

    today = datetime.now(settings.timezone).date()
    sleeps = list(db.scalars(select(SleepRecord).where(SleepRecord.sleep_date >= start, SleepRecord.sleep_date <= today, SleepRecord.duration_min.is_not(None)).order_by(SleepRecord.sleep_date.asc())).all())
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

    visible_findings: list[str] = []
    for key in ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct", "visceral_fat_index"):
        item = summaries.get(key)
        if item and item["sample_count"] >= 2:
            visible_findings.append(item["headline"])

    if "sleep_hours" in summaries:
        item = summaries["sleep_hours"]
        visible_findings.append(
            f"Sueño medio del período: {_fmt(item['average'], 1)} h; último registro {_fmt(item['current'], 1)} h."
        )
    if "activity_minutes" in summaries:
        item = summaries["activity_minutes"]
        visible_findings.append(
            f"Actividad media en días con registro: {_fmt(item['average'], 0)} min; último día {_fmt(item['current'], 0)} min."
        )

    return {
        "days": days,
        "from_date": start.isoformat(),
        "to_date": datetime.now(settings.timezone).date().isoformat(),
        "metric_summaries": summaries,
        "findings": visible_findings,
    }


def interpret_body_composition(db: Session) -> dict[str, Any]:
    snapshots = _snapshots(db)
    weighted = [item for item in snapshots if "weight_kg" in item["values"]]

    limits = [
        "Grasa, músculo, agua y grasa visceral provienen de estimaciones BIA y pueden variar con las condiciones de la medición.",
        "La masa grasa estimada es peso × porcentaje de grasa; la masa de agua estimada es peso × porcentaje de agua.",
        "Agua y músculo estimados no son compartimentos independientes, por lo que sus cambios no se suman para explicar el peso.",
        "Una comparación aislada no convierte una estimación en una medición clínica de tejido ganado o perdido.",
    ]

    if not weighted:
        return {
            "engine_version": ENGINE_VERSION,
            "status": "insufficient",
            "as_of": None,
            "compared_with": None,
            "confidence": {"level": "baja", "variables_compared": 0, "recent_measurements": 0, "gap_days": None},
            "headline": "No hay una medición de peso válida para calcular cambios.",
            "summary": "Sin comparación corporal disponible.",
            "observations": [],
            "metric_messages": {},
            "hypotheses": [],
            "context_findings": _context_findings(db),
            "limits": limits,
            "decision_note": "0 variables corporales comparadas.",
        }

    current = weighted[-1]
    baseline = weighted[0]
    previous_candidates = [item for item in weighted[:-1] if item["date"] < current["date"]]

    if not previous_candidates:
        empty = {"values": {}}
        observations = [
            obs for key in (
                "weight_kg", "body_fat_pct", "fat_mass_est_kg", "muscle_mass_kg",
                "body_water_pct", "water_mass_est_kg", "visceral_fat_index"
            )
            if (obs := _metric_observation(key, current, empty, baseline))
        ]
        return {
            "engine_version": ENGINE_VERSION,
            "status": "baseline",
            "as_of": current["date"].isoformat(),
            "compared_with": None,
            "confidence": {"level": "baja", "variables_compared": 0, "recent_measurements": 1, "gap_days": None},
            "headline": f"Línea base corporal registrada el {current['date'].isoformat()}.",
            "summary": "Todavía no existe una segunda fecha corporal comparable.",
            "observations": observations,
            "metric_messages": _metric_messages(observations),
            "hypotheses": [],
            "context_findings": _context_findings(db),
            "limits": limits,
            "decision_note": f"{len(observations)} valores disponibles en la línea base.",
        }

    previous = previous_candidates[-1]
    observations = [
        obs for key in (
            "weight_kg", "body_fat_pct", "fat_mass_est_kg", "muscle_mass_kg",
            "body_water_pct", "water_mass_est_kg", "visceral_fat_index"
        )
        if (obs := _metric_observation(key, current, previous, baseline))
    ]

    findings = _integrated_findings(current, previous)
    confidence = _confidence(current, previous, snapshots)
    weight_delta = _delta(current, previous, "weight_kg") or 0.0
    body_count = sum(1 for item in observations if item["delta"] is not None)

    if abs(weight_delta) <= GUARD_BANDS["weight_kg"]:
        headline = f"Peso {_fmt(_value(current, 'weight_kg'))} kg: cambio de {_signed(weight_delta)} kg frente al registro anterior."
    elif weight_delta > 0:
        headline = f"Peso {_fmt(_value(current, 'weight_kg'))} kg: subió {_fmt(abs(weight_delta))} kg frente al registro anterior."
    else:
        headline = f"Peso {_fmt(_value(current, 'weight_kg'))} kg: bajó {_fmt(abs(weight_delta))} kg frente al registro anterior."

    summary = " ".join(item["explanation"] for item in findings[:2])

    return {
        "engine_version": ENGINE_VERSION,
        "status": "ready",
        "as_of": current["date"].isoformat(),
        "compared_with": previous["date"].isoformat(),
        "confidence": confidence,
        "headline": headline,
        "summary": summary,
        "observations": observations,
        "metric_messages": _metric_messages(observations),
        "hypotheses": findings,
        "context_findings": _context_findings(db),
        "limits": limits,
        "decision_note": (
            f"Comparación automática {previous['date'].isoformat()} → {current['date'].isoformat()}: "
            f"{body_count} cambios corporales calculados."
        ),
    }
