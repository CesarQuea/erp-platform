# BE-ADR-003 — Portabilidad razonable de infraestructura y separación de almacenamiento

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO  
**Fecha:** 2026-08-28  
**Ámbito:** ERP Platform genérica + bounded contexts + despliegue  
**Plan relacionado:** `BE-PLAN-001`  
**ADR relacionado:** `BE-ADR-002 — Evolución incremental de ERP Platform y bounded contexts`  
**Aprobación:** Aprobado expresamente por el usuario el 2026-08-28.  
**Efecto:** gobierna P-7 en adelante, futuros módulos y futuras integraciones de almacenamiento; no reabre P-1 a P-6 ni O-4.

---

## 1. Decisión

ERP Platform se mantendrá como una plataforma **genérica, reutilizable y razonablemente portable entre infraestructuras**, evitando dependencias directas de proveedor dentro de Core, Platform y bounded contexts.

Se adoptan tres decisiones obligatorias:

1. **Plataforma genérica y sin marca en el Core.**
2. **Independencia razonable del proveedor de infraestructura en la lógica de aplicación.**
3. **Separación entre persistencia estructurada y almacenamiento de archivos binarios.**

Estas decisiones no implican multi-cloud, abstracciones universales ni soporte anticipado de servicios no utilizados.

---

## 2. Plataforma genérica y sin marca

Core, ERP Platform y los bounded contexts reutilizables no dependerán de una marca comercial concreta ni de una implementación empresarial específica.

La marca, especialización sectorial y configuración de una implantación se resolverán mediante mecanismos equivalentes a:

- configuración;
- `ImplementationProfile`;
- catálogos;
- defaults;
- módulos/verticales;
- permisos;
- rutas y configuración operacional.

Regla:

> **La identidad comercial de una implantación no forma parte de las invariantes de Core ni de ERP Platform.**

Queda prohibido introducir en motores transversales lógica equivalente a:

```text
if <marca>
if dairy
if food_manufacturing
```

salvo que se trate de configuración o especialización explícitamente aislada fuera del Core transversal.

---

## 3. Portabilidad razonable de infraestructura

La plataforma evitará dependencias directas de servicios propietarios del proveedor de infraestructura dentro de:

- Core;
- Platform;
- bounded contexts;
- contratos de dominio;
- protocolo Sync;
- persistencia funcional de los módulos.

Las particularidades de despliegue se resolverán mediante:

- configuración;
- variables de entorno;
- Docker/containerización;
- adaptadores de infraestructura cuando exista una necesidad real;
- documentación operativa específica del entorno.

Regla:

> **Un cambio de proveedor de infraestructura puede requerir cambios de deployment, DNS, networking, secrets, observabilidad o backup, pero no debe exigir rediseñar la lógica de dominio, los contratos públicos, el protocolo Sync ni las invariantes de ERP Platform.**

---

## 4. Lo que esta ADR NO exige

Esta decisión no obliga a implementar ahora:

- multi-cloud activo;
- despliegue simultáneo en varios proveedores;
- failover entre proveedores;
- Terraform para múltiples clouds;
- una interfaz universal `CloudProvider`;
- adaptadores anticipados para servicios que no se usan;
- abstracción de cada detalle de infraestructura;
- migración automática entre proveedores.

Principio de proporcionalidad:

> **Se protege la capacidad razonable de sustitución sin pagar anticipadamente el coste de una plataforma multi-cloud.**

---

## 5. Tecnologías y contratos portables

La portabilidad se favorece usando componentes y contratos estándar cuando resulten adecuados, por ejemplo:

```text
Docker / contenedores
FastAPI
HTTP / OpenAPI
PostgreSQL
Alembic
variables de entorno
TLS estándar
```

La utilización de un servicio administrado concreto no convierte ese servicio en parte del dominio ni en requisito arquitectónico de la plataforma.

---

## 6. Persistencia estructurada

PostgreSQL será la autoridad para:

- datos estructurados;
- relaciones;
- constraints;
- auditoría;
- trazabilidad;
- metadata;
- referencias lógicas a objetos externos;
- estado transaccional que corresponda al dominio.

Se preserva el modelo cerrado de PostgreSQL físicamente independiente por Tenant.

Esta ADR no modifica P-2.

---

## 7. Archivos binarios y Object Storage

Los archivos binarios de tamaño significativo no se almacenarán por defecto como blobs dentro de PostgreSQL.

Ejemplos:

- fotografías;
- documentos;
- comprobantes;
- adjuntos;
- imágenes;
- otros objetos binarios de tamaño relevante.

Cuando una necesidad funcional real lo requiera, el contenido binario residirá en **Object Storage**.

PostgreSQL conservará la información necesaria para relacionarlo con el dominio, por ejemplo:

```text
object_id
owner/entity reference
object_key
content_type
size_bytes
checksum
created_at / metadata aplicable
```

Regla:

> **PostgreSQL conserva identidad, relaciones y metadata; Object Storage conserva el contenido binario.**

---

## 8. Referencia lógica independiente del proveedor

La referencia persistida por el dominio deberá ser lógica y estable.

Preferencia conceptual:

```text
object_key = animals/<uuid>/profile.jpg
```

sobre una URL pública permanente que codifique detalles propietarios del proveedor.

La resolución física de esa referencia corresponderá a infraestructura/adaptador.

Esta ADR no congela todavía:

- layout definitivo de buckets;
- proveedor de Object Storage;
- signed URLs;
- CDN;
- multipart upload;
- reanudación de cargas;
- retención de objetos;
- protocolo de attachments.

Estas decisiones se tomarán cuando exista un caso real suficiente.

---

## 9. Regla de adaptadores

Cuando una integración específica de infraestructura sea necesaria, se aplicará la mínima abstracción útil.

Ejemplo conceptual futuro:

```text
ObjectStoragePort
├── put(...)
├── get(...)
├── delete(...)
└── exists(...)
        ↓
Infrastructure Adapter
        ↓
servicio concreto
```

La existencia de este ejemplo no autoriza implementar `ObjectStoragePort` durante P-7 si P-7 no lo necesita.

---

## 10. Aplicación específica a P-7

P-7 — Sync Foundation deberá ser independiente del proveedor de infraestructura.

P-7 v0.1 deberá respetar como mínimo:

1. Sync no conoce al proveedor de hosting.
2. Sync no conoce al proveedor de PostgreSQL.
3. Sync no conoce al proveedor de Object Storage.
4. Sync consume contratos HTTP/OpenAPI de P-6.
5. Sync utiliza identidad/contexto de P-3.
6. Sync reutiliza idempotencia/concurrencia de P-4 cuando corresponda.
7. Sync respeta Module Availability P-5.
8. No se introduce SDK propietario de infraestructura en Core/Platform.
9. P-7 debe poder verificarse completamente con Docker + PostgreSQL estándar.
10. Las integraciones específicas de infraestructura quedan fuera del protocolo Sync.
11. P-7 v0.1 se centrará en **datos estructurados**.
12. Binarios/attachments quedan fuera de P-7 salvo necesidad indispensable expresamente analizada y aprobada.

---

## 11. Relación P-7 y bounded contexts

P-7 define exclusivamente mecanismos e invariantes transversales de Sync.

Cada bounded context define:

- qué entidades/datos sincroniza;
- comandos/queries específicos;
- payloads de dominio;
- invariantes funcionales;
- resolución funcional de conflictos.

Regla heredada de BE-ADR-002:

> **Platform define las invariantes y mecanismos comunes. El módulo completa exclusivamente los mecanismos y semántica propios de su dominio.**

Si durante un módulo aparece una carencia de Sync:

```text
necesidad detectada
      ↓
¿dominio o transversal?
      ↓
DOMINIO      → módulo
TRANSVERSAL  → incremento P-7.x / Platform
```

