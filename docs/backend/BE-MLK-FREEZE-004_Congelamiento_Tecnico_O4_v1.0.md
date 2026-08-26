# BE-MLK-FREEZE-004 — Congelamiento técnico O-4 Backend Cloud Milking GENERAL

**Versión:** 1.0  
**Fecha:** 2026-08-25  
**Estado:** IMPLEMENTACIÓN CONGELADA / PENDIENTE DE VERIFICACIÓN INDEPENDIENTE  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** O-4 — Backend Cloud Milking GENERAL  
**Draft PR:** #8  
**Rama exclusiva:** `feat/milking-o4-backend-cloud-general`  
**Base autorizada:** `8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed`  
**HEAD técnico congelado:** `e38999ada6ad14d40dfba17ecc62cf7fc4291ac8`

---

## 1. Objeto

Congelar el snapshot técnico de O-4 para iniciar la verificación independiente exigida por `BE-MLK-DES-004`, sin declarar todavía cierre, merge ni autorización de O-5.

Este documento es posterior al HEAD técnico congelado y no modifica código productivo, migraciones ni tests del snapshot a verificar.

---

## 2. Genealogía Git congelada

```text
Base autorizada:
8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed

HEAD técnico O-4:
e38999ada6ad14d40dfba17ecc62cf7fc4291ac8

Rama:
feat/milking-o4-backend-cloud-general

Draft PR:
#8 -> main
```

Contraste Git al momento del congelamiento:

- merge-base = base autorizada exacta;
- O-4 = 25 commits ahead;
- O-4 = 0 commits behind;
- diff técnico = 41 archivos;
- `main` no forma parte del trabajo de implementación O-4;
- no se autoriza merge, tag, force push ni rebase destructivo.

Durante la verificación no debe modificarse el HEAD técnico. Si aparece un defecto, la verificación se detiene en condición FAIL/BLOCKED y se informa; cualquier corrección requiere decisión posterior del usuario.

---

## 3. Contrato de autoridad

Fuente contractual principal:

`docs/backend/BE-MLK-DES-004_Contrato_O4_Backend_Cloud_Milking_GENERAL_v0.1.md`

O-4 implementa la autoridad cloud de Milking GENERAL/TOTAL sobre:

```text
Tenant DB + Company + Farm reference
```

Preserva P-3 para Identity/Auth/RBAC y P-4 para idempotencia, transacción, concurrencia y audit técnico.

No reabre contratos cerrados de P-1/P-2/P-3/P-4 ni O-3.2.

---

## 4. Alcance técnico congelado

El snapshot incluye:

- dominio Milking GENERAL/TOTAL;
- `OutputProfile` versionado;
- `MilkingConfiguration` `Company + Farm + Shift -> OutputProfileVersion`;
- `MilkingSession` DRAFT/DONE/CANCELLED;
- `MilkingOutput` con cardinalidad 0..1 por sesión;
- `AnnulmentRequest`;
- business audit append-only;
- repositorios SQLAlchemy;
- runtime Milking compartiendo `TenantSessionScope`/transacción con P-4;
- API FastAPI específica Milking;
- queries Company-scoped;
- administración mínima de perfiles/configuración;
- autorización P-3 mediante capabilities `milking.*`;
- integridad técnica P-4;
- Tenant Alembic `0003_o4_milking_general -> 0004_o4_milking_lifecycle_hardening`;
- pruebas unitarias, API, PostgreSQL, migración, concurrencia y P-3 end-to-end preparadas en el repositorio.

---

## 5. Invariantes obligatorias a verificar

