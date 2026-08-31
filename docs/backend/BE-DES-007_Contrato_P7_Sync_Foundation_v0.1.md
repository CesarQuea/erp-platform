# BE-DES-007 — Contrato Sync Foundation

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO  
**Fecha:** 2026-08-30  
**Aprobación:** aprobada expresamente por el usuario el 2026-08-30.  
**Producto base:** ERP Platform genérica / marca comercial no asignada  
**Proyecto de desarrollo:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Plan maestro rector:** `BE-PLAN-001 v0.3`  
**ADR rectores:** `BE-ADR-002 v0.1`, `BE-ADR-003 v0.1`  
**Contratos preservados:** `BE-DES-001` a `BE-DES-006` y contratos cerrados de bounded contexts  
**Cortes cerrados preservados:** P-1 a P-6 y O-4  
**Estado Git revisado:** `main @ 215ce6b80bf53fca9404cdb7c4d436129013a491`  
**Base candidata de implementación:** `main @ 215ce6b80bf53fca9404cdb7c4d436129013a491` — **NO AUTORIZADA TODAVÍA**  
**Rama propuesta:** `feat/platform-p7-sync-foundation`  
**Implementación:** NO AUTORIZADA por este documento

---

## 1. Propósito

Definir la foundation transversal mínima, completa y reutilizable para sincronización offline-first entre clientes operacionales y ERP Platform, preservando PostgreSQL/backend como autoridad consolidada global, clientes locales como réplica operacional, multi-Tenant/multiempresa/multiusuario, idempotencia, concurrencia, contratos HTTP versionados, bounded contexts, portabilidad de infraestructura y separación de binarios.

> **Platform define cómo mantener una réplica operacional coherente; cada bounded context define qué información necesita disponible localmente, con qué semántica y durante cuánto tiempo.**

**Alcance de este documento:** `BE-DES-007 v0.1` es el contrato rector exclusivo para la implementación y verificación del corte transversal **P-7 — Sync Foundation**. Las referencias a clientes first-party y bounded contexts establecen fronteras arquitectónicas y obligaciones de integración futura; no amplían por sí mismas el alcance de implementación de P-7.

Las reglas dirigidas a Android/Room u otros clientes offline-first no autorizan su implementación dentro de P-7. La integración funcional de Milking corresponde a O-5 después del cierre de P-7, conforme a `BE-PLAN-001 v0.3`.

## 2. Fuentes de autoridad

Se interpreta conjuntamente con `BE-PLAN-001 v0.3`, `BE-ADR-002`, `BE-ADR-003`, contratos/cierres P-3 a P-6, contratos de cada bounded context, Git/código/migraciones/tests reales y decisiones expresamente aprobadas. Inventory V2 se conserva como antecedente de UUID distribuidos, `commandId`, `expectedVersion`, conflictos explícitos y futura Outbox/Inbox. Milking es el primer consumidor previsto, sin elevar su semántica a Platform.

Ante contradicción prevalece el contrato/ADR vigente más específico; no se modifica silenciosamente una decisión cerrada.

**Nota de revisión integral:** esta versión corrige precisiones detectadas al contrastar el borrador con el código real de P-4/P-5/P-6 y O-4: bootstrap verificable sin snapshot, compatibilidad de schemas sin negociación anticipada, límites reales de autorización de feeds, vínculo con `ModuleRegistry`, compatibilidad UUID Milking O-5, separación journal/audit, OpenAPI/PUBLIC_API_VERSION, primera materialización race-safe de streams y exclusión cross-module/cross-stream.

## 3. Principios preservados

- Tenant físicamente aislado por PostgreSQL DB.
- Company como scope operacional dentro del Tenant.
- `AuthenticatedPrincipal` y RBAC deny-by-default.
- `command_id`, fingerprint/idempotencia P-4.
- `expected_version`, optimistic concurrency/CAS.
- conflictos explícitos; no `last-write-wins` universal.
- ModuleRegistry/ModuleAvailability P-5.
- `ENABLED != AUTHORIZED` y `ENABLED != OPERATIONALLY_READY`.
- `/api/v1`, ErrorResponse y CommandResponse P-6.
- Core/Platform genéricos, sin marca/sector/proveedor hardcodeados.
- PostgreSQL para datos estructurados/metadata; binarios separados cuando exista Object Storage.

## 4. Frontera Platform / módulo / cliente

