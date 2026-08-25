# BE-DES-004 — Contrato P-4 Transactions, Idempotency, Concurrency & Audit

**Versión:** 0.1
**Estado:** APROBADO / CERRADO CONTRACTUALMENTE / CONGELADO — IMPLEMENTACIÓN AUTORIZADA
**Fecha:** 2026-08-24
**Repositorio:** `CesarQuea/erp-platform`
**Plan maestro:** `BE-PLAN-001 v0.2`
**Base de implementación autorizada:** `main @ 2427b8be82385e5f4c071df1e01b084087baee22`
**Rama:** `feat/platform-p4-command-integrity`

**Aprobación contractual:** aprobada expresamente por el usuario el 2026-08-24.
**Autorización de implementación:** el usuario autorizó expresamente `main @ 2427b8be82385e5f4c071df1e01b084087baee22` como base de implementación de P-4.
**Efecto:** quedan congelados alcance, invariantes, exclusiones y decisiones técnicas de P-4. El merge, cierre de P-4 e inicio de P-5 requieren autorizaciones separadas.

---

## 1. Objetivo

Completar las primitivas transversales necesarias para que los módulos de negocio de ERP Platform procesen operaciones mutantes de forma atómica, idempotente, segura ante reintentos, segura ante concurrencia, explícita ante conflictos, auditable técnicamente, neutral respecto del dominio y compatible con arquitectura offline-first y multiusuario.

P-4 no implementa comandos funcionales de Milking, Inventory, Manufacturing, Livestock, Sales u otros módulos.

---

## 2. Contexto que P-4 preserva

P-4 se construye sobre capacidades ya cerradas.

### P-1
Preserva `TransactionBoundary` framework-neutral, error foundation, UUID/time primitives, correlation/request id, logging estructurado y Docker/runtime.

### P-2
Preserva `TenantContext`, `TenantRegistry`, `TenantDataSourceResolver`, PostgreSQL físico independiente por Tenant, `Company`, `TenantSessionScope`, `SqlAlchemyTenantTransactionBoundary`, una transacción perteneciente a un solo Tenant, Alembic por Tenant, fail-closed, no cross-Tenant transaction y no `last-write-wins` como política futura.

### P-3
Preserva identidad global, `AuthenticatedPrincipal`, `TenantMembership`, `CompanyAccess`, RBAC `PLATFORM` / `TENANT` / `COMPANY`, revocación efectiva, contexto Tenant/Company autorizado y auditoría de seguridad.

### BE-ADR-001
Preserva `Tenant -> Company` como jerarquía transversal mínima. P-4 no introduce `Site` ni `OperationalUnit`.

---

## 3. Principio de pertenencia a Platform

P-4 implementa únicamente mecanismos transversales de integridad de comandos.

Platform define identidad técnica del comando, fingerprint, replay idempotente, conflicto de idempotencia, atomicidad de ejecución, primitivas de optimistic concurrency, errores técnicos comunes y audit técnico de ejecución.

Cada módulo define nombres de sus comandos, payload funcional, reglas de validación, recursos versionados, semántica de cada mutación, resolución funcional de conflictos y resultado funcional del comando.

---

## 4. Command identity

Todo comando mutante que utilice P-4 deberá disponer de un `command_id` estable UUID. `command_id` identifica una intención lógica de mutación. Un retry técnico conserva el mismo `command_id`; una intención funcional diferente debe utilizar otro.

P-4 soportará inicialmente scopes `TENANT` y `COMPANY`. Para `COMPANY`, `company_id` es obligatorio; para `TENANT`, es nulo. P-4 no crea scopes globales `SITE`, `OPERATIONAL_UNIT`, `FARM`, `WAREHOUSE` u otros.

---

## 5. Command descriptor

La infraestructura P-4 utilizará un descriptor interno equivalente a:

```text
CommandContext
├── command_id
├── command_name
├── command_schema_version
├── scope
├── tenant_id
├── company_id optional
├── actor_user_id
├── expected_version optional
└── correlation_id optional
```