1. Tenant y Company no se duplican.
2. Farm es referencia UUID externa; no existe maestro `milking_farms`.
3. Product/UoM son referencias externas; no existen maestros sombra Milking.
4. No se reintroducen Site, OperationalUnit, ProductionUnit, Plant, Facility, Branch, Warehouse ni Location como jerarquía Milking.
5. `Organization` Android no se materializa como autoridad cloud en O-4.
6. Todos los mutantes usan P-4; no existe command execution paralelo Milking.
7. Tenant/Company/actor se derivan de P-3; el cliente no puede elevar autoridad enviándolos en payload.
8. API fail-closed y deny-by-default.
9. Identidad activa única por `Company + Farm + Date + Shift` dentro del Tenant DB.
10. CANCELLED libera identidad operacional.
11. cantidades Milking usan PostgreSQL `NUMERIC` / Python `Decimal`; no FLOAT/DOUBLE/REAL.
12. GENERAL exige gross positivo cuando se informa; use/discard no negativos y no mayores al gross.
13. `net = gross - used - discarded`.
14. CONFIRM con net > 0 crea exactamente un Output; net = 0 crea 0 Output.
15. replay de CONFIRM no duplica Output ni business audit.
16. `expected_version` mantiene CAS explícito; no last-write-wins.
17. confirm/cancel concurrentes producen como máximo una transición válida.
18. business audit es append-only y no sustituye audit técnico P-4.
19. cada mutación es atómica en una única transacción PostgreSQL Tenant.
20. anulación DONE con Output crea solicitud PENDING; no borra/corrige silenciosamente Output.
21. queries permanecen Tenant DB + Company-scoped y no filtran recursos de otra Company/Tenant.
22. no existe endpoint genérico `/commands`.
23. no existe Outbox/Inbox cloud O-4.
24. `MilkingOutput` no se convierte en stock Inventory.

---

## 6. Exclusiones preservadas

Fuera de O-4 y por tanto prohibido interpretar como faltante del corte:

- Android↔Cloud Sync / O-5;
- Outbox/Inbox cloud;
- INDIVIDUAL/GROUP/test-day;
- Livestock backend completo;
- compra de leche/Purchase;
- Milk Logistics;
- Reception;
- Quality;
- Inventory posting;
- Warehouse/Location;
- Manufacturing;
- Web UI;
- deployment productivo;
- P-5/P-6 salvo capacidades previamente existentes.

---

## 7. Migraciones congeladas

Tenant Alembic esperado:

```text
0001_p2_tenant_company
-> 0002_p4_command_execution
-> 0003_o4_milking_general
-> 0004_o4_milking_lifecycle_hardening
```

La verificación debe demostrar forward migration real desde el head histórico P-4 a `0004_o4_milking_lifecycle_hardening` en PostgreSQL y debe usar al menos dos Tenant DB físicas.

Los tests históricos P-2/P-4 permanecen fijados a su revisión histórica cuando corresponda; el provisionamiento productivo conserva `head` como default.

---

## 8. Gates mínimos de verificación

La verificación independiente debe ejecutar y conservar evidencia primaria de:

### A. Precheck Git
- rama correcta;
- commit técnico congelado presente;
- diff documental posterior permitido únicamente para este acta/prompt;
- merge-base exacto;
- `git diff --check`;
- working tree limpio antes y después.

### B. Revisión estática
- diff base→HEAD técnico;
- términos/prohibiciones de frontera;
- ausencia de duplicación P-3/P-4;
- revisión de modelos, repositorios, runtime, API y Alembic;
- revisión de cambios heredados en tests P-2/P-4.

### C. Unit/API focal
Ejecutar todos los `tests/test_o4_milking_*.py` no dependientes de PostgreSQL y confirmar ausencia de skips inesperados.

### D. PostgreSQL real
Configurar como mínimo dos Tenant DB PostgreSQL mediante:

`O4_TEST_TENANT_DATABASES_JSON`

Ejecutar:

- `tests/test_o4_milking_postgres.py`;
- `tests/test_o4_milking_postgres_races.py`;
- `tests/test_o4_milking_forward_migration_postgres.py`;
- cualquier otro gate O-4 PostgreSQL presente.

### E. P-3 real end-to-end
Configurar Platform Identity PostgreSQL mediante:

`O4_TEST_IDENTITY_DATABASE_URL`

Ejecutar `tests/test_o4_milking_p3_api_integration.py` y demostrar:

- provisión de capabilities `milking.*` por APIs genéricas P-3;
- rol Company;
- JWT operacional Tenant+Company;
- endpoint O-4 autorizado;
- deny-by-default sin permisos.

### F. Concurrencia/stress
Demostrar en PostgreSQL real, como mínimo:

1. dos CREATE misma identidad -> máximo un ganador;
2. Farms distintas mismo Date+Shift -> ambos válidos;
3. mismo command_id concurrente -> máximo un efecto;
4. mismo command_id + payload distinto -> idempotency conflict;
5. dos updates mismo expectedVersion -> máximo uno confirma;
6. CONFIRM concurrente -> máximo un DONE y 0..1 Output;
7. replay CONFIRM -> sin duplicación;
8. CONFIRM vs CANCEL -> una transición válida;
9. aislamiento Companies;
10. aislamiento Tenant DB.

Las carreras repetibles deben ejecutarse por al menos 5 iteraciones cuando el test lo permita.

### G. Suite completa
Ejecutar pytest completo con los PostgreSQL env vars activos. Registrar tests collected/passed/failed/skipped y justificar cada skip.

No aceptar solo `pytest exit 0`; conservar XML JUnit.

### H. Compile/import
Ejecutar `python -m compileall app` y un import/startup real de la aplicación.

### I. Docker/runtime
- Docker build real;
- container run real con configuración de prueba;
- `/api/v1/health`;
- `/api/v1/live`;
- `/api/v1/ready`;
- comprobar que no se exponen DSN/secrets/tokens en respuestas/logs.

### J. Postcheck
- `git status --short`;
- `git diff --check`;
- SHA final;
- confirmar que el agente no modificó código, tests, migraciones ni documentación contractual.

---

## 9. Evidencias exigidas

El agente debe entregar un paquete, preferentemente:

`EVIDENCIAS_O4_e38999ad.zip`

con al menos:

```text
00_precheck/
01_static_review/
02_focal_tests/
03_postgres/
04_concurrency/
05_migrations/
06_p3_integration/
07_full_suite/
08_compile/
09_docker_runtime/
10_postcheck/
Reporte_Verificacion_O4.md
```

Debe incluir:

- comandos exactos;
- stdout/stderr primario;
- exit codes numéricos;
- XML JUnit;
- logs Alembic;
- logs de stress;
- evidencia de revisiones Tenant;
- evidencia de Platform Identity migration;
- Docker build/run logs;
- respuestas health/live/ready;
- `git status` inicial/final;
- SHA y diff comprobados.

No incluir passwords, tokens, JWT signing secrets, DSN con credenciales ni otros secretos.

---

## 10. Criterio de resultado del agente

El agente no decide el cierre.

Debe clasificar exclusivamente:

```text
PASS_VERIFICATION
FAIL_VERIFICATION
BLOCKED_VERIFICATION
```

`PASS_VERIFICATION` requiere evidencia primaria suficiente para todos los gates obligatorios.

Un test omitido por falta de infraestructura obligatoria no puede convertirse en PASS; debe ser BLOCKED salvo que el contrato permita expresamente el skip.

Cualquier discrepancia código/contrato es FAIL aunque la suite esté verde.

---

## 11. Gobierno posterior al congelamiento

Desde este acto:

- O-4 queda congelado en `e38999ada6ad14d40dfba17ecc62cf7fc4291ac8` como HEAD técnico;
- el agente verificador no modifica código;
- no se inicia O-5;
- no se mergea PR #8;
- no se crea tag;
- no se hace force push/rebase destructivo;
- si aparece un hallazgo, se devuelve evidencia para revisión arquitectónica;
- solo el usuario autoriza corrección, nuevo snapshot y eventual cierre.

---

## 12. Regla final

> El snapshot técnico O-4 `e38999ada6ad14d40dfba17ecc62cf7fc4291ac8` queda CONGELADO para verificación independiente. El congelamiento no equivale a cierre, no equivale a merge y no autoriza O-5.
