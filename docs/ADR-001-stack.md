# ADR-001 — Stack inicial

## Estado
Aceptado para la primera implementación auditable.

## Decisión
- Backend/API: FastAPI.
- Persistencia: SQLAlchemy con SQLite por defecto y posibilidad de cambiar `DATABASE_URL`.
- Interfaz web: HTML/Jinja + JavaScript sin pipeline de compilación.
- Cliente de escritorio: Python + Tkinter, solo lectura de métricas y acciones de recordatorios.
- Pruebas: pytest.

## Motivo
El proyecto necesita velocidad de construcción sin sacrificar trazabilidad, pruebas ni separación por capas. Este stack evita incorporar frontend y desktop con ecosistemas distintos antes de validar el flujo funcional.

## Consecuencias
- La primera versión es simple de ejecutar localmente.
- SQLite no se considera decisión definitiva para multiusuario.
- El cliente de escritorio puede sustituirse más adelante sin cambiar el contrato HTTP.
- La UI web queda deliberadamente sencilla hasta terminar auditoría UX.
