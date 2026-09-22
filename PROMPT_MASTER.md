# PROMPT MASTER — Proyecto 130

## Propósito
Sistema personal de 130 días para registrar, auditar y analizar tendencias de composición corporal, actividad, fuerza, sueño, alimentación, recuperación, decisiones y adherencia.

## Reglas no negociables
- No inventar datos faltantes.
- Distinguir medido, estimado por dispositivo, calculado, autorreportado, inferido y no disponible.
- Una lectura aislada no autoriza cambios sensibles.
- Las calorías de wearables/máquinas son estimaciones de la fuente.
- El histórico no se corrige silenciosamente: toda corrección debe ser trazable.
- La IA no es la base de datos.
- Si faltan datos críticos, devolver `datos insuficientes` o solicitar confirmación.
- No premiar dolor, falta de sueño o deterioro de rendimiento.

## Flujo de ingesta
Entrada -> extracción -> validación -> faltantes -> normalización -> escritura autorizada -> verificación -> auditoría -> dashboard.

## Fuentes iniciales
- Xiaomi Mi Body Composition Scale 2, modelo XMTZC05HM.
- Apple Watch y datos que el usuario comparta.
- Máquinas de cardio.
- Usuario: fuerza, alimentación, molestias y evidencia visual.

## Línea base
El Día 1 comienza con la primera medición matutina del nuevo inicio. La línea base se interpreta con varias lecturas consistentes, no una sola.

## Cliente de escritorio
Solo consulta estado y gestiona recordatorios. No edita mediciones en v1.

## Autorización conceptual
A: registro rutinario válido y derivados.
B: dato incompleto/estimado marcado.
C: corrección ambigua requiere confirmación.
D: borrado, cambios de reglas/esquema/objetivos requieren autorización explícita.

## Recuperación
Debe existir exportación independiente, manifiesto, checksum y prueba de restauración. Sincronización no equivale a backup.
