# BE-DES-005 — Contrato P-5 Module Registry, Activation, Configuration Ownership & Lifecycle

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO — IMPLEMENTACIÓN NO AUTORIZADA  
**Fecha:** 2026-08-26  
**Aprobación:** aprobada expresamente por el usuario el 2026-08-26  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Plan maestro:** `BE-PLAN-001 v0.2`  
**ADR rector:** `BE-ADR-002 v0.1` — aprobado/congelado, pendiente de merge documental  
**Base de implementación:** **TBD — debe ser el SHA exacto de `main` posterior al merge autorizado de BE-ADR-002**  
**Rama propuesta:** `feat/platform-p5-module-foundation`

---

## 1. Objetivo

Implementar la foundation transversal mínima y completa para que ERP Platform pueda:

- declarar qué módulos de negocio existen en el runtime;
- identificarlos mediante IDs técnicos estables;
- persistir su activación por Company;
- consultar su estado efectivo;
- habilitar/deshabilitar módulos de forma no destructiva;
- establecer la propiedad de configuración sin absorber configuración funcional de los dominios;
- ofrecer una API interna reutilizable para que P-6, P-7 y los módulos consuman esta información.

P-5 no implementa un plugin engine, marketplace, carga dinámica ni un sistema genérico de configuración funcional.

---

## 2. Contexto real

Después de O-4, `erp-platform` ya contiene:

```text
app/modules/
└── milking
```

pero la composición actual es estática:

```text
application.py
  └── build_milking_platform(...)

api/v1/router.py
  └── include_router(milking_router)
```

Esto es correcto para el monolito modular actual.

P-5 no sustituirá esta composición estática por carga dinámica.

P-5 agrega únicamente la capacidad transversal de:

```text
módulo disponible en el runtime
+
activación persistida por Company
+
consulta/lifecycle mínimo
```

---

## 3. Principios preservados

P-5 preserva:

- P-1 Core Runtime;
- P-2 Tenant + Company + PostgreSQL por Tenant;
- P-3 Identity/Auth/RBAC;
- P-4 Transactions + Idempotency + Concurrency + Audit;
- BE-ADR-001 `Tenant -> Company`;
- BE-ADR-002 arquitectura evolutiva + bounded contexts + plataforma transversal incremental;
- O-4 Milking cerrado.

P-5 no reabre ni redefine esos contratos.

---

# 4. Alcance mínimo P-5

P-5 se limita a cuatro piezas:

```text
ModuleDefinition
ModuleRegistry
CompanyModuleActivation
ModuleAvailabilityService
```

más:

- persistencia Tenant;
- lifecycle mínimo ENABLED/DISABLED;
- ownership explícito de configuración;
- integración con P-4 para mutaciones;
- pruebas PostgreSQL/concurrencia/migración;
- registro inicial del módulo Milking como módulo conocido.

---

# 5. ModuleDefinition

Un módulo desplegado en el monolito declara una definición estática e inmutable equivalente a:

```text
ModuleDefinition
├── module_id
├── module_version
├── configuration_namespace
└── description optional
```

## 5.1 module_id

`module_id` es un identificador técnico estable.

Ejemplo actual:

```text
milking
```

Reglas:

1. minúsculas;
2. estable entre releases;
3. no es nombre traducido de UI;
4. no depende de Tenant/Company;
5. no se reutiliza para otro bounded context;
6. duplicados provocan error de bootstrap.

## 5.2 module_version

Cada módulo declara una versión técnica estable y explícita:

```text
module_version
```

Reglas:

1. identifica la versión del módulo desplegado;
2. no representa la versión de la API pública; P-6 gobernará versionado/compatibilidad API;
3. no representa la revisión Alembic de la Tenant DB;
4. debe ser comparable y trazable entre releases;
5. su formato inicial será SemVer compatible (`MAJOR.MINOR.PATCH`);
6. se utiliza para diagnóstico, compatibilidad futura y evolución de módulos;
7. P-5 v0.1 no implementa resolución automática de dependencias por versión.

Ejemplo:

```text
module_id      = "milking"
module_version = "1.0.0"
```

## 5.3 configuration_namespace

Cada módulo declara un namespace de propiedad de configuración.

Inicialmente:

```text
configuration_namespace == module_id
```

Esto NO crea un store JSON genérico.

Su finalidad es declarar autoridad:

```text
milking.*  -> Milking
inventory.* -> Inventory
```

La persistencia y semántica de valores funcionales siguen perteneciendo al módulo.

---

# 6. ModuleRegistry

`ModuleRegistry` es una estructura in-process construida explícitamente durante bootstrap.

Debe permitir:

```text
register(definition)
get(module_id)
list()
contains(module_id)
```

Invariantes:

1. registro explícito;
2. determinista;
3. sin filesystem scanning;
4. sin reflection automática;
5. sin imports dinámicos por configuración;
6. sin carga/descarga en caliente;
7. duplicado de module_id => fallo de bootstrap;
8. module_id desconocido => `MODULE_NOT_REGISTERED`.

Una vez completado el bootstrap, el registry se considera inmutable durante la vida del proceso.


## 6.1 Compatibilidad futura del Registry

P-5 v0.1 utiliza registro explícito de módulos desplegados, pero el contrato del registry no deberá impedir una evolución posterior hacia:

```text
Module Package / Manifest
        ↓
validación
        ↓
ModuleRegistry
        ↓
installation/activation
```

La evolución futura podrá incorporar, mediante nuevos contratos:

- manifests externos;
- paquetes instalables;
- dependencias declarativas;
- módulos de integración/bridge;
- validación de compatibilidad;
- lifecycle de instalación.

Estas capacidades NO se implementan en P-5 v0.1.

La activación Company-scoped definida en este contrato deberá poder preservarse si en el futuro cambia el mecanismo mediante el cual un módulo llega al registry.

---

# 7. Qué NO es un módulo P-5

Las capacidades Core/Platform cerradas no son módulos activables:

```text
tenancy
company
identity
authorization
commands/idempotency
transactions
audit técnico
```

No pueden deshabilitarse mediante P-5.

P-5 gobierna bounded contexts funcionales, por ejemplo:

```text
milking
inventory
manufacturing
livestock
sales
```

cuando existan en backend.

---

# 8. Scope de activación

P-5 v0.1 adopta exclusivamente activación por:

```text
Tenant DB
+
Company
+
module_id
```

No introduce una segunda jerarquía de override Tenant + Company.

Razón:

- el Tenant ya es frontera física de DB;
- los módulos funcionales operan actualmente dentro de Company;
- soportar precedencias Tenant-default/Company-override sin un caso real añade complejidad innecesaria.

Una necesidad real de activación Tenant-wide podrá ampliar P-5 mediante nuevo incremento contractual.

---

# 9. Persistencia

Nueva tabla técnica Tenant:

```text
platform_module_activations
```

Modelo conceptual:

```text
company_id      UUID
module_id       VARCHAR
state           VARCHAR
version         BIGINT
created_at      TIMESTAMPTZ
created_by      UUID
updated_at      TIMESTAMPTZ NULL
updated_by      UUID NULL
```

Clave:

```text
PRIMARY KEY(company_id, module_id)
```

FK:

```text
company_id -> companies.id
```

Checks mínimos:

```text
state IN ('ENABLED', 'DISABLED')
version >= 1
module_id no vacío
```

No se almacena `tenant_id` porque la DB física pertenece al Tenant.

No se almacena la definición completa del módulo en DB.

---

# 10. Estado efectivo

Se distinguen dos conceptos:

## 10.1 Disponible

```text
AVAILABLE
```

significa:

> el módulo está registrado en el runtime desplegado.

## 10.2 Activado

Estado persistido por Company:

```text
ENABLED
DISABLED
```

Estado efectivo:

```text
registered
AND
company active
AND
activation == ENABLED
```

Si no existe fila de activación:

```text
effective state = DISABLED
version = 0
```

Esto es fail-closed.

---

# 11. Lifecycle mínimo

P-5 v0.1 implementa exclusivamente:

```text
UNCONFIGURED/ABSENT (effective DISABLED, version 0)
        ↓ enable
ENABLED
        ↓ disable
DISABLED
        ↓ enable
ENABLED
```

Reglas:

1. habilitar no crea ni migra schema del módulo;
2. deshabilitar no elimina tablas;
3. deshabilitar no borra datos;
4. deshabilitar no cancela workflows;
5. deshabilitar no modifica estados funcionales;
6. re-habilitar no recrea datos;
7. activation lifecycle y business lifecycle son independientes.

