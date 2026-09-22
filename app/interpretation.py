from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MetricRecord
from .timeutils import utc_naive_to_local_date


ENGINE_VERSION = "v1.0"
METRIC_KEYS = (
    "weight_kg",
    "body_fat_pct",
    "muscle_mass_kg",
    "body_water_pct",
    "visceral_fat_index",
    "bone_mass_kg",
)

# Bandas operativas conservadoras para evitar narrar como relevante cualquier
# variación mínima. NO representan error clínico validado del dispositivo.
GUARD_BANDS = {
    "weight_kg": 0.20,
    "body_fat_pct": 0.20,
    "muscle_mass_kg": 0.20,
    "body_water_pct": 0.20,
    "visceral_fat_index": 0.50,
    "fat_mass_est_kg": 0.15,
    "water_mass_est_kg": 0.20,
}


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(float(value), digits)


def _signed(value: float, digits: int = 2) -> str:
    rounded = round(value, digits)
    return f"+{rounded}" if rounded > 0 else str(rounded)


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


def _snapshots(db: Session) -> list[dict[str, Any]]:
    by_day: dict[Any, dict[str, MetricRecord]] = defaultdict(dict)
    for row in _usable_metrics(db):
        day = utc_naive_to_local_date(row.captured_at)
        # La última lectura válida de cada indicador en el día es la canónica.
        by_day[day][row.metric_key] = row

    snapshots: list[dict[str, Any]] = []
    for day in sorted(by_day):
        rows = by_day[day]
        values = {
            key: float(row.value)
            for key, row in rows.items()
            if row.value is not None
        }
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


def _delta(current: dict[str, Any], previous: dict[str, Any], key: str) -> float | None:
    current_value = current.get(key, current.get("values", {}).get(key))
    previous_value = previous.get(key, previous.get("values", {}).get(key))
    if current_value is None or previous_value is None:
        return None
    return float(current_value) - float(previous_value)


def _direction(delta: float | None, band: float) -> str:
    if delta is None:
        return "sin_comparacion"
    if abs(delta) <= band:
        return "estable"
    return "subio" if delta > 0 else "bajo"


def _metric_observation(
    key: str,
    label: str,
    unit: str,
    current: dict[str, Any],
    previous: dict[str, Any],
    kind: str,
    precision: int = 2,
) -> dict[str, Any] | None:
    current_value = current.get(key, current.get("values", {}).get(key))
    previous_value = previous.get(key, previous.get("values", {}).get(key))
    if current_value is None:
        return None

    delta = None if previous_value is None else float(current_value) - float(previous_value)
    band = GUARD_BANDS.get(key, 0.0)
    return {
        "key": key,
        "label": label,
        "kind": kind,
        "unit": unit,
        "current": _round(float(current_value), precision),
        "previous": _round(float(previous_value), precision) if previous_value is not None else None,
        "delta": _round(delta, precision),
        "direction": _direction(delta, band),
    }


def _confidence(current: dict[str, Any], previous: dict[str, Any], snapshots: list[dict[str, Any]]) -> dict[str, Any]:
    core = ("weight_kg", "body_fat_pct", "muscle_mass_kg", "body_water_pct")
    paired = sum(
        1
        for key in core
        if key in current["values"] and key in previous["values"]
    )
    gap_days = (current["date"] - previous["date"]).days
    span_ok = current["measurement_span_min"] <= 180 and previous["measurement_span_min"] <= 180
    recent_count = sum(1 for item in snapshots if (current["date"] - item["date"]).days <= 7)

    basis: list[str] = []
    if paired >= 4:
        basis.append("peso, grasa, músculo y agua están disponibles en ambas mediciones")
    elif paired >= 2:
        basis.append("solo una parte de la composición corporal está disponible en ambas mediciones")
    else:
        basis.append("faltan variables suficientes para cruzar la composición corporal")

    if span_ok:
        basis.append("las variables del mismo día fueron registradas en una ventana temporal coherente")
    else:
        basis.append("las variables del mismo día están separadas por varias horas y pueden no ser comparables")

    if recent_count >= 5:
        basis.append("hay varias mediciones recientes para contrastar la tendencia")
    else:
        basis.append("todavía hay poco historial reciente; una lectura aislada no confirma una tendencia")

    if paired >= 4 and span_ok and recent_count >= 5 and 1 <= gap_days <= 3:
        level = "alta"
    elif paired >= 3 and 1 <= gap_days <= 7:
        level = "media"
    else:
        level = "baja"

    return {"level": level, "basis": basis}


