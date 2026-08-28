# BE-REV-006 — Revisión estática P-6 API + Contracts + Compatibility

**Versión:** 1.0  
**Estado:** APTO PARA VERIFICACIÓN INDEPENDIENTE — NO IMPLICA CIERRE NI MERGE  
**Fecha:** 2026-08-27  
**Repositorio:** `CesarQuea/erp-platform`  
**Rama:** `feat/platform-p6-api-contracts`  
**Draft PR:** #10  
**Base autorizada:** `32ee8f209890166ae1a16a040e6d2784e7c541d4`  
**Contrato rector:** `BE-DES-006 v0.1`

---

## 1. Objeto

Registrar la revisión estática independiente de ChatGPT sobre el diff real de P-6 antes de entregar el corte a verificación dinámica independiente.

Esta revisión no sustituye PostgreSQL real, suite completa, Docker ni XML JUnit y no autoriza cierre o merge.

---

## 2. Alcance revisado

El diff final funcional se concentra en:

- contratos HTTP transversales P-6;
- dependency común Bearer/P-3;
- Module API sobre P-5;
- enforcement P-5 sobre Milking;
- versionado público `/api/v1` y `PUBLIC_API_VERSION=1.0.0`;
- OpenAPI baseline v1;
- generador OpenAPI determinista;
- endurecimiento del correlation ID contractual;
- pruebas P-6 y adaptación de regresión O-4/P-3;
- pin explícito de Pydantic para reproducibilidad del baseline.

No se introducen migraciones P-6 ni cambios en tablas, repositorios de dominio, P-7 Sync, Outbox/Inbox, API Gateway, plugins o SDK generation.

---

## 3. Contratos comunes

Se revisó `app/api/contracts/common.py`.

Resultado:

- `/api/v1` queda como major público;
- `PUBLIC_API_VERSION="1.0.0"` queda separado de module version/Alembic/Sync;
- `ErrorResponse` conserva `{error:{code,message,correlation_id}}`;
- `correlation_id` es obligatorio en el schema público;
- `CommandResponse` conserva `{code,replayed,data}`;
- límites ordinarios continúan 100/500;
- no se introduce success envelope genérico para GET.

No se detecta semántica de bounded context trasladada a Platform.

---

## 4. Security dependency

Se revisó `app/api/security.py`.

El orden queda:

```text
Bearer
 -> P-3 current principal
 -> operational Tenant+Company context
 -> P-5 require_enabled(module_id)
 -> bounded context
```

No se toma Tenant/Company de parámetros arbitrarios como autoridad.

`require_module_enabled()` consume `ModuleAvailabilityService`; no crea un motor paralelo de autorización o activación.

---

## 5. Module API

Se revisó `app/api/v1/modules.py`.

Queda expuesto:

```text
GET  /api/v1/modules
POST /api/v1/modules/{module_id}/enable
POST /api/v1/modules/{module_id}/disable
```

`GET` usa únicamente el contexto operacional del principal.

Enable/disable construyen `ChangeModuleActivation` y delegan en `ModuleActivationService`, que conserva autorización `platform.modules.manage`, P-4 idempotencia y CAS.

No existe backfill ni auto-enable Milking.

---

## 6. Milking / O-4

Se revisó el patch real de `app/api/v1/milking.py`.

Cambios permitidos:

- reemplazo de helpers Bearer duplicados por dependency transversal;
- uso del `CommandResponse` común;
- uso de constantes de paginación equivalentes a los valores O-4 previos;
- gate router-level `require_module_enabled("milking")`.

No se modifican:

- DTOs funcionales Milking;
- paths/métodos existentes;
- HTTP 200 de commands;
- semántica de dominio;
- configuración Farm/Shift/Profile;
- lifecycle O-4;
- listas `limit/offset`.

---

## 7. Auth / P-3

El patch de `app/api/v1/auth.py` es un refactor de dependencias:

- `identity_runtime`;
- `access_token`;
- `current_principal`.

No se modifican DTOs, paths, token semantics, refresh/logout/context selection ni permisos P-3.

Tokens continúan tratados como opacos por el contrato público.

---

## 8. Error handling y correlation ID

Se revisó `app/core/errors/handlers.py`.

P-6 endurece que todo error tenga `correlation_id` no nulo.

La ruta normal usa el valor creado/validado por `CorrelationIdMiddleware`; existe un UUID fallback para garantizar la invariante incluso si el state no estuviera disponible.

Se conserva sanitización del 422: no se serializa `exc.errors()` ni body sensible al cliente.

---

## 9. OpenAPI baseline

Se revisó el mecanismo:

```text
scripts/generate_openapi.py
contracts/api/v1/openapi.json
```

