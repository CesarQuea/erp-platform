# BE-REV-004 — Revisión Estática P-4 Command Integrity

**Versión:** 1.0  
**Estado:** REVISIÓN ESTÁTICA COMPLETADA — LISTO PARA VERIFICACIÓN INDEPENDIENTE  
**Fecha:** 2026-08-24  
**Repositorio:** `CesarQuea/erp-platform`  
**PR:** `#6 — draft: P-4 command integrity foundation`  
**Base autorizada:** `2427b8be82385e5f4c071df1e01b084087baee22`  
**HEAD funcional revisado:** `e040690b5f3d21cbb9c2a3eee6413adeed6d5253`  
**Contrato:** `BE-DES-004 v0.1`

---

## 1. Alcance revisado

La revisión estática contrastó contrato, archivos modificados y diff real del PR #6.

Áreas revisadas:

- command identity/context;
- fingerprint canónico;
- idempotency repository;
- claim concurrente PostgreSQL;
- replay y conflicto;
- transaction orchestration;
- optimistic compare-and-set;
- migración Tenant `0002_p4_command_execution`;
- logging/audit técnico;
- pruebas unitarias;
- pruebas transaccionales;
- pruebas de migración;
- pruebas P-3 de reautorización;
- pruebas PostgreSQL/concurrencia/stress;
- neutralidad respecto de módulos de negocio.

No se identificaron cambios funcionales en Milking, Inventory, Manufacturing, Livestock, Sales u otros dominios.

---

## 2. Arquitectura resultante

### 2.1 Command identity

`CommandRequest` recibe un `command_id` UUID estable generado externamente cuando corresponda.

`CommandContext` deriva `tenant_id`, `company_id`, `actor_user_id` y `session_id` del `AuthenticatedPrincipal`; el payload no es autoridad para Tenant/Company/actor.

Scopes P-4:

```text
TENANT
COMPANY
```

No se introducen Site/OperationalUnit/Farm/Warehouse como scopes P-4.

### 2.2 Fingerprint

El fingerprint es SHA-256 de una representación canónica que incorpora:

- command name;
- schema version;
- scope;
- Tenant;
- Company cuando aplica;
- actor;
- expectedVersion;
- payload normalizado.

Session y correlation id quedan fuera de la intención lógica.

Se evita JSON HTTP crudo y se rechazan `float` y datetime naive para impedir ambigüedad numérica/temporal.

### 2.3 Idempotency claim

La tabla `platform_command_executions` vive dentro de cada Tenant DB.

El claim usa:

```text
INSERT ... ON CONFLICT (command_id) DO NOTHING RETURNING command_id
```

La PK `command_id` actúa como exclusión transaccional.

Bajo PostgreSQL, un retry concurrente que pierde el INSERT espera la resolución de la fila conflictiva y luego:

- mismo fingerprint => replay;
- fingerprint diferente => `IDEMPOTENCY_CONFLICT`.

Si el primer intento hace rollback, su claim también desaparece y un retry posterior puede ejecutar legítimamente.

### 2.4 Atomicidad

P-4 reutiliza `TransactionBoundary` / `SqlAlchemyTenantTransactionBoundary` de P-1/P-2.

Dentro de una sola transacción Tenant quedan:

```text
idempotency claim
+
business mutation
+
minimal replay result
```

No existe transacción distribuida Platform Identity DB ↔ Tenant DB.

### 2.5 Concurrency

`SqlAlchemyCompareAndSet` realiza una actualización atómica equivalente a:

```sql
UPDATE resource
SET ..., version = version + 1
WHERE id = :id
  AND version = :expected_version
RETURNING version;
```

Sin match => `CONCURRENCY_CONFLICT`.

No se introduce `last-write-wins`, retry funcional automático, ni una clase ORM base obligatoria.

### 2.6 Authorization / replay

`CommandExecutionService` exige un callback de autorización que se ejecuta antes de cada intento, incluido replay.

Las pruebas P-4 integran el `AuthenticationService` real de P-3 y cubren:

- Membership revocada;
- CompanyAccess revocado;
- Company inactiva;
- sesión revocada.

Un replay no puede convertirse en bypass de P-3.

### 2.7 Audit técnico

La allowlist de logging incorpora únicamente campos técnicos seguros P-4.

