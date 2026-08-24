# BE-PLAN-001 — Plan Maestro de Desarrollo Backend ERP Platform

**Versión:** 0.2  
**Estado:** APROBADO / CONGELADO  
**Fecha:** 2026-08-24  
**Proyecto:** AliosurERP18  
**Plataforma backend:** `erp-platform`  
**Arquitectura inicial:** monolito modular  
**Primer vertical operativo:** `Milking / Ordeño`

---

## 0. Cambios respecto de v0.1

La versión 0.2 actualiza y consolida el plan maestro original del 2026-08-19 a partir de las decisiones e implementaciones ya cerradas en ERP Platform.

Cambios principales:

1. El antiguo **Corte 0 — Fundación ERP Platform** se formaliza como roadmap transversal **P-0 a P-8**.
2. Los antiguos subcortes:
   - `0.1` pasan a corresponder a **P-1 — Bootstrap + Core Runtime**;
   - `0.2` a **P-2 — Tenancy + Company + PostgreSQL por Tenant**;
   - `0.3` a **P-3 — Identity + Authentication + Authorization**;
   - `0.4` evoluciona a **P-4 — Transactions + Idempotency + Concurrency + Audit**.
3. Se reconoce como jerarquía transversal mínima:
   ```text
   Tenant
     └── Company
   ```
4. `Organization` deja de considerarse nivel obligatorio de ERP Platform.
5. `Site` y `OperationalUnit` no son niveles transversales obligatorios del Core, del contexto autenticado, del Tenant resolver ni del RBAC global.
6. Los scopes transversales de autorización quedan alineados con P-3:
   ```text
   PLATFORM
   TENANT
   COMPANY
   ```
7. Se incorpora explícitamente la regla de que **ERP Platform solo contiene capacidades transversales reutilizables**; cada módulo mantiene autoridad sobre su dominio.
8. Se formaliza el criterio de **proporcionalidad arquitectónica**: planificar a nivel macro no obliga a implementar anticipadamente.
9. `Sync` y `Cloud Operations / Production Foundation` se reconocen como capacidades transversales del roadmap macro, no como responsabilidades exclusivas de Milking.
10. Los módulos de negocio (`Milking`, `Inventory`, `Manufacturing`, `Livestock`, `Sales`, etc.) mantienen sus propios planes, contratos y cortes de implementación, integrándose sobre ERP Platform.
11. Se refuerza el gobierno Git:
    - cierre y merge son autorizaciones distintas;
    - cada corte parte de un SHA exacto de `main` expresamente autorizado;
    - se distingue HEAD funcional verificado de commits posteriores puramente documentales.
12. Se refuerza la regla de evidencia:
    - Git, código real, tests reales y documentos aprobados son fuente principal;
    - ZIP, parches e informes son evidencia complementaria;
    - el verificador independiente no modifica código;
    - no se acepta únicamente `BUILD SUCCESSFUL` ni un informe textual.

Esta versión no reabre P-1, P-2, P-3 ni decisiones ya cerradas.

---

## 1. Propósito

Definir el plan maestro de desarrollo del backend de AliosurERP como una plataforma ERP modular, multi-Tenant, multiempresa, multiusuario, offline-first y preparada para evolución cloud.

El objetivo es evitar dos errores opuestos:

1. construir backends específicos y desechables para cada módulo;
2. sobrearquitectar prematuramente una plataforma genérica sin necesidades reales de dominio.

El desarrollo seguirá una estrategia incremental:

> **Planificar el backend completo a nivel macro, congelar las capacidades transversales realmente necesarias, implementar módulos de negocio con autoridad propia sobre su dominio, verificar cada corte independientemente y evolucionar la plataforma solo mediante decisiones expresas y trazables.**

ERP Platform será la base transversal común. Los módulos de negocio se integrarán sobre ella sin duplicar capacidades ya resueltas por la plataforma.

---

## 2. Fuentes de autoridad

Este plan se interpreta conjuntamente con:

