# BE-PLAN-001 — Plan Maestro de Desarrollo Backend ERP Platform

**Versión:** 0.3  
**Estado:** APROBADO / CONGELADO  
**Fecha:** 2026-08-28  
**Producto base:** ERP Platform genérica / marca comercial no asignada  
**Repositorio backend:** `erp-platform`  
**Arquitectura inicial:** monolito modular  
**Primer vertical de validación:** `Milking / Ordeño`  
**Plan anterior:** `BE-PLAN-001 v0.2`  
**ADR rectores:** `BE-ADR-002 v0.1`, `BE-ADR-003 v0.1`  
**Aprobación:** actualización aprobada expresamente por el usuario el 2026-08-28.

---

## 0. Propósito de v0.3

BE-PLAN-001 v0.3 actualiza el Plan Maestro vigente después del cierre y merge de P-4, P-5 y P-6, y congela las decisiones arquitectónicas necesarias antes de P-7.

Esta versión:

1. preserva los contratos y cierres P-1 a P-6;
2. actualiza el estado real del roadmap transversal;
3. refuerza que ERP Platform es una plataforma genérica, reutilizable y sin marca comercial en Core/Platform;
4. incorpora `BE-ADR-003` como autoridad para portabilidad razonable de infraestructura y separación de almacenamiento;
5. fija P-7 como siguiente corte transversal;
6. formaliza que P-7 define Sync transversal y el bounded context completa exclusivamente su semántica de dominio;
7. fija la secuencia posterior `P-7 → O-5 local → Staging → cierre O-5 → P-8`;
8. establece que Staging es gate de validación del vertical, no prerrequisito para diseñar o implementar O-5;
9. mantiene P-8 como foundation de operación productiva, sin adelantarlo;
10. mantiene Object Storage fuera de P-7 v0.1 salvo necesidad indispensable expresamente aprobada.

BE-PLAN-001 v0.2 permanece como antecedente histórico. Las decisiones cerradas que no son modificadas por v0.3 continúan vigentes.

---

## 1. Propósito general

Definir el desarrollo del backend como una **ERP Platform genérica**, modular, multi-Tenant, multiempresa, multiusuario, offline-first y preparada para despliegue cloud sin depender arquitectónicamente de una marca comercial o proveedor de infraestructura concreto.

El plan evita dos errores opuestos:

1. construir infraestructura específica y duplicada dentro de cada módulo;
2. sobrearquitectar anticipadamente una plataforma universal sin casos reales suficientes.

Estrategia:

> **Arquitectura evolutiva + bounded contexts + plataforma transversal incremental.**

ERP Platform define invariantes, contratos y mecanismos comunes. Cada bounded context conserva autoridad sobre su dominio y completa únicamente las reglas y semántica que le pertenecen.

---

## 2. Fuentes de autoridad

Este plan se interpreta conjuntamente con:

- `BE-ADR-001` y decisiones vigentes sobre jerarquía transversal;
- `BE-ADR-002 — Evolución incremental de ERP Platform y bounded contexts`;
- `BE-ADR-003 — Portabilidad razonable de infraestructura y separación de almacenamiento`;
- contratos `BE-DES-*` aprobados;
- cierres `BE-CLOSE-*` aprobados;
- contratos/cierres de cada bounded context;
- Git y código real;
- tests, migraciones y evidencias reales;
- decisiones expresamente aprobadas por el usuario.

Ante contradicción:

1. prevalece el contrato/ADR más específico y vigente;
2. no se modifica silenciosamente una decisión cerrada;
3. se detiene el punto contradictorio;
4. se prepara ADR/adenda/nuevo contrato;
5. código, Git y pruebas reales prevalecen sobre informes no contrastados.

---

## 3. Principios arquitectónicos vigentes

### 3.1 Monolito modular

ERP Platform continúa inicialmente como monolito modular.

```text
erp-platform
│
├── platform/
│   ├── core
│   ├── tenancy
│   ├── identity
│   ├── authorization
│   ├── transactions
│   ├── modules
│   ├── contracts
│   ├── sync
│   └── operations
│
└── modules/
    ├── milking
    ├── inventory
    ├── manufacturing
    ├── livestock
    ├── sales
    └── otros bounded contexts
```

No se adoptan microservicios por defecto.

---

### 3.2 Capacidades transversales únicamente

ERP Platform contiene solo capacidades reutilizables por múltiples dominios con semántica común o cuyo impacto en seguridad, integridad, aislamiento, concurrencia u offline-first justifique centralizarlas.

Regla:

> **Si una necesidad es de dominio, pertenece al módulo. Si es transversal con semántica realmente común, puede pertenecer a Platform mediante contrato propio.**

Los módulos no duplican primitivas ya resueltas por Platform.

---

### 3.3 Plataforma genérica y sin marca en Core

