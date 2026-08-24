# BE-ADR-001 — Adenda arquitectónica: `Site` / `OperationalUnit`

**Versión:** 1.0  
**Estado:** APROBADA PARA REGISTRO DOCUMENTAL  
**Fecha:** 2026-08-23  
**Repositorio:** `CesarQuea/erp-platform`  
**Base documental:** `main` @ `2fdcc900996ad8e0dea028b3d4b32f68af187bcc`  
**Rama documental:** `docs/platform-adr-site-operationalunit`

---

## 1. Objeto

Formalizar la decisión arquitectónica transversal relativa a los conceptos `Site` y `OperationalUnit` después del cierre y merge de P-3.

Esta adenda **no reabre, modifica ni invalida P-1, P-2 o P-3**. Su función es evitar que los cortes posteriores introduzcan `Site` / `OperationalUnit` como niveles universales u obligatorios del Core de ERP Platform sin una necesidad funcional concreta y un contrato específico.

La decisión nace de la revisión práctica del nuevo desarrollo de Milking, donde `OperationalUnit` fue introducido como nivel intermedio y comenzó a generar complejidad para la puesta en operación sin aportar una autoridad de dominio claramente diferenciada.

---

## 2. Contexto cerrado que se preserva

ERP Platform mantiene como jerarquía transversal de plataforma:

```text
Tenant
  └── Company
```

P-2 conserva:

- `Tenant` como frontera técnica;
- PostgreSQL físico independiente por Tenant;
- `Company` dentro del Tenant;
- `TenantContext`;
- `TenantRegistry`;
- `TenantDataSourceResolver`;
- `platform_tenant_metadata`;
- ausencia de `tenant_id` redundante en `companies`;
- `Organization` no obligatorio;
- aislamiento fail-closed y sin fallback cross-Tenant.

P-3 conserva:

- identidad global;
- `TenantMembership`;
- `CompanyAccess`;
- `AuthenticatedPrincipal`;
- RBAC con scopes `PLATFORM`, `TENANT` y `COMPANY`;
- selección y revalidación explícita de Tenant + Company;
- ningún UUID/header como autoridad suficiente;
- ninguna dependencia de `Site` / `OperationalUnit` para autenticación o resolución de datasource.

---

## 3. Decisión arquitectónica

### 3.1. `Site` NO es un nivel transversal obligatorio del Core

ERP Platform **no impondrá** una jerarquía universal del tipo:

```text
Tenant
  └── Company
      └── Site
          └── ...
```

`Site` no forma parte obligatoria de:

- `TenantContext`;
- `AuthenticatedPrincipal`;
- `CompanyAccess`;
- Tenant resolution;
- selección de PostgreSQL;
- RBAC transversal;
- ownership general de los módulos;
- contrato mínimo que todo módulo de negocio deba implementar.

### 3.2. `OperationalUnit` NO es un nivel transversal obligatorio del Core

ERP Platform **no impondrá** una jerarquía universal del tipo:

```text
Company
  └── Site
      └── OperationalUnit
          └── Farm / Warehouse / POS / Milking / Processing / ...
```

`OperationalUnit` no se utilizará como wrapper genérico obligatorio para recursos que ya tienen significado funcional propio.

No será, por defecto:

- scope RBAC global;
- contexto obligatorio de sesión;
- clave de routing Tenant;
- autoridad de Company;
- requisito para crear operaciones de Milking, Inventory, Sales, Livestock o Manufacturing.

---

## 4. Regla de modelado por dominio

Después de `Tenant` + `Company`, cada módulo deberá utilizar la entidad que represente una necesidad real de su dominio.

Modelo de referencia:

```text
Tenant
  └── Company
      ├── Livestock
      │   └── Farm
      │
      ├── Milking
      │   └── referencia Farm cuando corresponda
      │
      ├── Inventory
      │   └── Warehouse
      │       └── Location
      │
      ├── Sales
      │   └── PointOfSale
      │
      └── Manufacturing
          └── recursos definidos por su propio contrato
```

La regla es:

> **No crear un nivel intermedio genérico si la entidad específica del dominio ya expresa correctamente identidad, ownership, operación y trazabilidad.**

---

