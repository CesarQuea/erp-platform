# BE-MLK-DES-004 — Contrato O-4 Backend Cloud Milking GENERAL

**Versión:** v0.1  
**Fecha:** 2026-08-25  
**Estado:** APROBADO / CONGELADO  
**Proyecto:** AliosurERP18  
**Repositorio:** `CesarQuea/erp-platform`  
**Corte:** O-4 — Backend Cloud Milking GENERAL  
**Base autorizada:** `8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed`

---

## 1. Objetivo

Implementar en `erp-platform` la autoridad cloud PostgreSQL del slice Milking V2 GENERAL/TOTAL, preservando la semántica funcional cerrada en Android y reutilizando, sin duplicarlas, las capacidades transversales ya cerradas en ERP Platform P-1, P-2, P-3, BE-ADR-001 y P-4.

O-4 implementa backend autoritativo de Milking. O-4 **NO** implementa sincronización Android↔Cloud; esa responsabilidad corresponde a O-5.

---

## 2. Fuentes de autoridad

O-4 se interpreta conjuntamente con:

- ERP Platform P-1 — Core Runtime.
- ERP Platform P-2 — Tenant + Company + PostgreSQL por Tenant.
- ERP Platform P-3 — Identity/Auth/Membership/RBAC.
- BE-ADR-001 — `Tenant -> Company` como jerarquía transversal mínima.
- ERP Platform P-4 — Transactions + Idempotency + Concurrency + Audit.
- Milking V2 contratos cerrados O-0.3, O-1, O-2, O-3 y O-3.1.
- MLK-DES-007 — O-3.2 retiro Site/OperationalUnit.
- MLK-ADD-004 — fronteras de dominio.
- MLK-IMP-007 — resultado implementación O-3.2.
- MLK-CLOSE-008 — cierre O-3.2.
- Código y pruebas reales de Android Milking V2 y ERP Platform.

Ante contradicción prevalece el contrato/ADR aprobado más específico y vigente.

---

## 3. Frontera transversal

Cloud usa:

```text
Tenant
└── Company
    └── recursos propios de cada módulo
```

Milking Cloud usa:

```text
AuthenticatedPrincipal
        ↓
TenantContext
        ↓
CompanyContext
        ↓
Milking
├── Farm reference
├── OutputProfile
├── MilkingConfiguration
├── MilkingSession
├── MilkingOutput
├── AnnulmentRequest
└── BusinessAudit
```

Quedan prohibidos como niveles obligatorios de Milking:

- `Organization` cloud;
- `Site`;
- `OperationalUnit`;
- `ProductionUnit`;
- `Plant`;
- `Facility`;
- `Branch`;
- `Warehouse`;
- `Location`.

`organizationId` de Android no se materializa como tabla cloud obligatoria. Su correspondencia con `TenantContext` se resolverá en O-5.

---

## 4. Autoridad de dominio

### 4.1 Farm

Livestock es autoridad de `Farm`.

Milking:

- referencia `farm_id` UUID estable;
- no crea maestro Farm;
- no almacena nombre, código, propietario, dirección ni atributos ganaderos;
- no edita ni elimina Farm.

Mientras Livestock Cloud no exista, una `MilkingConfiguration` activa habilita temporalmente un `farm_id` para Milking, sin convertir a Milking en autoridad de Farm.

### 4.2 Product / UoM

Product y UoM son referencias externas estables.

Milking almacena `product_id` y `quantity_uom_id`, pero no crea `MilkingProduct` ni `MilkingUom`.

### 4.3 Módulos downstream

- Purchase gobierna compra de leche a terceros.
- Milk Logistics gobierna recojo/transporte.
- Reception gobierna recepción física.
- Quality gobierna calidad.
- Inventory gobierna stock, Warehouse y Location.

Leche comprada nunca crea `MilkingSession` ni `MilkingOutput`.

`MilkingOutput` es producción propia confirmada; no es stock disponible.

---

## 5. Slice funcional O-4

O-4 implementa únicamente GENERAL/TOTAL.

Estados:

```text
DRAFT
DONE
CANCELLED
```

Fuente autoritativa implementada:

```text
GENERAL
```

Quedan reservadas y no implementadas:

```text
INDIVIDUAL_TOTAL
GROUP_TOTAL
```

