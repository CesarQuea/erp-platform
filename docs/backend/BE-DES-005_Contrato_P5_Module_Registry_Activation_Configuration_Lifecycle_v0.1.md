# BE-DES-005 — Contrato P-5 Module Registry, Activation, Configuration Ownership & Lifecycle

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO — IMPLEMENTACIÓN AUTORIZADA SOBRE BASE FIJADA  
**Fecha:** 2026-08-26  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Plan maestro:** `BE-PLAN-001 v0.2`  
**ADR rector:** `BE-ADR-002 v0.1`  
**Base autorizada:** `85e52661528756be269888b5970cbecd57cc9b05`  
**Rama:** `feat/platform-p5-module-foundation`

## 1. Objetivo

Implementar la foundation transversal mínima y completa para que ERP Platform pueda declarar módulos de negocio disponibles en el runtime, identificarlos mediante IDs técnicos estables y versionados, persistir activación por Company, consultar estado efectivo, habilitar/deshabilitar de forma no destructiva, declarar ownership de configuración sin absorber configuración funcional y dejar una API interna reutilizable por P-6/P-7 y módulos futuros.

P-5 v0.1 no implementa plugin engine, marketplace, carga dinámica, package manager ni store genérico de configuración funcional.

## 2. Arquitectura

P-5 usa arquitectura evolutiva, bounded contexts y plataforma transversal incremental. La composición de módulos es explícita/estática en este incremento, pero `ModuleDefinition` y `ModuleRegistry` no deben impedir una evolución futura hacia manifests/paquetes instalables.

### 2.1 ModuleDefinition

Campos mínimos:

- `module_id`: técnico, estable, minúsculas, no traducible, no reutilizable;
- `module_version`: SemVer compatible `MAJOR.MINOR.PATCH`, separada de API version y Alembic;
- `configuration_namespace`: ownership de configuración, inicialmente igual a `module_id`;
- `description`: opcional.

### 2.2 ModuleRegistry

Registry in-process, explícito, determinista e inmutable tras bootstrap. Debe soportar `register`, `get`, `list`, `contains`; duplicado falla bootstrap; módulo desconocido => `MODULE_NOT_REGISTERED`. Sin scanning, reflection, imports dinámicos, hot load/unload.

### 2.3 Scope

Activación exclusivamente Company-scoped dentro de cada Tenant DB:

`Tenant DB + Company + module_id`.

No existe override Tenant-default/Company-override en P-5 v0.1.

## 3. Persistencia

Nueva tabla Tenant `platform_module_activations`:

- `company_id UUID`;
- `module_id VARCHAR`;
- `state VARCHAR`;
- `version BIGINT`;
- `created_at TIMESTAMPTZ`;
- `created_by UUID`;
- `updated_at TIMESTAMPTZ NULL`;
- `updated_by UUID NULL`.

PK `(company_id, module_id)`, FK `company_id -> companies.id`, checks `state IN ('ENABLED','DISABLED')`, `version >= 1`, `module_id` no vacío. No se almacena `tenant_id` porque la DB física es la frontera Tenant. No se persiste la definición completa del módulo.

Migración propuesta: `0005_p5_module_activation`, descendiente de `0004_o4_milking_lifecycle_hardening`.

## 4. Estado efectivo

`AVAILABLE = ModuleRegistry.contains(module_id)`.

`EFFECTIVELY_ENABLED = AVAILABLE AND Company active AND activation.state == ENABLED`.

Ausencia de fila => `DISABLED`, `version=0`, fail-closed. Si existe activation histórica pero el módulo no está registrado en runtime => `MODULE_NOT_REGISTERED`, fail-closed.

`ENABLED` no equivale a `OPERATIONALLY_READY`: readiness funcional pertenece al bounded context.

## 5. Lifecycle mínimo

Estados persistidos: `ENABLED`, `DISABLED`.

Ausente representa estado inicial efectivo `DISABLED/version 0`.

Enable/disable no instala ni elimina schema, no borra datos, no cancela workflows, no revierte estados funcionales, no ejecuta compensaciones y no resuelve sync pendiente. Migrations y activation son conceptos separados; Alembic sigue siendo global por Tenant DB.

## 6. Configuration ownership

Platform gobierna activación y ownership/namespace; cada bounded context gobierna semántica y persistencia de su configuración funcional. No se crea JSONB settings genérico ni key/value store.

Milking mantiene intacta su configuración O-4 (`Company + Farm + Shift -> OutputProfileVersion`).

## 7. Separación de responsabilidades

- Activation != Authorization P-3.
- Activation != Entitlement/Licensing/Billing.
- Module activation != Feature Flags.
- Ningún módulo puede asumir dependencias implícitas de otro bounded context.
- Dependencias futuras o módulos bridge requieren análisis/contrato posterior.

## 8. ModuleAvailabilityService

Foundation interna reutilizable:

- `is_registered(module_id)`;
- `get_activation(tenant_context, company_id, module_id)`;
- `is_enabled(...)`;
- `require_enabled(...)`;
- `list_available_modules()`;
- `list_company_modules(...)`.

P-5 no modifica todavía el comportamiento HTTP de endpoints O-4. P-6 congelará el enforcement y representación HTTP común.

## 9. Mutaciones e integridad P-4

`enable_module` y `disable_module` reutilizan P-4:

- `command_id`;
- `expected_version`;
- actor derivado de P-3;
- Tenant/Company context derivado de autoridad autenticada;
- CAS/idempotencia;
- sin last-write-wins.