## 5. Milking / Ordeño

La nueva versión de Milking se desarrolla en paralelo a la versión legacy y fue la que introdujo `OperationalUnit`.

Esta adenda establece para la revisión de esa nueva versión:

1. `OperationalUnit` no debe mantenerse únicamente por coherencia con una abstracción Core, porque esa abstracción deja de ser requisito transversal.
2. El contrato de Milking debe revisar si `Farm` constituye el contexto funcional suficiente para el registro de sesiones de ordeño.
3. La dirección conceptual preferida, sujeta al contrato propio del módulo, es:

```text
Tenant
  └── Company
      └── Farm
          └── MilkingSession
              └── MilkLot
```

4. Milking no debe implementar login, Membership, CompanyAccess ni Tenant resolver propios; debe consumir P-2/P-3.
5. La versión legacy de Milking no debe eliminarse hasta que la nueva versión haya sido completada, migrada cuando corresponda y validada mediante su propio corte.

Esta adenda **no modifica por sí sola código Android ni código Milking**.

---

## 6. Inventory, Sales y otros módulos

La ausencia de `Site` / `OperationalUnit` transversal no elimina conceptos físicos reales.

Ejemplos:

- Inventory conserva `Warehouse` y `Location` cuando sean funcionalmente necesarios.
- Sales puede conservar/crear `PointOfSale` conforme a su contrato.
- Livestock conserva `Farm` como entidad propia del dominio.
- Manufacturing podrá definir `Plant`, `WorkCenter`, `Facility` u otras entidades si existe una necesidad real aprobada.

Ninguna de estas entidades necesita ser encapsulada obligatoriamente por `OperationalUnit`.

---

## 7. Posible necesidad futura de `Site`, `Branch` o `Facility`

Esta decisión **no prohíbe para siempre** modelar una sede, sucursal, instalación o facility.

Un concepto futuro como:

- `Branch`;
- `Facility`;
- `Plant`;
- `Site`;
- otro equivalente;

podrá introducirse si existe una necesidad funcional concreta, por ejemplo:

- fiscalidad o establecimiento legal;
- contabilidad separada;
- permisos propios;
- reporting regulatorio;
- operación física diferenciada;
- planificación de recursos;
- mantenimiento;
- logística;
- restricciones geográficas.

Su incorporación deberá realizarse mediante un contrato/corte específico que defina:

- semántica;
- ownership;
- cardinalidad;
- relación con `Company`;
- relación con módulos;
- autorización;
- persistencia;
- migraciones;
- sincronización;
- pruebas.

No se introducirá por anticipación o “por si acaso”.

---

## 8. Impacto en seguridad y autorización

Los scopes transversales P-3 continúan siendo:

```text
PLATFORM
TENANT
COMPANY
```

Esta adenda NO crea:

```text
SITE
OPERATIONAL_UNIT
```

como scopes RBAC globales.

Si un módulo futuro necesita una restricción más fina que `COMPANY`, deberá definirla en su propio contrato sin alterar silenciosamente el motor global de autorización.

Ejemplo:

- un operador de Milking limitado a determinadas Farms;
- un usuario de Inventory limitado a ciertos Warehouses;
- un vendedor limitado a determinados PointsOfSale.

Esas restricciones deben modelarse como autorización funcional del módulo o mediante una extensión transversal futura expresamente aprobada; no mediante la reintroducción automática de `OperationalUnit`.

---

## 9. Impacto en persistencia y migraciones

Para ERP Platform actual:

- no existe tabla Core `sites` derivada de P-1/P-2/P-3;
- no existe tabla Core `operational_units` derivada de P-1/P-2/P-3;
- no existe migración PostgreSQL que deba revertirse por esta decisión;
- no existe modificación de Platform Alembic;
- no existe modificación de Tenant Alembic;
- no existe cambio en `companies`;
- no existe cambio en `TenantDataSourceResolver`.

Por tanto, esta adenda es **documental/arquitectónica** en ERP Platform.

Cualquier retiro físico de entidades homónimas ya existentes en Android o en la nueva implementación de Milking pertenece al corte correspondiente de esos componentes y no se ejecuta mediante esta adenda.

---

## 10. Invariantes congeladas por esta adenda

