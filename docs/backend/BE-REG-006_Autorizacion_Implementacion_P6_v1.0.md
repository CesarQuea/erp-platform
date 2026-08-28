# BE-REG-006 — Autorización de implementación P-6

**Versión:** 1.0  
**Estado:** REGISTRADO  
**Fecha:** 2026-08-27  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** P-6 — API + Contracts + Compatibility  
**Contrato rector:** `BE-DES-006 v0.1` — APROBADO / CONGELADO  
**ADR rector:** `BE-ADR-002 v0.1`  

---

## 1. Autorización

El usuario autorizó expresamente:

> `main @ 32ee8f209890166ae1a16a040e6d2784e7c541d4` como base de implementación de P-6.

La autorización fue emitida el **2026-08-27**.

---

## 2. Base congelada

```text
repository: CesarQuea/erp-platform
base branch: main
base SHA: 32ee8f209890166ae1a16a040e6d2784e7c541d4
work branch: feat/platform-p6-api-contracts
```

Todo código funcional P-6 debe descender de ese SHA y permanecer exclusivamente en la rama P-6 y su Draft PR.

---

## 3. Alcance autorizado

La autorización cubre exclusivamente la implementación del contrato congelado `BE-DES-006 v0.1`, incluyendo:

- API v1 y política de compatibilidad;
- contratos HTTP comunes;
- ErrorResponse / CommandResponse comunes;
- Module API P-5;
- enforcement HTTP de module activation sobre Milking;
- OpenAPI baseline versionado;
- pruebas de contrato, compatibilidad y regresión.

No autoriza ampliar el alcance contractual.

---

## 4. Exclusiones preservadas

La autorización NO permite:

- P-7 Sync;
- Outbox/Inbox;
- API Gateway;
- generated SDK obligatorio;
- migrations P-6 sin revisión contractual;
- cambios de semántica O-4;
- cambios a contratos cerrados P-1/P-2/P-3/P-4/P-5;
- push directo a main;
- force push;
- merge sin autorización separada;
- iniciar P-7 automáticamente.

---

## 5. Regla final

> **P-6 queda autorizado para implementación únicamente desde `main @ 32ee8f209890166ae1a16a040e6d2784e7c541d4`, bajo `BE-DES-006 v0.1`, en `feat/platform-p6-api-contracts` y Draft PR propio.**
