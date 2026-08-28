# BE-DES-006 — Contrato P-6 API + Contracts + Compatibility

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO — IMPLEMENTACIÓN NO AUTORIZADA  
**Fecha:** 2026-08-27  
**Aprobación:** aprobada expresamente por el usuario el 2026-08-27  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Plan maestro:** `BE-PLAN-001 v0.2`  
**ADR rector:** `BE-ADR-002 v0.1`  
**Cortes preservados:** P-1, P-2, P-3, P-4, P-5 y O-4 cerrados  
**Base candidata:** `main @ 32ee8f209890166ae1a16a040e6d2784e7c541d4` — NO autorizada todavía como base P-6  
**Rama propuesta:** `feat/platform-p6-api-contracts`

---

## 1. Objetivo

Implementar la foundation transversal mínima y completa para que ERP Platform disponga de contratos HTTP públicos estables, versionados y verificables, compatibles con clientes Android/Web que puedan evolucionar en momentos distintos del backend.

P-6 debe:

- formalizar el API público mayor `v1`;
- congelar reglas de compatibilidad dentro de `v1`;
- estandarizar los contratos HTTP transversales ya existentes;
- formalizar el envelope común de errores;
- formalizar el contrato común de respuestas de comandos P-4;
- exponer la administración mínima de módulos P-5 mediante HTTP;
- aplicar `ModuleAvailabilityService` como gate HTTP de bounded contexts;
- preservar O-4 Milking sin cambiar su semántica funcional;
- introducir una evidencia machine-readable del contrato OpenAPI;
- impedir cambios públicos accidentales mediante tests de contrato.

P-6 NO implementa Sync, Outbox/Inbox, API Gateway, plugins, SDK generation ni una plataforma exhaustiva de API management.

---

## 2. Contexto real después de P-5

`main` actual:

```text
32ee8f209890166ae1a16a040e6d2784e7c541d4
```

El backend ya expone:

```text
/api/v1/live
/api/v1/ready
/api/v1/health

/api/v1/auth/*
/api/v1/milking/*
```

El API ya utiliza:

```text
command_id
expected_version
client_occurred_at
client_instance_id
correlation_id
```

según el caso.

El runtime ya dispone de:

```text
P-3 Authentication / Authorization
P-4 Idempotency / Concurrency / Command Result
P-5 Module Registry / Activation
```

pero P-5 dejó expresamente fuera:

```text
HTTP enforcement
endpoint universal de módulos
representation HTTP de errores P-5
compatibility policy
```

P-6 completa exclusivamente esa frontera pública.

---

## 3. Principios preservados

P-6 preserva sin reabrir:

- Tenant físico por PostgreSQL DB;
- Company como scope operacional;
- AuthenticatedPrincipal P-3;
- RBAC deny-by-default;
- `command_id` / idempotencia P-4;
- `expected_version` / CAS P-4;
- ModuleRegistry P-5;
- activation Company-scoped;
- ausencia de activation = DISABLED/version 0;
- `ENABLED != OPERATIONALLY_READY`;
- Activation != Authorization;
- Activation != Entitlement;
- módulo deshabilitado no borra datos;
- bounded contexts conservan sus contratos de dominio;
- Milking conserva su semántica O-4.

---

# 4. Alcance mínimo P-6

P-6 v0.1 se limita a seis bloques:

```text
A. API versioning policy
B. Common HTTP contracts
C. Module HTTP administration
D. Module enforcement
E. OpenAPI contract baseline
F. Compatibility regression tests
```

No introduce persistencia nueva.

No requiere migración Alembic nueva.

El head Tenant debe continuar:

```text
0005_p5_module_activation
```

---

# 5. Versionado público del API

## 5.1 Major version en URL

Se congela:

```text
/api/v1
```

como namespace mayor del contrato público actual.

P-6 NO introduce:

```text
Accept-Version
vendor media types
/api/v1.1
query-string API versioning
```

Regla:

> Los cambios compatibles pueden evolucionar dentro de `/api/v1`. Un cambio incompatible requiere un nuevo major público y no puede sustituir silenciosamente el contrato v1.