La identidad comercial de una implantación no forma parte de Core/Platform.

La especialización se resuelve mediante:

- configuración;
- `ImplementationProfile`;
- catálogos;
- defaults;
- módulos;
- permisos;
- configuración operacional.

No se admite lógica hardcodeada de marca o sector dentro de motores transversales.

---

### 3.4 Portabilidad razonable de infraestructura

Core, Platform, bounded contexts y Sync no dependen directamente de APIs propietarias de un proveedor de infraestructura.

Las particularidades del deployment se mantienen en:

- configuración;
- variables de entorno;
- containerización;
- adaptadores cuando exista necesidad real;
- documentación operativa.

No se exige multi-cloud ni una abstracción universal de proveedores.

Un cambio de infraestructura puede implicar trabajo en deployment, DNS, networking, secrets, observabilidad o backup, pero no debe exigir rediseñar dominio, API pública o protocolo Sync.

---

### 3.5 Proporcionalidad arquitectónica

Planificar una capacidad futura no obliga a implementarla anticipadamente.

No se crean abstracciones, providers, adapters o protocolos hasta que exista una necesidad suficientemente demostrada.

---

## 4. Jerarquía y persistencia

### 4.1 Jerarquía transversal mínima

Se preserva:

```text
Tenant
  └── Company
```

`Site`, `OperationalUnit`, `Farm`, `Warehouse`, etc. no se convierten automáticamente en scopes globales de Platform.

Cada bounded context usa entidades de dominio con semántica real.

---

### 4.2 PostgreSQL por Tenant

Se preserva la decisión P-2:

```text
Tenant A → PostgreSQL A
Tenant B → PostgreSQL B
```

Una Tenant DB puede contener varias Companies.

No se adopta shared-schema multi-tenancy.

---

### 4.3 Datos estructurados y archivos binarios

PostgreSQL es autoridad para:

- datos estructurados;
- relaciones;
- constraints;
- auditoría;
- trazabilidad;
- metadata;
- referencias lógicas.

Los binarios de tamaño significativo —fotografías, documentos, comprobantes y adjuntos— se almacenarán mediante **Object Storage** cuando exista una necesidad funcional real.

PostgreSQL conservará la referencia lógica y metadata correspondiente.

P-7 v0.1 no implementará automáticamente Object Storage ni Attachment Sync.

---

## 5. Offline-first y autoridad consolidada

Se preserva:

1. Android/Room es fuente inmediata de operación local;
2. pérdida de red no invalida automáticamente una operación local válida;
3. operaciones pendientes sobreviven hasta sincronización;
4. PostgreSQL/backend se convierte en autoridad consolidada global cuando la sincronización está habilitada;
5. `business status` y `sync status` son conceptos distintos;
6. no se aplica `last-write-wins` indiscriminadamente;
7. conflictos deben ser explícitos y recuperables;
8. identificadores distribuidos deben ser estables.

---

## 6. Regla de evolución Platform ↔ bounded context

Se preserva BE-ADR-002:

> **Platform define las invariantes y mecanismos comunes para todos los módulos. El módulo completa exclusivamente los mecanismos y semántica propios de su dominio.**

Cuando un módulo detecta una carencia:

```text
necesidad detectada
      ↓
análisis arquitectónico
      ↓
DOMINIO              TRANSVERSAL
  ↓                       ↓
módulo                Platform P-x / P-x.y
  ↓                       ↓
implementa             contrato + implementación + verificación
      \                 /
       módulo consume
```

No se resuelve privadamente en el módulo una necesidad que realmente sea transversal.

---

## 7. Metodología por cortes

Todo corte crítico sigue:

```text
ANÁLISIS
  ↓
CONTRATO
  ↓
APROBACIÓN EXPRESA
  ↓
SHA BASE AUTORIZADO
  ↓
RAMA PROPIA
  ↓
DRAFT PR
  ↓
IMPLEMENTACIÓN EN COMMITS PEQUEÑOS
  ↓
REVISIÓN ESTÁTICA DEL DIFF REAL
  ↓
VERIFICACIÓN INDEPENDIENTE
  ↓
XML / LOGS / MIGRACIONES / EVIDENCIAS
  ↓
CONTRASTE CHATGPT: CONTRATO + CÓDIGO + DIFF + EVIDENCIA
  ↓
RECOMENDACIÓN DE CIERRE
  ↓
CIERRE SOLO POR AUTORIZACIÓN DEL USUARIO
  ↓
MERGE SOLO POR AUTORIZACIÓN SEPARADA
```

Prohibido:

- push directo a `main`;
- force push;
- merge sin autorización;
- tag sin autorización;
- rebase destructivo;
- ampliar alcance silenciosamente;
- iniciar el siguiente corte sin autorización.

---

# 8. ROADMAP TRANSVERSAL ERP PLATFORM