No se implementará privadamente una primitive transversal dentro del módulo.

---

## 12. Secuencia de validación posterior a P-7

La infraestructura staging no es prerrequisito para diseñar ni implementar un bounded context sobre P-7.

Secuencia aprobada:

```text
P-7 — Sync Foundation
        ↓
implementación + verificación + cierre P-7
        ↓
O-5 — implementación específica Milking sobre P-7
        ↓
verificación local end-to-end O-5
        ↓
Bootstrap / validación Staging
        ↓
verificación cloud de O-5
        ↓
cierre O-5
        ↓
P-8 — Cloud Operations / Production Foundation
```

Staging actúa como **gate de validación del vertical**, no como requisito arquitectónico previo para construir O-5.

---

## 13. Producción

El hecho de que un vertical pueda escribir datos reales en un entorno piloto/staging no convierte automáticamente ese entorno en producción formal.

P-8 mantiene autoridad sobre las capacidades transversales de operación productiva, incluyendo cuando su contrato lo determine:

- backup;
- restore probado;
- secrets productivos;
- monitoreo;
- alertas;
- despliegue controlado;
- rollback operativo;
- procedimientos de contingencia.

Esta ADR no adelanta P-8.

---

## 14. Consecuencias positivas

- Core y Platform permanecen reutilizables.
- La marca comercial puede evolucionar sin afectar el núcleo técnico.
- El primer proveedor de infraestructura no se convierte en dependencia de dominio.
- P-7 nace neutral respecto del hosting.
- PostgreSQL no se sobrecarga con archivos binarios pesados.
- Las fotografías/adjuntos futuros pueden migrar de storage sin rediseñar bounded contexts.
- Se conserva capacidad de evolución sin implementar multi-cloud prematuramente.

---

## 15. Costes y trade-offs aceptados

- Algunas integraciones de infraestructura requerirán adapters/configuración adicional.
- Migrar de proveedor nunca será coste cero: deployment, networking, DNS, backups y secrets pueden requerir trabajo.
- Object Storage introduce una segunda clase de persistencia cuando sea necesario.
- La separación metadata/binario exige gestionar consistencia referencial a nivel de aplicación/infraestructura.

Estos costes se aceptan únicamente cuando exista la necesidad real correspondiente.

---

## 16. Invariantes congeladas

1. Core/Platform no dependen de una marca comercial concreta.
2. La especialización se resuelve mediante configuración/ImplementationProfile/módulos.
3. Core/Platform/bounded contexts no dependen directamente de APIs propietarias de hosting.
4. No se exige soporte multi-cloud.
5. No se crean abstracciones anticipadas para servicios no utilizados.
6. PostgreSQL conserva datos estructurados, relaciones, auditoría, trazabilidad y metadata.
7. Binarios significativos se almacenarán mediante Object Storage cuando exista necesidad real.
8. El dominio persiste referencias lógicas, no URLs propietarias permanentes como autoridad.
9. P-7 será neutral respecto del proveedor de infraestructura.
10. P-7 v0.1 se centra en datos estructurados.
11. Attachments/binarios no entran automáticamente en P-7.
12. O-5 especializa P-7 para Milking.
13. Staging valida O-5; no es prerrequisito para diseñarlo/implementarlo.
14. P-8 sigue siendo el corte que prepara operación productiva.

---

## 17. Regla resumida

> **ERP Platform debe ser genérica y mantener independencia razonable del proveedor de infraestructura en su lógica de aplicación. La portabilidad se logra evitando acoplamientos propietarios en Core, Platform, bounded contexts y Sync, sin exigir multi-cloud ni abstracciones anticipadas. PostgreSQL conserva datos estructurados y metadata; los archivos binarios se almacenarán mediante Object Storage cuando exista una necesidad real, relacionados por referencias lógicas independientes del proveedor. P-7 se cierra antes de especializar Sync en O-5; Staging se utiliza posteriormente como gate de validación cloud del vertical antes de su cierre y antes de P-8.**