Versionado:

- ausente => v0;
- primera activación => v1;
- cada cambio efectivo => `version + 1`.

Mismo `command_id` + misma intención => replay. Mismo `command_id` + intención distinta => `IDEMPOTENCY_CONFLICT`. Writers con mismo `expected_version`: máximo uno confirma, resto `CONCURRENCY_CONFLICT`.

## 10. Authorization boundary

P-5 no crea un sistema paralelo de autorización. La administración pública futura deberá usar capability transversal dedicada; código propuesto `platform.modules.manage`, cuyo contrato HTTP definitivo queda para P-6.

## 11. Milking como primer módulo

Se registra:

- `module_id = "milking"`;
- `module_version = "1.0.0"`;
- `configuration_namespace = "milking"`.

La definición vive del lado del bounded context y se aporta al registry durante composition/bootstrap. Platform no conoce Farm, Shift, OutputProfile, MilkingSession, MilkingOutput ni reglas de ordeño.

P-5 no reabre ni modifica O-4 y no aplica todavía enforcement HTTP de activation sobre endpoints Milking.

## 12. Compatibilidad futura

P-5 v0.1 usa registro explícito de módulos desplegados, pero deja compatible una evolución futura hacia:

`Module Package / Manifest -> validación -> ModuleRegistry -> installation/activation`.

Quedan fuera de P-5 v0.1: manifests externos, paquetes instalables, dependency solver, third-party runtime modules, installation lifecycle y bridge/integration modules; estos últimos se reconocen como evolución válida futura.

## 13. P-6/P-7

P-6 podrá consumir P-5 para enforcement HTTP, catálogo/activación y contratos comunes. P-7 deberá revalidar activation en servidor y no sincronizar módulos deshabilitados; comandos creados offline no conservan autoridad por una activación pasada.

## 14. Backfill

P-5 no aplica enforcement HTTP todavía y no hardcodea un backfill Milking en la migración. Antes de P-6 enforcement público deberá existir política explícita de provisioning/activation para Companies existentes.

## 15. Errores mínimos

- `MODULE_NOT_REGISTERED`;
- `MODULE_NOT_ENABLED`;
- `MODULE_ACTIVATION_NOT_AVAILABLE`;
- `CONCURRENCY_CONFLICT`;
- `IDEMPOTENCY_CONFLICT`.

P-6 congelará representación HTTP común.

## 16. Pruebas obligatorias

Unitarias: validación `module_id/module_version`, duplicados, registry frozen, unknown module, namespace ownership, absent=disabled/v0, lifecycle y versiones.

PostgreSQL real con dos Tenant DB: migración `0004 -> 0005`, PK/FK/checks, aislamiento Company/Tenant, enable v1, disable v2, re-enable v3, rollback, replay/fingerprint conflict P-4.

Concurrencia: dos writers con mismo expectedVersion => uno confirma/otro conflict; stress repetido.

Regresión: P-1/P-2/P-3/P-4/O-4, migrations, Docker y health/live/ready.

## 17. Exclusiones expresas

No plugin engine, dynamic loading, scanning, hot reload/unload, marketplace, install/uninstall, dependency graph/solver, manifest externo, package manager, third-party runtime modules, migrations condicionadas por módulo, generic config store, configuración funcional de módulos, endpoint universal `/modules` en P-5, UI Web, P-6 compatibility, P-7 Sync, Outbox/Inbox, P-8 operations, microservicios, Site/OperationalUnit ni lógica sectorial.

## 18. Invariantes congeladas

1. Registry contiene únicamente módulos desplegados y es explícito/determinista en v0.1.
2. `ModuleDefinition` incluye `module_version` y es evolutivo hacia manifests/paquetes futuros.
3. Core Platform no es deshabilitable vía P-5.
4. Activation v0.1 es Company-scoped y Tenant sigue siendo frontera física.
5. Ausencia de activation = disabled/version 0.
6. Registry + Company activa + activation ENABLED determinan disponibilidad efectiva.
7. `ENABLED` no implica readiness funcional.
8. Activation, Authorization, Entitlement y Feature Flags son conceptos distintos.
9. Disable es administrativo/no destructivo.
10. Migrations no dependen de activation.
11. Mutaciones de activation usan P-4 y no LWW.
12. Configuration ownership no equivale a generic configuration storage.
13. Cada módulo conserva su configuración y semántica funcional.
14. No existen dependencias implícitas entre módulos.
15. P-5 no modifica todavía contratos HTTP O-4.
16. P-6/P-7 consumen P-5 y no duplican registry/activation.
17. P-1/P-2/P-3/P-4/O-4 permanecen cerrados.

## 19. Gate de cierre

P-5 será cerrable cuando ERP Platform pueda declarar módulos explícitamente, persistir/consultar activation Company-scoped con PostgreSQL real, modificarla de forma idempotente y concurrentemente segura usando P-4, mantener aislamiento Tenant/Company y preservar O-4 sin plugin engines, generic config stores ni lógica sectorial.

## 20. Gobierno Git

Base autorizada exacta: `85e52661528756be269888b5970cbecd57cc9b05`.

Rama exclusiva: `feat/platform-p5-module-foundation`.

Prohibidos push directo a `main`, force push, merge/tag sin autorización, rebase destructivo e iniciar P-6 sin cierre y autorización correspondiente.