- contratos y cierres vigentes de ERP Platform (`BE-DES-*`, `BE-CLOSE-*`, `BE-ADR-*`);
- contratos vigentes de Milking V2 (`MLK-DES-*`, `MLK-DEC-*`, `MLK-CLOSE-*`);
- contratos vigentes de Inventory V2 (`INV-DES-*`, `INV-API-*`, `INV-CLOSE-*`);
- Git y código real de `erp-platform`;
- Git y código real de AliosurERP Android;
- pruebas y evidencias reales;
- decisiones expresamente aprobadas por el usuario.

### 2.1 Jerarquía de autoridad

Ante contradicción:

1. prevalece el contrato o ADR aprobado más específico y vigente;
2. no se modifica silenciosamente una decisión congelada;
3. se detiene la implementación del punto contradictorio;
4. se prepara una adenda, ADR o nuevo contrato para aprobación;
5. Git/código/tests reales prevalecen sobre afirmaciones no verificadas de agentes o informes.

### 2.2 Evidencias

Fuente principal:

```text
contratos aprobados
+ Git real
+ código real
+ diff real
+ tests reales
+ migraciones reales
```

Evidencias complementarias:

```text
ZIP
parches
informes del agente
capturas
resúmenes
```

El informe del agente nunca sustituye la revisión independiente.

---

## 3. Principios arquitectónicos

### 3.1 Arquitectura inicial

ERP Platform se implementará inicialmente como **monolito modular**.

```text
erp-platform
│
├── platform/
│   ├── core
│   ├── tenancy
│   ├── company
│   ├── identity
│   ├── authorization
│   ├── transactions
│   ├── idempotency
│   ├── concurrency
│   ├── audit
│   ├── contracts
│   ├── sync
│   └── operations
│
└── modules/
    ├── milking
    ├── inventory
    ├── milk_logistics
    ├── manufacturing
    ├── livestock
    └── sales
```

La estructura física concreta podrá evolucionar, pero se preservará la separación de responsabilidades.

No se adoptarán microservicios al inicio.

Un módulo solo podrá extraerse a un servicio independiente si existe una necesidad técnica demostrable y una decisión arquitectónica posterior aprobada.

### 3.2 Regla de capacidades transversales reutilizables

ERP Platform contendrá **únicamente capacidades transversales reutilizables por múltiples dominios con semántica común**.

Reglas:

1. cada módulo conserva autoridad sobre sus entidades, reglas, casos de uso, persistencia funcional y contratos específicos;
2. si una capacidad pertenece únicamente a un módulo, se implementa dentro de ese módulo;
3. si varios módulos necesitan conceptos parecidos pero con invariantes diferentes, no se elevarán automáticamente al Core;
4. una capacidad solo se incorpora a ERP Platform cuando exista una necesidad transversal suficientemente demostrada o un coste/riesgo alto de incorporarla tardíamente;
5. Platform no debe conocer reglas sectoriales de Milking, Inventory, Manufacturing, Livestock, Sales u otros dominios;
6. los módulos no deben duplicar capacidades transversales ya resueltas por Platform.

Criterio práctico:

> **Si una necesidad es propia de un dominio, pertenece al módulo. Si varios dominios la necesitan con la misma semántica, puede ser candidata a ERP Platform. Si la similitud es solo aparente o las reglas difieren, permanece fuera del Core hasta demostrar una abstracción transversal real.**

### 3.3 Principio de proporcionalidad arquitectónica

“No sobrearquitectar” no se interpreta como prohibición de diseñar capacidades futuras.

Antes de elevar una capacidad a ERP Platform se analizarán, como mínimo:

- reutilización real;
- semántica común;
- impacto en integridad;
- impacto en seguridad;
- impacto en concurrencia;
- impacto en offline-first;
- coste de incorporarla después;
- coste de migración;
- acoplamiento;
- complejidad introducida;
- capacidad de evolución;
- verificabilidad mediante pruebas.

Regla:

> **Planificar a nivel macro no obliga a implementar anticipadamente. Una capacidad futura puede quedar prevista y diferirse hasta contar con casos reales suficientes para congelar correctamente su contrato.**

