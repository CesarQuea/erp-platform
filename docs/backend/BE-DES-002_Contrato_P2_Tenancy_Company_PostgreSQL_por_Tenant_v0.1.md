# BE-DES-002 — Contrato de Implementación P-2 Tenancy, Company y PostgreSQL por Tenant

**Versión:** 0.1  
**Estado:** CONGELADO PARA IMPLEMENTACIÓN P-2  
**Fecha:** 2026-08-22  
**Repositorio:** `CesarQuea/erp-platform`  
**Base autorizada:** `7e38e022481fdef18011064c5ba2f80d16c92c16`  
**Rama:** `feat/platform-p2-tenancy-company-db`

---

## 1. Objetivo

Implementar la frontera técnica multi-Tenant y la base multiempresa de ERP Platform sobre PostgreSQL, de forma general y reusable por todos los módulos.

P-2 debe demostrar en código y pruebas que:

1. cada `Tenant` dispone de un datasource PostgreSQL físicamente independiente;
2. el backend resuelve el datasource únicamente desde un contexto Tenant autorizado/proporcionado por la plataforma;
3. una conexión destinada a Tenant A nunca opera sobre Tenant B;
4. dentro de cada Tenant pueden existir una o varias `Company`;
5. la separación multiempresa queda preparada mediante `company_id` y ownership explícito;
6. las migraciones se ejecutan por Tenant;
7. las transacciones SQLAlchemy quedan encapsuladas detrás de las abstracciones de Core creadas en P-1.

P-2 no implementa todavía autenticación, memberships, RBAC, sync ni módulos de negocio.

---

## 2. Decisiones arquitectónicas congeladas para P-2

### 2.1 Tenant

`Tenant` es exclusivamente una frontera técnica de plataforma:

- aislamiento de datos;
- datasource;
- provisioning;
- migration lifecycle;
- backup/restore futuro;
- configuración técnica.

No representa necesariamente una empresa legal.

### 2.2 Company

`Company` representa una entidad empresarial/legal contenida dentro de un Tenant.

```text
Tenant
├── Company A
└── Company B
```

### 2.3 Organization

P-2 **no crea `Organization` como entidad obligatoria**.

### 2.4 Base de datos por Tenant

Cada Tenant utiliza una base PostgreSQL físicamente independiente.

```text
Tenant A → PostgreSQL Database A
Tenant B → PostgreSQL Database B
```

No se implementa shared-schema multi-tenancy.

### 2.5 Nomenclatura

Los identificadores técnicos nuevos utilizarán inglés:

```text
tenant_id
company_id
tenant_context
tenant_registry
data_source
company_repository
```

La documentación y mensajes humanos permanecen en español/localizable.

---

## 3. Compatibilidad con `organizationId`

Los contratos Android V2 existentes no se modifican en P-2.

P-2 utilizará internamente:

```text
tenant_id
```

y no creará una segunda entidad `Organization`.

La compatibilidad conceptual permanece:

```text
organizationId V2
      ↕
tenant_id cloud
```

La traducción contractual definitiva queda fuera de P-2 y requerirá el corte de integración correspondiente.

No se modifica Android, Room, Inventory V2 ni Milking V2.

---

## 4. Componentes de plataforma

P-2 incorporará, como mínimo, responsabilidades equivalentes a:

```text
app/
├── platform/
│   ├── tenancy/
│   │   ├── context
│   │   ├── registry
│   │   └── resolver
│   └── company/
│       ├── model
│       ├── repository
│       └── service
│
└── infrastructure/
    └── database/
        ├── engines
        ├── sessions
        ├── transactions
        └── migrations
```

Los nombres físicos definitivos podrán ajustarse durante implementación si preservan estas fronteras. No se crean carpetas vacías sin responsabilidad real.

---

## 5. TenantContext

Debe existir una representación explícita del Tenant activo.

Conceptualmente:

```text
TenantContext
└── tenant_id
```

Reglas:

