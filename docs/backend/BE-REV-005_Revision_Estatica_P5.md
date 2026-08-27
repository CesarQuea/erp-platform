# BE-REV-005 — Revisión estática de implementación P-5

**Corte:** P-5 — Module Registry + Configuration + Lifecycle  
**Contrato:** `BE-DES-005 v0.1` aprobado/congelado  
**Base autorizada:** `85e52661528756be269888b5970cbecd57cc9b05`  
**HEAD revisado:** `19ec72b363a25a11b4bc69ce5bbba4b251172133`  
**Rama:** `feat/platform-p5-module-foundation`  
**Draft PR:** #9  
**Estado de esta revisión:** APTO PARA VERIFICACIÓN INDEPENDIENTE — NO IMPLICA CIERRE NI MERGE

## 1. Alcance revisado

Se revisó el diff real `85e52661528756be269888b5970cbecd57cc9b05..19ec72b363a25a11b4bc69ce5bbba4b251172133` y la composición final del corte.

El cambio se concentra en:

- `app/platform/modules/*`;
- `app/infrastructure/database/module_*`;
- `app/bootstrap/module_platform.py`;
- definición de módulo del bounded context Milking;
- migración Tenant `0005_p5_module_activation`;
- extensión aditiva del CAS P-4 para identidad compuesta;
- wiring mínimo en `application.py`;
- pruebas P-5 y ajustes de tests históricos O-4 por el nuevo head de migración;
- documentación P-5.

No se añadieron endpoints HTTP P-5/P-6 ni enforcement sobre endpoints Milking.

## 2. Correspondencia con BE-DES-005

La revisión estática confirma implementación de:

- `ModuleDefinition` con `module_id`, `module_version`, `configuration_namespace`, `description`;
- SemVer compatible para `module_version`;
- `configuration_namespace == module_id` en P-5 v0.1;
- `ModuleRegistry` explícito, determinista e inmutable post-bootstrap;
- Milking registrado como primer módulo desplegado;
- activación Company-scoped dentro de cada Tenant DB;
- ausencia de fila = `DISABLED/version 0`;
- lifecycle persistido limitado a `ENABLED/DISABLED`;
- disable no destructivo;
- separación activation/readiness/authorization/entitlement/feature flags;
- `ModuleAvailabilityService`;
- `ModuleActivationService`;
- mutaciones sobre P-4 `CommandExecutionService`;
- CAS optimista sin last-write-wins;
- migración lineal `0004_o4_milking_lifecycle_hardening -> 0005_p5_module_activation`;
- ausencia de plugin engine, generic config store, dependency solver y lógica sectorial en Platform.

## 3. Hallazgos detectados y corregidos durante la revisión

### H-01 — Contrato Git condensado

El primer registro Git contenía una versión condensada de `BE-DES-005`.

**Corrección:** se restauró íntegramente el documento aprobado/congelado. Las autorizaciones posteriores se registran separadamente en `BE-REG-005`, sin reescribir el estado histórico del contrato.

### H-02 — `effective_enabled` dentro del replay de mutación

Un resultado replayable podía representar disponibilidad efectiva histórica y quedar obsoleto.

**Corrección:** las mutaciones devuelven únicamente hecho durable de la mutación (`module_id`, `state`, `version`, `changed`). La autoridad de disponibilidad efectiva queda en `ModuleAvailabilityService`.

### H-03 — Namespace más amplio que el contrato v0.1

La validación permitía namespaces jerárquicos aunque el contrato inicial exige igualdad con `module_id`.

**Corrección:** `configuration_namespace == module_id` se valida explícitamente.

### H-04 — Índice especulativo

Se había añadido un índice `(company_id, state)` sin consumidor actual.

**Corrección:** eliminado para evitar sobrearquitectura; la PK `(company_id, module_id)` cubre las lecturas contractuales actuales.

### H-05 — Activation huérfana

Una fila histórica cuyo módulo ya no estuviera registrado podía quedar oculta como simple estado falso.

**Corrección:** módulo no registrado produce `MODULE_NOT_REGISTERED` y el sistema falla cerrado; el listado detecta activaciones huérfanas.

### H-06 — Metadata de actualización inconsistente

Dominio y DB no exigían inicialmente la misma relación entre `version` y `updated_*`.

**Corrección:** v1 exige `updated_at/updated_by = NULL`; v2+ exige ambos presentes, tanto en dominio como en constraint DB.

