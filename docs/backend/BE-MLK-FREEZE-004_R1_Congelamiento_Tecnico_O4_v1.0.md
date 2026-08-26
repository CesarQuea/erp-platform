# BE-MLK-FREEZE-004-R1 — Congelamiento técnico O-4 posterior a corrección Alembic

**Versión:** 1.0  
**Fecha:** 2026-08-25  
**Estado:** IMPLEMENTACIÓN CORREGIDA / CONGELADA / PENDIENTE DE REVERIFICACIÓN INDEPENDIENTE  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** O-4 — Backend Cloud Milking GENERAL  
**Draft PR:** #8  
**Rama:** `feat/milking-o4-backend-cloud-general`  
**Base autorizada:** `8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed`  
**HEAD técnico anterior fallido:** `e38999ada6ad14d40dfba17ecc62cf7fc4291ac8`  
**HEAD técnico corregido y congelado:** `6535bd8a22781e6a3043369f9f4c95e2c6d6fd40`

---

## 1. Motivo de R1

La primera verificación independiente sobre `e38999ad...` terminó `FAIL_VERIFICATION` porque los gates PostgreSQL no podían completar el provisionamiento Tenant al intentar persistir el revision ID:

`0004_o4_milking_lifecycle_hardening`

Ese identificador tiene 35 caracteres, mientras Alembic crea por defecto `alembic_version.version_num` como `VARCHAR(32)`.

La evidencia primaria mostró que Alembic sí alcanzaba la cadena `0001 -> 0002 -> 0003 -> 0004`; por ello no se modificó `migrations/env.py` ni la resolución dinámica de DSN.

---

## 2. Corrección autorizada

Se preservó el revision ID congelado `0004_o4_milking_lifecycle_hardening` y se amplió, dentro de la migración O-4 `0003_o4_milking_general`, la columna interna:

```text
alembic_version.version_num
VARCHAR(32) -> VARCHAR(128)
```

antes de que Alembic deba persistir el revision ID de `0004`.

El downgrade de `0003` restaura `VARCHAR(32)` una vez eliminados los objetos O-4, cuando la revisión destino vuelve a `0002_p4_command_execution` y cabe en 32 caracteres.

Se añadió prueba preventiva para asegurar que los revision IDs Tenant actuales no excedan la capacidad O-4 de 128 caracteres y documentar la regresión que motivó la ampliación.

---

## 3. Delta técnico R1

Desde el HEAD documental previo `c7daeaeea17b7c09ef704e95ab6eab926fd7bb39` hasta el nuevo HEAD técnico:

`6535bd8a22781e6a3043369f9f4c95e2c6d6fd40`

existen exactamente 2 commits técnicos y 2 archivos afectados:

1. `migrations/versions/0003_o4_milking_general.py`
   - +22 / -0
   - amplía/restaura la capacidad de `alembic_version.version_num`.

2. `tests/test_o4_alembic_version_capacity.py`
   - nuevo, +35
   - prueba preventiva de capacidad de revision IDs.

No se modificó:

- `migrations/env.py`;
- `migrations/versions/0004_o4_milking_lifecycle_hardening.py`;
- dominio Milking;
- SQLAlchemy models/repositories;
- API FastAPI;
- P-3 Identity/RBAC;
- P-4 command integrity;
- Dockerfile;
- requirements.

---

## 4. Contratos preservados

Continúan vigentes sin cambios:

- `BE-MLK-DES-004_Contrato_O4_Backend_Cloud_Milking_GENERAL_v0.1.md`;
- fronteras `Tenant + Company + Farm reference`;
- prohibición Site/OperationalUnit/Organization cloud obligatoria;
- `MilkingOutput 0..1`;
- P-3 como autoridad Identity/RBAC;
- P-4 como autoridad de transacción/idempotencia/CAS/audit técnico;
- O-5 Sync fuera de alcance.

La cadena Tenant esperada continúa siendo:

```text
0001_p2_tenant_company
-> 0002_p4_command_execution
-> 0003_o4_milking_general
-> 0004_o4_milking_lifecycle_hardening
```

---

## 5. Reverificación obligatoria

R1 no autoriza cierre. Debe repetirse la verificación completa porque la primera ejecución no llegó a validar realmente PostgreSQL, concurrencia, P-3 end-to-end ni readiness integrado.

La reverificación debe usar infraestructura de verificación limpia y separada para:

- O-4 PostgreSQL funcional: `O4_TEST_TENANT_DATABASES_JSON` con >=2 Tenant DB;
- forward migration: `O4_MIGRATION_TEST_TENANT_DATABASES_JSON` con >=2 Tenant DB dedicadas;
- P-3 Identity: `O4_TEST_IDENTITY_DATABASE_URL`;
- regresión PostgreSQL histórica P-4: `P4_TEST_TENANT_DATABASES_JSON` con >=2 DB dedicadas.

No reutilizar bases parcialmente migradas de la primera verificación.

La suite completa debe ejecutarse con todos los env obligatorios activos y no puede aceptar skips de gates O-4/P-4 por falta de infraestructura.

Docker debe probar `/health`, `/live` y `/ready` con PostgreSQL real disponible.

Los exit codes deben registrarse como enteros numéricos reales, no booleanos PowerShell.

---

## 6. Gobierno

Desde este congelamiento:

- `6535bd8a22781e6a3043369f9f4c95e2c6d6fd40` es el HEAD técnico O-4 R1 a verificar;
- cualquier commit posterior permitido antes del gate debe ser exclusivamente documental de congelamiento/prompt;
- el agente verificador no modifica código;
- no mergear PR #8;
- no iniciar O-5;
- no tag/force-push/rebase destructivo;
- cualquier nuevo defecto vuelve a revisión arquitectónica antes de corregirse.

> O-4 R1 queda congelado para reverificación independiente. El congelamiento no equivale a cierre ni merge.