---

## 6. Modelo funcional PostgreSQL

Tablas funcionales O-4:

```text
milking_output_profiles
milking_configurations
milking_sessions
milking_outputs
milking_annulment_requests
milking_audit_events
```

No crear:

```text
milking_farms
milking_products
milking_uoms
milking_command_executions
milking_technical_audit
milking_outbox
milking_inbox
```

La idempotencia técnica utiliza `platform_command_executions` de P-4.

---

## 7. OutputProfile

`OutputProfile` pertenece a Milking y es versionado.

Modelo conceptual:

```text
profile_id          UUID
profile_version     BIGINT
company_id          UUID
product_id          UUID
quantity_uom_id     UUID
is_active           BOOLEAN
created_at          TIMESTAMPTZ
created_by          UUID
```

Clave:

```text
PRIMARY KEY(profile_id, profile_version)
```

Reglas:

1. `profile_version > 0`.
2. Una versión publicada no se modifica destructivamente.
3. Un cambio contractual de producto/UoM crea una nueva versión.
4. `product_id` y `quantity_uom_id` son UUID externos.
5. Al crear una sesión, Profile/Product/UoM se snapshottean.
6. Cambios futuros de profile no alteran sesiones históricas.

---

## 8. MilkingConfiguration

Regla:

```text
Company + Farm + Shift -> OutputProfileVersion
```

Modelo conceptual:

```text
id                      UUID PK
company_id              UUID
farm_id                 UUID
shift_code              VARCHAR
output_profile_id       UUID
output_profile_version  BIGINT
is_active               BOOLEAN
created_at              TIMESTAMPTZ
created_by              UUID
updated_at              TIMESTAMPTZ NULL
updated_by              UUID NULL
```

Constraints:

```text
UNIQUE(company_id, farm_id, shift_code)
FK(output_profile_id, output_profile_version)
  -> milking_output_profiles
```

No se introducen `valid_from/valid_to` en O-4.

---

## 9. MilkingSession

Campos conceptuales:

```text
id                              UUID PK
company_id                      UUID
farm_id                         UUID
milking_date                    DATE
shift_code                      VARCHAR
operator_id                     UUID NULL
status                          VARCHAR
animals_milked_count            INTEGER NULL
general_gross_quantity          NUMERIC NULL
quantity_uom_id                 UUID
authoritative_gross_quantity    NUMERIC NULL
authoritative_total_source      VARCHAR NULL
used_on_farm_quantity           NUMERIC NULL
discarded_quantity              NUMERIC NULL
net_output_quantity             NUMERIC NULL
reconciliation_status           VARCHAR
output_profile_id               UUID
output_profile_version          BIGINT
product_id                      UUID
notes                           VARCHAR(500) NULL
version                         BIGINT
created_at                      TIMESTAMPTZ
created_by                      UUID
updated_at                      TIMESTAMPTZ NULL
updated_by                      UUID NULL
confirmed_at                    TIMESTAMPTZ NULL
confirmed_by                    UUID NULL
cancelled_at                    TIMESTAMPTZ NULL
cancelled_by                    UUID NULL
cancel_reason                   TEXT NULL
```

Tenant no se repite por fila porque la DB física pertenece al Tenant. `company_id` sí es obligatorio.

---

## 10. Identidad operacional

Identidad lógica:

```text
Tenant DB
+ company_id
+ farm_id
+ milking_date
+ shift_code
```

Solo una sesión activa/no cancelada puede ocupar esa identidad.

PostgreSQL debe protegerlo mediante un índice/constraint equivalente a:

```sql
UNIQUE(company_id, farm_id, milking_date, shift_code)
WHERE status <> 'CANCELLED'
```

Reglas:

- DRAFT ocupa identidad.
- DONE ocupa identidad.
- CANCELLED libera identidad.
- mismo Date/Shift en Farms diferentes es válido.

---

## 11. Cantidades

Cloud utiliza:

```text
PostgreSQL NUMERIC
Python Decimal
Android BigDecimal
```

Quedan prohibidos `FLOAT`, `DOUBLE` y `REAL` para cantidades de Milking.

O-4 no congela arbitrariamente un scale fijo `NUMERIC(p,s)` sin requerimiento funcional.