## P-0 — Arquitectura y Gobierno

**Estado:** EJECUTADO / CONSOLIDADO.

Gobierna arquitectura macro, método de trabajo y separación Platform/dominio.

---

## P-1 — Bootstrap + Core Runtime

**Estado:** CERRADO + MERGED.

Foundation de runtime, configuración, health, errores, correlation, Docker y tests base.

---

## P-2 — Tenancy + Company + PostgreSQL por Tenant

**Estado:** CERRADO + MERGED.

Aislamiento multi-Tenant, Company, datasource físico por Tenant y provisioning/migraciones Tenant.

---

## P-3 — Identity + Authentication + Authorization

**Estado:** CERRADO + MERGED.

Identidad global, memberships, Company access, RBAC, tokens y contexto autorizado.

---

## P-4 — Transactions + Idempotency + Concurrency + Audit

**Estado:** CERRADO + MERGED.

Primitivas transversales de command execution, idempotencia, optimistic concurrency y audit técnico.

---

## P-5 — Module Registry + Configuration + Lifecycle

**Estado:** CERRADO + MERGED.

Module Registry explícito, activation Company-scoped, lifecycle y Module Availability.

---

## P-6 — API + Contracts + Compatibility

**Estado:** CERRADO + MERGED.

API v1, contratos públicos comunes, Module API/enforcement y baseline OpenAPI/compatibilidad.

---

## P-7 — Sync Foundation

**Estado:** SIGUIENTE CORTE TRANSVERSAL — ALCANCE DETALLADO NO CONGELADO.

### Objetivo macro

Proporcionar mecanismos comunes de sincronización offline-first reutilizables por múltiples bounded contexts.

### Áreas candidatas a analizar

- protocol/version de Sync;
- push/pull incremental;
- cursor/checkpoint;
- retry;
- acknowledgement;
- replay/deduplicación;
- identidad de cliente/instancia;
- ordenamiento mínimo;
- conflictos técnicos;
- integración con P-3/P-4/P-5/P-6;
- atomicidad de unidades Sync;
- errores transversales;
- observabilidad mínima necesaria para diagnóstico de Sync.

La lista es candidata, no autorización de implementación.

### Invariantes previas obligatorias

P-7 deberá:

1. ser proveedor-neutral;
2. consumir HTTP/OpenAPI P-6;
3. reutilizar P-3, P-4 y P-5;
4. no conocer reglas de Milking/Inventory/etc.;
5. centrarse inicialmente en datos estructurados;
6. no introducir Object Storage/Attachment Sync salvo análisis y aprobación expresa;
7. poder verificarse con Docker + PostgreSQL estándar;
8. evitar protocolos o SDK propietarios de infraestructura.

### Relación con módulos

P-7 define **cómo** sincronizar de forma transversal.

El módulo define **qué** sincroniza y con qué semántica.

---

## P-8 — Cloud Operations / Production Foundation

**Estado:** ROADMAP MACRO — ALCANCE NO CONGELADO.

### Objetivo macro

Preparar operación productiva segura, recuperable y mantenible.

Áreas candidatas:

- deployment productivo;
- configuración/secrets;
- TLS;
- migraciones operativas;
- backups;
- restore probado;
- logs/métricas;
- health/alertas;
- rollback operativo;
- procedimientos de contingencia;
- lifecycle operacional.

P-8 no se adelanta durante P-7/O-5 salvo necesidades mínimas ya existentes de desarrollo/verificación.

---

# 9. COORDINACIÓN CON EL PRIMER VERTICAL

## 9.1 Milking / Ordeño

Milking continúa como primer bounded context utilizado para validar la plataforma transversal.

Su contrato funcional pertenece a sus documentos propios.

Después de P-7:

- Milking no implementará su propia primitive transversal de Sync;
- O-5 consumirá P-7;
- O-5 definirá entidades/payloads/comandos/reglas Milking de Sync;
- si O-5 detecta una carencia transversal real, se detendrá ese punto y se evaluará un incremento P-7.x.

---

## 9.2 Secuencia aprobada P-7 → O-5 → P-8

Se congela la siguiente secuencia:

```text
P-7 — Sync Foundation
        ↓
implementación + pruebas + verificación independiente
        ↓
cierre + merge P-7
        ↓
O-5 — implementación Milking sobre P-7
        ↓
verificación local end-to-end O-5
        ↓
Bootstrap / validación de Staging
        ↓
verificación cloud O-5
        ↓
cierre O-5
        ↓
P-8 — Cloud Operations / Production Foundation
        ↓
producción formal cuando P-8 lo habilite
```

### Regla de Staging

Staging:

- **NO** es prerrequisito para diseñar P-7;
- **NO** es prerrequisito para implementar O-5;
- **SÍ** es un gate de validación cloud de O-5 antes de cerrarlo como vertical end-to-end;
- debe desplegar el mismo backend/contratos ya verificados localmente, evitando rediseñar Sync para el proveedor.

