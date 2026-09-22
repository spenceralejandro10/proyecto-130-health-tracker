# Proyecto 130 Health Tracker

Primera implementación auditable del sistema documentado en **Proyecto 130**. El objetivo no es ser una app genérica de fitness: es un sistema de captura, trazabilidad, análisis y soporte de decisiones para un experimento longitudinal personal.

## Qué incluye

- API para métricas corporales, actividad, fuerza, sueño, alimentación, decisiones y recordatorios.
- Trazabilidad de origen, calidad, evidencia y versión de reglas.
- Protección contra duplicados mediante `source_event_id` en entradas que pueden reprocesarse.
- Dashboard web simple con peso, media móvil, día del ciclo, actividad, sueño, recordatorios y alertas contextuales.
- Cliente de escritorio Python siempre disponible, con resumen y recordatorios; no modifica mediciones.
- Registro de decisiones y auditoría.
- Exportación completa y script de snapshot con SHA-256 y manifiesto.
- Pruebas automatizadas y CI.
- Checklist específico para auditor funcional/lógica de negocio.

## Principio central

**Dato -> validación -> almacenamiento -> métrica -> interpretación -> decisión -> resultado -> auditoría.**

No se inventan datos ni se convierten estimaciones de dispositivos en mediciones exactas.

## Ejecutar

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -e ".[dev]"
cp .env.example .env  # en Windows, copiar manualmente
uvicorn app.main:app --reload
```

Abrir `http://127.0.0.1:8000`.

La API interactiva está en `http://127.0.0.1:8000/docs`.

## Cliente de escritorio

Con la API ejecutándose:

```bash
python desktop/client.py
```

Variables opcionales:

```text
PROJECT130_API_URL=http://127.0.0.1:8000
PROJECT130_API_KEY=
PROJECT130_POLL_MS=60000
```

En Windows se puede instalar el inicio automático, de forma explícita, con:

```bash
python desktop/install_autostart_windows.py
```

## Backup

```bash
python scripts/backup.py
```

Crea `snapshot-*.json` y un manifiesto con versión, conteo de registros y SHA-256. La carpeta `backups/` no se versiona en Git.

## Datos de composición

La báscula inicial documentada es **Xiaomi Mi Body Composition Scale 2 / XMTZC05HM**. El peso se registra como medición. Las métricas de composición BIA se registran como estimaciones del dispositivo.

Métricas sugeridas:

- `weight_kg`
- `body_fat_pct`
- `muscle_mass_kg`
- `body_water_pct`
- `visceral_fat_index`
- `bone_mass_kg`

No se obliga a que estas variables expliquen exactamente todo cambio diario de peso.

## Auditoría funcional

Antes de ampliar el sistema, revisar [`docs/FUNCTIONAL_AUDIT_CHECKLIST.md`](docs/FUNCTIONAL_AUDIT_CHECKLIST.md). La trazabilidad inicial está en [`docs/TRACEABILITY.md`](docs/TRACEABILITY.md).

## Estado conocido / no resuelto deliberadamente

- Integración automática con Xiaomi/Apple Health aún no está implementada; la primera fase acepta evidencia y registro validado.
- Las reglas nutricionales cuantitativas permanecen pendientes de revisión especializada.
- La UI visual es funcional y deliberadamente mínima hasta auditoría UX.
- SQLite es el almacenamiento inicial local, no una decisión irreversible para una futura versión multiusuario.