---

## 12. Invariantes GENERAL

1. `general_gross_quantity > 0` cuando se informa.
2. `animals_milked_count >= 0` si no es null.
3. `used_on_farm_quantity >= 0`.
4. `discarded_quantity >= 0`.
5. `used + discarded <= authoritative gross`.
6. `net = authoritative gross - used - discarded`.
7. DRAFT no materializa total autoritativo.
8. DONE exige total GENERAL autoritativo.
9. DONE exige use/discard explícitos.
10. CANCELLED exige motivo.
11. Notes: null o máximo 500 caracteres.
12. `version` inicia en 1 y crece monotónicamente en mutaciones funcionales.

---

## 13. MilkingOutput

Modelo conceptual:

```text
id                       UUID PK
company_id               UUID
milking_session_id       UUID
farm_id                  UUID
product_id               UUID
quantity                 NUMERIC
uom_id                    UUID
production_date           DATE
created_at                TIMESTAMPTZ
created_by                UUID
```

Constraint:

```text
UNIQUE(milking_session_id)
```

Cardinalidad:

```text
MilkingSession 1 -> 0..1 MilkingOutput
```

Reglas:

- CONFIRM con `net > 0` crea exactamente un Output.
- CONFIRM con `net = 0` no crea Output.
- Output no es stock.
- Output referencia Farm/producto/UoM snapshotteados.

---

## 14. Annulment

### DONE sin Output

Solicitud de anulación puede aplicar transición inmediata a `CANCELLED`.

### DONE con Output

No se elimina ni corrige silenciosamente el Output. Se crea `milking_annulment_requests` con estado `PENDING`.

Modelo conceptual:

```text
id                       UUID PK
company_id               UUID
milking_session_id       UUID
reason                   TEXT
requested_by             UUID
client_occurred_at       TIMESTAMPTZ
recorded_at              TIMESTAMPTZ
state                    VARCHAR
```

Máximo una solicitud `PENDING` por sesión.

La compensación downstream completa de una anulación con Output queda fuera de O-4.

---

## 15. Actor, operator y timestamps

### actor

`actor_user_id` se deriva exclusivamente de `AuthenticatedPrincipal` P-3. El servidor nunca confía en `actorId` enviado libremente por Android.

### localEmployeeId

No existe en Cloud.

### operator_id

Permanece como referencia de negocio opcional, distinta del actor:

```text
actor = quien ejecutó el comando
operator = quien realizó físicamente el ordeño
```

### timestamps

Se distinguen:

```text
client_occurred_at
server recorded/committed_at
```

`clientOccurredAt` se conserva como evidencia del momento declarado por el cliente y no sustituye el timestamp de commit servidor.

---

## 16. P-3 Authorization

Tenant/Company provienen del principal y de los contextos P-3.

El cliente no puede elevar autoridad enviando `tenant_id`, `company_id` o `actor_id` que contradigan el contexto autenticado.

Capabilities mínimas:

```text
milking.session.create
milking.session.update_draft
milking.session.confirm
milking.session.cancel
milking.session.read
milking.config.read
milking.config.manage
milking.output_profile.read
milking.output_profile.manage
```

O-4 no introduce `FARM` como scope Core.

---

## 17. P-4 Command Integrity

Todos los comandos mutantes O-4 usan P-4.

P-4 gobierna:

- `command_id`;
- command name/schema version;
- fingerprint;
- replay;
- idempotency conflict;
- transaction boundary;
- optimistic concurrency primitives;
- technical audit.

O-4 no crea infraestructura paralela.

El payload normalizado del módulo participa en el fingerprint P-4.

Reautorización P-3 se ejecuta antes de procesamiento nuevo o replay.

---

## 18. Optimistic concurrency

Mutaciones sobre sesión requieren `expected_version`.

Si `current_version != expected_version`, el resultado es conflicto explícito (`CONCURRENCY_CONFLICT` / `VERSION_CONFLICT`) sin last-write-wins ni retry automático de negocio.

CREATE no requiere `expected_version`.

Administración de configuración/profile debe mantener conflicto explícito ante concurrencia.

---

## 19. Atomicidad

Cada comando mutante se ejecuta dentro de una única transacción PostgreSQL del Tenant.