P-5 no implementa:

```text
INSTALLING
INSTALLED
UPGRADING
FAILED
UNINSTALLING
```

---

# 12. Migrations y activation son conceptos distintos

En el monolito modular:

> la presencia del schema físico no implica que el módulo esté habilitado para una Company.

Una Tenant DB puede contener tablas Milking aunque Milking esté deshabilitado para una Company.

P-5 no condiciona Alembic a activaciones.

Esto evita migraciones parciales diferentes entre Companies dentro de la misma Tenant DB.

---

# 13. Configuration ownership

P-5 NO introduce:

```text
platform_module_settings JSONB
generic key/value config store
arbitrary JSON configuration
```

Regla:

> Platform gobierna activación y propiedad; cada bounded context gobierna la semántica y persistencia de su configuración funcional.

Ejemplo:

```text
P-5:
milking está ENABLED para Company X

Milking:
Company + Farm + Shift -> OutputProfileVersion
```

`MilkingConfiguration` de O-4 permanece íntegramente dentro del módulo Milking.

---

# 14. ModuleAvailabilityService

P-5 expone internamente una abstracción transversal equivalente a:

```text
is_registered(module_id)
get_activation(tenant_context, company_id, module_id)
is_enabled(tenant_context, company_id, module_id)
require_enabled(...)
list_available_modules()
list_company_modules(...)
```

Debe ser consumible por:

- P-6 API foundation;
- P-7 Sync foundation;
- módulos futuros;
- provisioning/administración posterior.

P-5 v0.1 NO obliga todavía a que todos los endpoints O-4 sean bloqueados por esta foundation.

La política HTTP común de enforcement se congela en P-6.

---

# 15. Mutaciones de activation

Mutaciones:

```text
enable_module
disable_module
```

usan P-4.

Cada mutación requiere:

```text
command_id
expected_version
actor
Tenant/Company context
```

Convención de versión:

```text
fila ausente => version 0
primera activación => version 1
cada cambio efectivo => version + 1
```

Ejemplo:

```text
enable(module=milking, expected_version=0)
  -> ENABLED version 1
```

Dos administradores con expectedVersion igual:

```text
máximo uno confirma
otro -> CONCURRENCY_CONFLICT
```

No se usa last-write-wins.

---

# 16. Idempotencia

Las mutaciones P-5 reutilizan:

```text
platform_command_executions
```

No se crea:

```text
module_command_executions
module_idempotency
```

Mismo command_id + misma intención:

```text
replay
```

Mismo command_id + intención distinta:

```text
IDEMPOTENCY_CONFLICT
```

---

# 17. Authorization boundary

P-5 no crea un nuevo sistema de autorización.

La identidad del actor y Company provienen de P-3.

P-5 v0.1 congela que la futura administración pública de módulos deberá exigir una capability transversal dedicada.

Código propuesto:

```text
platform.modules.manage
```

Sin embargo, la exposición HTTP de administración y su contrato definitivo quedan para P-6.

Los servicios internos no deberán aceptar `actor_id`, `tenant_id` o `company_id` de confianza ciega si existe `AuthenticatedPrincipal`.

---

# 18. Milking como primer módulo registrado

P-5 registrará:

```text
module_id               = "milking"
module_version          = "1.0.0"
configuration_namespace = "milking"
```

Esto NO traslada ninguna regla Milking a Platform.

P-5 no conoce:

- Farm;
- Shift;
- OutputProfile;
- MilkingSession;
- MilkingOutput;
- cantidades;
- lifecycle de ordeño.

La definición del módulo debe vivir del lado del bounded context y ser aportada al registry durante composition/bootstrap.

---

# 19. Compatibilidad con O-4

P-5 no reabre O-4.

No modifica:

- tablas funcionales Milking;
- invariantes GENERAL/TOTAL;
- OutputProfile;
- MilkingConfiguration;
- MilkingSession;
- MilkingOutput;
- AnnulmentRequest;
- business audit.

En P-5 v0.1 no se cambia todavía el comportamiento HTTP de O-4 según activation.

Esto evita introducir una nueva regla pública antes de P-6.

P-6 decidirá cómo una API responde cuando un módulo está registrado pero no habilitado.

---

# 20. Reglas adicionales de separación y estado

## 20.1 ENABLED no equivale a OPERATIONALLY_READY

