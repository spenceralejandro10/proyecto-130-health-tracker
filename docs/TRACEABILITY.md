# Trazabilidad inicial

| Requisito | Implementación | Caso principal | Prueba |
|---|---|---|---|
| RF-MED | `POST /api/metrics`, `GET /api/metrics` | CU-001 | `test_metric_idempotency_and_dashboard` |
| RF-ACT | `POST /api/activities` | CU-005 | `test_activity_dashboard_minutes` |
| RF-FUE | `POST /api/strength`, `GET /api/strength/last/{exercise}` | CU-006 | `test_strength_last_set` |
| RF-SUE | `POST /api/sleep` | CU-007 | `test_sleep_alert` |
| RF-ALI | `POST /api/nutrition` | módulo pendiente de reglas | validación de esquema |
| RF-DEC | `POST /api/decisions`, resultado posterior | CU-009/010 | `test_decision_audit` |
| RF-DASH | `GET /api/dashboard` | CU-003 | varios tests |
| RF-DESK | `desktop/client.py` | CU-011 | prueba manual/UX |
| RF-ALR | `/api/reminders*` + cliente desktop | CU-012/013 | `test_reminder_flow` |
| RF-BKP/RF-EXP | `GET /api/export`, `scripts/backup.py` | CU-016/018 | `test_export_contains_audit` |
| RF-AUD | `audit_logs`, `GET /api/audit` | CU-020 | `test_decision_audit` |
| RNF-IDM | `source_event_id` único | CU-014 | `test_metric_idempotency_and_dashboard` |