La generación:

- parte de `create_app()` real;
- usa orden JSON determinista;
- conserva metadata y campos públicos, sin normalizaciones que puedan ocultar cambios;
- representa `v1.0.0`;
- contiene Module API y Milking;
- no contiene rutas P-7 Sync;
- representa `ErrorResponse` común;
- documenta respuestas system de forma específica.

Durante implementación se utilizó un workflow temporal exclusivamente para generar y comparar el snapshot real. Dicho workflow fue retirado del diff final.

La versión de Pydantic que produjo el baseline (`2.13.4`) quedó fijada explícitamente en `requirements.txt` para evitar drift del OpenAPI por dependencia transitiva.

---

## 10. PostgreSQL / aislamiento

El test P-6 PostgreSQL preparado exige:

- Platform Identity PostgreSQL real;
- dos Tenant DB PostgreSQL físicas;
- dos Companies dentro del mismo Tenant A;
- una Company en Tenant B.

Debe demostrar dinámicamente:

- absence = DISABLED/v0;
- module enforcement Milking;
- enable v1;
- replay;
- fingerprint conflict;
- stale expected version;
- disable v2;
- aislamiento entre Companies del mismo Tenant;
- aislamiento físico entre Tenants;
- mismo `command_id` reutilizable independientemente en Tenant DB distintas.

Esta revisión estática no afirma que esas pruebas hayan pasado; corresponde al verificador independiente ejecutarlas.

---

## 11. Persistencia y migraciones

No hay cambios en `migrations/` ni nuevas tablas.

Se preserva:

```text
Tenant head = 0005_p5_module_activation
```

P-6 no introduce persistencia propia.

---

## 12. Hallazgos detectados y corregidos antes del gate

### H-01 — baseline OpenAPI inicialmente transcrito manualmente

**Severidad previa:** HIGH de evidencia/contrato.  
**Estado:** CORREGIDO.

El primer archivo comprometido no coincidía exactamente con el OpenAPI generado. El control automático lo rechazó. Se sustituyó por el JSON generado desde el código real y se verificó diff cero.

### H-02 — documentación de errores de system demasiado amplia

**Severidad previa:** MEDIUM contractual.  
**Estado:** CORREGIDO.

Se evitó declarar 401/403/409 en endpoints system que no los producen. `/live`, `/ready`, `/health` documentan subconjuntos coherentes.

### H-03 — `correlation_id` nullable en schema

**Severidad previa:** MEDIUM contractual.  
**Estado:** CORREGIDO.

El contrato congelado lo exige; schema y runtime ahora garantizan string no nulo.

### H-04 — Pydantic no fijado explícitamente

**Severidad previa:** MEDIUM de reproducibilidad.  
**Estado:** CORREGIDO.

Se fijó `pydantic==2.13.4`, la versión usada para generar/verificar el baseline.

### H-05 — aislamiento Company dentro del mismo Tenant no explícito en test P-6

**Severidad previa:** MEDIUM de evidencia.  
**Estado:** CORREGIDO.

El test PostgreSQL P-6 ahora crea una segunda Company en Tenant A y verifica que habilitar Milking en Company A no habilita Company A2.

---

## 13. Controles preliminares ya observados

Un control automatizado temporal sobre el código P-6 confirmó preliminarmente:

- generación OpenAPI: PASS;
- sincronización exacta baseline: PASS;
- diff baseline generado/comprometido: PASS;
- compileall focal: PASS;
- focales `test_p6_api_contracts.py`, `test_p6_module_api.py`, `test_o4_milking_api.py`: PASS.

Esto es evidencia preliminar y no reemplaza la verificación final independiente sobre el HEAD exacto.

---

## 14. Exclusiones verificadas estáticamente

No aparecen en el diff final:

- P-7 Sync;
- Outbox/Inbox;
- cursor/checkpoint/ACK;
- migration P-6;
- API Gateway;
- GraphQL/gRPC;
- generated SDK obligatorio;
- plugin engine;
- entitlement/licensing;
- feature flags;
- generic config store;
- Site/OperationalUnit;
- lógica Dairy/Aliosur hardcodeada en Platform.

---

## 15. Veredicto estático

> **P-6 se considera APTO PARA VERIFICACIÓN INDEPENDIENTE.**

No se identifican hallazgos estáticos BLOCKER/HIGH/MEDIUM pendientes después de las correcciones descritas.

Este veredicto no autoriza:

- cierre P-6;
- merge PR #10;
- inicio P-7;
- tag/release.

La siguiente etapa obligatoria es ejecutar verificación independiente sobre el HEAD exacto, con PostgreSQL real, regresiones, suite completa, OpenAPI, Docker y evidencias XML/logs.