### H-07 — Lectura ORM potencialmente stale después del CAS compuesto

El servicio normalmente carga la activation antes de ejecutar el `UPDATE` Core; la identity map podía conservar la instancia pre-CAS.

**Corrección:** después del CAS, el repository fuerza refresh ORM con `populate_existing=True`. Se añadió prueba focal específica.

### H-08 — Invariantes incompletas de `CompanyModuleStatus`

El dataclass permitía combinaciones imposibles como activation ausente + `ENABLED`, o activation presente con `version=0`.

**Corrección:** las combinaciones de `activation_present/state/version/effective_enabled` se validan explícitamente.

### H-09 — Orden autorización/existencia

La mutación comprobaba registro del módulo antes de autorizar al principal, permitiendo potencial enumeración por diferencia de error.

**Corrección:** P-3 authorization se evalúa primero a través de P-4; la existencia del módulo se verifica dentro de la operación autorizada. Se añadió prueba dedicada.

## 4. Preservación de contratos cerrados

### P-4

La única modificación de código P-4 es aditiva: `SqlAlchemyCompareAndSet.update_versioned()` conserva su firma y delega a una nueva variante reutilizable para identidades compuestas. No se cambia la semántica del API existente.

### O-4

No se modifican dominio, servicios funcionales, tablas ni endpoints Milking. `app/modules/milking/module.py` aporta únicamente metadata estática al registry.

Los cambios en tests O-4 son de migración:

- el forward test O-4 fija explícitamente su target histórico `0004`;
- el migration-chain test reconoce que `0005` extiende linealmente a `0004`.

Debe verificarse dinámicamente que la suite O-4 completa permanezca verde sobre el nuevo head Tenant.

## 5. Migración revisada

`0005_p5_module_activation`:

- `down_revision = 0004_o4_milking_lifecycle_hardening`;
- crea solo `platform_module_activations`;
- PK `(company_id, module_id)`;
- FK `company_id -> companies.id ON DELETE RESTRICT`;
- estados limitados a `ENABLED/DISABLED`;
- `version >= 1`;
- `module_id` no vacío;
- consistencia `version/update metadata`;
- no backfill Milking;
- no modificación de tablas Milking ni P-4 command table.

## 6. Pruebas incorporadas

La rama contiene pruebas para:

- definición/versionado/registry;
- namespace ownership;
- lifecycle v0/v1/v2/v3 y no-op;
- unknown/orphan module fail-closed;
- autorización independiente;
- idempotency replay/fingerprint conflict;
- rollback;
- repository/constraints;
- refresh ORM post-CAS;
- PostgreSQL real con dos Tenant DB;
- aislamiento Company/Tenant;
- concurrencia primer enable y CAS de cambios;
- forward migration `0004 -> 0005`;
- migration chain;
- regresión funcional O-4 sobre schema P-5.

La existencia de estos tests no constituye evidencia de ejecución.

## 7. Revisión de sobrearquitectura y exclusiones

No se observan en el diff:

- plugin engine;
- package manager;
- filesystem scanning/reflection;
- dynamic loading/hot reload;
- dependency solver;
- install/uninstall lifecycle;
- third-party modules;
- generic JSON config store;
- feature flags;
- entitlement/licensing;
- endpoints universales de módulos;
- enforcement HTTP P-6;
- Sync P-7;
- Outbox/Inbox;
- P-8 Operations;
- microservicios;
- Site/OperationalUnit;
- lógica Dairy/Aliosur hardcodeada en Platform.

## 8. Resultado estático

No queda identificado un bloqueo estático conocido para pasar a verificación independiente.

Esto NO significa que P-5 esté cerrado. Aún deben demostrarse con ejecución real:

- suite focal;
- suite completa;
- PostgreSQL real en dos Tenant DB;
- migración forward `0004 -> 0005`;
- constraints reales;
- concurrencia/stress;
- rollback;
- P-4 replay/conflict;
- regresión O-4;
- compile/import;
- Docker build/run;
- health/live/ready;
- hygiene de secretos/logs;
- working tree limpio.

## 9. Gate posterior

El agente verificador debe trabajar sobre el HEAD exacto indicado por ChatGPT al momento de entrega del prompt y NO modificar código ni documentación.

Cualquier cambio posterior en la rama invalida el HEAD verificado y requiere repetir al menos las verificaciones afectadas.

Solo el usuario puede autorizar cierre y merge de P-5.
