# BE-ADR-002 — Evolución incremental de ERP Platform y bounded contexts

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO  
**Fecha:** 2026-08-25  
**Proyecto:** AliosurERP18  
**Ámbito:** ERP Platform + módulos de negocio  
**Plan maestro relacionado:** `BE-PLAN-001 v0.2`  
**Aprobación:** Aprobado expresamente por el usuario el 2026-08-25.  
**Efecto:** gobierna P-5 en adelante y los nuevos módulos backend; no modifica retroactivamente P-1, P-2, P-3 ni P-4.

---

## 1. Decisión

AliosurERP se desarrollará mediante una combinación de:

- **arquitectura evolutiva**;
- **bounded contexts**;
- **plataforma transversal incremental**.

ERP Platform define y proporciona las invariantes, contratos y mecanismos comunes que deben mantenerse coherentes para todos los módulos.

Cada módulo conserva autoridad sobre su propio dominio y completa exclusivamente:

- entidades de dominio;
- reglas funcionales;
- casos de uso;
- persistencia funcional;
- semántica específica;
- contratos propios del módulo;
- resolución funcional de conflictos;
- comportamiento de UI/cliente relacionado con su dominio.

Las capacidades transversales se desarrollarán mediante incrementos acotados, pero cada incremento deberá quedar **completo dentro de su alcance, contractual, implementado, probado y apto para ser consumido por los módulos**.

---

## 2. Contexto

AliosurERP es un ERP modular, multi-Tenant, multiempresa, multiusuario, offline-first y preparado para backend cloud.

La plataforma transversal ya contiene capacidades cerradas como:

- P-1 — Core Runtime;
- P-2 — Tenancy + Company + PostgreSQL por Tenant;
- P-3 — Identity + Authentication + Authorization;
- P-4 — Transactions + Idempotency + Concurrency + Audit.

Los módulos de negocio, entre ellos Milking, Inventory, Manufacturing, Livestock y Sales, evolucionan como bounded contexts independientes pero consumen capacidades comunes de ERP Platform.

El crecimiento del sistema puede revelar nuevas necesidades que inicialmente aparecen durante la implementación de un módulo, pero cuya naturaleza real puede ser transversal.

Se requiere una regla explícita para decidir dónde debe implementarse cada necesidad y evitar tanto:

- duplicación de infraestructura entre módulos;
- como sobrearquitectura prematura en Platform.

---

## 3. Principio de arquitectura evolutiva

La arquitectura del ERP no se considera una especificación exhaustiva e inmutable definida por anticipado.

Se conserva una arquitectura objetivo y un roadmap macro, pero las capacidades concretas evolucionan mediante decisiones progresivas basadas en necesidades reales verificadas.

Regla:

> **AliosurERP mantiene una arquitectura objetivo estable, pero permite evolucionar sus mecanismos internos mediante incrementos explícitos, contractuales y trazables, siempre preservando las invariantes ya cerradas.**

La evolución nunca autoriza:

- cambios silenciosos de contratos cerrados;
- refactorizaciones transversales sin análisis previo;
- implementaciones provisionales incompatibles entre módulos;
- ampliaciones fuera del corte autorizado.

---

## 4. Principio de bounded contexts

Cada módulo de negocio constituye un bounded context con autoridad sobre su dominio.

Ejemplos:

```text
Milking
Inventory
Manufacturing
Livestock
Sales
```

Cada bounded context define sus propias:

- entidades;
- reglas;
- estados;
- workflows;
- validaciones;
- operaciones;
- persistencia funcional;
- contratos de dominio.

ERP Platform no debe conocer la semántica funcional específica de esos módulos.

Ejemplo:

```text
Platform conoce:
- command_id
- expected_version
- idempotency
- CAS
- CONCURRENCY_CONFLICT

Milking conoce:
- qué comando confirma una sesión
- qué entidad Milking está versionada
- qué significa un conflicto funcional de ordeño
```

---

## 5. Principio de plataforma transversal incremental

ERP Platform evoluciona mediante **incrementos transversales pequeños pero completos**.

Un incremento transversal válido debe quedar:

1. analizado;
2. contractual;
3. aprobado;
4. implementado;
5. probado;
6. verificado independientemente;
7. apto para ser consumido;
8. cerrado mediante autorización expresa.

No se considera aceptable:

```text
foundation provisional
→ módulo la usa
→ luego se reemplaza completamente
```

La regla correcta es:

```text
foundation transversal acotada
→ completa dentro de su alcance
→ módulo la consume
→ experiencia real
→ nuevo incremento si aparece otra necesidad transversal
```

---

## 6. Regla de autoridad Platform vs módulo

ERP Platform define:

- invariantes comunes;
- mecanismos transversales;
- contratos técnicos comunes;
- convenciones compartidas;
- políticas de seguridad e integridad globales;
- primitivas reutilizables.

El módulo define:

- comportamiento funcional;
- semántica del dominio;
- reglas propias;
- entidades;
- comandos/queries específicos;
- respuestas funcionales;
- resolución funcional de conflictos.

Regla:

> **Platform define las invariantes y mecanismos comunes para todos los módulos. El módulo completa exclusivamente los mecanismos y semántica propios de su dominio.**

---

## 7. Regla ante una carencia detectada por un módulo

Si durante la implementación de un módulo aparece una necesidad nueva, esta no se resolverá automáticamente dentro del módulo.

Debe ejecutarse primero un análisis arquitectónico.

Flujo obligatorio:

```text
Módulo detecta una necesidad
           │
           ▼
Análisis arquitectónico
           │
      ┌────┴────┐
      │         │
   DOMINIO   TRANSVERSAL
      │         │
      ▼         ▼
Contrato      Contrato / ADR
del módulo    ERP Platform
      │         │
      ▼         ▼
Implementa    Incremento Platform
el módulo     completo + probado
      │         │
      └────┬────┘
           ▼
     módulo lo consume
```

---

## 8. Criterios para clasificar una necesidad

Antes de decidir si una necesidad pertenece a Platform o al módulo, se analizará al menos desde estas aristas:

### 8.1 Reutilización

¿La capacidad puede ser requerida por múltiples módulos?

### 8.2 Semántica

¿La semántica es realmente común o solo aparentemente similar?

### 8.3 Integridad

¿Resolverla de manera distinta entre módulos puede comprometer consistencia o trazabilidad?

### 8.4 Seguridad

¿La capacidad afecta autorización, aislamiento, identidad o protección global?

### 8.5 Concurrencia

¿Debe conservar reglas comunes entre usuarios/dispositivos?

### 8.6 Offline-first

¿Afecta contratos o mecanismos comunes de operación offline/sync?

### 8.7 Coste futuro

¿Incorporarla después implicaría migraciones o cambios costosos en varios módulos?

### 8.8 Acoplamiento

¿Centralizarla introduce dependencias innecesarias entre dominios?

### 8.9 Complejidad

¿El coste de elevarla a Platform está justificado por su beneficio transversal?

### 8.10 Evolución

¿Puede ampliarse posteriormente sin romper contratos ya consumidos?

---

## 9. Clasificación de decisiones

Una necesidad deberá clasificarse en una de estas tres categorías:

### A. Necesidad de dominio

Características:

- aplica solo a un bounded context;
- depende de reglas funcionales propias;
- no requiere consistencia global común.

Resultado:

> Se implementa en el módulo.

### B. Extensión de un mecanismo transversal existente

Características:

- Platform ya posee la foundation;
- el módulo necesita configurar o especializar su uso;
- no modifica las invariantes globales.

Resultado:

> Platform mantiene el mecanismo; el módulo aporta su extensión funcional.

### C. Nueva capacidad transversal

Características:

- afecta varios bounded contexts o la coherencia global;
- requiere semántica común;
- duplicarla produciría inconsistencias o deuda técnica;
- o su incorporación tardía tendría un coste/riesgo elevado.

Resultado:

> Se prepara contrato/ADR Platform y se implementa como nuevo incremento transversal antes de que el módulo adopte una solución privada incompatible.

---

## 10. Prohibición de implementaciones paralelas

Queda prohibido que un módulo cree una implementación paralela de una capacidad cuya autoridad ya pertenece a ERP Platform.

Ejemplo no permitido:

```text
MilkingIdempotencyEngine
InventoryIdempotencyEngine
SalesIdempotencyEngine
```

si ERP Platform ya proporciona idempotencia transversal.

Ejemplo permitido:

```text
Platform:
- command_id
- idempotency
- CAS
- CONCURRENCY_CONFLICT

Milking:
- qué comando usa expectedVersion
- qué recurso Milking se versiona
- qué respuesta funcional corresponde al conflicto

Inventory:
- qué operación Inventory usa expectedVersion
- qué recurso de stock se versiona
- qué respuesta funcional corresponde al conflicto
```

---

## 11. Regla de ampliación de Platform

Cuando una necesidad transversal sea confirmada:

1. se documenta el problema;
2. se identifica el mecanismo transversal afectado;
3. se analiza compatibilidad con contratos cerrados;
4. se define alcance mínimo correcto;
5. se congela contrato o ADR;
6. se implementa en rama/corte propio;
7. se verifica independientemente;
8. se cierra;
9. recién entonces el módulo consume la ampliación.