**Platform:** protocolo, endpoints transversales, streams, cursor, `SyncBatch`, journal, posición commit-safe, atomicidad, errores, límites, seguridad común.

**Bounded context:** streams declarados, proyecciones, payloads, autorización funcional, baseline, retención local, cobertura offline y resolución funcional de conflictos.

**Cliente:** réplica local, Outbox durable, causalidad, retry/backoff, transacciones Room/equivalentes, conservación de intenciones conflictivas y UX de conflicto.

## 5. Offline-first transversal

Offline-first es capacidad transversal. Cada bounded context declara conceptualmente qué operaciones son `OFFLINE_REQUIRED`, `OFFLINE_CAPABLE` u `ONLINE_REQUIRED`; esos nombres no obligan a crear un enum global. Estar en ciudad/planta no justifica por sí solo acoplar un flujo móvil a conexión permanente. Tampoco se obliga a que toda función sea offline.

## 6. Identidad UUID distribuida

> **Una entidad que pueda originarse legítimamente offline y necesite ser referenciada antes de confirmación cloud debe poder conservar un UUID técnico estable asignado en el origen.**

Reglas:
- `resource_id != command_id`;
- no todos los recursos deben ser client-assigned;
- recursos exclusivamente server-created pueden recibir UUID backend;
- backend valida y conserva el UUID recibido, sin remapeo silencioso;
- UUID no concede autorización ni sustituye constraints funcionales;
- numeraciones humanas/comerciales/fiscales son independientes.

### 6.1 Precisión respecto de Milking O-4 / O-5

P-7 **no modifica** el contrato O-4 cerrado ni su endpoint actual de creación de `MilkingSession`. En O-4, `CreateMilkingSession`/`CreateSessionRequest` no reciben todavía `session_id`, por lo que el UUID de la sesión se genera actualmente en backend. El dominio Milking ya admite técnicamente un `session_id` opcional al construir un draft, pero esa capacidad interna no autoriza por sí sola un cambio de API.

La adaptación corresponde a O-5. Si O-5 confirma que `MilkingSession` debe nacer offline con identidad estable, podrá evolucionar `/api/v1` de forma compatible añadiendo un `session_id` opcional, sujeto a P-6/OpenAPI. En ese caso:

- el `session_id` recibido deberá formar parte del payload normalizado/fingerprint P-4;
- mismo `command_id` intentando crear recursos distintos deberá producir `IDEMPOTENCY_CONFLICT`;
- deberá revisarse expresamente si `MILKING_CREATE` requiere evolución de `command_schema_version`;
- `MilkingOutput` puede continuar siendo server-created cuando sea un recurso derivado de `CONFIRM`.

## 7. Push y retry

No existe `/api/v1/sync/push` universal. La Outbox publica usando endpoints funcionales del bounded context bajo P-3/P-5/P-4/P-6.

Durante un retry de la misma intención se conservan `command_id`, payload, `expected_version`, `client_occurred_at` y `client_instance_id`. Pueden cambiar token, `correlation_id`, red y hora del request. Una nueva decisión funcional genera nuevo `command_id`.

`client_occurred_at` no ordena Sync. `client_instance_id` es opaco y no es credencial.

## 8. Tratamiento mínimo de resultados Push

- sin red/timeout: retry mismo comando;
- 5xx/503 temporal: retry con backoff+jitter;
- 401: renovar auth cuando proceda y retry;
- 403 `ACCESS_DENIED`: bloquear, no retry ciego, preservar intención;
- 409 `CONCURRENCY_CONFLICT`: Pull + resolución funcional;
- 409 `IDEMPOTENCY_CONFLICT`: error terminal de integridad;
- 409 `MODULE_NOT_ENABLED`: bloquear por condición;
- 422 validación: no retry ciego;
- 200 `replayed=false/true`: éxito confirmado.

No existe ACK Push separado: `CommandResponse` es suficiente.

## 9. Outbox durable y causalidad

Mutación local + inserción Outbox son atómicas. Crash en `IN_FLIGHT` no implica confirmación. No hay compactación automática genérica. La Outbox conserva contexto de origen para impedir publicación bajo usuario/Tenant/Company incompatibles.

El orden se preserva por **cadena causal**, no por FIFO global ni timestamp. Máximo un comando en vuelo por cadena. Cadenas independientes pueden avanzar en paralelo bajo límite global configurable. Dependencias explícitas equivalentes a `depends_on_command_id` son permitidas sin construir un DAG universal.