Reglas: Tenant/Company provienen del contexto autenticado/autorizado; `actor_user_id` proviene de `AuthenticatedPrincipal`; `session_id` puede auditarse pero no forma parte de la identidad lógica; `correlation_id` identifica el intento/request, no la intención; P-4 no congela todavía un envelope HTTP público.

---

## 6. Fingerprint lógico

P-4 calculará un fingerprint determinista SHA-256 sobre representación canónica de datos semánticamente relevantes, incluyendo como mínimo:

```text
command_name
command_schema_version
scope
tenant_id
company_id
actor_user_id
expected_version
payload normalizado del comando
```

No se calcula sobre body HTTP crudo ni incluye tokens, headers irrelevantes o correlation id. El módulo entrega payload semánticamente normalizado; Platform aplica serialización canónica determinista. El payload completo no se persiste en la tabla de idempotencia ni se registra en logs.

Mismo `command_id` + fingerprint diferente => `IDEMPOTENCY_CONFLICT`.

---

## 7. Semántica de idempotencia

### 7.1 Primer procesamiento exitoso

```text
BEGIN Tenant Transaction
    registrar identidad/fingerprint del comando
    ejecutar mutación
    registrar resultado mínimo de replay
COMMIT
```

La escritura de idempotencia y la mutación de negocio forman parte de la misma transacción PostgreSQL del Tenant.

### 7.2 Replay idéntico

Si ya existe un comando confirmado con mismo `command_id` y mismo fingerprint, la operación funcional no se vuelve a ejecutar y se devuelve un resultado semánticamente equivalente usando el replay result persistido.

### 7.3 Reuso conflictivo

Mismo `command_id` + fingerprint diferente => `IDEMPOTENCY_CONFLICT`, sin mutación funcional.

### 7.4 Concurrencia sobre el mismo command_id

Dos o más requests concurrentes con el mismo `command_id` no pueden producir múltiples efectos válidos. PostgreSQL/constraint + operación atómica deben garantizar máximo un efecto de negocio; los demás requests se convierten en replay o conflicto según fingerprint.

---

## 8. Persistencia de idempotencia

La persistencia vivirá en cada Tenant DB, no en Platform Identity DB, para que identidad del comando y mutación de negocio puedan confirmarse o revertirse dentro de la misma transacción física.

Tabla técnica propuesta: `platform_command_executions`.

Campos conceptuales mínimos:

```text
command_id UUID PK
command_name
command_schema_version
scope
company_id nullable
actor_user_id
fingerprint
result_code
result_json
committed_at
```

Reglas: `command_id` único dentro de la Tenant DB; `company_id` referencia `companies` cuando scope = COMPANY; `actor_user_id` no tiene FK cross-database hacia Platform Identity DB; el Tenant se deriva de DB física + `TenantContext`; check constraint COMPANY=>company_id NOT NULL y TENANT=>company_id NULL; no se persiste payload original ni secretos.

El replay result debe ser mínimo y seguro. Propuesta inicial: máximo 32 KiB serializados; si un módulo necesita más, persiste el recurso en su dominio y P-4 guarda solo referencia/resultado mínimo.

P-4 no implementará borrado automático de registros idempotentes. La retención/archivo se difiere hasta demostrar que no permite reejecutar comandos antiguos válidos.

---

## 9. Fallos y rollback

Solo una operación cuyo transaction boundary terminó correctamente queda registrada como ejecución idempotente confirmada.

Error de infraestructura o excepción inesperada => rollback completo:

```text
business mutation = NO
idempotency record = NO
```

El mismo `command_id` puede reintentarse posteriormente.

Rechazos funcionales sin mutación no requieren convertirse en efecto idempotente persistido en P-4. El cliente/módulo sigue obligado a no reutilizar deliberadamente un `command_id` para una intención diferente.

---

## 10. Authorization y replay

La idempotencia nunca sustituye autorización. Antes de ejecución nueva, replay o lectura del resultado idempotente debe revalidarse la autoridad actual P-3.

Ejemplo:

```text
comando ejecutado ayer
↓
usuario pierde CompanyAccess hoy
↓
retry hoy
↓
ACCESS_DENIED
```

P-4 no puede devolver el resultado anterior saltándose la revocación actual.

---

## 11. Optimistic concurrency