No se incorporan:

- payload;
- result body;
- password;
- access/refresh token;
- DSN;
- secretos.

Business audit permanece fuera del corte.

---

## 3. Hallazgos de revisión y correcciones aplicadas

### H-1 — Estado de replay incompleto

**Riesgo:** un estado técnico inconsistente con `result_code/result_json` pero sin confirmación explícita podía interpretarse como replay.

**Corrección:** `CommandExecutionRecord` expone `committed_at`; P-4 exige `result_code + result_json + committed_at` para replay. Estado incompleto => fail-closed `COMMAND_EXECUTION_UNAVAILABLE`.

**Estado:** CORREGIDO.

### H-2 — Evidencia específica de revocación P-3

**Riesgo:** existía prueba genérica del callback de autorización, pero el contrato exige revocaciones reales P-3.

**Corrección:** se añadieron pruebas integradas con `AuthenticationService`/`IdentityProvisioningService` reales para Membership, CompanyAccess, Company inactiva y sesión revocada.

**Estado:** CORREGIDO.

### H-3 — Cobertura PostgreSQL de conflicto concurrente y rollback

**Riesgo:** el gate PostgreSQL inicial cubría replay concurrente y CAS, pero no mezcla concurrente de fingerprints distintos ni rollback PostgreSQL explícito.

**Corrección:** se añadieron:

- mismo command_id + fingerprints concurrentes distintos => uno ejecuta, otro `IDEMPOTENCY_CONFLICT`;
- fallo tras mutación => rollback de mutación y claim + retry exitoso;
- replay concurrente repetido en 5 iteraciones con 8 workers.

**Estado:** CORREGIDO.

### H-4 — Literal de dominio en test genérico

**Riesgo:** pruebas de fingerprint usaban nombres ilustrativos de módulos concretos.

**Corrección:** sustitución por `domain.*` para mantener neutralidad incluso en ejemplos/tests P-4.

**Estado:** CORREGIDO.

---

## 4. Exclusiones verificadas estáticamente

No se observó implementación de:

- Milking;
- Inventory;
- Manufacturing;
- Livestock;
- Sales;
- Sync Android;
- Outbox/Inbox;
- endpoint universal `/commands`;
- Kafka/RabbitMQ;
- saga/distributed transaction;
- business audit general;
- Module Registry/P-5;
- ImplementationProfile;
- microservicios.

---

## 5. Riesgos que solo pueden cerrarse con evidencia dinámica

La revisión estática NO demuestra por sí sola:

1. comportamiento real de `ON CONFLICT` bajo carreras PostgreSQL;
2. ausencia de deadlocks/intermitencias bajo stress;
3. migración real sobre dos PostgreSQL Tenant independientes;
4. regresión completa P-1/P-2/P-3;
5. compatibilidad efectiva de Docker/runtime;
6. ausencia de skips involuntarios en el gate PostgreSQL;
7. XML JUnit y conteo final real.

Estos puntos requieren verificador independiente.

---

## 6. Gate PostgreSQL obligatorio

`tests/test_p4_postgres.py` está protegido por la variable:

```text
P4_TEST_TENANT_DATABASES_JSON
```

Para el gate final:

- deben utilizarse **dos bases PostgreSQL de prueba dedicadas**, nunca productivas;
- ambas deben ser provisionadas/migradas realmente;
- los tests PostgreSQL P-4 deben ejecutarse;
- **0 skips** es obligatorio para esa ejecución focal;
- un resultado donde `test_p4_postgres.py` figure skipped NO satisface BE-DES-004.

---

## 7. Resultado de revisión estática

No se identifica actualmente un blocker estático material contra `BE-DES-004 v0.1`.

La implementación queda:

> **LISTA PARA VERIFICACIÓN INDEPENDIENTE, NO LISTA PARA CIERRE.**

No se recomienda cerrar ni mergear P-4 hasta contrastar evidencia primaria de PostgreSQL, concurrencia/stress, migraciones, suite completa, compile/runtime, Docker y seguridad/logging.

---

## 8. Gobierno

- PR #6 permanece Draft;
- no merge;
- no tag;
- no force push;
- no rebase destructivo;
- P-5 no iniciado;
- cualquier cambio funcional posterior al HEAD revisado exige recontrastar el delta antes del cierre.