def _metric_messages(observations: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for obs in observations:
        key = obs["key"]
        delta = obs["delta"]
        if delta is None:
            out[key] = f"{obs['label']}: aún no existe una medición previa comparable."
            continue

        if obs["direction"] == "estable":
            out[key] = (
                f"{obs['label']}: cambio pequeño ({_signed(delta)} {obs['unit']}); "
                "se mantiene dentro de la banda operativa de estabilidad del motor."
            )
        elif obs["direction"] == "subio":
            out[key] = f"{obs['label']}: subió {_round(abs(delta), 2)} {obs['unit']} frente a la medición comparable anterior."
        else:
            out[key] = f"{obs['label']}: bajó {_round(abs(delta), 2)} {obs['unit']} frente a la medición comparable anterior."
    return out


def _hypotheses(current: dict[str, Any], previous: dict[str, Any]) -> list[dict[str, str]]:
    weight_delta = _delta(current, previous, "weight_kg")
    fat_mass_delta = _delta(current, previous, "fat_mass_est_kg")
    water_mass_delta = _delta(current, previous, "water_mass_est_kg")
    muscle_delta = _delta(current, previous, "muscle_mass_kg")
    fat_pct_delta = _delta(current, previous, "body_fat_pct")

    if weight_delta is None:
        return []

    hypotheses: list[dict[str, str]] = []
    weight_dir = _direction(weight_delta, GUARD_BANDS["weight_kg"])

    if weight_dir == "estable":
        hypotheses.append({
            "code": "weight_stable",
            "label": "Peso estable",
            "confidence": "media",
            "explanation": (
                "El cambio de peso es pequeño. No hay base para atribuirlo a una ganancia o pérdida real de tejido."
            ),
        })
        return hypotheses

    if weight_delta > 0:
        if (
            water_mass_delta is not None
            and water_mass_delta > GUARD_BANDS["water_mass_est_kg"]
            and (fat_mass_delta is None or fat_mass_delta <= GUARD_BANDS["fat_mass_est_kg"])
        ):
            hypotheses.append({
                "code": "fluid_compatible_gain",
                "label": "Patrón compatible con mayor agua corporal",
                "confidence": "media",
                "explanation": (
                    "El peso subió mientras la estimación derivada de agua corporal también aumentó y la masa grasa estimada no mostró un aumento claro. "
                    "Esto es compatible con variación de líquidos, pero la báscula BIA no permite demostrar cuántos litros se retuvieron ni excluir otras causas."
                ),
            })
        if (
            fat_mass_delta is not None
            and fat_mass_delta > GUARD_BANDS["fat_mass_est_kg"]
            and (water_mass_delta is None or water_mass_delta <= GUARD_BANDS["water_mass_est_kg"])
        ):
            hypotheses.append({
                "code": "fat_compatible_gain",
                "label": "Aumento de grasa estimada que requiere confirmación",
                "confidence": "baja",
                "explanation": (
                    "La masa grasa derivada de peso × porcentaje de grasa aumentó. Una sola comparación BIA no demuestra ganancia real de grasa; debe confirmarse con mediciones repetidas en condiciones similares."
                ),
            })
        if (
            muscle_delta is not None
            and muscle_delta > GUARD_BANDS["muscle_mass_kg"]
            and water_mass_delta is not None
            and water_mass_delta > GUARD_BANDS["water_mass_est_kg"]
        ):
            hypotheses.append({
                "code": "muscle_water_coupled",
                "label": "Músculo estimado y agua subieron juntos",
                "confidence": "media",
                "explanation": (
                    "La báscula estimó más masa muscular al mismo tiempo que más agua corporal. En BIA ambas estimaciones están relacionadas con el estado de hidratación, por lo que no debe interpretarse automáticamente como tejido muscular nuevo."
                ),
            })

    if weight_delta < 0:
        if (
            fat_mass_delta is not None
            and fat_mass_delta < -GUARD_BANDS["fat_mass_est_kg"]
            and (water_mass_delta is None or abs(water_mass_delta) <= GUARD_BANDS["water_mass_est_kg"])
        ):
            hypotheses.append({
                "code": "fat_compatible_loss",
                "label": "Patrón compatible con reducción de grasa estimada",
                "confidence": "media",
                "explanation": (
                    "El peso bajó y la masa grasa derivada también disminuyó sin una caída clara del agua estimada. El patrón es compatible con reducción de grasa, pero necesita repetirse para considerarse tendencia."
                ),
            })
        if (
            water_mass_delta is not None
            and water_mass_delta < -GUARD_BANDS["water_mass_est_kg"]
            and (fat_mass_delta is None or abs(fat_mass_delta) <= GUARD_BANDS["fat_mass_est_kg"])
        ):
            hypotheses.append({
                "code": "fluid_compatible_loss",
                "label": "Patrón compatible con menor agua corporal",
                "confidence": "media",
                "explanation": (
                    "El peso bajó al mismo tiempo que la estimación derivada de agua corporal. Parte del descenso puede corresponder a variación de líquidos; no debe contarse automáticamente como grasa perdida."
                ),
            })

    if fat_pct_delta is not None and abs(fat_pct_delta) <= GUARD_BANDS["body_fat_pct"] and not hypotheses:
        hypotheses.append({
            "code": "undetermined",
            "label": "Cambio de peso sin explicación dominante",
            "confidence": "baja",
            "explanation": (
                "El peso cambió, pero las demás variables no muestran un patrón suficientemente claro para atribuirlo a grasa, agua o músculo."
            ),
        })

    if not hypotheses:
        hypotheses.append({
            "code": "undetermined",
            "label": "Datos insuficientes para atribuir el cambio",
            "confidence": "baja",
            "explanation": (
                "Existe un cambio de peso, pero faltan señales concordantes para explicar con seriedad qué componente lo produjo."
            ),
        })
    return hypotheses


def interpret_body_composition(db: Session) -> dict[str, Any]:
    snapshots = _snapshots(db)
    weighted = [item for item in snapshots if "weight_kg" in item["values"]]

    limits = [
        "La báscula de bioimpedancia (BIA) estima grasa, músculo y agua; esos valores pueden variar con hidratación, comida, ejercicio, hora y condiciones de medición.",
        "La masa grasa estimada se calcula como peso × porcentaje de grasa. Es una derivación matemática de la lectura de la báscula, no una medición directa de tejido.",
        "La masa de agua estimada se calcula como peso × porcentaje de agua y se usa solo para comparar tendencias. No equivale de forma fiable a litros retenidos o perdidos.",
        "Los umbrales del motor son bandas operativas para evitar reaccionar a variaciones pequeñas; no son márgenes clínicos certificados del dispositivo.",
    ]

    if not weighted:
        return {
            "engine_version": ENGINE_VERSION,
            "status": "insufficient",
            "as_of": None,
            "compared_with": None,
            "confidence": {"level": "baja", "basis": ["no hay mediciones de peso válidas"]},
            "headline": "Aún no hay datos suficientes para interpretar cambios corporales.",
            "summary": "Registra una medición completa para crear la línea base.",
            "observations": [],
            "metric_messages": {},
            "hypotheses": [],
            "limits": limits,
            "decision_note": "No se genera una explicación fisiológica sin una comparación válida.",
        }

    current = weighted[-1]
    previous_candidates = [item for item in weighted[:-1] if item["date"] < current["date"]]
    if not previous_candidates:
        observations = [
            obs
            for obs in [
                _metric_observation("weight_kg", "Peso", "kg", current, {"values": {}}, "observado"),
                _metric_observation("body_fat_pct", "Grasa corporal", "%", current, {"values": {}}, "estimado_por_dispositivo"),
                _metric_observation("muscle_mass_kg", "Masa muscular", "kg", current, {"values": {}}, "estimado_por_dispositivo"),
                _metric_observation("body_water_pct", "Agua corporal", "%", current, {"values": {}}, "estimado_por_dispositivo"),
                _metric_observation("visceral_fat_index", "Grasa visceral", "índice", current, {"values": {}}, "estimado_por_dispositivo"),
            ]
            if obs
        ]
        return {
            "engine_version": ENGINE_VERSION,
            "status": "baseline",
            "as_of": current["date"].isoformat(),
            "compared_with": None,
            "confidence": {"level": "baja", "basis": ["solo existe una fecha con peso válido"]},
            "headline": "Línea base registrada.",
            "summary": "Todavía no hay una medición previa comparable. El motor mostrará cambios cuando exista al menos una segunda fecha válida.",
            "observations": observations,
            "metric_messages": _metric_messages(observations),
            "hypotheses": [],
            "limits": limits,
            "decision_note": "La primera medición describe el punto de partida; no permite afirmar tendencia.",
        }

    previous = previous_candidates[-1]
    observations = [
        obs
        for obs in [
            _metric_observation("weight_kg", "Peso", "kg", current, previous, "observado"),
            _metric_observation("body_fat_pct", "Grasa corporal", "%", current, previous, "estimado_por_dispositivo"),
            _metric_observation("fat_mass_est_kg", "Masa grasa estimada", "kg", current, previous, "derivado"),
            _metric_observation("muscle_mass_kg", "Masa muscular", "kg", current, previous, "estimado_por_dispositivo"),
            _metric_observation("body_water_pct", "Agua corporal", "%", current, previous, "estimado_por_dispositivo"),
            _metric_observation("water_mass_est_kg", "Masa de agua estimada", "kg", current, previous, "derivado"),
            _metric_observation("visceral_fat_index", "Grasa visceral", "índice", current, previous, "estimado_por_dispositivo"),
        ]
        if obs
    ]

    hypotheses = _hypotheses(current, previous)
    confidence = _confidence(current, previous, snapshots)
    weight_delta = _delta(current, previous, "weight_kg") or 0.0
    primary = hypotheses[0]

    if abs(weight_delta) <= GUARD_BANDS["weight_kg"]:
        headline = f"El peso se mantiene prácticamente estable ({_signed(weight_delta)} kg)."
    elif weight_delta > 0:
        headline = f"El peso subió {_round(abs(weight_delta), 2)} kg desde la medición comparable anterior."
    else:
        headline = f"El peso bajó {_round(abs(weight_delta), 2)} kg desde la medición comparable anterior."

    summary = (
        f"{headline} {primary['explanation']} "
        f"Confianza global del análisis: {confidence['level']}."
    )

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
        "hypotheses": hypotheses,
        "limits": limits,
        "decision_note": (
            "El motor separa aritmética de interpretación: los deltas se calculan directamente; las explicaciones fisiológicas se presentan como hipótesis y deben confirmarse con tendencia, contexto y mediciones repetidas."
        ),
    }