1. no existe Tenant implícito global;
2. no se usa un Tenant por defecto silencioso;
3. ausencia de Tenant requerido → fail closed;
4. el contexto no contiene DSN ni credenciales;
5. el contexto no se deriva todavía de headers públicos sin autenticación.

P-3 será responsable de enlazar identidad autenticada con Tenant/Company autorizados.

---

## 6. Tenant Registry

P-2 debe definir un port/interfaz `TenantRegistry` capaz de resolver metadata técnica del Tenant.

Conceptualmente:

```text
TenantRegistry
tenant_id
    ↓
TenantConnectionConfig
```

El contrato debe impedir que módulos de negocio conozcan DSN o secretos.

### 6.1 Implementación inicial

P-2 puede utilizar una implementación basada en configuración segura/environment para desarrollo y test, siempre detrás del `TenantRegistry`.

No se hardcodean reglas como:

```text
if tenant_id == "aliosur":
    database_url = ...
```

### 6.2 Control Plane

Una base/control plane persistente completa queda diferida. P-2 solo debe mantener la interfaz suficientemente estable para sustituir en el futuro la implementación de configuración por un Control Plane real sin cambiar módulos de negocio.

---

## 7. TenantDataSourceResolver

Debe existir una única responsabilidad central para resolver/acceder al datasource del Tenant.

Flujo:

```text
TenantContext
      ↓
TenantRegistry
      ↓
TenantDataSourceResolver
      ↓
Engine / Session del Tenant
```

Reglas:

1. los módulos no crean engines directamente;
2. no construyen URLs PostgreSQL;
3. no seleccionan bases mediante condicionales;
4. no reutilizan una Session entre Tenants;
5. no existe fallback automático hacia otra base;
6. Tenant desconocido/inactivo/configuración inválida → fail closed.

---

## 8. Verificación de identidad física de la base

Cada base Tenant deberá contener metadata mínima que permita comprobar a qué Tenant pertenece físicamente.

Se propone una tabla técnica equivalente a:

```text
platform_tenant_metadata
```

con al menos:

```text
tenant_id
schema_version / migration metadata cuando corresponda
```

Invariante crítica:

> Resolver Tenant A hacia una base cuya metadata declara Tenant B debe fallar antes de ejecutar una operación funcional.

Esto protege frente a errores de configuración del registry. La forma exacta de la tabla se congelará con la migración P-2.

---

## 9. Company

P-2 implementará un modelo mínimo y neutral `Company`.

Campos mínimos propuestos:

```text
id
code
legal_name
is_active
created_at
updated_at
```

Reglas:

- `id` estable UUID;
- `code` único dentro de la base Tenant;
- `legal_name` es contenido humano, no identificador técnico;
- no existe lógica sectorial;
- no se modelan contabilidad, impuestos o localización fiscal todavía.

### 9.1 `tenant_id` dentro de Company

Dado que la base PostgreSQL ya constituye la frontera física Tenant, P-2 **no duplicará automáticamente `tenant_id` en todas las tablas**.

La identidad del Tenant se obtiene del datasource + `TenantContext` + metadata física de la base.

Esta decisión evita divergencias entre `database tenant` y `row tenant_id`. Si un recurso futuro requiere `tenant_id` explícito por contrato, deberá justificarlo.

---

## 10. Ownership Scope Foundation

P-2 introducirá la base conceptual para declarar ownership de datos.

Scopes de referencia:

```text
PLATFORM
TENANT
COMPANY
OPERATIONAL
RESOURCE_SPECIFIC
```

No implica que todos los modelos implementen todos los scopes.

Regla:

> Cada recurso de negocio futuro deberá declarar explícitamente su ownership; no se presume `company_id` obligatorio ni compartición global.

P-2 solo implementará lo mínimo necesario para Company y pruebas de aislamiento.

---

## 11. SQLAlchemy

P-2 incorporará SQLAlchemy como implementación de infraestructura manteniendo Core desacoplado.

Reglas:

1. Application/Domain no recibe `Session` como contrato público;
2. `TransactionBoundary` de P-1 continúa siendo abstracción Core;
3. infraestructura puede implementar un `SqlAlchemyTransactionBoundary`/UnitOfWork equivalente;
4. cada transacción pertenece a un solo Tenant;
5. no se permite una transacción que abarque dos bases Tenant en P-2;
6. rollback debe cerrar completamente la transacción del Tenant afectado.

---

## 12. Pools y lifecycle

El resolver puede mantener engines/pools por Tenant.

Debe:

- identificarlos por `tenant_id`;
- reutilizar solo dentro del mismo Tenant;
- permitir `dispose`;
- evitar crear pools ilimitados sin control;
- no exponer credenciales en logs;
- limpiar recursos en shutdown.

La política final de escalado/pooling dinámico puede evolucionar en Cloud Operations.

---

## 13. Alembic y migraciones por Tenant

P-2 introduce Alembic como autoridad de schema.

Reglas:

1. prohibido `Base.metadata.create_all()` como mecanismo normal de producción;
2. cada Tenant mantiene su propio `alembic_version`;
3. una migración debe poder aplicarse a un Tenant específico;
4. el estado de migración debe poder consultarse;
5. fallo en Tenant A no debe provocar escritura automática sobre Tenant B;
6. no se ejecutan destructive migrations silenciosas;
7. las migraciones deben ser reproducibles desde base limpia.

Migración inicial P-2:

```text
platform_tenant_metadata
companies
```

y las estructuras estrictamente necesarias de soporte.

---

## 14. Provisioning mínimo

P-2 podrá incluir un servicio/script interno para preparar una base Tenant nueva:

```text
create empty database (fuera o mediante herramienta controlada)
      ↓
run Alembic
      ↓
write/validate tenant metadata
      ↓
optional initial Company
```

No se implementa todavía un panel Web de provisioning.

El provisioning debe ser idempotente o fallar de manera segura cuando detecta un estado incompatible.

---

## 15. API HTTP

P-2 **no debe aceptar un `X-Tenant-ID` público como autoridad de seguridad**.

Sin P-3 no existe todavía una identidad autenticada que pueda autorizar selección de Tenant.

Por tanto:

- no se expone un selector público inseguro de Tenant;
- las pruebas de P-2 se realizan en servicios/repositorios/integración;
- cualquier endpoint técnico temporal requerirá justificación expresa y no podrá considerarse autoridad futura.

Los endpoints P-1 `/live`, `/ready` y `/health` deben continuar funcionando y no romperse.

---

## 16. Seguridad e aislamiento

### 16.1 Cross-Tenant

Prueba obligatoria con dos bases físicas distintas:

```text
Tenant A → DB A
Tenant B → DB B
```

Debe demostrarse:

- escritura Company A solo aparece en DB A;
- escritura Company B solo aparece en DB B;
- lectura Tenant A nunca devuelve datos de DB B;
- resolver con metadata cruzada falla;
- UUID conocido de otro Tenant no permite acceder a su base.

### 16.2 Cross-Company

Dentro de una misma DB Tenant deben existir al menos dos Companies en pruebas.

P-2 debe demostrar que los repositories/services que requieran company scope reciben `company_id` explícito.

La autorización de usuarios por Company pertenece a P-3.

---

## 17. Atomicidad

Cada caso de uso mutante P-2 debe ser transaccional dentro de una sola base Tenant.

Ejemplo `register_company()`:

```text
BEGIN
validate
write
COMMIT
```

o ante error:

```text
ROLLBACK
```

No deben quedar escrituras parciales.

---

## 18. Idempotencia y concurrencia

La infraestructura general de command idempotency y optimistic locking pertenece a P-4.

P-2 no debe introducir una implementación provisional incompatible.

Sin embargo:

- constraints de unicidad de Company deben proteger integridad;
- errores de constraint deben mapearse de forma controlada;
- no se utilizará `last-write-wins` como política futura.

---

## 19. Auditoría

La auditoría completa pertenece a P-4.

P-2 puede registrar logs técnicos mínimos de tenant resolution, migration, provisioning y datasource lifecycle, sin incluir passwords, DSN completos ni secretos.

---