Ejemplo futuro:

```text
/api/v1/milking/...
/api/v2/milking/...
```

si un bounded context necesita una ruptura contractual.

No es obligatorio duplicar todo el API en v2; la estrategia concreta se congelará cuando aparezca un caso real.

---

## 5.2 API contract version

Se propone formalizar:

```text
PUBLIC_API_VERSION = "1.0.0"
```

como versión documental/técnica del contrato público v1.

Esta versión:

- NO es `module_version`;
- NO es Alembic revision;
- NO es Android app version;
- NO es backend build/release version;
- NO es future sync protocol version.

`FastAPI.version` podrá reflejar `PUBLIC_API_VERSION`.

---

# 6. Separación de versiones

Quedan explícitamente separados:

```text
API public major/version
        !=
ModuleDefinition.module_version
        !=
P-4 command_schema_version
        !=
Alembic revision
        !=
future P-7 sync_protocol_version
        !=
Android/Web client version
```

Ningún cliente deberá interpretar `module_version` como versión del API HTTP.

---

# 7. Política de compatibilidad dentro de v1

## 7.1 Cambios no permitidos silenciosamente

Dentro de `/api/v1` no se permite sin nuevo contrato/major:

- eliminar endpoint existente;
- cambiar método HTTP;
- cambiar path existente;
- renombrar campo público existente;
- eliminar campo de respuesta existente;
- cambiar tipo JSON de un campo;
- convertir campo opcional de request en obligatorio;
- añadir nuevo campo obligatorio de request;
- cambiar semántica de un campo manteniendo el mismo nombre;
- cambiar arbitrariamente status HTTP asociado a un error estable;
- reutilizar un `error.code` existente con otra semántica;
- estrechar una validación de forma que requests v1 previamente válidos pasen a ser inválidos sin revisión explícita;
- cambiar una enum cerrada de manera incompatible.

---

## 7.2 Cambios compatibles permitidos con revisión

Pueden permanecer en v1, previa revisión de contrato:

- endpoint nuevo;
- campo nuevo opcional;
- nuevo filtro opcional;
- ampliación de metadata no obligatoria;
- nueva operación de dominio;
- nuevas capacidades de módulos;
- correcciones que no cambien el significado del contrato existente.

Toda modificación pública debe actualizar deliberadamente la evidencia OpenAPI si corresponde.

---

## 7.3 Clientes first-party

Los clientes Android/Web deberán:

- ignorar campos JSON desconocidos cuando el serializer lo permita;
- no depender del texto de `error.message`;
- interpretar `error.code` como identificador de máquina;
- disponer de fallback seguro para error code desconocido;
- tratar access/refresh token como opacos;
- no asumir que `module_version` determina compatibilidad HTTP.

Estas reglas deberán ser consumidas posteriormente por O-5/P-7 cuando corresponda.

---

# 8. Contrato común de errores

El envelope actual se congela como contrato v1:

```json
{
  "error": {
    "code": "CONCURRENCY_CONFLICT",
    "message": "The resource version changed before the command could be applied.",
    "correlation_id": "..."
  }
}
```

Modelo conceptual:

```text
ErrorResponse
└── error
    ├── code
    ├── message
    └── correlation_id
```

Reglas:

1. `error.code` es estable y machine-readable.
2. `error.message` es human-readable y NO se considera identificador contractual.
3. `correlation_id` debe corresponder al `X-Correlation-ID` de la respuesta.
4. no se reflejan passwords, refresh tokens, JWTs ni body sensible.
5. errores inesperados se transforman en `INTERNAL_ERROR`.
6. request validation conserva `REQUEST_VALIDATION_FAILED`.
7. no se serializa directamente `exc.errors()` hacia el cliente si puede contener información sensible.

---

# 9. Códigos HTTP transversales preservados

P-6 congela como mínimo la representación HTTP ya existente de:

```text
AUTHENTICATION_FAILED             401
ACCESS_DENIED                     403

MODULE_NOT_REGISTERED             404

IDEMPOTENCY_CONFLICT              409
CONCURRENCY_CONFLICT              409
MODULE_NOT_ENABLED                409
MODULE_ACTIVATION_NOT_AVAILABLE   409

REQUEST_VALIDATION_FAILED         422

INTERNAL_ERROR                    500

IDENTITY_UNAVAILABLE              503
COMMAND_EXECUTION_UNAVAILABLE     503
```

Los códigos propios de cada bounded context siguen perteneciendo a ese módulo.

P-6 no convierte todos los errores de dominio en un catálogo global.

---

# 10. Correlation ID

Se preserva:

```text
X-Correlation-ID
```

Reglas:

- si el cliente envía un valor válido, el servidor lo conserva;
- si falta/es inválido, el servidor genera uno;
- toda respuesta HTTP debe devolverlo;
- todo ErrorResponse debe incluir el mismo valor;
- nunca se utiliza como autorización, idempotency key ni identidad de command.

---

# 11. Contrato común de mutaciones P-4

Las mutaciones que utilizan P-4 deben mantener:

```text
command_id
```

como identidad durable de comando.

Si el recurso utiliza optimistic concurrency:

```text
expected_version
```

es obligatorio.

La respuesta común actual se congela:

```json
{
  "code": "SOME_RESULT",
  "replayed": false,
  "data": {}
}
```

Modelo:

```text
CommandResponse
├── code
├── replayed
└── data
```

Reglas:

- `code` identifica el resultado lógico;
- `replayed=true` significa replay idempotente, no segunda ejecución;
- `data` contiene el resultado mínimo durable definido por el comando;
- los command endpoints actuales mantienen HTTP 200 en v1;
- P-6 no cambia create commands a 201 ni introduces 202 async semantics.

---

# 12. client_occurred_at y client_instance_id

P-6 preserva los campos ya existentes en Milking:

```text
client_occurred_at
client_instance_id
```

pero NO los eleva todavía a requisito universal de todo comando Platform.

Razón:

- son necesarios para dominios/offline concretos;
- P-7 deberá congelar su semántica transversal de Sync;
- P-6 no debe adelantar el protocolo offline.

La administración de módulos P-5 no necesita estos campos en P-6 v0.1.

---

# 13. Pagination v1

Las consultas ordinarias actuales Milking preservan:

```text
limit
offset
```

con:

```text
default limit = 100
max limit     = 500
offset >= 0
```

y respuestas como listas JSON directas.

P-6 NO transforma esas respuestas a:

```json
{
  "items": [],
  "total": 0,
  "next": "..."
}
```

porque sería ruptura de O-4.

P-7 Sync usará su propia semántica de cursor/checkpoint y NO reutilizará necesariamente esta pagination.

---

# 14. API de módulos P-5

P-6 expone la foundation P-5 mediante HTTP.

## 14.1 GET /api/v1/modules

Devuelve el catálogo/estado de módulos para la Company activa del principal.

No recibe:

```text
tenant_id
company_id
```

desde query/body de confianza.

Ambos se derivan del `AuthenticatedPrincipal`.

Acceso:

> cualquier principal autenticado con contexto operacional válido puede consultar los módulos de su propia Company.

Esto permite a clientes first-party conocer capacidades disponibles sin requerir permiso administrativo.

Respuesta conceptual:

```text
ModuleStatusResponse
├── module_id
├── module_version
├── description
├── state
├── version
├── activation_present
└── effective_enabled
```

`configuration_namespace` permanece interno en v0.1 y no necesita exponerse al cliente.

`description` es informativa y NO debe usarse como etiqueta UI localizada.

---

## 14.2 POST /api/v1/modules/{module_id}/enable

Request:

```json
{
  "command_id": "...",
  "expected_version": 0
}
```

Requiere:

```text
platform.modules.manage
```

y contexto Tenant + Company P-3.

Usa exclusivamente `ModuleActivationService`.

No implementa motor paralelo.

---

## 14.3 POST /api/v1/modules/{module_id}/disable

Mismo contrato transversal:

```text
command_id
expected_version
platform.modules.manage
```

Respuesta:

```text
CommandResponse
```

P-4 conserva:

- replay;
- fingerprint conflict;
- optimistic concurrency;
- rollback.

---

# 15. Module enforcement HTTP

P-6 introduce el primer enforcement público P-5.

Regla:

> Todo router de bounded context sujeto a Module Registry debe comprobar que su módulo está efectivamente habilitado para la Company activa antes de ejecutar lógica funcional.

Para Milking:

```text
AuthenticatedPrincipal
      ↓
Tenant + Company context
      ↓
ModuleAvailabilityService.require_enabled("milking")
      ↓
Milking domain authorization/service
```

P-6 NO duplica reglas Milking.

---

## 15.1 Endpoints no sujetos a module activation

No quedan detrás de module activation:

```text
/api/v1/live
/api/v1/ready
/api/v1/health

/api/v1/auth/*

/api/v1/modules
/api/v1/modules/{id}/enable
/api/v1/modules/{id}/disable
```

El Core Platform no es módulo activable.

---

## 15.2 Módulo no habilitado

Si Milking está registrado pero no habilitado:

```text
409
MODULE_NOT_ENABLED
```

El request no entra a la lógica funcional Milking.

---

## 15.3 Módulo no registrado

Si existe una inconsistencia runtime/router:

```text
404
MODULE_NOT_REGISTERED
```

fail-closed.

---

## 15.4 Readiness funcional

P-6 solo valida:

```text
registered + company active + activation ENABLED
```

No valida:

```text
MilkingConfiguration
Farm
Shift
OutputProfile
```

Si el módulo está ENABLED pero funcionalmente no configurado, el bounded context responde con su error propio.

---

# 16. Orden de seguridad

P-6 no deberá consultar una Tenant DB de forma confiada antes de disponer de identidad/contexto autorizado P-3.

La dependencia de módulo se ejecuta únicamente después de obtener un `AuthenticatedPrincipal` válido.

P-6 no toma `tenant_id/company_id` desde headers arbitrarios como autorización.

---

# 17. Transición de O-4 hacia enforcement P-6

P-5 congeló:

```text
absence = DISABLED/version 0
```

Por tanto P-6 NO puede preservar acceso implícito a Milking cuando no existe activation.

Decisión propuesta:

> No se realizará backfill automático ni se habilitará Milking silenciosamente.

Las Companies existentes de desarrollo/prueba deberán realizar explícitamente:

```text
GET /api/v1/modules
POST /api/v1/modules/milking/enable
```

con un principal autorizado.

Luego:

```text
Milking API -> disponible
```

Razones:

- preserva fail-closed P-5;
- evita hardcodear Milking en Core;
- no introduce defaults invisibles;
- mantiene activation como decisión administrativa explícita.

Dado que O-5 todavía no está cerrado/operativo end-to-end, esta transición puede efectuarse antes de puesta en operación.

Si en un futuro existe una Company productiva que no pueda tolerar una ventana de activation durante despliegue, el rollout operativo deberá tener contrato específico P-8; P-6 no implementa un feature flag de transición.

---

# 18. OpenAPI como evidencia machine-readable

P-6 introduce un baseline versionado:

```text
contracts/api/v1/openapi.json
```

generado desde el FastAPI real.

El baseline debe representar el contrato público del API v1.

---

## 18.1 Contract snapshot test

Se implementará un test que:

1. genera OpenAPI desde `create_app()`;
2. canonicaliza JSON de forma determinista;
3. compara contra `contracts/api/v1/openapi.json`;
4. falla si existe diferencia no registrada.

El snapshot es un **detector de cambio**, no un algoritmo que por sí mismo decida si el cambio es breaking.

Regla:

> Todo cambio del snapshot requiere revisión explícita del diff contractual.

---

## 18.2 Cambios compatibles futuros

Si un nuevo endpoint/campo opcional es compatible:

- se revisa el OpenAPI diff;
- se actualiza el baseline en el mismo corte;
- se deja evidencia de compatibilidad;
- el API permanece v1.

---

## 18.3 Cambios incompatibles futuros

No se autoriza simplemente actualizar el snapshot v1 para ocultar una ruptura.