---

## 9.3 Producción y datos reales

O-5 puede utilizar datos reales en un piloto/staging controlado si su contrato y operación lo permiten.

Eso no convierte dichos datos en producción formal.

Producción oficial requiere que P-8 cierre las capacidades operativas necesarias y que el usuario autorice expresamente la puesta en producción.

---

# 10. WEB Y OTROS CLIENTES

Android, Web y otros first-party clients consumen la misma API pública v1 definida por P-6.

No se crea un backend independiente por tipo de cliente.

P-7 debe poder ser consumido por clientes compatibles sin incorporar lógica específica de una marca o plataforma de despliegue.

---

# 11. IMPLEMENTATION PROFILE

La especialización de una implantación podrá usar `ImplementationProfile` u otro mecanismo contractual equivalente.

Puede configurar:

- marca;
- módulos;
- features;
- defaults;
- catálogos;
- rutas;
- permisos;
- configuración operacional.

No puede introducir lógica sectorial hardcodeada en motores transversales.

El detalle de `ImplementationProfile` solo se ampliará cuando exista una necesidad real suficiente.

---

# 12. ESTRATEGIA GLOBAL DE PRUEBAS

La suite backend es acumulativa.

Debe cubrir según cada corte:

- unit;
- contract/API/OpenAPI;
- PostgreSQL integration;
- migration;
- concurrency/idempotency;
- security/isolation;
- Sync offline/retry/replay/dispositivos cuando P-7 corresponda;
- Docker/runtime;
- production readiness cuando P-8 corresponda.

No se acepta como evidencia suficiente:

```text
BUILD SUCCESSFUL
tests passed
informe textual del agente
```

El verificador independiente no modifica código.

---

# 13. ESTADO ACTUAL

Después del merge de P-6:

```text
P-0  Arquitectura y gobierno                           EJECUTADO / CONSOLIDADO
P-1  Bootstrap + Core Runtime                          CERRADO + MERGED
P-2  Tenancy + Company + PostgreSQL por Tenant         CERRADO + MERGED
P-3  Identity + Authentication + Authorization         CERRADO + MERGED
P-4  Transactions + Idempotency + Concurrency + Audit  CERRADO + MERGED
P-5  Module Registry + Configuration + Lifecycle       CERRADO + MERGED
P-6  API + Contracts + Compatibility                   CERRADO + MERGED
P-7  Sync Foundation                                   SIGUIENTE CORTE TRANSVERSAL
P-8  Cloud Operations / Production Foundation          ROADMAP MACRO
```

`main` al momento de preparar esta actualización documental:

```text
89dfa09cbb12451887649b75dac724b459af7ae7
```

Este SHA no constituye todavía autorización automática para implementar P-7.

---

# 14. SECUENCIA INMEDIATA

```text
1. Registrar BE-ADR-003 y BE-PLAN-001 v0.3
2. Merge documental solo mediante autorización expresa
3. Confirmar nuevo SHA exacto de main
4. Analizar P-7 desde offline-first, seguridad, idempotencia, concurrencia y compatibilidad
5. Definir el alcance transversal mínimo de P-7
6. Preparar BE-DES-007
7. Revisar y aprobar BE-DES-007
8. Autorizar SHA base P-7
9. Crear rama y Draft PR P-7
10. Implementar en commits pequeños
11. Revisión estática
12. Verificación independiente
13. Cierre P-7 por autorización expresa
14. Merge P-7 por autorización separada
15. Continuar O-5 sobre P-7 cerrado
```

---

# 15. APROBACIÓN

BE-PLAN-001 v0.3 queda **APROBADO / CONGELADO** como actualización vigente del Plan Maestro para la etapa posterior a P-6.

La aprobación:

- no reabre P-1 a P-6;
- no autoriza automáticamente P-7;
- no congela todavía `BE-DES-007`;
- no autoriza deployment staging;
- no autoriza producción;
- no autoriza P-8;
- no autoriza merge de esta rama documental sin acto separado.

---

# 16. REGLA RESUMIDA

> **ERP Platform es una plataforma backend genérica y reutilizable. Platform contiene únicamente invariantes y mecanismos transversales; cada bounded context conserva su dominio. La lógica de aplicación mantiene independencia razonable del proveedor de infraestructura sin exigir multi-cloud. PostgreSQL conserva datos estructurados y metadata, mientras los binarios utilizarán Object Storage cuando exista necesidad real. P-7 será la Sync Foundation transversal y se cerrará antes de que O-5 especialice Sync para Milking. O-5 se implementará y verificará localmente antes de usar Staging como gate de validación cloud; después se cerrará O-5 y se abordará P-8 como foundation de operación productiva.**
