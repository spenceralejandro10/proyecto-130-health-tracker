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
    assert "compatible" in analysis["summary"].lower()
    assert "demostrar" in " ".join(analysis["limits"]).lower() or "no equivale" in " ".join(analysis["limits"]).lower()


def test_interpretation_never_calls_device_estimates_direct_measurements():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]
    kinds = {item["key"]: item["kind"] for item in analysis["observations"]}
    assert kinds["weight_kg"] == "observado"
    assert kinds["body_fat_pct"] == "estimado_por_dispositivo"
    assert kinds["body_water_pct"] == "estimado_por_dispositivo"