Debe:

- conservarse v1;
- crear nuevo major/contrato;
- o aprobarse una estrategia explícita de transición.

---

# 19. OpenAPI y runtime deben coincidir

P-6 debe corregir cualquier discrepancia relevante entre documentación generada y comportamiento real.

Especialmente:

- envelope real de errores;
- 422 sanitizado;
- schemas de module endpoints;
- auth Bearer;
- request/response models.

No se exige documentar exhaustivamente cada error de dominio en v0.1 si ello sobredimensiona el corte.

Sí se exige que los contratos transversales centrales no contradigan el runtime.

---

# 20. Contratos comunes en código

Se propone extraer a una capa API transversal reutilizable, sin mover semántica de dominio:

```text
app/api/contracts/
    common.py
```

con conceptos equivalentes a:

```text
ErrorResponse
ErrorBody
CommandResponse
API version constants
pagination constants
```

P-6 puede refactorizar Milking para consumir `CommandResponse` común si el OpenAPI/JSON resultante permanece compatible.

No se extraen:

```text
SessionResponse
OutputResponse
MilkingConfigurationResponse
Milking commands
```

porque pertenecen al bounded context.

---

# 21. Security dependency común

Para evitar implementaciones duplicadas de Bearer parsing/principal resolution se propone una dependency API transversal, equivalente a:

```text
current_principal(...)
require_operational_principal(...)
require_module_enabled(module_id)
```

Debe consumir P-3/P-5 existentes.

No implementa un nuevo auth engine.

---

# 22. Compatibility de tokens

Los clientes deben considerar:

```text
access_token
refresh_token
```

como valores opacos.

P-6 no congela claims JWT como API pública de cliente.

La compatibilidad pública queda en:

- endpoints auth;
- request/response JSON;
- Bearer usage;
- expiraciones publicadas.

Esto preserva libertad futura para evolucionar internamente P-3 sin romper clientes.

---

# 23. Error handling de clientes

P-6 congela que first-party clients deben disponer de fallback general.

Ejemplo conceptual:

```text
known error code
    -> tratamiento específico

unknown error code
    -> error genérico + correlation_id
```

El cliente no debe fallar por recibir un nuevo `error.code` compatible.

---

# 24. No API Gateway en P-6

P-6 NO introduce:

- Kong;
- Traefik como API management;
- service mesh;
- external gateway policies;
- rate limiting distribuido;
- OAuth2 authorization server externo.

La API sigue servida directamente por FastAPI.

Esas capacidades se analizarán cuando exista necesidad operacional real.

---

# 25. No SDK generation en P-6

P-6 NO obliga todavía a:

- generar cliente Kotlin;
- generar TypeScript SDK;
- publicar paquetes;
- codegen automático.

OpenAPI baseline deja esa posibilidad abierta para futuros incrementos.

O-5 podrá decidir si consume OpenAPI mediante client manual o generado.

---

# 26. P-7 queda fuera

P-6 NO define:

```text
sync endpoint
push/pull
cursor
checkpoint
ACK
Outbox
Inbox
sync_protocol_version
conflict resolution protocol
```

P-7 deberá consumir:

- P-3 identity/context;
- P-4 command/idempotency/concurrency;
- P-5 module availability;
- P-6 public API compatibility rules.

---

# 27. Persistencia y migraciones

P-6 v0.1 no necesita tablas nuevas.

No modifica:

```text
Platform Identity DB schema
Tenant DB schema
platform_module_activations
platform_command_executions
Milking tables
```

Tenant Alembic head permanece:

```text
0005_p5_module_activation
```

Platform Alembic permanece en su head P-3 vigente.

Si durante implementación aparece una necesidad real de persistencia P-6, se detendrá ese punto y deberá revisarse el contrato antes de añadir una migration.

---

# 28. Pruebas obligatorias

## 28.1 API contract unit

- PUBLIC_API_VERSION;
- error envelope;
- CommandResponse;
- pagination constants;
- correlation ID.

## 28.2 OpenAPI

