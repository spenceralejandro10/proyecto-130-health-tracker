from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _metric(day: str, key: str, value: float, unit: str, origin: str = "device_estimated", tag: str = "main") -> None:
    response = client.post(
        "/api/metrics",
        json={
            "captured_at": f"{day}T08:15:00-05:00",
            "metric_key": key,
            "value": value,
            "unit": unit,
            "source": "BIA test fixture",
            "origin": origin,
            "validation_status": "confirmed" if key == "weight_kg" else "estimated",
            "source_event_id": f"interpretation-{tag}-{day}-{key}-{value}",
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
        _metric("2026-09-21", key, value, unit, "measured" if key == "weight_kg" else "device_estimated")
    for key, (value, unit) in current.items():
        _metric("2026-09-22", key, value, unit, "measured" if key == "weight_kg" else "device_estimated")

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]

    assert analysis["status"] == "ready"
    assert analysis["as_of"] == "2026-09-22"
    assert analysis["compared_with"] == "2026-09-21"
    assert any(item["key"] == "fat_mass_est_kg" and item["kind"] == "derivado" for item in analysis["observations"])
    assert any(item["code"] == "weight_up_water_up_fat_not_up" for item in analysis["hypotheses"])
    assert "agua corporal subió" in analysis["summary"].lower()
    assert "grasa corporal bajó" in analysis["summary"].lower()
    assert "+1" in analysis["headline"] or "subió 1" in analysis["headline"].lower()
    assert "tmb calculada" in " ".join(analysis["limits"]).lower()


def test_interpretation_never_calls_device_estimates_direct_measurements():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]
    kinds = {item["key"]: item["kind"] for item in analysis["observations"]}
    assert kinds["weight_kg"] == "observado"
    assert kinds["body_fat_pct"] == "estimado_por_dispositivo"
    assert kinds["body_water_pct"] == "estimado_por_dispositivo"


def test_period_analysis_returns_processed_metric_changes():
    _metric("2026-09-21", "weight_kg", 118.0, "kg", "measured", "period")
    _metric("2026-09-21", "body_fat_pct", 32.0, "%", tag="period")
    _metric("2026-09-21", "body_water_pct", 48.0, "%", tag="period")
    _metric("2026-09-22", "weight_kg", 117.4, "kg", "measured", "period")
    _metric("2026-09-22", "body_fat_pct", 31.6, "%", tag="period")
    _metric("2026-09-22", "body_water_pct", 48.6, "%", tag="period")

    response = client.get("/api/project-series?days=7")
    assert response.status_code == 200
    analysis = response.json()["analysis"]
    weight = analysis["metric_summaries"]["weight_kg"]

    assert weight["current"] == 117.4
    assert weight["delta_period"] == -0.6
    assert weight["delta_latest"] == -0.6
    assert "Peso bajó" in weight["headline"]
    assert "Último cambio" in weight["headline"]


def test_visible_metric_messages_are_results_not_hypothetical_instructions():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    analysis = dashboard.json()["interpretation"]
    visible_text = " ".join(analysis["metric_messages"].values()).lower()

    assert "si baja" not in visible_text
    assert "si sube" not in visible_text
    assert "si observas" not in visible_text
    assert "subió" in visible_text or "bajó" in visible_text or "no cambió" in visible_text
    assert "se interpreta por tendencia" not in visible_text
    assert "se sigue como tendencia" not in visible_text


def test_resting_energy_recalculates_from_current_body_state():
    _metric("2026-09-20", "weight_kg", 120.0, "kg", "measured", "energy")
    _metric("2026-09-20", "body_fat_pct", 35.0, "%", tag="energy")
    _metric("2026-09-22", "weight_kg", 118.0, "kg", "measured", "energy")
    _metric("2026-09-22", "body_fat_pct", 35.0, "%", tag="energy")

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    energy = dashboard.json()["interpretation"]["energy"]

    expected_lean = 118.0 * 0.65
    expected_resting = round(370 + 21.6 * expected_lean)
    assert energy["lean_mass_est_kg"] == round(expected_lean, 2)
    assert energy["resting_kcal_day"] == expected_resting
    assert energy["resting_change_kcal_day"] is not None


def test_metric_copy_is_direct_not_instructional():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    messages = dashboard.json()["interpretation"]["metric_messages"]
    joined = " ".join(messages.values()).lower()

    forbidden = [
        "si baja",
        "si sube",
        "se interpreta por tendencia",
        "se sigue como tendencia",
        "no indica por sí solo",
    ]
    for phrase in forbidden:
        assert phrase not in joined


def test_goal_pace_uses_90_kg_and_updates_from_weight():
    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    data = dashboard.json()
    pace = data["goal_pace"]

    assert data["goal_weight_kg"] == 90.0
    assert pace["goal_weight_kg"] == 90.0
    if pace.get("current_weight_kg") is not None:
        assert pace["remaining_kg"] == round(max(pace["current_weight_kg"] - 90.0, 0), 2)
        assert pace["days_left"] >= 0
        assert "series" in pace


def test_nutrition_day_can_be_updated_and_recalculates_energy_series():
    day = "2026-09-18"
    first = {
        "nutrition_date": day,
        "calories": 1800,
        "protein_g": 120,
        "fat_g": 60,
        "carbs_g": 180,
        "source": "test",
    }
    second = {**first, "calories": 1700, "protein_g": 130}

    response = client.put(f"/api/nutrition/{day}", json=first)
    assert response.status_code == 200
    response = client.put(f"/api/nutrition/{day}", json=second)
    assert response.status_code == 200
    assert response.json()["calories"] == 1700
    assert response.json()["protein_g"] == 130

    series = client.get("/api/project-series?days=14")
    assert series.status_code == 200
    assert "energy_history" in series.json()


def test_profile_switches_resting_metabolism_to_mifflin():
    profile = client.put(
        "/api/profile",
        json={"height_cm": 180, "age_years": 40, "sex": "male"},
    )
    assert profile.status_code == 200

    dashboard = client.get("/api/dashboard")
    assert dashboard.status_code == 200
    energy = dashboard.json()["interpretation"]["energy"]

    if energy.get("resting_kcal_day") is not None:
        assert energy["resting_method"] == "mifflin_st_jeor"
        assert energy["profile_height_cm"] == 180
        assert energy["profile_age_years"] == 40
        assert energy["profile_sex"] == "male"