## 10. Conflictos

> **Platform detecta, preserva y aísla el conflicto; el bounded context decide su significado y resolución. Ningún comando se reescribe silenciosamente.**

El comando conflictivo mantiene `command_id`, payload y `expected_version`; descendientes quedan bloqueados. Antes de resolver un conflicto de versión se obtiene estado cloud actual. Reaplicar genera nuevo comando. Descendientes antiguos no se reactivan automáticamente. No existe merge universal ni LWW. Resolución automática solo si el módulo la declara determinista y segura.

## 11. Pull transversal

Forma propuesta:

```text
GET /api/v1/sync/{module_id}/changes
```

Platform gobierna protocolo/cursor/batches/transporte. El bounded context registra un provider explícito que gobierna contenido y autorización funcional. Platform no introspecta tablas funcionales.

## 12. Streams

Identidad lógica:

```text
Tenant DB + Company + module_id + stream_id
```

Reglas:
- `stream_id` soportado desde inicio;
- un solo stream por defecto normalmente;
- streams adicionales solo con necesidad real;
- cursor y orden independientes por stream;
- no existe orden global entre streams;
- cambios atómicos no se separan entre streams;
- streams declarados explícitamente por módulo;
- `stream_id` estable, técnico y no UI.

## 13. SyncBatch

Unidad mínima e indivisible de entrega incremental. Pertenece a una Company/módulo/stream y representa cambios sincronizables de una única transacción confirmada. Puede contener uno o varios cambios ordenados y no se divide entre páginas.

Tipos transversales iniciales: `UPSERT`, `TOMBSTONE`.

Modelo conceptual:

```text
SyncChange
├── entity_type
├── entity_id
├── change_kind
├── schema_version
├── entity_version?
└── payload
```

Platform preserva atomicidad/orden/transporte; el módulo preserva semántica/payload.

## 14. Aplicación local del batch

El cliente aplica todos los cambios del batch y avanza metadata/checkpoint dentro de una única transacción local. Resultado válido: todo aplicado + checkpoint avanzado, o nada aplicado + checkpoint intacto. Reentregas deben ser idempotentes.

## 15. Journal, posición y cursor

Cada stream mantiene posición monotónica asignada por servidor, no por timestamp. Debe ser **commit-safe**; implementación esperada: lock `FOR UPDATE` sobre la fila `Company + module + stream`, incremento, inserción del batch y commit conjunto. El lock no es global.

El cursor es opaco, client-held, interpretable solo por Platform, ligado a Tenant/Company/module/stream y no es credencial. Un cursor de otro scope devuelve error genérico sin revelar su origen.

## 16. Bootstrap operacional

Forma propuesta:

```text
GET /api/v1/sync/{module_id}/bootstrap
```

Bootstrap no replayea todo el journal ni descarga todo el histórico. El módulo define el baseline; Platform proporciona paginación/continuación opaca, un `bootstrap_start_cursor`, versiones, seguridad y límites.

### 16.1 Algoritmo contractual v0.1

```text
T0: capturar posición/cursor S
        ↓
bootstrap_start_cursor = S
        ↓
descargar baseline mediante paginación estable
        ↓
cloud puede publicar S+1, S+2, ... mientras continúa el bootstrap
        ↓
terminar baseline
        ↓
Pull incremental desde S
        ↓
aplicar S+1 ... S+n hasta has_more=false
        ↓
marcar réplica como operacionalmente lista
```

No se requiere snapshot físico/materializado. La réplica **no** se considera lista antes de completar el catch-up incremental desde `bootstrap_start_cursor`.

### 16.2 Paginación estable

Bootstrap no deberá depender de `offset` sobre un conjunto mutable. La continuación debe ser opaca para el cliente y materializar una estrategia equivalente a **keyset pagination** sobre una clave estable/determinista del provider, ligada al menos a:

```text
Tenant/Company
module_id
stream_id
bootstrap_start_cursor
última clave/continuación estable
```

El mecanismo físico concreto puede variar, pero debe impedir omisiones/duplicaciones causadas únicamente por desplazamiento de offsets mientras el conjunto cambia.

### 16.3 Semántica de UPSERT para catch-up