### 3.4 Jerarquía transversal mínima

ERP Platform mantiene como jerarquía transversal mínima:

```text
Tenant
  └── Company
```

- `Tenant` es una frontera técnica de aislamiento y datasource.
- `Company` representa la entidad empresarial/legal dentro de un Tenant.
- `Organization` no es un nivel obligatorio.
- `Site` no es un nivel transversal obligatorio.
- `OperationalUnit` no es un nivel transversal obligatorio.

Después de `Tenant + Company`, cada módulo utiliza entidades de dominio con semántica real.

Ejemplos:

```text
Livestock      → Farm
Milking        → Farm cuando corresponda
Inventory      → Warehouse / Location
Sales          → PointOfSale
Manufacturing  → entidades definidas por su propio contrato
```

### 3.5 Especialización sectorial

El Core debe permanecer genérico.

La especialización Aliosur / Food Manufacturing / Dairy se realizará mediante:

- configuración;
- `ImplementationProfile`;
- defaults;
- catálogos;
- rutas;
- permisos;
- integración de módulos.

Queda prohibida lógica del tipo:

```text
if dairy
if aliosur
```

dentro de los motores transversales.

---

## 4. Persistencia y contexto

### 4.1 PostgreSQL por Tenant

Cada Tenant utiliza una base PostgreSQL físicamente independiente.

```text
Tenant A → PostgreSQL A
Tenant B → PostgreSQL B
```

No se adopta shared-schema multi-tenancy.

### 4.2 Company

Dentro de una base Tenant pueden existir varias Companies.

```text
Tenant A
├── Company A1
└── Company A2
```

### 4.3 Reglas de aislamiento

1. ningún módulo conoce DSN ni credenciales;
2. ninguna Session cruza Tenant;
3. ninguna transacción cruza Tenant;
4. no existe fallback silencioso a otro Tenant;
5. el datasource se resuelve únicamente mediante la infraestructura de plataforma;
6. la metadata física de la DB debe coincidir con el Tenant solicitado;
7. un UUID conocido no concede acceso;
8. un header público no constituye autorización;
9. el contexto autorizado se valida antes de acceder al datasource Tenant solicitado.

---

## 5. Identity y autorización transversal

La identidad es global a ERP Platform.

Flujo conceptual:

```text
UserAccount
   ↓
TenantMembership
   ↓
CompanyAccess
   ↓
Role / Permission
   ↓
AuthenticatedPrincipal
   ↓
TenantContext + CompanyContext
```

Scopes transversales:

```text
PLATFORM
TENANT
COMPANY
```

No se crean automáticamente scopes globales:

```text
SITE
OPERATIONAL_UNIT
FARM
WAREHOUSE
POINT_OF_SALE
```

Las restricciones más finas pertenecen al dominio correspondiente, salvo decisión transversal futura aprobada.

---

## 6. Offline-first y autoridad cloud

AliosurERP mantiene arquitectura offline-first.

Reglas:

1. Android/Room es la fuente inmediata de operación local;
2. una pérdida de red no debe impedir operaciones locales válidas conforme al contrato del módulo;
3. las operaciones pendientes sobreviven hasta sincronización;
4. backend/PostgreSQL pasa a ser autoridad consolidada global cuando la sincronización está habilitada;
5. “guardado localmente” no equivale a “sincronizado”;
6. business status y sync status no se confunden;
7. errores de red no revierten automáticamente operaciones locales ya válidas;
8. no se aplica `last-write-wins` indiscriminadamente;
9. los conflictos globales deben ser explícitos y recuperables;
10. identificadores distribuidos deben ser estables.

---

## 7. Trazabilidad y corrección

La trazabilidad se diseña desde contratos y modelo, no como una función agregada al final.

Reglas generales:

- actor y contexto deben poder auditarse cuando corresponda;
- timestamps deben ser consistentes;
- relaciones de origen/destino deben ser estables;
- registros críticos validados no se editan o eliminan libremente si eso destruye trazabilidad;
- las correcciones funcionales se resolverán mediante anulación, reversión, nueva versión o compensación según el contrato del dominio;
- las reglas concretas de trazabilidad pertenecen al módulo, salvo primitivas técnicas transversales.

