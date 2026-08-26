# BE-MLK-FREEZE-004 R2 — Congelamiento Técnico O-4

**Corte:** O-4 Backend Cloud Milking GENERAL  
**Estado:** CONGELADO PARA REVERIFICACIÓN / NO CERRADO / NO MERGEADO  
**Base autorizada:** `8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed`  
**HEAD técnico R1:** `6535bd8a22781e6a3043369f9f4c95e2c6d6fd40`  
**HEAD documental previo a R2:** `805a05309c090c4e63ace86f61369db3c7bf5468`  
**HEAD técnico R2 congelado:** `dac40376ae8161d46e844b5f339cdc427923af8d`  
**Rama:** `feat/milking-o4-backend-cloud-general`  
**Draft PR:** #8

## 1. Motivo del R2

La reverificación R1 confirmó que la corrección Alembic fue efectiva y que los gates de PostgreSQL, P-3, P-4 y concurrencia estaban mayoritariamente verdes. El único fallo funcional del paquete PostgreSQL provenía de un test de replay mal construido.

El test `test_o4_same_create_command_replays_same_session_without_duplicate_audit` reutilizaba el mismo `command_id`, pero el helper `_create_session()` generaba un `client_occurred_at=datetime.now(UTC)` distinto en cada llamada. Como `client_occurred_at` participa en el fingerprint P-4, el segundo envío era correctamente clasificado como `IDEMPOTENCY_CONFLICT`, no replay.

## 2. Corrección R2 autorizada

Se modificó exclusivamente:

`tests/test_o4_milking_postgres.py`

Cambios:

1. `_create_session()` recibe opcionalmente `client_occurred_at`.
2. Si no se proporciona, conserva el comportamiento previo `datetime.now(UTC)`.
3. El test de replay fija un único `occurred_at` y lo reutiliza en ambas invocaciones.
4. No se modifica ningún archivo productivo.

Commit R2:

`dac40376ae8161d46e844b5f339cdc427923af8d`

Delta respecto del HEAD documental previo `805a0530...`:

- 1 commit;
- 1 archivo;
- `tests/test_o4_milking_postgres.py`;
- +24 / -4;
- 0 código productivo.

## 3. Decisiones no modificadas

R2 NO cambia:

- contrato O-4;
- dominio Milking;
- API;
- PostgreSQL schema;
- Alembic 0003/0004;
- P-3;
- P-4;
- `PlatformError`;
- Dockerfile;
- Site/OperationalUnit/Organization;
- Farm/Product/UoM ownership;
- O-5.

El runtime objetivo continúa siendo Python 3.12 conforme al Dockerfile (`python:3.12-slim`). El `TypeError` observado bajo Python 3.14 no motiva cambio de Platform en R2, porque se produjo después de que el test generara correctamente un `IDEMPOTENCY_CONFLICT` por payload distinto.

## 4. Condiciones de reverificación R2

La reverificación debe:

- ejecutarse con Python 3.12;
- confirmar replay CREATE con payload idéntico;
- confirmar `same command_id + payload distinto -> IDEMPOTENCY_CONFLICT`;
- usar PostgreSQL real y bases limpias/separadas;
- recrear o limpiar las DB dedicadas de forward migration antes de la suite completa;
- ejecutar P-3 real;
- ejecutar P-4 PostgreSQL sin skips;
- ejecutar suite completa con 0 failures/errors y sin skips obligatorios;
- usar Docker con un `--env-file` o mecanismo que preserve JSON válido;
- comprobar `/health`, `/live` y `/ready` con DB real;
- registrar exit codes numéricos;
- eliminar artefactos temporales propios antes del postcheck;
- dejar Git limpio.

## 5. Regla de cierre

Este congelamiento R2 NO autoriza cierre, merge ni O-5.

Solo después de recibir evidencia primaria completa y contrastarla independientemente contra código/diff podrá recomendarse el cierre O-4.
