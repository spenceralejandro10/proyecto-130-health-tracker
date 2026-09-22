from datetime import date, datetime

from fastapi.testclient import TestClient

from app.main import app
from app.config import settings

client = TestClient(app)


def test_metric_idempotency_and_dashboard():
    payload = {
        "captured_at": "2026-09-22T06:10:00",
        "metric_key": "weight_kg",
        "value": 118.0,
        "unit": "kg",
        "source": "Xiaomi Mi Body Composition Scale 2",
        "origin": "measured",
        "validation_status": "confirmed",
        "source_event_id": "photo-2026-09-22-weight",
    }
    assert client.post("/api/metrics", json=payload).status_code == 201
    assert client.post("/api/metrics", json=payload).status_code == 409
    dash = client.get("/api/dashboard").json()
    assert dash["project_started"] is True
    assert dash["current_weight_kg"] == 118.0
    assert dash["baseline_weight_kg"] == 118.0


def test_activity_dashboard_minutes():
    payload = {
        "started_at": datetime.now(settings.timezone).replace(tzinfo=None, microsecond=0).isoformat(),
        "activity_type": "walk",
        "duration_min": 45,
        "integrated": True,
        "integration_context": "conversation",
    }
    assert client.post("/api/activities", json=payload).status_code == 201
    dash = client.get("/api/dashboard").json()
    assert dash["activity_minutes_today"] >= 45
    assert dash["integrated_minutes_today"] >= 45


def test_strength_last_set():
    payload = {
        "performed_at": datetime.now().replace(microsecond=0).isoformat(),
        "exercise_name": "Chest Press",
        "set_number": 1,
        "load_kg": 30,
        "reps": 10,
    }
    assert client.post("/api/strength", json=payload).status_code == 201
    result = client.get("/api/strength/last/Chest%20Press")
    assert result.status_code == 200
    assert result.json()["reps"] == 10


def test_sleep_alert():
    payload = {"sleep_date": date.today().isoformat(), "duration_min": 300, "fatigue_score": 8}
    assert client.post("/api/sleep", json=payload).status_code == 201
    dash = client.get("/api/dashboard").json()
    assert any("sueño" in x.lower() or "fatiga" in x.lower() for x in dash["alerts"])


def test_decision_audit():
    created = client.post("/api/decisions", json={"variable":"walk_minutes","reason":"prueba","old_value":"30","new_value":"45","observation_days":7})
    assert created.status_code == 201
    decision_id = created.json()["id"]
    evaluated = client.patch(f"/api/decisions/{decision_id}/result", json={"result":"sin conclusión causal"})
    assert evaluated.status_code == 200
    logs = client.get("/api/audit").json()
    assert any(x["entity_type"] == "decision" and x["action"] == "evaluate" for x in logs)


def test_reminder_flow():
    created = client.post("/api/reminders", json={"title":"Caminata de la tarde","time_local":"18:00"})
    assert created.status_code == 201
    rid = created.json()["id"]
    event = client.post(f"/api/reminders/{rid}/event", json={"action":"done"})
    assert event.status_code == 201


def test_export_contains_audit():
    export = client.get("/api/export")
    assert export.status_code == 200
    body = export.json()
    assert body["schema_version"] == "v1"
    assert "audit" in body["data"]


def test_same_evidence_can_create_multiple_metrics():
    base = {
        "captured_at": "2026-09-23T06:10:00",
        "unit": "%",
        "source": "Xiaomi Mi Body Composition Scale 2",
        "origin": "device_estimated",
        "validation_status": "estimated",
        "source_event_id": "xiaomi-summary-2026-09-23",
    }
    fat = {**base, "metric_key": "body_fat_pct", "value": 32.1}
    water = {**base, "metric_key": "body_water_pct", "value": 48.2}
    assert client.post("/api/metrics", json=fat).status_code == 201
    assert client.post("/api/metrics", json=water).status_code == 201
    dash = client.get("/api/dashboard").json()
    assert dash["composition"]["body_fat_pct"]["value"] == 32.1
    assert dash["composition"]["body_water_pct"]["value"] == 48.2


def test_reminder_can_be_updated_and_disabled():
    created = client.post("/api/reminders", json={"title":"Funcional","time_local":"17:30"})
    assert created.status_code == 201
    rid = created.json()["id"]
    updated = client.patch(f"/api/reminders/{rid}", json={"time_local":"18:15","active":False})
    assert updated.status_code == 200
    assert updated.json()["time_local"] == "18:15"
    assert updated.json()["active"] is False