Quedan congeladas para los siguientes cortes:

1. La jerarquía transversal mínima de ERP Platform permanece `Tenant -> Company`.
2. `Site` no es un nivel obligatorio del Core.
3. `OperationalUnit` no es un nivel obligatorio del Core.
4. `Site` / `OperationalUnit` no participan en Tenant resolution.
5. `Site` / `OperationalUnit` no son parte obligatoria de `AuthenticatedPrincipal`.
6. `Site` / `OperationalUnit` no son scopes RBAC globales de P-3.
7. Los módulos deben preferir entidades de dominio con semántica propia (`Farm`, `Warehouse`, `PointOfSale`, etc.).
8. No se creará un wrapper genérico para un recurso de dominio sin una necesidad funcional demostrable.
9. Una futura `Branch` / `Facility` / `Site` requiere contrato específico; no se introduce preventivamente.
10. Esta decisión no autoriza eliminar la versión legacy de Milking.
11. Esta decisión no autoriza cambios Android, DB o API por sí sola.
12. Esta decisión no modifica P-1, P-2 o P-3 ya cerrados.

---

## 11. Exclusiones

Fuera del alcance de esta adenda:

- refactor de Android;
- eliminación de `SiteEntity` legacy;
- eliminación de `OperatingUnitEntity` / `ProductionUnitEntity` legacy;
- migraciones Room;
- migraciones de datos Milking;
- cambio de API Milking;
- eliminación de versión legacy de Ordeño;
- diseño de Farm master definitivo;
- restricciones por Farm/Warehouse/POS;
- Branch/Facility future model;
- P-4;
- sync Android ↔ Cloud.

Cada uno requiere su propio análisis/corte cuando corresponda.

---

## 12. Consecuencias positivas esperadas

- reduce jerarquía artificial;
- simplifica onboarding de módulos;
- evita duplicar conceptos de dominio;
- alinea Android/Cloud con `Tenant + Company` de P-2/P-3;
- reduce acoplamiento de autorización;
- facilita reutilización del Core en otros sectores;
- evita que una abstracción nacida de un módulo sectorial se convierta en requisito global;
- permite que cada módulo mantenga ownership y semántica claros.

---

## 13. Riesgos y controles

### Riesgo A — módulos necesiten segmentación sub-Company

Control:
no reintroducir `OperationalUnit` automáticamente; congelar primero la necesidad concreta y definir la entidad/scope apropiado.

### Riesgo B — conceptos físicos repetidos entre módulos

Control:
evaluar caso por caso si existe una entidad compartida real (`Facility`, por ejemplo) antes de crearla.

### Riesgo C — compatibilidad con Android legacy

Control:
no borrar entidades/tablas legacy de forma transversal; efectuar impact scan y migración únicamente en cortes autorizados.

### Riesgo D — Milking nuevo ya depende de `OperationalUnit`

Control:
rediseñar únicamente la nueva versión en su propio corte, manteniendo legacy operativa hasta validación.

---

## 14. Relación con documentos cerrados

Esta adenda complementa y debe interpretarse en coherencia con:

- `BE-CLOSE-002_Cierre_P2_Tenancy_Company_PostgreSQL_por_Tenant_v1.0.md`;
- `BE-DES-003_Contrato_P3_Identity_Authentication_Authorization_v0.1.md`;
- `BE-DES-003A_Adenda_Aprobada_P3_Password_y_Sesion_v1.0.md`;
- `BE-CLOSE-003_Cierre_P3_Identity_Authentication_Authorization_v1.0.md`.

No altera sus invariantes ya cerradas.

---

## 15. Decisión final

> **ERP Platform no adopta `Site` ni `OperationalUnit` como niveles transversales obligatorios del Core. La plataforma conserva `Tenant -> Company` como jerarquía transversal mínima y delega a cada módulo la definición de entidades operativas con semántica real. Cualquier futura `Site`, `Branch`, `Facility` o equivalente requerirá una necesidad funcional concreta y un contrato específico.**

La implementación concreta del retiro/adaptación de `OperationalUnit` en la nueva versión de Milking se realizará exclusivamente en el corte propio del módulo y no forma parte de esta adenda documental.