P-4 define una semántica transversal de versión sin obligar a todos los modelos a heredar una clase ORM común.

Los recursos que su módulo declare versionados utilizarán una versión monotónica entera. El valor inicial se define en el contrato del módulo.

Una mutación sobre recurso versionado recibe `expected_version` y solo confirma si `current_version == expected_version`.

Patrón conceptual CAS:

```sql
UPDATE resource
SET ..., version = version + 1
WHERE id = :id
  AND version = :expected_version;
```

Si ninguna fila se actualiza, no existe actualización silenciosa. P-4 define `CONCURRENCY_CONFLICT`. No se aplica retry automático de la mutación funcional ni `last-write-wins`.

Comandos de creación no requieren obligatoriamente `expected_version`; la unicidad se protege con `command_id`, constraints y reglas de dominio.

---

## 12. Concurrency primitives

P-4 podrá incorporar helpers SQLAlchemy para compare-and-set, pero no impondrá herencia ORM común, no introducirá `VersionedEntityBase` obligatorio, no añadirá `version` indiscriminadamente a tablas existentes y no modificará `Company` solo para demostrar P-4.

La verificación PostgreSQL podrá utilizar tablas de prueba aisladas/temporales para demostrar el helper sin contaminar el schema funcional.

---

## 13. Transaction orchestration

P-4 reutiliza el `TransactionBoundary` existente.

Invariantes: una ejecución pertenece a un solo Tenant; no nested Tenant transaction; no cross-Tenant transaction; no transacciones distribuidas Platform DB ↔ Tenant DB; idempotency + business mutation + replay result se confirman o revierten juntas; la implementación no expone `sqlalchemy.orm.Session` como contrato de dominio; la sesión activa continúa gobernada por `TenantSessionScope`.

---

## 14. Audit técnico P-4

P-4 implementa audit técnico de ejecución de comandos, no auditoría funcional completa del ERP.

Eventos candidatos:

```text
command_succeeded
command_replayed
idempotency_conflict
concurrency_conflict
command_failed
```

Metadatos seguros permitidos:

```text
correlation_id
command_id
command_name
user_id
session_id
tenant_id
company_id
scope
expected_version
current_version cuando sea seguro
outcome
```

Prohibido registrar payload completo, passwords, tokens, DSN, secretos o result body completo.

Business audit como “usuario cambió precio X→Y”, “anuló lote” o “cambió litros” queda fuera de P-4 y pertenece a cada módulo o a un futuro contrato de auditoría funcional.

---

## 15. Compatibilidad con evolución por etapas

P-4 debe preservar la capacidad de evolución de ERP Platform sin adelantar la implementación de cortes posteriores.

### 15.1 Extensibilidad transaccional

La arquitectura P-4 no debe impedir que un corte posterior incorpore nuevas escrituras técnicas dentro de la misma transacción Tenant cuando exista una necesidad transversal aprobada.

Patrón conceptual futuro:

```text
BEGIN Tenant Transaction
    idempotency record
    business mutation
    future technical record
COMMIT
```

P-4 no implementa Outbox/Inbox, pero su TransactionBoundary y su persistencia no deberán impedir que un mecanismo posterior pueda participar atómicamente en la misma transacción física del Tenant.

### 15.2 `command_id` distribuido y durable

`command_id` debe poder ser generado fuera del servidor y conservarse de extremo a extremo durante reintentos y procesamiento diferido.

Reglas:

1. P-4 no obliga a generar `command_id` al recibir una request HTTP;
2. un productor autorizado puede generar el identificador antes de disponer de conectividad;
3. el mismo `command_id` conserva su semántica aunque la ejecución se produzca posteriormente;
4. retries técnicos conservan el mismo `command_id`;
5. una intención lógica distinta utiliza un nuevo `command_id`.

Esta propiedad es necesaria para una arquitectura distribuida y offline-first, independientemente del módulo que consuma P-4.

### 15.3 Retención compatible con procesamiento diferido

P-4 no implementará borrado automático de registros idempotentes.

Cualquier política futura de retención, archivo o purga deberá demostrar que:

- no permite reejecutar accidentalmente una intención previamente confirmada;
- no rompe procesamiento diferido o reintentos legítimos;
- mantiene las garantías de idempotencia durante el horizonte definido por contratos posteriores.

La política concreta de retención se definirá cuando existan requisitos suficientes para congelarla.

---

## 16. Outbox / Inbox

**Fuera del alcance de P-4.**

Justificación: P-4 no implementa mensajería distribuida; el monolito modular no necesita Outbox para comunicación interna síncrona; un corte posterior podrá requerir Outbox/Inbox con requisitos propios; incorporarlo ahora condicionaría prematuramente contratos futuros.

Solo podrá adelantarse mediante adenda expresa si se demuestra una necesidad transaccional transversal que no pueda resolverse sin este mecanismo.

---

## 17. API pública

P-4 no añade obligatoriamente endpoints HTTP funcionales ni congela un endpoint universal `/commands` o command bus HTTP. Los módulos integrarán sus endpoints con P-4 mediante application services. Las reglas API transversales definitivas pertenecen a P-6.

---

## 18. Errores P-4

Códigos mínimos:

```text
IDEMPOTENCY_CONFLICT
CONCURRENCY_CONFLICT
INVALID_COMMAND_CONTEXT
IDEMPOTENCY_RESULT_TOO_LARGE
```

Se integran con `PlatformError`/error foundation existente. La semántica HTTP inicial recomendada para conflictos es 409, sin convertir P-4 en autoridad completa del contrato API P-6.

---

## 19. Migraciones

P-4 requiere una migración Tenant Alembic propuesta: `0002_p4_command_execution`.

Incluye únicamente estructuras técnicas necesarias para idempotencia P-4.

No modifica Platform Identity DB, `user_accounts`, sesiones P-3, RBAC, `companies` salvo FK referenciada, ni tablas sectoriales.

Debe ser reproducible sobre `0001_p2_tenant_company -> 0002_p4_command_execution` en al menos dos Tenant DB físicas.

---

## 20. Seguridad

Invariantes: no confiar en Tenant/Company raw cuando contradicen principal; no devolver replay sin autorización actual; no almacenar payload completo; no almacenar secretos; no loggear result body; `actor_user_id` se deriva del principal; misma commandId bajo Company/actor/contexto diferente => conflicto; error no filtra información de otro Tenant/Company; no existe idempotency lookup cross-Tenant.

---

## 21. Pruebas obligatorias

### Unit
- `CommandContext` y scopes;
- fingerprint canónico estable;
- fingerprint cambia ante cambio semántico;
- correlation/session no alteran fingerprint;
- replay result size;
- errores P-4;
- optimistic version primitive.

### PostgreSQL integration
Con dos Tenant DB reales: migración P-4 en ambas, registro en DB correcta, mismo command_id físicamente aislado entre Tenants, Company scope válido/inválido, rollback elimina mutación y registro idempotente.

### Idempotency
1. primer comando => efecto una vez;
2. replay secuencial idéntico => no duplicado;
3. mismo command_id + payload distinto => IDEMPOTENCY_CONFLICT;
4. mismo command_id + Company distinta => conflicto;
5. mismo command_id + actor distinto => conflicto;
6. error de infraestructura => rollback completo;
7. retry posterior al rollback puede ejecutar;
8. replay seguro y acotado.

### Concurrency / stress
- dos comandos concurrentes mismo expectedVersion: exactamente uno confirma y el otro recibe CONCURRENCY_CONFLICT;
- múltiples retries concurrentes mismo command_id: máximo un efecto;
- mezcla fingerprint igual/diferente concurrente;
- sin deadlocks no manejados;
- estado final determinista;
- repetir escenarios para descartar carreras intermitentes.

### Authorization regression
- Membership revocada => no replay;
- CompanyAccess revocado => no replay;
- Company inactiva => no operación/replay;
- sesión revocada => no operación/replay.

### Regression P-1/P-2/P-3
Mantener verdes suite P-1, tenancy/isolation P-2, identity/auth/RBAC P-3, Platform Alembic, Tenant Alembic, Docker, health/readiness y logging hygiene.

---

## 22. Evidencias obligatorias

