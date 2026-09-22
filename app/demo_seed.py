from datetime import date, datetime, time, timedelta

from sqlalchemy import func, select

from .config import settings
from .db import SessionLocal
from .models import Activity, MetricRecord, Reminder, SleepRecord, StrengthSet


def _local_dt(day: date, hh: int, mm: int = 0) -> datetime:
    return datetime.combine(day, time(hh, mm))


def seed_demo_data() -> None:
    """Carga datos simulados plausibles solo cuando DEMO_DATA=true.

    Nunca se presentan como mediciones reales del usuario.
    """
    db = SessionLocal()
    try:
        existing = db.scalar(select(func.count()).select_from(MetricRecord))
        if existing:
            return

        today = datetime.now(settings.timezone).date()
        start = today - timedelta(days=13)

        # Trayectoria simulada cercana al contexto conocido: ~118 kg actuales,
        # con variación diaria realista y descenso moderado de tendencia.
        weights = [120.1,119.9,119.7,119.8,119.4,119.2,119.0,119.1,118.8,118.6,118.5,118.3,118.2,118.0]
        fat =     [34.6,34.5,34.4,34.5,34.2,34.1,34.0,34.1,33.9,33.8,33.7,33.6,33.5,33.4]
        muscle =  [73.0,73.1,73.0,72.9,73.1,73.0,73.1,73.0,73.2,73.1,73.1,73.2,73.1,73.2]
        water =   [47.5,47.7,47.8,47.6,48.0,48.1,48.0,47.9,48.2,48.3,48.2,48.4,48.3,48.5]

        for i, w in enumerate(weights):
            d = start + timedelta(days=i)
            captured = _local_dt(d, 6, 20)
            evidence=f"demo:xiaomi:{d.isoformat()}"
            metrics=[
                ("weight_kg", w, "kg", "measured"),
                ("body_fat_pct", fat[i], "%", "device_estimated"),
                ("muscle_mass_kg", muscle[i], "kg", "device_estimated"),
                ("body_water_pct", water[i], "%", "device_estimated"),
                ("visceral_fat_index", 16.0 if i < 7 else 15.0, "index", "device_estimated"),
            ]
            for key,val,unit,origin in metrics:
                db.add(MetricRecord(
                    captured_at=captured, metric_key=key, value=val, unit=unit,
                    source="SIMULACIÓN · Xiaomi Mi Body Composition Scale 2",
                    origin=origin, validation_status="estimated" if key!="weight_kg" else "confirmed",
                    confidence=0.5, evidence_ref="DEMO_DATA", source_event_id=evidence,
                    notes="Dato simulado para visualizar el producto; no es una medición real."
                ))

            # Actividad simulada coherente con la rutina documentada:
            # caminata de mañana + fuerza (lunes-sábado) + sesión funcional corta
            # y, algunos días, caminata suave de noche.
            morning_walk = [50,60,55,60,60,65,40,60,55,60,60,60,70,60][i]
            db.add(Activity(
                started_at=_local_dt(d, 8, 0), activity_type="caminata_manana", duration_min=morning_walk,
                speed_kmh=4.5, device_calories=round(morning_walk*5.5,1), perceived_exertion=3,
                pain_score=0, integrated=True, integration_context="conversación/estudio",
                source="SIMULACIÓN", source_event_id=f"demo:walk-am:{d.isoformat()}",
                notes="Caminata matutina simulada."
            ))

            weekday = d.weekday()  # lunes=0
            if weekday < 6:
                strength_minutes = [70,75,75,70,75,80][weekday]
                db.add(Activity(
                    started_at=_local_dt(d, 9, 15), activity_type="fuerza_gimnasio", duration_min=strength_minutes,
                    perceived_exertion=6, pain_score=0, integrated=False,
                    integration_context=None, source="SIMULACIÓN",
                    source_event_id=f"demo:gym:{d.isoformat()}",
                    notes="Sesión de fuerza simulada según la división semanal."
                ))

                # No todos los días se completa el bloque funcional: así la adherencia es visible.
                if i not in {3, 8, 12}:
                    functional_minutes = 20 if i % 2 == 0 else 25
                    db.add(Activity(
                        started_at=_local_dt(d, 16, 30), activity_type="funcional_tarde", duration_min=functional_minutes,
                        perceived_exertion=5, pain_score=0, integrated=False,
                        source="SIMULACIÓN", source_event_id=f"demo:functional:{d.isoformat()}",
                        notes="Sesión funcional simulada."
                    ))

                if i in {1,2,4,5,7,9,10,11,13}:
                    evening_walk = 30 if i % 3 else 40
                    db.add(Activity(
                        started_at=_local_dt(d, 19, 30), activity_type="caminata_noche", duration_min=evening_walk,
                        speed_kmh=4.3, device_calories=round(evening_walk*5.2,1), perceived_exertion=2,
                        pain_score=0, integrated=True, integration_context="contenido/conversación",
                        source="SIMULACIÓN", source_event_id=f"demo:walk-pm:{d.isoformat()}",
                        notes="Caminata nocturna simulada."
                    ))

            # Sueño: refleja el riesgo conocido de algunas noches cortas sin convertirlo en diagnóstico.
            sleep_hours=[6.4,6.8,7.1,5.9,7.0,6.6,7.2,5.4,6.2,7.0,6.7,7.3,6.5,6.9][i]
            db.add(SleepRecord(
                sleep_date=d, duration_min=round(sleep_hours*60),
                energy_score=7 if sleep_hours>=6.5 else 5,
                fatigue_score=3 if sleep_hours>=6.5 else 6,
                source="SIMULACIÓN · Apple Watch", notes="Dato simulado."
            ))

        # Algunas series recientes para que fuerza tenga historial visible.
        for j,(exercise,load,reps) in enumerate([
            ("Chest Press",35,10),("Lat Pulldown",40,10),("Leg Press",90,12),
            ("Shoulder Press",25,10),("Seated Row",40,11)
        ],1):
            db.add(StrengthSet(
                performed_at=_local_dt(today-timedelta(days=j),9,20),
                exercise_name=exercise,set_number=1,load_kg=load,reps=reps,rpe=6,pain_score=0,
                notes="Serie simulada para demostración.",source_event_id=f"demo:strength:{j}"
            ))

        for title,kind,clock in [
            ("Caminata de la tarde","activity","17:30"),
            ("Ejercicio funcional 20 min","activity","19:00"),
            ("Preparar descanso","recovery","22:30"),
        ]:
            db.add(Reminder(title=title,kind=kind,time_local=clock,recurrence="daily",active=True,snooze_minutes=15,notes="Recordatorio de demostración."))

        db.commit()
    finally:
        db.close()