---

## 8. Metodología de trabajo por cortes

Cada corte crítico sigue:

```text
PLAN / ROADMAP
  ↓
ANÁLISIS DEL CORTE
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
PUSH SOLO A ESA RAMA
  ↓
REVISIÓN ESTÁTICA DEL DIFF REAL
  ↓
VERIFICACIÓN INDEPENDIENTE
  ↓
EVIDENCIAS REALES
  ↓
CONTRASTE CHATGPT: CONTRATO + CÓDIGO + DIFF + EVIDENCIAS
  ↓
RECOMENDACIÓN DE CIERRE
  ↓
CIERRE SOLO POR AUTORIZACIÓN DEL USUARIO
  ↓
MERGE SOLO POR AUTORIZACIÓN SEPARADA
```

### 8.1 Prohibiciones

- push directo a ramas estables;
- force push;
- merge sin autorización;
- tag sin autorización;
- rebase destructivo;
- ampliar alcance por criterio del agente;
- iniciar el siguiente corte sin autorización;
- modificar un corte cerrado sin nuevo contrato/adenda/corrección autorizada.

### 8.2 HEAD funcional y documentación

Debe distinguirse entre:

```text
HEAD funcional verificado
```

y:

```text
commits posteriores exclusivamente documentales
```

Cualquier cambio funcional posterior invalida la presunción de que las evidencias anteriores siguen cubriendo el código.

### 8.3 Verificador independiente

El verificador:

- no modifica código;
- ejecuta pruebas focales;
- ejecuta suite completa;
- verifica migraciones;
- ejecuta concurrencia/stress cuando corresponda;
- verifica compile/build/container;
- recopila XML JUnit/logs/evidencia primaria;
- registra base/HEAD/diff/working tree.

No se acepta únicamente:

```text
BUILD SUCCESSFUL
tests passed
informe textual del agente
```

---

# 9. ROADMAP TRANSVERSAL ERP PLATFORM

El roadmap P-0 a P-8 es **macro**.

Que un corte figure en el roadmap no significa que su alcance detallado esté congelado ni que deba implementarse automáticamente.

Antes de cada corte:

1. se revisa su necesidad actual;
2. se analizan pros/contras y alternativas;
3. se comprueba qué ya fue resuelto por cortes previos;
4. se define el alcance mínimo correcto;
5. se congela un contrato propio;
6. solo entonces se implementa.

---

## P-0 — Arquitectura y Gobierno

### Objetivo

Congelar las decisiones transversales y el método de trabajo que gobiernan ERP Platform.

Incluye conceptualmente:

- arquitectura macro;
- modular monolith;
- fuentes de autoridad;
- reglas Git;
- contratación por cortes;
- método de revisión/verificación;
- principios de modularidad;
- separación Platform vs dominios.

### Estado

**EJECUTADO / CONSOLIDADO mediante decisiones y documentos previos.**

No se reabre automáticamente.

---

## P-1 — Bootstrap + Core Runtime

### Objetivo

Transformar el backend experimental en un Core Runtime neutral, modular y verificable.

Incluye:

- bootstrap FastAPI;
- configuración;
- `/api/v1`;
- health/liveness/readiness;
- error foundation;
- identifiers/time;
- TransactionBoundary;
- logging/correlation;
- Docker;
- tests base.

### Estado

**CERRADO + MERGED.**

---

## P-2 — Tenancy + Company + PostgreSQL por Tenant

### Objetivo

Implementar aislamiento técnico multi-Tenant y base multiempresa.

Incluye:

- `TenantContext`;
- `TenantRegistry`;
- `TenantDataSourceResolver`;
- PostgreSQL físico por Tenant;
- metadata física;
- `Company`;
- transacciones SQLAlchemy por Tenant;
- Alembic por Tenant;
- provisioning mínimo;
- aislamiento cross-Tenant/cross-Company.

### Estado

**CERRADO + MERGED.**

---