No se permite:

```text
módulo implementa workaround
→ después se intenta generalizarlo
```

salvo corrección de emergencia expresamente autorizada.

---

## 12. Platform debe evolucionar un paso por delante

Regla:

> **ERP Platform debe evolucionar suficientemente por delante de los módulos para evitar que estos dupliquen infraestructura transversal, pero no tan por delante que se construyan abstracciones sin casos de uso reales que permitan validarlas.**

Consecuencia:

```text
arquitectura objetivo
       +
roadmap macro
       +
foundation transversal suficiente
       +
vertical real
       +
feedback
       +
siguiente incremento
```

No se pretende:

```text
diseñar e implementar toda la plataforma futura
antes del primer vertical productivo
```

ni tampoco:

```text
dejar que cada módulo resuelva por sí mismo
sus necesidades transversales
```

---

## 13. Desarrollo por etapas

Los cortes transversales futuros pueden dividirse conceptualmente en incrementos menores.

Ejemplo:

```text
P-6 API + Contracts + Compatibility

P-6.1
Contract Foundation mínima

P-6.2
Compatibility Evolution

P-6.3
Capacidades adicionales futuras
```

La nomenclatura concreta se decidirá al congelar cada corte.

La condición obligatoria es que cada incremento quede completo y cerrado dentro de su alcance antes de ser considerado foundation válida para módulos.

---

## 14. Aplicación a módulos futuros

Esta decisión gobierna todos los módulos backend posteriores.

Cuando Milking, Inventory, Manufacturing, Livestock, Sales u otro módulo detecte una necesidad:

```text
¿es propia del bounded context?
    Sí → módulo

¿extiende una foundation Platform?
    Sí → módulo consume/extiende bajo contrato existente

¿es transversal?
    Sí → nuevo incremento Platform antes de solución privada
```

---

## 15. Relación con P-5, P-6, P-7 y P-8

Los cortes P-5, P-6, P-7 y P-8 del roadmap macro se ejecutarán bajo este ADR.

Su presencia en `BE-PLAN-001 v0.2` no obliga a una implementación exhaustiva inmediata.

Cada uno deberá:

- analizarse;
- definir su alcance transversal mínimo correcto;
- quedar completo dentro de dicho alcance;
- ser probado;
- ser consumible por módulos;
- ampliarse posteriormente mediante nuevos incrementos cuando exista necesidad demostrada.

---

## 16. Consecuencias positivas

- reduce duplicación entre módulos;
- preserva consistencia global;
- reduce deuda técnica;
- evita sobrearquitectura;
- permite evolución progresiva;
- facilita testing y trazabilidad;
- mantiene bounded contexts claros;
- permite que Platform aprenda de casos reales;
- evita convertir ERP Platform en un “god backend”;
- favorece eventual extracción futura de servicios si aparece una necesidad real.

---

## 17. Riesgos y mitigaciones

### Riesgo: Platform demasiado mínima

Puede obligar a módulos a esperar una capacidad transversal faltante.

Mitigación:

> análisis temprano de necesidades del siguiente vertical.

### Riesgo: Platform demasiado amplia

Puede introducir abstracciones no validadas.

Mitigación:

> alcance pequeño y basado en necesidades reales.

### Riesgo: módulo implementa workaround privado

Puede generar divergencia.

Mitigación:

> gate arquitectónico obligatorio antes de resolver carencias transversales.

### Riesgo: demasiados incrementos pequeños

Puede generar fragmentación documental.

Mitigación:

> consolidar incrementos bajo el mismo roadmap/capacidad cuando sea práctico, manteniendo contratos claros.

---

## 18. Gobierno

Este ADR no modifica retroactivamente P-1, P-2, P-3 ni P-4.

Gobierna:

- P-5 en adelante;
- nuevos módulos backend;
- ampliaciones transversales descubiertas durante el desarrollo de módulos;
- decisiones futuras sobre ubicación de capacidades.

Cualquier excepción requiere aprobación expresa.

---

## 19. Regla resumida

> **AliosurERP se desarrolla mediante arquitectura evolutiva, bounded contexts y una plataforma transversal incremental. ERP Platform define invariantes y mecanismos comunes; cada módulo conserva autoridad sobre su dominio. Las capacidades transversales se implementan mediante incrementos pequeños pero completos, contractuales, probados y consumibles. Si un módulo detecta una carencia que puede ser transversal, no la resuelve privadamente: primero se analiza y, si corresponde, se amplía ERP Platform mediante un nuevo contrato antes de que el módulo adopte una solución incompatible. Platform debe evolucionar un paso por delante de los módulos, pero no construir abstracciones sin casos reales que las validen.**
