# Contratos de flujo funcional v0.1

Este documento responde la pregunta del auditor: **¿qué hace cada acción y qué pasa después?**

## Dashboard
- Las tarjetas son de solo lectura.
- Cada valor proviene de la API; la interfaz no calcula conclusiones fisiológicas por su cuenta.
- Si no existe la primera medición de peso, el ciclo permanece en **Inicio pendiente**.
- Las alertas informan; no modifican entrenamiento, alimentación ni datos.

## Registrar peso
1. Usuario ingresa peso.
2. La UI envía `weight_kg`, unidad, fuente, hora y referencia de evidencia.
3. API valida el esquema.
4. `source_event_id` impide procesar dos veces la misma lectura.
5. Se guarda el registro.
6. Se crea un evento de auditoría.
7. Dashboard se recalcula.
8. Una variación aislada no genera una orden automática de cambio.

## Registrar actividad
1. Se recibe tipo y duración; el resto es opcional.
2. `integrated=true` indica actividad simultánea con estudio/conversación u otra actividad.
3. Las calorías del dispositivo, cuando existan, se conservan como estimación de la fuente.
4. Dolor relevante puede crear una alerta de revisión; no cambia el plan automáticamente.

## Registrar fuerza
1. Cada serie es un evento independiente.
2. Campos mínimos: ejercicio, número de serie, carga y repeticiones.
3. `GET /api/strength/last/{exercise}` devuelve la serie anterior para facilitar repetición o ajuste.
4. No se infiere ganancia/pérdida muscular a partir de una sola serie.

## Registrar sueño
1. Un registro representa una fecha de sueño.
2. Si hay inicio y fin pero no duración, la API calcula la duración.
3. Sueño corto o fatiga alta pueden generar alerta contextual.
4. La alerta no incrementa ni reduce automáticamente actividad.

## Decisiones
1. El cambio se registra con razón, evidencia, valor anterior/nuevo e hipótesis.
2. Posteriormente se añade resultado.
3. El sistema no atribuye causalidad automática.

## Recordatorios
- `Hecho`: cierra el recordatorio de ese día.
- `Posponer`: crea un evento con nueva hora de revisión.
- `Descartar hoy`: cierra el recordatorio del día sin marcar la actividad como realizada.
- Ninguna de las tres acciones crea por sí sola una caminata o sesión de ejercicio.

## Cliente de escritorio
- Solo lee dashboard y recordatorios.
- Puede responder a un recordatorio.
- No modifica peso, composición, actividad, fuerza, sueño o alimentación.
- Si pierde conexión, mantiene lo último visible y muestra **sin conexión**.

## Exportación / backup
- `GET /api/export` entrega datos y auditoría.
- `scripts/backup.py` guarda snapshot + manifiesto + SHA-256.
- Sincronización no se considera backup.

## Estados no resueltos
Todo comportamiento que no figure aquí o en la trazabilidad se considera **pendiente de definición**, no comportamiento implícito.
