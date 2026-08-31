# BE-REG-008 — Ratificación del contrato HTTP de P-7

**Versión:** 1.0  
**Estado:** REGISTRADO  
**Fecha:** 2026-08-31  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** P-7 — Sync Foundation  
**Contrato rector:** `BE-DES-007 v0.1` — APROBADO / CONGELADO  
**Plan rector:** `BE-PLAN-001 v0.3`  
**ADR rectores:** `BE-ADR-002 v0.1`, `BE-ADR-003 v0.1`  
**Base autorizada:** `main @ c63e073680c7cf5b6517a75b4f331932d6291ae0`  
**Rama de implementación:** `feat/platform-p7-sync-foundation`  

---

## 1. Decisión ratificada

El usuario ratificó expresamente el 2026-08-31 la decisión D-1 pendiente de `BE-DES-007 v0.1`, congelando para P-7 v0.1 los literales HTTP/JSON ya materializados durante la implementación.

La ratificación no reabre `BE-DES-007`, no amplía el alcance P-7 y no autoriza O-5 ni ningún cambio fuera de la rama P-7.

---

## 2. Versiones públicas

Se congelan:

```text
API_V1_PREFIX = /api/v1
PUBLIC_API_VERSION = 1.1.0
SYNC_PROTOCOL_VERSION = 1
```

`PUBLIC_API_VERSION` y `SYNC_PROTOCOL_VERSION` son contratos distintos. La API pública puede evolucionar de forma compatible dentro de `/api/v1` sin obligar por sí sola a cambiar la versión del protocolo Sync.

---

## 3. Endpoints Sync P-7 v0.1

Se congelan exclusivamente:

```text
GET /api/v1/sync/{module_id}/changes
GET /api/v1/sync/{module_id}/bootstrap
```

No existe `/api/v1/sync/push` universal en P-7.

---

## 4. Parámetros HTTP

### 4.1 Pull incremental

```text
module_id              path, obligatorio
stream_id              query, opcional, default = default
cursor                 query, opcional, opaco
sync_protocol_version  query, opcional, default = 1
limit                  query, opcional, sujeto a límites P-6/P-7
```

### 4.2 Bootstrap

```text
module_id              path, obligatorio
stream_id              query, opcional, default = default
page_token             query, opcional, opaco
sync_protocol_version  query, opcional, default = 1
limit                  query, opcional, sujeto a límites P-6/P-7
```

`stream_id` permanece como partición técnica del feed y no como recurso de dominio en la ruta. Su valor por defecto simplifica el caso habitual de un único stream sin impedir múltiples streams declarados por el provider.

---

## 5. Envelopes JSON congelados

### 5.1 Pull incremental

```text
SyncChangesResponse
├── sync_protocol_version
├── module_id
├── stream_id
├── batches[]
├── next_cursor
└── has_more
```

Cada batch conserva:

```text
SyncBatchResponse
├── batch_id
├── position
├── recorded_at
├── source_command_id?
└── changes[]
```

Cada cambio conserva:

```text
SyncChangeResponse
├── entity_type
├── entity_id
├── change_kind
├── schema_version
├── entity_version?
└── payload
```

Los tipos transversales iniciales de `change_kind` siguen siendo `UPSERT` y `TOMBSTONE` conforme a `BE-DES-007 v0.1`.

### 5.2 Bootstrap

```text
SyncBootstrapResponse
├── sync_protocol_version
├── module_id
├── stream_id
├── items[]
├── bootstrap_start_cursor
├── next_page_token?
└── has_more
```

Cada item conserva:

```text
SyncProjectionResponse
├── entity_type
├── entity_id
├── schema_version
├── entity_version?
└── payload
```

No se incorpora `observed_through_cursor` en P-7 v0.1.

---

## 6. Errores y compatibilidad

Los endpoints Sync reutilizan `ErrorResponse` P-6 y mantienen los códigos/semántica Sync aprobados por `BE-DES-007 v0.1`. Los errores específicos de Sync no amplían silenciosamente la superficie de errores de Auth, Modules ni Milking.

En particular, HTTP 410 queda reservado a las rutas Sync para representar la condición contractual de checkpoint/cursor expirado cuando dicha capacidad sea aplicable.

---

## 7. Invariantes preservadas

Esta ratificación no modifica:

- aislamiento físico por Tenant DB;
- Company como scope operacional;
- `Tenant + Company + module_id + stream_id` como scope lógico Sync;
- cursor/continuation opacos y scope-bound;
- batches indivisibles;
- posición monotónica commit-safe;
- provider Sync subordinado a `ModuleRegistry` P-5;
- autorización fail-closed P-3/P-5;
- atomicidad negocio + P-4 + Sync en una misma `TenantTransactionBoundary`;
- exclusión de O-5, Android/Room/Outbox concreta, Object Storage, ACK/device registry, brokers externos, row-scoped feeds genéricos y atomicidad cross-module/cross-stream.

---

## 8. Regla de evolución

Los literales anteriores constituyen el contrato HTTP estable de P-7 v0.1. Si un consumidor real posterior demuestra una necesidad transversal incompatible, su evolución deberá tramitarse mediante el gobierno vigente de ERP Platform —análisis, contrato/ADR o nuevo incremento aprobado— y no mediante cambios silenciosos.

---

## 9. Regla final

> **D-1 queda ratificada: P-7 v0.1 mantiene `/api/v1`, `PUBLIC_API_VERSION = 1.1.0`, `SYNC_PROTOCOL_VERSION = 1`, `stream_id` opcional por query con default `default`, los endpoints `/changes` y `/bootstrap`, y los envelopes JSON definidos en este registro.**
