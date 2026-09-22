from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _metric(day: str, key: str, value: float, unit: str, origin: str = "device_estimated") -> None:
    response = client.post(
        "/api/metrics",
        json={
            "captured_at": f"{day}T06:15:00-05:00",
            "metric_key": key,
            "value": value,
            "unit": unit,
            "source": "BIA test fixture",
            "origin": origin,
            "validation_status": "confirmed" if key == "weight_kg" else "estimated",
            "source_event_id": f"interpretation-{day}-{key}",
        },
    )
    assert response.status_code == 201


def test_interpretation_distinguishes_observation_from_hypothesis():
    baseline = {
        "weight_kg": (118.0, "kg"),
        "body_fat_pct": (32.0, "%"),
        "muscle_mass_kg": (60.0, "kg"),
        "body_water_pct": (48.0, "%"),
        "visceral_fat_index": (14.0, "index"),
    }
    current = {
        "weight_kg": (119.0, "kg"),
        "body_fat_pct": (31.5, "%"),
        "muscle_mass_kg": (60.6, "kg"),
        "body_water_pct": (49.0, "%"),
        "visceral_fat_index": (14.0, "index"),
    }

    for key, (value, unit) in baseline.items():
        _metric("2030-01-01", key, value, unit, "measured" if key == "weight_kg" else "device_estimated")
    for key, (value, unit) in current.items():
        _metric("2030-01-02", key, value, unit, "measured" if key == "weight_kg" else "device_estimated")

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]

    assert analysis["status"] == "ready"
    assert analysis["as_of"] == "2030-01-02"
    assert analysis["compared_with"] == "2030-01-01"
    assert any(item["key"] == "fat_mass_est_kg" and item["kind"] == "derivado" for item in analysis["observations"])
    assert any(item["code"] == "fluid_compatible_gain" for item in analysis["hypotheses"])
    assert "masa de agua estimada" in analysis["summary"].lower()
    assert "+1" in analysis["headline"] or "subió 1" in analysis["headline"].lower()
    assert "demostrar" in " ".join(analysis["limits"]).lower() or "no equivale" in " ".join(analysis["limits"]).lower()


def test_interpretation_never_calls_device_estimates_direct_measurements():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]
    kinds = {item["key"]: item["kind"] for item in analysis["observations"]}
    assert kinds["weight_kg"] == "observado"
    assert kinds["body_fat_pct"] == "estimado_por_dispositivo"
    assert kinds["body_water_pct"] == "estimado_por_dispositivo"


def test_period_analysis_returns_processed_metric_changes():
    _metric("2026-09-21", "weight_kg", 118.0, "kg", "measured")
    _metric("2026-09-21", "body_fat_pct", 32.0, "%")
    _metric("2026-09-21", "body_water_pct", 48.0, "%")
    _metric("2026-09-22", "weight_kg", 117.4, "kg", "measured")
    _metric("2026-09-22", "body_fat_pct", 31.6, "%")
    _metric("2026-09-22", "body_water_pct", 48.6, "%")

    response = client.get("/api/project-series?days=7")
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    weight = analysis["metric_summaries"]["weight_kg"]

    assert weight["current"] == 117.4
    assert weight["delta_period"] == -0.6
    assert weight["delta_latest"] == -0.6
    assert "Peso:" in weight["headline"]
    assert "Último cambio" in weight["headline"]


def test_visible_metric_messages_are_results_not_hypothetical_instructions():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]
    visible_text = " ".join(analysis["metric_messages"].values()).lower()

    assert "si baja" not in visible_text
    assert "si sube" not in visible_text
    assert "si observas" not in visible_text
    assert "cambio frente a la medición anterior" in visible_text
