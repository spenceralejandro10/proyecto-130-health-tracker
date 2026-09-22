# Huecos conocidos y bloqueos explícitos

No se ocultan detrás de una interfaz aparentemente terminada.

## Bloqueos externos
1. **Xiaomi Mi Body Composition Scale 2 / XMTZC05HM**: falta validar una vía autorizada y estable para importar automáticamente historial y composición.
2. **Apple Watch / Apple Health**: falta definir la integración autorizada disponible para el entorno final.
3. **Reglas nutricionales cuantitativas**: no se codifican hasta cerrar la revisión especializada correspondiente.

## Pendientes de producto
1. Restauración automatizada desde snapshot: el backup y manifiesto están implementados; la restauración destructiva queda pendiente de una puerta de confirmación y prueba dedicada.
2. Corrección avanzada de registros históricos: actualmente la auditoría registra creaciones y decisiones; se debe definir el contrato exacto antes de permitir ediciones retrospectivas desde UI.
3. UX del cliente de escritorio: posición, tamaño y frecuencia deben validarse con uso real.
4. Autenticación multiusuario: fuera del alcance del primer Paciente Cero. Existe API key opcional para operación local/controlada.
5. Generalización a otros usuarios: no se presume validada.

## Regla de auditoría
Un hueco conocido no se considera defecto oculto si está documentado y bloquea explícitamente la función correspondiente. Si una función aparenta estar disponible pero carece de flujo completo, sí debe reportarse como defecto.