- snapshot exacto;
- routes bajo `/api/v1`;
- auth security;
- schemas comunes;
- module endpoints;
- no route P-7 Sync;
- runtime y OpenAPI sin contradicción transversal conocida.

## 28.3 Module API PostgreSQL

Con Identity DB real + al menos dos Tenant DB:

- GET modules;
- absent => DISABLED/version 0;
- user sin manage no puede enable/disable;
- admin enable expectedVersion=0 => v1;
- replay mismo command;
- fingerprint conflict;
- stale expectedVersion => CONCURRENCY_CONFLICT;
- disable => v2;
- Company isolation;
- Tenant isolation.

## 28.4 HTTP enforcement Milking

- sin activation => MODULE_NOT_ENABLED;
- enable => Milking endpoint ejecutable;
- disable => Milking vuelve a quedar bloqueado;
- auth/system no se bloquean;
- enabled pero no ready => responde bounded context, no P-6;
- módulo no registrado => fail-closed.

## 28.5 P-3/O-4 regression

- login;
- context selection;
- access denied;
- O-4 commands/queries;
- replay/concurrency;
- PostgreSQL real;
- O-4 races históricas vigentes.

## 28.6 Compatibility

- requests/responses O-4 existentes conservan JSON y status;
- plain list pagination preservada;
- CommandResponse preservado;
- error envelope preservado;
- X-Correlation-ID preservado.

## 28.7 Full suite

- 0 failures;
- 0 errors;
- 0 skips críticos P-3/P-4/P-5/O-4/P-6;
- XML JUnit real.

---

# 29. Concurrencia

P-6 no crea nueva primitive de concurrencia.

Las mutaciones HTTP de activation deben demostrar que atraviesan correctamente P-4/P-5.

Stress mínimo recomendado:

```text
dos enable concurrentes expectedVersion=0
-> un winner
-> resto CONCURRENCY_CONFLICT
```

No se crea locking HTTP paralelo.

---

# 30. Evidencia obligatoria

El verificador independiente deberá aportar como mínimo:

- base SHA;
- HEAD SHA;
- diff;
- `git diff --check`;
- OpenAPI baseline;
- diff OpenAPI;
- JUnit focal;
- JUnit PostgreSQL;
- JUnit suite completa;
- Identity PostgreSQL;
- dos Tenant PostgreSQL;
- module enable/disable vía HTTP;
- module enforcement Milking;
- correlation/error contract;
- replay/conflict/concurrency;
- O-4 regression;
- compile/import;
- Docker PostgreSQL;
- health/live/ready;
- secret/log hygiene;
- working tree final limpio.

El agente no modifica código.

---

# 31. Exclusiones expresas

P-6 NO implementa:

- P-7 Sync;
- Outbox/Inbox;
- cursor/checkpoint;
- ACK protocol;
- API Gateway;
- rate limiting distribuido;
- service mesh;
- GraphQL;
- gRPC;
- generic success envelope para todos los GET;
- cambio de list responses a `{items,total}`;
- plugin engine;
- module installer;
- dependency solver;
- entitlement/licensing;
- feature flags;
- generic configuration store;
- generated SDK obligatorio;
- Web UI;
- Android Sync;
- microservicios;
- Site/OperationalUnit;
- lógica Dairy/Aliosur en Platform.

---

# 32. Invariantes propuestas

1. Todo API público funcional permanece versionado bajo `/api/v1`.
2. Breaking changes no se introducen silenciosamente dentro de v1.
3. API version, module version, command schema version, Alembic y future sync protocol son independientes.
4. Error envelope v1 es estable.
5. `error.code` es machine contract; `message` no.
6. Correlation ID está presente y es consistente header/body en errores.
7. P-4 command mutations conservan `CommandResponse`.
8. `command_id` sigue siendo la identidad de idempotencia.
9. `expected_version` sigue gobernado por P-4/P-5/domain.
10. ordinary pagination O-4 permanece limit/offset + list.
11. P-6 no redefine domain DTOs.
12. module administration consume P-5.
13. module enable/disable requiere `platform.modules.manage`.
14. GET modules solo opera sobre el contexto Tenant/Company autorizado del principal.
15. module enforcement se aplica antes de lógica funcional del bounded context.
16. Module enforcement no equivale a domain readiness.
17. ausencia de activation sigue siendo DISABLED/v0.
18. no hay backfill/enable automático de Milking.
19. auth/system/Core no quedan detrás de Module activation.
20. OpenAPI baseline es evidencia versionada.
21. cambiar OpenAPI baseline requiere revisión explícita.
22. P-6 no implementa Sync.
23. P-1/P-2/P-3/P-4/P-5/O-4 permanecen cerrados.
24. no se añade migration P-6 salvo revisión contractual expresa.

