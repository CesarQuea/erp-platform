# BE-CLOSE-006 — Cierre P-6 API + Contracts + Compatibility

**Versión:** 1.0

**Estado:** CERRADO

**Fecha de cierre:** 2026-08-28

**Proyecto:** AliosurERP18 / ERP Platform

**Corte:** P-6 — API + Contracts + Compatibility

**Contrato rector:** `BE-DES-006 v0.1`

**Base autorizada:** `32ee8f209890166ae1a16a040e6d2784e7c541d4`

**Snapshot técnico cerrado y verificado:** `059c438ba788da8f794bafa354072051f5e9c08e`

**Rama:** `feat/platform-p6-api-contracts`

**Draft PR:** #10

## 1. Decisión de cierre

El responsable del proyecto autorizó expresamente el cierre de P-6 el 2026-08-28.

P-6 queda formalmente **CERRADO** sobre el snapshot técnico:

`059c438ba788da8f794bafa354072051f5e9c08e`

Los commits documentales posteriores a ese SHA registran únicamente evidencia consolidada y este acto de cierre. No modifican el snapshot técnico evaluado.

## 2. Alcance cerrado

P-6 cierra la foundation transversal de API + Contracts + Compatibility definida en `BE-DES-006 v0.1`, incluyendo:

- `/api/v1` como major público;
- `PUBLIC_API_VERSION = 1.0.0`;
- contratos transversales `ErrorResponse` y `CommandResponse`;
- manejo consistente de `X-Correlation-ID` / `correlation_id`;
- dependencias API reutilizables para principal operacional P-3;
- `GET /api/v1/modules`;
- `POST /api/v1/modules/{module_id}/enable`;
- `POST /api/v1/modules/{module_id}/disable`;
- enforcement de Module Availability P-5 sobre Milking;
- separación `Activation != Authorization`;
- ausencia de autoactivación/backfill Milking;
- preservación de pagination y DTOs O-4;
- OpenAPI baseline versionado en `contracts/api/v1/openapi.json`;
- generador reproducible de OpenAPI;
- pruebas de compatibilidad y regresión P-3/P-4/P-5/O-4.

## 3. Invariantes preservadas

Con el cierre se consideran preservadas:

1. Tenant físico por PostgreSQL DB.
2. Company como scope operacional.
3. P-3 Authentication/Authorization deny-by-default.
4. P-4 command idempotency y optimistic concurrency.
5. P-5 Module Registry/Activation Company-scoped.
6. `absence = DISABLED/version 0`.
7. `ENABLED != OPERATIONALLY_READY`.
8. `Activation != Authorization`.
9. `Activation != Entitlement`.
10. disable no destructivo.
11. Milking conserva su semántica O-4.
12. OpenAPI público v1 no incorpora Sync P-7.

## 4. Exclusiones preservadas

P-6 no implementa:

- P-7 Sync;
- Outbox/Inbox;
- cursor/checkpoint/ACK protocol;
- API Gateway;
- service mesh;
- GraphQL/gRPC;
- plugin engine;
- module installer/dependency solver;
- feature flags;
- entitlement/licensing;
- generic configuration store;
- generated SDK obligatorio;
- Web UI;
- Android Sync;
- microservicios;
- Site/OperationalUnit;
- lógica Dairy/Aliosur hardcodeada en Platform.

## 5. Persistencia y migraciones

P-6 no introduce migration propia.

El Tenant head permanece:

`0005_p5_module_activation`

La verificación final confirmó además:

- forward histórico O-4 `0002 -> 0004`;
- forward P-5 `0004 -> 0005`;
- 0 skips críticos de migración.

## 6. Evidencia final de cierre

La ronda final R4 confirmó:

- focal P-6: 14/14 PASS;
- forward O-4: 1/1 PASS, 0 skips;
- forward P-5: 1/1 PASS, 0 skips;
- suite completa: 231/231 PASS;
- 0 failures;
- 0 errors;
- 0 skips;
- PostgreSQL real con bases segregadas;
- `git diff --check`: PASS;
- OpenAPI reproducible y sin diff;
- `/api/v1/live`: 200;
- `/api/v1/ready`: 200;
- `/api/v1/health`: 200;
- evidence package sanitizado;
- working snapshot coherente con el PR.

SHA-256 del paquete R4 contrastado:

`04564A7FF294A0B7E21EFB2E3192B885485DF4D7D5FC6374AD627E53EECA9020`

El detalle consolidado se registra en:

`verification/P6/Reporte_Verificacion_Final_P6_Consolidado.md`

## 7. Hallazgos resueltos durante P-6

Durante la implementación y verificación se detectaron y resolvieron, antes del cierre:

- incompatibilidad de `PlatformError` frozen al atravesar un `contextmanager` transaccional desde Module Availability;
- baseline OpenAPI inicialmente no idéntico al generado;
- documentación demasiado amplia de errores en system endpoints;
- `correlation_id` inicialmente nullable en OpenAPI;
- dependencia Pydantic no fijada para reproducibilidad contractual;
- pruebas históricas O-4 que asumían que `0004` seguía siendo head actual;
- harness de verificación que reutilizaba DBs entre cortes históricos;
- skips de forward migrations por variables de entorno no configuradas;
- hygiene incompleto de paquetes de evidencia intermedios.

No quedan BLOCKER, HIGH ni MEDIUM abiertos asociados al alcance P-6.

## 8. Observaciones LOW aceptadas

Se aceptan como no bloqueantes:

- warnings/deprecations ya conocidas de tooling/migraciones sin impacto funcional demostrado;
- inconsistencias de denominación en informes intermedios del agente, corregidas en la documentación oficial de cierre.

## 9. Gobierno posterior

El cierre de P-6 no implica automáticamente merge ni inicio de P-7.

Queda prohibido:

- merge del PR #10 sin autorización expresa del responsable del proyecto;
- push directo a `main`;
- iniciar P-7 sin el acto de gobierno correspondiente.

El siguiente acto procedimental es independiente: autorización expresa para mergear el PR #10 a `main`.

## 10. Declaración final

**P-6 — API + Contracts + Compatibility queda formalmente CERRADO sobre `059c438ba788da8f794bafa354072051f5e9c08e`.**