Para v0.1, un `UPSERT` representa la **proyección completa actual del recurso bajo su `projection_schema_version`**, no un PATCH genérico. Esto permite que el catch-up posterior al baseline vuelva a aplicar de forma idempotente el estado autoritativo más reciente sin depender de la forma en que el recurso apareció durante páginas previas del bootstrap.

No se introduce `observed_through_cursor` por item/página en v0.1, porque la foundation no mantiene metadata genérica por entidad que permita demostrar esa semántica de forma universal. La garantía contractual se obtiene mediante `bootstrap_start_cursor + baseline estable + catch-up obligatorio`.

## 17. Histórico y retención local

- Sync no implica réplica íntegra del histórico cloud.
- No existe ventana histórica universal Platform.
- Cada bounded context define su política de réplica/retención.
- La ventana puede ser configurable.
- No se elimina por antigüedad información pendiente, conflictiva, no sincronizada o necesaria para integridad/workflow.
- El histórico completo permanece cloud.
- Reporting extenso se resuelve preferentemente online.
- Retención cloud y local son independientes.
- Descarga histórica offline ampliada es capacidad opcional de módulo/cliente.
- Limpieza local nunca compromete Outbox/checkpoints/conflictos.

## 18. Cursor expirado

El protocolo admite futuro `SYNC_CURSOR_EXPIRED` cuando un checkpoint quede fuera de la ventana retenida. La respuesta contractual es nuevo bootstrap. No se fijan todavía días de retención ni motor de purga/compactación.

## 19. Versionado y compatibilidad

Se separan:

```text
API version
!= module_version
!= command_schema_version
!= sync_protocol_version
!= projection_schema_version
!= Alembic
!= Room schema
!= app version
```

`sync_protocol_version` gobierna envelope, cursor, streams, batches, bootstrap y errores. `projection_schema_version` pertenece al módulo.

Cambios compatibles deben preferirse aditivamente. Breaking projection requiere nueva schema + estrategia explícita de transición. Journal conserva de forma inmutable el payload/version realmente publicado. Incompatibilidad de Pull no borra Outbox.

### 19.1 Sin negociación anticipada de projection schemas en v0.1

P-7 v0.1 **no** implementa un framework de negociación mediante el cual el cliente anuncie todas las `projection_schema_version` que soporta. Por ello, el servidor no puede asumir que conoce de antemano la capacidad exacta del cliente para cada `entity_type`.

Regla v0.1:

- cada item/change transporta explícitamente su `schema_version`;
- el cliente procesa únicamente schemas que conoce;
- ante una schema desconocida, el cliente falla cerrado, no aplica ese batch/item y no avanza el checkpoint correspondiente;
- el trabajo local/Outbox se preserva;
- la estrategia normal es actualizar el cliente y, si corresponde, re-bootstrap;
- una futura negociación explícita de schemas requerirá extensión contractual propia.

`SYNC_SCHEMA_UNSUPPORTED` queda **reservado** para una futura negociación server-side o para un endpoint que disponga realmente de información suficiente sobre capacidades del cliente; no se exige que P-7 v0.1 lo emita.

## 20. Seguridad

Sync no crea una frontera de seguridad paralela:

```text
Access Token
→ AuthenticatedPrincipal
→ Tenant/Company
→ ModuleAvailability
→ autorización funcional del módulo
```

Tenant/Company nunca se seleccionan por cursor/body/query de confianza. Cursor, UUID, command/batch IDs y client instance no conceden autoridad. Permisos se reevalúan en cada interacción de red. Revocación o módulo deshabilitado bloquean transmisión pero no borran automáticamente trabajo local.

## 21. Scopes funcionales y autorización de feeds

No se introducen como primitives globales nuevos scopes como Farm/Warehouse/Site/Location/WorkCenter. P-7 v0.1 garantiza de forma transversal aislamiento/autorización hasta la frontera:

```text
Tenant DB + Company + module_id + stream_id
```

Un bounded context **no puede asumir automáticamente** que Platform ofrece feeds row-scoped seguros por Farm/Warehouse/Site dentro de un mismo stream. Si necesita visibilidad más fina, deberá definir una estrategia **cursor-safe** explícita —por ejemplo partición contractual de streams u otra extensión aprobada— que preserve paginación, revocación, cursor y no filtración de datos.

Por tanto:

- P-7 no crea scopes globales Farm/Warehouse/Site;
- P-7 tampoco promete filtrado row-level genérico dentro de un stream compartido;
- O-4 Milking continúa Company-scoped según su contrato vigente;
- una necesidad futura de autorización por finca/almacén debe analizarse y congelarse antes de incorporarla a Sync.

La promoción futura de un scope de dominio a Platform requiere necesidad transversal demostrada y contrato propio.

## 22. Persistencia PostgreSQL mínima

Solo dos tablas nuevas por Tenant DB:

```text
platform_sync_streams
platform_sync_batches
```

No se duplica `platform_command_executions`.

### `platform_sync_streams` candidato

```text
company_id
module_id
stream_id
current_position
created_at
updated_at
PK(company_id,module_id,stream_id)
```

La ausencia de fila para un stream declarado equivale conceptualmente a `current_position = 0` hasta su materialización. La primera publicación deberá crear/materializar la fila de manera **race-safe** y luego aplicar el mismo lock/avance commit-safe. P-5 `enable` no crea streams ni conoce Sync. Debe existir prueba de dos primeras publicaciones concurrentes sobre un stream aún no materializado.

### `platform_sync_batches` candidato

```text
batch_id
company_id
module_id
stream_id
position
sync_protocol_version
source_command_id?
recorded_at
changes_json
UNIQUE(company_id,module_id,stream_id,position)
FK → platform_sync_streams
```

`changes_json` contiene el array ordenado. No existe `platform_sync_changes` separada ni índices funcionales sobre JSON. `source_command_id` es trazabilidad opcional; no se exige FK fuerte ni unicidad.

## 23. Atomicidad PostgreSQL

> **Una mutación funcional observable por Sync no puede confirmarse sin que el SyncBatch quede durablemente registrado en la misma transacción.**

```text
TenantTransactionBoundary
└── session.begin()
    ├── P-4 claim
    ├── business mutation
    ├── SyncPublisher.publish()
    ├── P-4 complete
    └── COMMIT
```

`SyncPublisher` reutiliza la sesión Tenant activa y nunca abre un segundo commit. Si publish falla, revierte mutación, batch, posición y confirmación P-4. Replay P-4 no genera nuevo batch ni posición.

## 24. Journal append-only y separación de auditorías

Después del commit no se reescribe payload, schema ni posición histórica. Retención futura podrá eliminar batches antiguos bajo contrato específico, pero el journal no se convierte en una segunda base funcional.

Quedan explícitamente separados:

```text
platform_command_executions
→ integridad/idempotencia/audit técnico P-4

milking_audit_events u otros business audits de módulo
→ evidencia funcional del bounded context

platform_sync_batches
→ reproducción incremental para réplicas
```

El Sync journal **no sustituye** business audit ni technical audit. Una futura purga/retención del journal no puede utilizarse como mecanismo de borrado de evidencia funcional que pertenezca a otro contrato.

## 25. Límites

Pull/Bootstrap siempre paginados. `limit` es máximo solicitado; servidor aplica default/max configurables. Batch es indivisible y tiene tamaño serializado máximo configurable. Batch excesivo falla antes de commit. Bootstrap y Pull pueden tener tamaños distintos. Los números concretos son tuning operacional, no invariante arquitectónica.

## 26. Errores específicos de Sync

Se reutiliza ErrorResponse P-6 y los códigos existentes cuando representen la misma condición. Nuevos códigos iniciales:

| Código | HTTP recomendado | Semántica |
|---|---:|---|
| `SYNC_STREAM_NOT_FOUND` | 404 | stream no declarado |
| `SYNC_CURSOR_INVALID` | 400 | cursor inválido/incompatible con scope |
| `SYNC_CURSOR_EXPIRED` | 410 | requiere nuevo bootstrap |
| `SYNC_PROTOCOL_UNSUPPORTED` | 409 | protocolo no soportado |
| `SYNC_SCHEMA_UNSUPPORTED` | 409 | **RESERVADO** para futura negociación/capability server-side; no es emisión obligatoria en v0.1 |
| `SYNC_BATCH_TOO_LARGE` | 500 | error del publicador backend + rollback |

El cliente actúa por `error.code`, no por `message`.

## 27. Observabilidad

Se reutilizan `X-Correlation-ID` y logging estructurado. `correlation_id`, `command_id` y `batch_id` son distintos. Logs pueden incluir IDs/scopes/posiciones/conteos/outcome, pero nunca payload funcional, `changes_json`, tokens, secretos, cuerpos completos ni cursor opaco completo. No se obliga aún a Prometheus/Grafana/OpenTelemetry/APM.