Base/HEAD exactos, diff real, `git diff --check`, lista de archivos, pytest focal + suite completa, XML JUnit, dos PostgreSQL Tenant, migración P-4 real, replay secuencial y concurrente, fingerprint conflict, CAS concurrency, rollback, revocación P-3, secret/log scan, compileall, Docker build/run y working tree limpio.

No se acepta únicamente `BUILD SUCCESSFUL` ni informe textual del agente.

---

## 23. Exclusiones expresas

P-4 NO implementa Milking, Inventory, Manufacturing, Livestock, Sales, lógica Dairy/Aliosur, endpoints universales de command bus, Sync Android, cursor/checkpoint, Outbox/Inbox, event bus distribuido, Kafka/RabbitMQ, saga/distributed transactions, automatic conflict resolution, last-write-wins, business audit completo, Module Registry, ImplementationProfile, API compatibility P-6, Cloud Operations P-8 ni microservicios.

---

## 24. Invariantes no negociables

1. P-4 es neutral respecto del dominio.
2. `command_id` identifica una intención lógica.
3. mismo command_id + misma intención => máximo un efecto.
4. mismo command_id + intención/contexto distinto => conflicto.
5. idempotency record y business mutation comparten transacción Tenant.
6. fallo transaccional => ninguno persiste.
7. replay nunca salta autorización P-3.
8. no cross-Tenant lookup/transaction.
9. no `last-write-wins`.
10. optimistic concurrency usa comparación atómica.
11. conflicto no dispara retry funcional automático.
12. Platform no impone ORM base versionada a todos los módulos.
13. no payload completo en idempotency storage/logs.
14. audit P-4 es técnico, no business audit general.
15. Outbox/Inbox permanece fuera de P-4 salvo adenda expresa.
16. P-1/P-2/P-3 y BE-ADR-001 permanecen cerrados.
17. P-4 debe permitir que futuras escrituras técnicas participen atómicamente en la misma transacción Tenant sin rediseñar su foundation.
18. `command_id` debe ser durable y transportable desde productores externos/offline hasta el servidor sin regeneración obligatoria.
19. ninguna política de retención futura podrá romper las garantías de idempotencia o procesamiento diferido.

---

## 25. Decisiones congeladas

1. `platform_command_executions` vive en cada Tenant DB.
2. idempotency + mutación + replay result se confirman en una misma transacción.
3. P-4 soporta scopes `TENANT` y `COMPANY`.
4. fingerprint incluye command/context/actor/expectedVersion/payload normalizado; no raw HTTP.
5. solo ejecución confirmada genera replay persistente.
6. cada retry/replay revalida autoridad P-3.
7. concurrency = version monotónica + expectedVersion + CAS; no LWW.
8. audit técnico estructurado; business audit fuera.
9. Outbox/Inbox fuera de P-4.
10. no endpoint universal `/commands` en P-4.
11. P-4 no modifica Platform Identity DB.
12. sin borrado automático en P-4.
13. replay result mínimo JSON acotado; propuesta 32 KiB.
14. P-4 preserva extensibilidad para futuras escrituras técnicas en la misma transacción Tenant.
15. `command_id` puede originarse fuera del servidor y preservarse durante procesamiento diferido/offline.
16. cualquier política futura de retención debe preservar idempotencia y reintentos diferidos.

---

## 26. Gate de cierre

> **P-4 será cerrable cuando ERP Platform demuestre sobre PostgreSQL real que comandos mutantes pueden ejecutarse atómicamente, repetirse sin doble efecto, rechazar commandId reutilizado con intención distinta, detectar conflictos de versión sin last-write-wins y producir auditoría técnica segura; preservando autorización P-3, aislamiento P-2 y Core P-1, sin introducir lógica sectorial ni adelantar Sync/Outbox.**

---

## 27. Gobierno Git

Base autorizada: `main @ 2427b8be82385e5f4c071df1e01b084087baee22`.

Rama: `feat/platform-p4-command-integrity`.

Draft PR propio. Commits pequeños y push periódico únicamente a esta rama. Sin merge/tag/force push/rebase destructivo. El cierre de P-4 y el inicio de P-5 requieren autorización expresa del usuario.