P-5 distingue activación administrativa de readiness funcional.

```text
REGISTERED
+
ENABLED
≠
OPERATIONALLY_READY
```

Platform puede determinar si un módulo está registrado y habilitado, pero no interpreta si su configuración funcional es suficiente para operar.

Ejemplo:

```text
Platform:
is_enabled("milking") -> true

Milking:
is_operationally_ready(...) -> false
```

si falta configuración propia como `Company + Farm + Shift -> OutputProfileVersion`.

La readiness funcional pertenece al bounded context.

## 20.2 Activation no equivale a Authorization

La activación responde:

> ¿La Company tiene administrativamente habilitado este módulo?

La autorización P-3 responde:

> ¿Este usuario puede ejecutar esta operación?

Ambos gates son ortogonales y obligatorios cuando correspondan.

P-5 no incorpora permisos dentro de `platform_module_activations`.

## 20.3 Activation no equivale a Entitlement o Licensing

P-5 no implementa licenciamiento, billing, planes comerciales ni entitlement.

Se congela expresamente:

```text
entitlement != activation
```

Una futura capacidad SaaS/licensing deberá tener contrato y autoridad propios y podrá condicionar activation, pero no reutilizará semánticamente `platform_module_activations` como tabla de licencias.

## 20.4 Disable es administrativo y no destructivo

Deshabilitar un módulo:

- no borra datos;
- no elimina schema;
- no cancela workflows;
- no revierte estados funcionales;
- no ejecuta compensaciones;
- no elimina histórico;
- no resuelve sync pendiente por sí mismo.

Cuando P-6 introduzca enforcement público, `DISABLED` impedirá nuevas operaciones funcionales según el contrato API correspondiente.

La política sobre comandos creados offline antes de un disable se resolverá en P-7/O-5 mediante revalidación servidor.

## 20.5 Disponibilidad efectiva requiere Registry + Activation

La existencia de una fila de activación no convierte en disponible a un módulo cuyo código no está desplegado/registrado.

Regla:

```text
AVAILABLE
=
ModuleRegistry.contains(module_id)

EFFECTIVELY_ENABLED
=
AVAILABLE
AND Company active
AND activation.state == ENABLED
```

Si existe activation pero el módulo no está registrado:

```text
MODULE_NOT_REGISTERED
```

y el sistema actúa fail-closed.

Esto protege deployments, rollbacks y versiones donde una activación histórica pueda quedar huérfana.

## 20.6 Module activation no es feature flag

P-5 gobierna bounded contexts funcionales, no flags de funcionalidades internas.

No se utilizará `platform_module_activations` para representar características como:

```text
milking_new_screen
inventory_batch_feature
experimental_report
```

Si en el futuro se requieren feature flags, deberán tener mecanismo y contrato separados.

## 20.7 Dependencias no pueden ser implícitas

P-5 v0.1 no implementa dependency graph.

Sin embargo, ningún módulo podrá asumir silenciosamente que otro está habilitado.

Si aparece una dependencia real entre bounded contexts, deberá analizarse para decidir si corresponde:

- dependencia contractual explícita futura; o
- módulo/adaptador de integración separado.

---

# 21. Compatibilidad con P-6 y P-7

P-5 debe dejar una foundation suficiente para que posteriormente:

```text
P-6:
- exponga catálogo/activation si corresponde;
- aplique module availability a contratos HTTP;
- defina error envelope/compatibilidad.

P-7:
- conozca qué módulos están habilitados;
- no sincronice módulos deshabilitados;
- use module_id como namespace estable de sync.
```

P-5 no implementa ninguna de esas responsabilidades.

---

# 22. Migración

La siguiente revisión Tenant deberá partir del head actual:

```text
0004_o4_milking_lifecycle_hardening
```

Migración propuesta:

```text
0005_p5_module_activation
```

Crea únicamente:

```text
platform_module_activations
```

No modifica:

- Platform Identity DB;
- tablas Milking;
- P-4 command table;
- companies salvo FK referenciada.

---

# 23. Backfill y comportamiento existente

P-5 v0.1 NO aplicará todavía enforcement HTTP sobre Milking.

Por tanto, la ausencia inicial de una fila de activation no rompe O-4.

No se requiere hardcodear un backfill Milking dentro de la migración Platform.

Antes de que P-6 active enforcement público, deberá existir una política explícita de provisioning/activation para Companies existentes.

