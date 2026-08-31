# BE-REG-007 — Autorización de implementación P-7

**Versión:** 1.0  
**Estado:** REGISTRADO  
**Fecha:** 2026-08-30  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** P-7 — Sync Foundation  
**Contrato rector:** `BE-DES-007 v0.1` — APROBADO / CONGELADO  
**Plan rector:** `BE-PLAN-001 v0.3`  
**ADR rectores:** `BE-ADR-002 v0.1`, `BE-ADR-003 v0.1`  

---

## 1. Autorización

El usuario autorizó expresamente:

> `main @ c63e073680c7cf5b6517a75b4f331932d6291ae0` como base de implementación de P-7.

La autorización fue emitida el **2026-08-30**.

---

## 2. Base congelada

```text
repository: CesarQuea/erp-platform
base branch: main
base SHA: c63e073680c7cf5b6517a75b4f331932d6291ae0
work branch: feat/platform-p7-sync-foundation
```

Todo código funcional P-7 debe descender de ese SHA y permanecer exclusivamente en la rama P-7 y su Draft PR.

---

## 3. Alcance autorizado

La autorización cubre exclusivamente la implementación de `BE-DES-007 v0.1`, incluyendo:

- Pull incremental transversal y Bootstrap operacional;
- streams, cursores y `SyncBatch`;
- journal durable/append-only;
- posición commit-safe por `Company + module_id + stream_id`;
- publicación Sync dentro de la misma `TenantTransactionBoundary` que la mutación funcional/P-4;
- persistencia Tenant mínima `platform_sync_streams` y `platform_sync_batches`;
- providers Sync explícitos únicamente para módulos registrados P-5;
- seguridad/aislamiento reutilizando P-3/P-5;
- errores públicos, compatibilidad y OpenAPI conforme a P-6;
- límites operacionales y observabilidad estructurada;
- migración Tenant posterior a `0005_p5_module_activation`;
- pruebas unitarias, PostgreSQL real, atomicidad, replay, concurrencia, Bootstrap/catch-up, seguridad, migraciones y regresión completa.

No autoriza ampliar el alcance contractual.

---

## 4. Exclusiones preservadas

La autorización NO permite:

- O-5 ni integración funcional específica de Milking con Sync;
- modificaciones de Android/Room o implementación concreta de Outbox cliente;
- `/api/v1/sync/push` universal;
- Object Storage, fotos o binarios;
- snapshots materializados, ACKs/checkpoints server-side o registro de dispositivos;
- motor universal de merge o `last-write-wins`;
- Event Bus/Kafka/RabbitMQ u otro broker externo;
- atomicidad Sync cross-module/cross-stream;
- feeds genéricos row-scoped por Farm/Warehouse/Site/Location;
- cambios silenciosos a contratos cerrados P-1/P-2/P-3/P-4/P-5/P-6/O-4;
- dependencia de un proveedor cloud concreto;
- push directo a `main`;
- force push, rebase destructivo o merge sin autorización separada;
- iniciar O-5 automáticamente al terminar la implementación P-7.

---

## 5. Regla final

> **P-7 queda autorizado para implementación únicamente desde `main @ c63e073680c7cf5b6517a75b4f331932d6291ae0`, bajo `BE-DES-007 v0.1`, en `feat/platform-p7-sync-foundation` y Draft PR propio.**