## 20. Configuración y secretos

Credenciales de bases Tenant:

- fuera de Git;
- fuera de código;
- no devueltas por API;
- no impresas completas en logs.

`.env.example` puede contener placeholders.

La implementación inicial de registry por environment es temporal y sustituible.

---

## 21. Pruebas obligatorias

### 21.1 Unit

- `TenantContext`;
- registry;
- resolver;
- ownership primitives;
- Company validation.

### 21.2 Integration — PostgreSQL real

Con dos PostgreSQL/databases independientes:

```text
tenant-a-db
tenant-b-db
```

Verificar resolución, creación de sessions, transacciones, Company repository y aislamiento.

### 21.3 Migration

Desde bases vacías:

- `alembic upgrade head`;
- schema esperado;
- `alembic_version`;
- metadata Tenant;
- repetibilidad;
- segunda base independiente.

### 21.4 Isolation / Negative

Obligatorio:

- unknown Tenant;
- inactive/missing config;
- metadata Tenant mismatch;
- Company ID inexistente;
- misma UUID textual usada en contexto incorrecto;
- intento de reutilizar Session/transaction entre Tenants.

### 21.5 Transaction

- commit correcto;
- rollback ante error;
- constraint violation sin escritura parcial.

### 21.6 Regression P-1

Mantener verdes tests P-1, `/live`, `/ready`, `/health`, error safety y Docker build.

---

## 22. Evidencias obligatorias de cierre

El agente independiente deberá aportar HEAD/base exactos, diff real, `git diff --check`, suite pytest + XML JUnit, PostgreSQL real con dos Tenants, schema/migrations de ambas bases, consultas que demuestren aislamiento, prueba de metadata mismatch, prueba cross-Company, rollback, Docker build/run, secret scan, scope scan y working tree limpio.

No se acepta solo un resumen textual.

---

## 23. Exclusiones expresas

P-2 NO implementa Milking, Inventory, Manufacturing, Sales, Livestock, lógica Dairy, Identity, Authentication, Membership, Authorization/RBAC, permisos por usuario, JWT/OAuth, idempotency store, optimistic locking general, Outbox/Inbox, sync móvil, Module Registry, ImplementationProfile, Web UI, billing, backup/restore productivo, cloud provider, control plane persistente completo, traducción definitiva `organizationId → tenantId`, intercompany ni consolidación contable.

---

## 24. Invariantes no negociables

1. Ningún módulo conoce DSN.
2. Ningún Tenant comparte base física con otro.
3. Ninguna Session cruza Tenant.
4. No existe fallback de Tenant.
5. Metadata física de DB debe coincidir con Tenant solicitado.
6. Company vive dentro de la frontera Tenant.
7. `Organization` no se crea como nivel obligatorio.
8. No se replica `tenant_id` indiscriminadamente en todas las tablas.
9. Alembic gobierna el schema.
10. No `create_all()` productivo.
11. No lógica Aliosur/Dairy.
12. No cambios Android.
13. No autoridad de Tenant basada solo en header público.
14. P-1 no se rompe.
15. Cualquier cambio fuera de este contrato requiere autorización.

---

## 25. Secuencia Git

Base autorizada:

```text
7e38e022481fdef18011064c5ba2f80d16c92c16
```

Rama:

```text
feat/platform-p2-tenancy-company-db
```

Reglas:

1. implementar exclusivamente P-2;
2. commits pequeños;
3. push solo a esta rama;
4. sin merge/tag/force push/rebase destructivo;
5. no iniciar P-3 sin cierre expreso.

---

## 26. Gate de cierre

> **P-2 será cerrable cuando ERP Platform demuestre con PostgreSQL real que puede resolver de forma fail-closed dos Tenants hacia dos bases físicas independientes, verificar la identidad física de cada base, ejecutar migraciones Alembic por Tenant, operar Companies dentro de cada Tenant mediante transacciones aisladas, preservar P-1 y superar pruebas negativas cross-Tenant/cross-Company sin exponer secretos ni introducir autenticación o lógica sectorial prematuramente.**