## 28. Contrato HTTP mínimo — puntos a cerrar en revisión

Semántica requerida:

```text
GET /api/v1/sync/{module_id}/bootstrap
GET /api/v1/sync/{module_id}/changes
```

Request conceptual: `stream_id`, `sync_protocol_version`, `limit`, continuation token en bootstrap y cursor en incremental.

Respuesta incremental conceptual:

```text
sync_protocol_version
module_id
stream_id
batches[]
next_cursor
has_more
```

Respuesta bootstrap conceptual:

```text
sync_protocol_version
module_id
stream_id
items[]
bootstrap_start_cursor
next_page_token?
has_more
```

El `next_page_token` es opaco y debe materializar paginación estable equivalente a keyset, ligado al contexto y `bootstrap_start_cursor`. No se incluye `observed_through_cursor` en v0.1.

Antes del congelamiento final deben aprobarse los nombres JSON exactos, ubicación/obligatoriedad de `stream_id`, literal inicial del protocol version y la representación final de los tokens/cursors sin alterar las invariantes ya cerradas.

## 29. Provider Sync de bounded context

Provider explícito, sin reflection/plugins dinámicos ni introspección de tablas. Conceptualmente declara `module_id`, streams, autorización y construcción de bootstrap/proyecciones. Nombres concretos de interfaces/clases son detalle de implementación, no semántica de dominio.

El registro de providers Sync **no constituye un segundo Module Registry**. Solo puede registrarse un provider para un `module_id` existente en el `ModuleRegistry` P-5. La capability Sync extiende al módulo ya registrado; no crea un catálogo paralelo ni permite alias divergentes. La validación `registered module + declared stream + Company activation` debe ser fail-closed.

## 30. Migración y contrato público P-6

La cadena Tenant actual termina en `0005_p5_module_activation`. La foundation requiere una nueva migración posterior que cree solo `platform_sync_streams` y `platform_sync_batches`. Nombre candidato según convención: `0006_p7_sync_foundation.py`. No modifica Platform/Identity DB ni hace backfill específico de Milking/u otro módulo.

P-7 añade endpoints públicos dentro de `/api/v1`; por tanto, conforme a P-6 debe:

- actualizar deliberadamente `contracts/api/v1/openapi.json`;
- mantener reproducible el generador/baseline OpenAPI;
- ejecutar contract regression;
- **decidir expresamente** el valor de `PUBLIC_API_VERSION` aplicable al nuevo contrato, sin asumir ni omitir su evolución por accidente.

Este documento no fija por sí solo un nuevo número de `PUBLIC_API_VERSION`; la decisión se congela con el contrato HTTP/OpenAPI final antes de implementación.

## 31. Pruebas obligatorias

Debe existir cobertura de:

- primitives, cursor, stream, batch, UPSERT/TOMBSTONE, versiones y límites;
- PostgreSQL real: PK/FK/constraints, posición monotónica, aislamiento, journal inmutable;
- atomicidad negocio + P-4 + Sync con fallo inducido y rollback inspeccionado en DB;
- replay P-4 sin batch/posición duplicados;
- concurrency/stress en mismo stream e independencia entre streams/Companies;
- Pull incremental: orden, cursor, `has_more`, paginación, batch indivisible;
- Bootstrap con `bootstrap_start_cursor`, paginación estable/keyset, escrituras concurrentes y catch-up sin pérdida;
- primera materialización concurrente de un stream inexistente sin duplicar fila/posición;
- seguridad: auth, contexto, módulo, permisos, cursor cruzado, Tenant/Company;
- demostrar que v0.1 no promete row-level feeds por Farm/Warehouse dentro de un stream sin estrategia cursor-safe;
- versionado: protocolo soportado/no soportado; schema conocida procesable y schema desconocida fail-closed en cliente/contrato sin avance de checkpoint;
- Alembic desde base limpia y upgrade desde 0005;
- OpenAPI regression P-6;
- suite completa del repositorio.

No se acepta demostrar atomicidad solo con mocks.

## 32. Verificación independiente

