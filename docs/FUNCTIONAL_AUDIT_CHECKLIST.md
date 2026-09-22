# Auditor funcional y de lógica de negocio

El objetivo de esta revisión no es validar estética ni especialidades clínicas. Debe encontrar contradicciones, huecos, acciones sin propósito y estados sin salida.

## Preguntas obligatorias
1. ¿Cada entrada tiene un destino definido?
2. ¿Cada botón produce un efecto observable y esperado?
3. ¿Qué pasa si falta un dato?
4. ¿Qué pasa si el mismo dato llega dos veces?
5. ¿Qué pasa si el servidor no responde?
6. ¿Qué pasa si dos fuentes contradicen el mismo valor?
7. ¿Se distingue dato original de cálculo derivado?
8. ¿Puede explicarse de dónde salió cada resultado?
9. ¿Una alerta modifica datos o solo informa? Debe quedar explícito.
10. ¿Existe algún flujo que termine en un estado sin acción posible?
11. ¿Un usuario puede interpretar una estimación como medición exacta?
12. ¿Un cambio sensible puede ocurrir por una sola lectura aislada?
13. ¿La acción de posponer un recordatorio tiene un final definido?
14. ¿La pérdida de conexión conserva el último estado y lo marca como desactualizado?
15. ¿Toda modificación relevante queda en auditoría?

## Contrato de resultado
Cada hallazgo debe incluir: ID, flujo afectado, condición, resultado actual, resultado esperado, severidad y propuesta de corrección.