---

# 33. Decisiones aprobadas

Antes de congelar P-6 deben aprobarse expresamente:

1. **Versioning:** `/api/v1` como major público; sin header/media-type versioning.
2. **Public API version:** formalizar `1.0.0`.
3. **Breaking policy:** ruptura requiere nuevo major/estrategia explícita.
4. **Error contract:** congelar `{error:{code,message,correlation_id}}`.
5. **Error semantics:** `code` estable; `message` no machine-contract.
6. **Correlation:** `X-Correlation-ID` obligatorio en respuestas.
7. **CommandResponse:** mantener `{code,replayed,data}` y HTTP 200.
8. **Pagination:** preservar `limit/offset` + list para queries ordinarias existentes.
9. **Module catalog:** `GET /api/v1/modules`.
10. **Module read access:** cualquier principal autenticado con contexto operacional puede listar su propia Company.
11. **Module admin:** enable/disable por POST, permiso `platform.modules.manage`.
12. **Module enforcement:** Milking queda bloqueado cuando activation no está ENABLED.
13. **No backfill:** no activar Milking automáticamente.
14. **Readiness:** P-6 no valida configuración funcional Milking.
15. **OpenAPI baseline:** `contracts/api/v1/openapi.json`.
16. **Snapshot gate:** cualquier cambio OpenAPI requiere revisión explícita.
17. **No semantic diff engine complejo:** snapshot funciona inicialmente como change detector.
18. **Token opacity:** JWT claims no son API pública de cliente.
19. **No DB migration:** Tenant head permanece `0005`.
20. **No P-7:** Sync permanece completamente fuera.
21. **No SDK obligatorio:** codegen futuro queda abierto.
22. **No API Gateway:** se difiere a necesidad operacional real.

---

## 33.1 Estado de aprobación

Las 22 decisiones enumeradas en esta sección quedan **APROBADAS y CONGELADAS**.

En particular, se ratifica expresamente que:

- P-7 Sync queda fuera de P-6;
- no se exige generación automática de SDK en P-6;
- no se introduce API Gateway en P-6.

Cualquier modificación posterior de estas decisiones requerirá revisión contractual expresa.

---

# 34. Gate de cierre

> P-6 será cerrable cuando ERP Platform tenga un contrato HTTP v1 explícito, un error/command contract común, administración HTTP de módulos P-5, enforcement de module availability sobre Milking, baseline OpenAPI versionado y pruebas de compatibilidad que demuestren que P-3/P-4/P-5/O-4 siguen funcionando sin introducir Sync P-7.

---

# 35. Gobierno Git

Antes de implementar:

1. aprobar/congelar `BE-DES-006 v0.1`;
2. autorizar expresamente `main @ 32ee8f209890166ae1a16a040e6d2784e7c541d4` como base P-6;
3. crear:

```text
feat/platform-p6-api-contracts
```

4. abrir Draft PR propio;
5. registrar contrato aprobado;
6. implementar en commits pequeños.

Prohibido:

- push directo a main;
- force push;
- merge sin autorización;
- tag sin autorización;
- rebase destructivo;
- iniciar P-7 sin cierre y autorización correspondiente.

---

# 36. Regla resumida

> **P-6 convierte el API HTTP ya existente en un contrato público v1 explícito y verificable. Formaliza versionado, errores, command responses, correlation ID, compatibilidad, OpenAPI baseline y la exposición/enforcement de Module Activation P-5. No modifica la semántica de los bounded contexts ni adelanta Sync P-7.**