## P-3 — Identity + Authentication + Authorization

### Objetivo

Implementar autoridad global de identidad y acceso.

Incluye:

- `UserAccount`;
- password hashing;
- sesiones;
- access/refresh tokens;
- `TenantMembership`;
- `CompanyAccess`;
- RBAC;
- `AuthenticatedPrincipal`;
- selección autorizada de contexto;
- revocación;
- auditoría de seguridad.

### Estado

**CERRADO + MERGED.**

---

## P-4 — Transactions + Idempotency + Concurrency + Audit

### Objetivo macro

Completar las primitivas transversales necesarias para procesar comandos mutantes de forma segura en un entorno multiusuario, multidispositivo y offline-first.

### Capacidades candidatas

- `commandId`;
- fingerprint lógico;
- replay idempotente;
- conflicto de idempotencia;
- `expectedVersion`;
- optimistic locking / CAS equivalente;
- conflictos explícitos;
- integración con TransactionBoundary ya existente;
- audit técnico de ejecución;
- actor/contexto/correlation;
- Outbox foundation solo si el contrato P-4 demuestra que pertenece a este corte.

### Reglas

- no reimplementar primitivas ya cerradas en P-1/P-2/P-3;
- no `last-write-wins`;
- no lógica sectorial;
- no comandos específicos de Milking/Inventory en Platform;
- concurrencia e idempotencia deben demostrarse con PostgreSQL real.

### Estado

**SIGUIENTE CORTE TRANSVERSAL PROPUESTO.**

Su alcance detallado requiere `BE-DES-004` y aprobación expresa antes de implementación.

---

## P-5 — Module Registry + Configuration + Lifecycle

### Objetivo macro

Definir la capacidad transversal mínima para declarar, configurar y activar módulos sin trasladar reglas de dominio al Core.

### Consideraciones

Su existencia en el roadmap no autoriza una plataforma de plugins compleja.

Antes de implementarlo se analizará si basta con capacidades equivalentes a:

- definición de módulo;
- activación por Tenant/Company;
- configuración;
- lifecycle/version mínima;
- capabilities expuestas.

### Estado

**ROADMAP MACRO — ALCANCE NO CONGELADO.**

---

## P-6 — API + Contracts + Compatibility

### Objetivo macro

Consolidar reglas transversales de estabilidad contractual para Android, Web y otros clientes.

Áreas candidatas:

- versionado API;
- estabilidad de errores;
- contract compatibility;
- breaking changes;
- deprecations;
- compatibilidad cliente/servidor;
- contract tests.

### Estado

**ROADMAP MACRO — ALCANCE NO CONGELADO.**

---

## P-7 — Sync Foundation

### Objetivo macro

Proporcionar primitivas comunes de sincronización offline-first reutilizables por múltiples módulos.

Áreas candidatas:

- push/pull;
- cursor/checkpoint;
- retry;
- acknowledgements;
- replay protection;
- Outbox/Inbox;
- orden;
- conflictos;
- bootstrap de dispositivo;
- sync status;
- compatibilidad de versiones.

### Regla

Platform define la mecánica transversal de sync.

Cada módulo define:

- qué sincroniza;
- sus comandos;
- sus invariantes;
- su resolución funcional de conflictos.

### Estado

**ROADMAP MACRO — ALCANCE NO CONGELADO.**

Su diseño debe contrastarse con casos reales de al menos los módulos que lo necesiten.

---

## P-8 — Cloud Operations / Production Foundation

### Objetivo macro

Proporcionar capacidades transversales de operación productiva del backend.

Áreas candidatas:

- deployment;
- configuración/secrets;
- TLS;
- migraciones operativas;
- backup;
- restore probado;
- logging;
- métricas;
- health;
- alertas;
- rollback;
- lifecycle operativo.

### Estado

**ROADMAP MACRO — ALCANCE NO CONGELADO.**

Debe completarse antes de declarar producción real de los módulos que dependan de estas capacidades.

---

# 10. ROADMAPS DE MÓDULOS

ERP Platform no sustituye los planes específicos de cada dominio.