Ejemplo CONFIRM:

```text
BEGIN
  P-4 idempotency identity/fingerprint
  validar sesión
  CAS expectedVersion
  calcular net
  UPDATE session -> DONE
  INSERT Output si net > 0
  INSERT business audit
  persistir replay result P-4
COMMIT
```

Ante fallo no se confirma mutación de negocio, Output, business audit ni ejecución P-4 confirmada.

---

## 20. Business audit

P-4 audit técnico no sustituye business audit Milking.

Tabla:

```text
milking_audit_events
```

Campos conceptuales:

```text
id
company_id
session_id
command_id
event_type
version_before
version_after
actor_user_id
client_occurred_at
recorded_at
change_payload JSONB
```

Características:

- append-only;
- sin secretos/tokens;
- no reescribe eventos previos;
- registra mutaciones funcionales relevantes.

---

## 21. Administración mínima incluida

O-4 incluye API administrativa mínima para:

### OutputProfile
- crear perfil/version inicial;
- crear nueva versión;
- consultar perfiles/versiones;
- activar/desactivar según reglas;
- no editar destructivamente una versión histórica publicada.

### MilkingConfiguration
- crear configuración Company+Farm+Shift;
- consultar configuraciones;
- cambiar OutputProfileVersion;
- activar/desactivar;
- conflicto explícito ante concurrencia.

O-4 no incluye UI Web administrativa.

---

## 22. API HTTP específica

### Operación

```text
POST   /milking/sessions
PATCH  /milking/sessions/{session_id}/general
PATCH  /milking/sessions/{session_id}/notes
PATCH  /milking/sessions/{session_id}/use-discard
POST   /milking/sessions/{session_id}/confirm
POST   /milking/sessions/{session_id}/cancel
POST   /milking/sessions/{session_id}/annulment-requests
```

### Consulta

```text
GET    /milking/sessions
GET    /milking/sessions/{session_id}
GET    /milking/outputs
GET    /milking/outputs/{output_id}
```

### Administración mínima

```text
GET    /milking/output-profiles
POST   /milking/output-profiles
POST   /milking/output-profiles/{profile_id}/versions
PATCH  /milking/output-profiles/{profile_id}/versions/{version}
GET    /milking/configurations
POST   /milking/configurations
PATCH  /milking/configurations/{configuration_id}
```

No se implementa endpoint genérico `/commands`.

---

## 23. Payload de comandos

Los mutantes reciben `command_id` estable.

Mutaciones sobre recursos versionados reciben `expected_version`.

Se conserva `client_occurred_at` y `client_instance_id` cuando sea útil para trazabilidad/sync futuro.

El cliente no envía como autoridad actor global, Tenant autorizado ni Company autorizada fuera del mecanismo P-3.

---

## 24. Respuestas y errores

Resultado mínimo de comando Milking:

```text
session_id
version
status
output_id nullable
replayed
```

Errores funcionales mínimos:

```text
RESOURCE_NOT_AVAILABLE
ACCESS_DENIED
VALIDATION_FAILED
ALREADY_EXISTS
STATE_CONFLICT
VERSION_CONFLICT / CONCURRENCY_CONFLICT
IDEMPOTENCY_CONFLICT
BUSINESS_CONFLICT
TEMPORARY_UNAVAILABLE
```

La API debe preservar fail-closed y no filtrar existencia de recursos de otra Company/Tenant.

---

## 25. Queries

Las consultas siempre se ejecutan dentro del Tenant DB y Company autorizada.

Filtros mínimos:

```text
farm_id
status
date_from
date_to
shift_code
```

No existe filtro Site/OperationalUnit.

La paginación debe ser determinista y acotada.

---

## 26. Alembic

O-4 agrega migración Tenant posterior a P-4.

Debe:

- crear solo estructuras funcionales Milking;
- no modificar Platform Identity DB;
- no duplicar `companies`;
- no crear Site/OU;
- no crear Farm/Product/UoM maestros;
- preservar forward migration desde el head Tenant vigente;
- verificarse en al menos dos Tenant DB físicas.

---

## 27. Concurrencia obligatoria

Pruebas PostgreSQL reales deben cubrir como mínimo:

1. dos CREATE concurrentes misma Company+Farm+Date+Shift -> máximo un ganador;
2. CREATE en Farms distintas mismo Date+Shift -> ambos válidos;
3. mismo `command_id` concurrente -> máximo un efecto;
4. mismo `command_id` + payload diferente -> conflict;
5. dos updates mismo expectedVersion -> máximo uno confirma;
6. CONFIRM concurrente -> máximo un DONE y 0..1 Output;
7. replay CONFIRM -> no duplica Output ni audit funcional;
8. cancel/confirm carrera -> una transición válida y conflicto explícito para la otra;
9. aislamiento entre Companies;
10. aislamiento entre Tenant DB.

---

## 28. Pruebas obligatorias

### Unit
- invariantes Milking;
- Decimal;
- net calculation;
- state guards;
- OutputProfile versioning;
- configuration resolution;
- command payload normalization;
- error mapping.

### Integration PostgreSQL real
- CRUD funcional;
- partial uniqueness;
- FK internas;
- Output 0..1;
- annulment;
- audit append-only;
- P-4 integration;
- P-3 authorization context;
- CAS;
- rollback.

### API
- auth required;
- Company isolation;
- capabilities;
- endpoint request/response;
- replay;
- conflicts;
- read filters/pagination.

### Migration/build/runtime
- head P-4 -> O-4;
- al menos dos Tenant DB;
- pytest completo;
- compile/import;
- Docker build/run;
- health/live/ready.

---

## 29. Outbox / Sync

Cloud Outbox no se implementa en O-4.

O-5 implementará Android↔Cloud sync, push/pull, checkpoints/cursors, mapping Android `organizationId` -> Tenant, conflicto offline/cloud e Inbox/Outbox si el contrato lo exige.

O-4 no mezcla business lifecycle con sync lifecycle.

---

## 30. Exclusiones O-4

Fuera del alcance:

- INDIVIDUAL;
- GROUP;
- test-day;
- animales/grupos;
- Livestock backend completo;
- Purchase;
- Milk Logistics;
- Reception;
- Quality;
- Inventory posting;
- Warehouse/Location;
- Manufacturing;
- Web UI;
- sync Android;
- Outbox/Inbox cloud;
- production deployment;
- monitoring/operations avanzadas;
- P-5/P-6 Platform salvo capacidades ya disponibles y estrictamente necesarias.

---

## 31. Invariantes de no duplicación

1. Tenant/Company no se duplican.
2. Farm no se duplica.
3. Product/UoM no se duplican.
4. P-4 command execution no se duplica.
5. Technical audit P-4 no se duplica.
6. `MilkingOutput` no se convierte en Inventory stock.
7. compra de leche no se convierte en Milking.
8. Site/OU no se reintroducen.
9. `Organization` cloud no se crea por simetría Android.
10. referencias externas no se transforman en maestros sombra.

---

## 32. Gobierno Git

Base autorizada:

```text
8cdd0ee47db9569ca6fcec4530f3c3dffb9390ed
```

Rama exclusiva:

```text
feat/milking-o4-backend-cloud-general
```

Reglas:

- Draft PR contra `main`;
- commits pequeños y temáticos;
- push solo a la rama O-4;
- sin push directo a `main`;
- sin force push;
- sin merge/tag/rebase destructivo;
- O-5 no se inicia sin autorización expresa.

---

## 33. Gate de cierre

O-4 solo podrá recomendarse para cierre con:

- diff real revisado;
- tests focales;
- PostgreSQL real;
- concurrencia/stress;
- migration forward;
- suite completa;
- API tests;
- Docker build/run;
- logs/resultados primarios;
- `git diff --check`;
- working tree limpio;
- verificación independiente;
- contraste final contrato + código + diff + evidencias.

Solo el usuario puede autorizar el cierre. El cierre no autoriza automáticamente merge ni O-5.

---

## 34. Regla final congelada

> O-4 implementa la autoridad cloud del ordeño propio GENERAL/TOTAL sobre `Tenant + Company + Farm`, con persistencia PostgreSQL, API específica, administración mínima de `OutputProfile` y `MilkingConfiguration`, integridad de comandos P-4 y autorización P-3, sin duplicar maestros ni reintroducir Site/OperationalUnit. O-5 queda reservado para sincronización Android↔Cloud.