El agente verificador no modifica código. Debe registrar SHA exacto, diff base→HEAD, comandos ejecutados, tests focales/completos, PostgreSQL/migraciones, stress, XML JUnit y logs. El cierre se recomienda solo después de contrastar contrato ↔ código ↔ diff ↔ pruebas ↔ evidencias. El usuario es la única autoridad de cierre y merge.

## 33. Exclusiones

Fuera de alcance:

- integración funcional específica de Milking;
- implementación Android/Room concreta;
- Object Storage y Attachment/Photo/Binary Sync;
- `/sync/push` universal;
- motor universal de merge/LWW;
- snapshots materializados, snapshot files, CDN, compaction engine;
- purga automática/retención definitiva del journal;
- tablas server de devices/acks/conflicts/snapshots/checkpoints;
- Kafka/RabbitMQ/Event Bus/broker externo;
- plugins dinámicos;
- proveedor cloud específico;
- APM/metrics stack obligatorio;
- reporting histórico/analítico;
- cambios funcionales O-4 para hacerlo sincronizable;
- ventana histórica local universal;
- nuevos scopes globales Farm/Warehouse/Site/etc.;
- feeds row-scoped genéricos por Farm/Warehouse/Site dentro de un stream sin estrategia cursor-safe aprobada;
- atomicidad Sync cross-module o cross-stream: P-7 v0.1 no garantiza que batches de módulos/streams distintos se apliquen como una única transacción local; cualquier necesidad real exige extensión contractual;
- reabrir P-3/P-4/P-5/P-6 sin incompatibilidad demostrada y aprobación;
- Production Readiness, backups/restore/TLS/alertas/rollback operativo completos.

## 34. Criterio de aceptación

No basta con tablas/endpoints. Debe demostrarse con PostgreSQL real que publicación, atomicidad, replay, posición, locks, Pull, bootstrap/catch-up, aislamiento, seguridad, compatibilidad, límites y migración cumplen las invariantes bajo fallos y concurrencia, sin introducir semántica de módulos ni dependencia de proveedor.

## 35. Invariantes resumidas

1. Platform define mecanismo; módulo define semántica.
2. Backend es autoridad consolidada; local es réplica operacional.
3. Sync no descarga todo el histórico.
4. Push reutiliza comandos P-4/P-6.
5. Retry conserva misma intención/command_id.
6. Recursos offline-creables pueden conservar UUID estable de origen.
7. Outbox es durable y causal.
8. No FIFO global ni paralelismo ilimitado.
9. Conflictos se preservan; no LWW universal.
10. SyncBatch es unidad atómica.
11. Orden solo dentro de stream.
12. Posición commit-safe.
13. Cursor opaco, client-held y scope-bound.
14. Bootstrap = `bootstrap_start_cursor` + baseline paginado estable + catch-up obligatorio; no snapshot materializado.
15. `UPSERT` v0.1 transporta proyección completa del recurso bajo su schema.
16. Journal append-only y distinto de business audit/P-4 audit.
17. Negocio + P-4 + Sync = mismo COMMIT.
18. Seguridad actual se reevalúa al volver online.
19. Revocación no borra silenciosamente trabajo pendiente.
20. Versiones Sync separadas de API/module/command/DB/app; no negociación exhaustiva de schemas en v0.1.
21. Provider Sync solo existe para módulos registrados P-5.
22. Primera materialización de stream es race-safe y no acopla P-5 activation a Sync.
23. P-7 v0.1 no promete atomicidad cross-module/cross-stream ni row-level feeds genéricos por Farm/Warehouse.
24. Binarios fuera de Sync estructurado inicial.
25. Core/Platform sin marca, sector ni proveedor cloud.

## 36. Estado y siguiente paso

```text
BE-DES-007 v0.1
APROBADO / CONGELADO
IMPLEMENTACIÓN NO AUTORIZADA TODAVÍA
```

Esta versión incorpora la auditoría integral contra `BE-PLAN-001 v0.3`, `BE-ADR-002/003`, P-4/P-5/P-6 y O-4 Milking sin reabrir sus contratos cerrados.

La aprobación y congelamiento de este contrato **no autorizan por sí solos la implementación**. El siguiente acto de gobierno es registrar documentalmente esta versión aprobada en Git mediante rama/PR autorizados y, después, autorizar expresamente el SHA base de implementación, la rama y el Draft PR de P-7.

No se autoriza por este documento iniciar O-5, modificar Android/Room ni introducir cambios funcionales de Milking destinados a Sync antes del cierre de P-7.