Los módulos se desarrollan mediante sus propios contratos/cortes.

Ejemplos:

```text
Milking
Inventory
Milk Logistics
Manufacturing
Livestock
Sales
```

Cada módulo:

- conserva autoridad de dominio;
- define persistencia funcional;
- define comandos/queries específicos;
- define errores funcionales;
- define trazabilidad funcional;
- define integración con otros módulos;
- consume las capacidades transversales de ERP Platform.

Los planes específicos de módulo pueden avanzar en paralelo siempre que no dupliquen ni contradigan capacidades transversales cerradas.

---

## 11. Milking / Ordeño

Milking es el primer vertical operativo.

Su backend funcional no se diseña ni congela en detalle dentro de BE-PLAN-001.

Su autoridad corresponde a sus documentos y cortes propios.

ERP Platform proporciona, según avance el roadmap:

- Tenant/Company;
- Identity/Authentication/Authorization;
- Transaction foundation;
- P-4 idempotency/concurrency;
- contratos transversales;
- Sync Foundation;
- Cloud Operations.

Milking no debe implementar versiones paralelas de esas capacidades.

---

## 12. Inventory

Inventory mantiene autoridad sobre:

- Warehouse;
- Location;
- StockMove;
- LotSerial;
- StockBalance;
- Availability;
- Reservations;
- Restrictions;
- rutas/trazabilidad según contratos vigentes.

No se implementa lógica Inventory dentro de ERP Platform.

La integración con Milking se realiza mediante contratos explícitos, no mediante acceso directo a tablas de otro dominio.

---

## 13. Manufacturing, Livestock, Sales y otros

Se mantienen como roadmap de dominios independientes.

No se congelará su backend detallado dentro de este plan maestro transversal.

Cada uno deberá:

1. revisar contratos Android/Core vigentes;
2. identificar dependencias transversales;
3. congelar su contrato backend;
4. integrarse mediante las capacidades comunes de Platform.

---

## 14. Integración entre módulos

Un módulo no debe modificar directamente las tablas de otro para implementar reglas funcionales.

Ejemplo no deseado:

```text
Milking → UPDATE inventory_stock...
```

Dirección preferida:

```text
Milking
  ↓
contrato / application service / command
  ↓
Inventory
```

La integración puede ocurrir dentro del mismo proceso del monolito modular, pero debe preservar fronteras de dominio.

---

## 15. Web

La Web consumirá la misma API pública que Android.

No se creará un backend independiente para Web.

Puede iniciarse cuando existan contratos suficientemente estables del módulo correspondiente.

---

## 16. ImplementationProfile

ERP Platform reserva configuración/provisioning para especializaciones.

Ejemplo conceptual:

```text
ERP Core
   │
ImplementationProfile
   └── Food Manufacturing — Dairy
```

Puede configurar:

- features;
- defaults;
- Locations;
- OperationProfiles;
- Routes;
- permisos;
- catálogos;
- integración Quality;
- configuración de módulos.

No puede introducir lógica sectorial hardcodeada en Core.

El detalle de `ImplementationProfile` deberá congelarse en el corte transversal que corresponda cuando exista necesidad suficiente.

---

## 17. Estrategia global de pruebas

La suite backend crecerá de forma acumulativa.

### Unit

- dominio transversal;
- application services;
- errores;
- políticas.

### Contract

- API;
- comandos;
- eventos;
- compatibilidad cliente/backend.

### PostgreSQL integration

- repositories reales;
- constraints;
- transacciones;
- aislamiento.

### Migration

- upgrade;
- estado previo;
- forward strategy;
- rollback cuando aplique y sea seguro.

### Concurrency

- optimistic locking;
- idempotencia;
- carreras;
- no doble efecto.

### Security / isolation

- cross-Tenant;
- cross-Company;
- scopes;
- capabilities;
- UUID guessing;
- revocación.

### Sync

- replay;
- offline;
- interrupciones;
- dos dispositivos;
- reintentos.

### Production readiness

- backup;
- restore;
- deploy;
- rollback;
- health;
- observabilidad.