Esta decisión evita introducir data migration sectorial dentro del Core P-5.

---

# 24. Errores P-5

Códigos internos mínimos:

```text
MODULE_NOT_REGISTERED
MODULE_NOT_ENABLED
MODULE_ACTIVATION_NOT_AVAILABLE
CONCURRENCY_CONFLICT
IDEMPOTENCY_CONFLICT
```

P-6 congelará su representación HTTP común.

---

# 25. Pruebas obligatorias

## 24.1 Unit

- module_id válido;
- duplicate registration;
- registry immutable post-bootstrap;
- unknown module;
- configuration namespace ownership;
- effective state absent = disabled;
- lifecycle enabled/disabled;
- version semantics;
- error mapping interno.

## 24.2 PostgreSQL real

Con al menos dos Tenant DB:

- migración `0004 -> 0005`;
- tabla/PK/FK/checks;
- Company A activation no aparece en Company B;
- mismo module_id en Tenant A/B físicamente aislado;
- ausencia = disabled/version 0;
- enable => v1;
- disable => v2;
- re-enable => v3;
- rollback;
- P-4 replay;
- P-4 fingerprint conflict.

## 24.3 Concurrency

- dos enable concurrentes expectedVersion=0 -> máximo uno confirma;
- dos cambios concurrentes mismo expectedVersion -> uno confirma, otro conflict;
- ninguna carrera produce doble versión válida;
- repetir stress múltiples iteraciones.

## 24.4 Regression

Mantener verdes:

- P-1;
- P-2;
- P-3;
- P-4;
- O-4 Milking;
- Tenant migrations;
- Docker;
- health/live/ready.

---

# 26. Evidencia obligatoria

Verificador independiente debe aportar:

- SHA base;
- HEAD;
- diff;
- `git diff --check`;
- XML JUnit focal;
- XML suite completa;
- dos Tenant PostgreSQL;
- migration `0004 -> 0005`;
- constraints reales;
- activation isolation;
- concurrency/stress;
- P-4 replay/conflict;
- rollback;
- compile/import;
- Docker build/run;
- health/live/ready;
- secret/log hygiene;
- working tree limpio.

El verificador no modifica código.

---

# 27. Exclusiones expresas

P-5 NO implementa:

- plugin engine;
- dynamic module loading;
- filesystem/module scanning;
- hot reload/unload;
- marketplace;
- install/uninstall de módulos;
- dependency graph/solver;
- instalación/desinstalación dinámica;
- descubrimiento de módulos por manifest externo;
- package manager de módulos;
- módulos de terceros cargables en runtime;
- migrations condicionadas por módulo;
- generic JSON config store;
- configuración funcional Milking;
- configuración funcional Inventory;
- endpoint universal `/modules` todavía;
- UI Web;
- P-6 compatibility;
- P-7 Sync;
- Outbox/Inbox;
- P-8 operations;
- microservicios;
- Site/OperationalUnit;
- lógica Dairy/Aliosur.

---

# 28. Invariantes propuestas

1. ModuleRegistry contiene únicamente módulos desplegados.
2. Registry es explícito y determinista en P-5 v0.1.
3. ModuleDefinition incluye `module_version` desde P-5 v0.1.
4. El contrato del Registry debe permitir evolución futura hacia manifests/paquetes sin romper la activación existente.
5. `ENABLED` no equivale a readiness funcional; cada bounded context gobierna su readiness.
6. Activation y Authorization son gates distintos.
7. Activation y Entitlement/Licensing son conceptos distintos.
8. Disable es administrativo y no destructivo.
9. La disponibilidad efectiva exige registro runtime + Company activa + activation ENABLED.
10. Module activation no se utilizará como feature flag.
11. Ningún módulo puede asumir dependencias implícitas sobre otro bounded context.
12. Platform Core no es deshabilitable vía P-5.
13. activación P-5 v0.1 es Company-scoped.
14. Tenant sigue siendo frontera física de aislamiento.
15. ausencia de activation = disabled/version 0.
16. enable/disable no modifica datos funcionales.
17. migrations no dependen de activation.
18. module activation usa P-4.
19. no last-write-wins.
20. configuration ownership no equivale a generic configuration storage.
21. cada módulo conserva su configuración funcional.
22. Milking se registra sin trasladar semántica Milking a Platform.
23. P-5 no modifica todavía contratos HTTP O-4.
24. P-6 y P-7 consumen P-5; no duplican registry/activation.
25. P-1/P-2/P-3/P-4/O-4 permanecen cerrados.

---

# 29. Decisiones aprobadas

Antes de congelar P-5 deben aprobarse expresamente:

1. **Registry estático evolutivo:** módulos registrados explícitamente en código en P-5 v0.1; no plugin engine, pero el contrato no impedirá manifests/paquetes futuros.
2. **Module version:** `module_version` se incorpora desde P-5 v0.1 como metadata técnica SemVer compatible, separada de API version y Alembic.
3. **Scope:** activación exclusivamente por Company en P-5 v0.1.
4. **Persistencia:** `platform_module_activations` en cada Tenant DB.
5. **Fail-closed:** ausencia de fila = DISABLED / version 0.
6. **Lifecycle:** solo ENABLED/DISABLED.
7. **No install/uninstall:** migrations siguen siendo globales por Tenant DB.
8. **Configuration:** Platform declara ownership/namespace; valores funcionales pertenecen al módulo.
9. **P-4:** enable/disable usan command_id + expectedVersion + CAS/idempotencia.
10. **Milking:** se registra como primer módulo, pero P-5 no toca su configuración funcional.
11. **HTTP:** P-5 no aplica todavía enforcement de activation sobre endpoints O-4; P-6 congela esa política.
12. **Backfill:** no se hardcodea activación Milking en migration P-5.
13. **API administrativa:** contrato HTTP de gestión de módulos se difiere a P-6.
14. **No dependency graph:** dependencias de módulos quedan fuera hasta necesidad real.
15. **Future bridge modules:** se reconoce como evolución válida futura un módulo de integración separado entre bounded contexts, sin implementarlo en P-5 v0.1.
16. **Readiness:** `ENABLED` no implica `OPERATIONALLY_READY`; readiness funcional pertenece al módulo.
17. **Authorization:** activation y permisos P-3 permanecen separados.
18. **Entitlement:** activation no representa licencia, plan comercial ni entitlement.
19. **Disable:** deshabilitar es no destructivo y no altera business lifecycle.
20. **Effective availability:** una activation huérfana no habilita un módulo ausente del runtime.
21. **Feature flags:** P-5 no se utilizará para flags de funcionalidades.
22. **Offline revalidation:** P-7/O-5 deberá revalidar activation en servidor al procesar comandos offline.
23. **No implicit dependencies:** cualquier dependencia entre módulos requiere análisis/contrato explícito o integración separada.

---

# 30. Racional de benchmarking

El diseño se alinea con patrones observados en ERP modulares maduros:

- módulos/addons desplegados con metadata/manifiesto;
- activación/instalación separada de la mera presencia del código;
- versionado explícito;
- extensibilidad gobernada;
- posibilidad futura de módulos de integración entre bounded contexts.

P-5 v0.1 adopta deliberadamente solo la parte necesaria hoy:

```text
código desplegado
      ↓
ModuleDefinition explícita
      ↓
ModuleRegistry
      ↓
Company activation
```

y deja para incrementos futuros:

```text
manifest/package
dependency validation
installation lifecycle
third-party modules
bridge/integration modules
```

Este corte no congela la composición estática como decisión irreversible; congela únicamente que P-5 v0.1 no necesita todavía infraestructura de plugins dinámicos.

---

# 31. Gate de cierre

> P-5 será cerrable cuando ERP Platform pueda declarar módulos explícitamente, persistir y consultar activation Company-scoped con PostgreSQL real, modificarla de forma idempotente y concurrentemente segura usando P-4, mantener aislamiento Tenant/Company y preservar O-4 sin introducir plugin engines, generic config stores ni lógica sectorial.

---

# 32. Gobierno Git

Antes de implementar:

1. merge autorizado de `BE-ADR-002`;
2. obtener nuevo SHA exacto de `main`;
3. aprobar/congelar este contrato;
4. autorizar ese SHA como base P-5.

Después:

```text
branch: feat/platform-p5-module-foundation
Draft PR propio
```

Prohibido:

- push directo a main;
- force push;
- merge sin autorización;
- tag sin autorización;
- rebase destructivo;
- iniciar P-6 sin cierre y autorización correspondiente.