No se acepta únicamente `BUILD SUCCESSFUL`, “tests passed” o el informe textual del agente.

---

## 18. Estrategia documental

La documentación vigente de ERP Platform permanece en:

```text
docs/backend/
```

No se moverán documentos cerrados solo para hacer coincidir una estructura propuesta antigua.

Documentos transversales principales:

```text
BE-PLAN-*
BE-DES-*
BE-CLOSE-*
BE-ADR-*
verification/
```

Los módulos mantendrán sus documentos específicos según su convención aprobada.

La documentación transversal tendrá una sola fuente canónica en Git.

No se mantendrán copias divergentes de decisiones congeladas.

---

## 19. Estado actual

A la fecha de esta propuesta:

```text
P-0  Arquitectura y gobierno                           EJECUTADO / CONSOLIDADO
P-1  Bootstrap + Core Runtime                          CERRADO + MERGED
P-2  Tenancy + Company + PostgreSQL por Tenant         CERRADO + MERGED
P-3  Identity + Authentication + Authorization         CERRADO + MERGED
P-4  Transactions + Idempotency + Concurrency + Audit  SIGUIENTE PROPUESTO
P-5  Module Registry + Configuration + Lifecycle       ROADMAP MACRO
P-6  API + Contracts + Compatibility                   ROADMAP MACRO
P-7  Sync Foundation                                   ROADMAP MACRO
P-8  Cloud Operations / Production Foundation          ROADMAP MACRO
```

Las decisiones posteriores de `BE-ADR-001` sobre `Site` / `OperationalUnit` forman parte del contexto obligatorio del plan.

Los verticales de negocio se desarrollan mediante sus propios planes/cortes y pueden avanzar en paralelo sin duplicar capacidades transversales cerradas.

---

## 20. Secuencia propuesta inmediata

```text
1. Revisar BE-PLAN-001 v0.2
2. Aprobar/congelar BE-PLAN-001 v0.2
3. Registrar la versión aprobada en Git mediante corte documental autorizado
4. Confirmar SHA exacto de main
5. Analizar P-4 desde arquitectura, seguridad, concurrencia, persistencia y offline-first
6. Preparar BE-DES-004
7. Revisar y aprobar BE-DES-004
8. Autorizar SHA base, rama y Draft PR P-4
9. Implementar P-4 en commits pequeños
10. Revisión estática del diff real
11. Verificación independiente
12. Contraste final código + diff + evidencias
13. Cierre únicamente por autorización del usuario
14. Merge únicamente por autorización separada
```

---

## 21. Aprobación

Este plan maestro **BE-PLAN-001 v0.2** fue aprobado expresamente por el usuario el **2026-08-24** como plan vigente de ERP Platform y autorizado para su registro documental en Git.

La aprobación de este plan:

- no reabre P-1, P-2 o P-3;
- no autoriza automáticamente la implementación de P-4;
- no congela el alcance detallado de P-5, P-6, P-7 o P-8;
- no autoriza merge, tag ni cambios funcionales adicionales;
- mantiene como requisito que cada corte futuro tenga análisis, contrato propio, base Git autorizada, rama, Draft PR, verificación independiente y cierre expreso.

> **BE-PLAN-001 v0.2 queda APROBADO / CONGELADO como Plan Maestro vigente de ERP Platform.**

---

## 22. Regla resumida del plan

> **ERP Platform es la base backend transversal común del ERP y contiene únicamente capacidades reutilizables cuya transversalidad, impacto en integridad/seguridad o elevado coste de incorporación posterior justifiquen su existencia en la plataforma. Cada módulo conserva autoridad sobre su dominio, casos de uso, persistencia funcional y contratos específicos. La arquitectura inicial es un monolito modular. El roadmap P-0 a P-8 es macro: antes de implementar cada corte se revisan necesidad, alternativas, pros/contras, alcance mínimo y compatibilidad con contratos cerrados; luego se congela un contrato específico. Ningún corte avanza, se cierra o se mergea sin autorización expresa del usuario y evidencia primaria contrastada.**