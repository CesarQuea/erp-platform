# BE-ADR-003 — Portabilidad razonable de infraestructura y separación de almacenamiento

**Versión:** 0.1  
**Estado:** APROBADO / CONGELADO  
**Fecha:** 2026-08-28  
**Ámbito:** ERP Platform genérica + bounded contexts + infraestructura  
**ADR relacionado:** `BE-ADR-002 — Evolución incremental de ERP Platform y bounded contexts`  
**Aprobación:** aprobada expresamente por el usuario el 2026-08-28.  
**Efecto:** decisión arquitectónica transversal aplicable a la evolución futura de ERP Platform, bounded contexts e integraciones de infraestructura. No modifica retroactivamente contratos cerrados.

---

## 1. Decisión

ERP Platform se mantendrá como una plataforma **genérica, reutilizable y razonablemente portable entre infraestructuras**, evitando dependencias directas de proveedor dentro de Core, Platform y bounded contexts.

Se adoptan tres decisiones arquitectónicas duraderas:

1. **Plataforma genérica y sin marca en el Core.**
2. **Independencia razonable del proveedor de infraestructura en la lógica de aplicación.**
3. **Separación entre persistencia estructurada y almacenamiento de archivos binarios.**

Estas decisiones no implican multi-cloud, abstracciones universales ni soporte anticipado de servicios no utilizados.

---

## 2. Plataforma genérica y sin marca

Core, ERP Platform y los bounded contexts reutilizables no dependerán de una marca comercial concreta ni de una implantación empresarial específica.

La marca, especialización sectorial y configuración de una implantación se resolverán mediante mecanismos equivalentes a:

- configuración;
- `ImplementationProfile`;
- catálogos;
- defaults;
- módulos/verticales;
- permisos;
- configuración operacional.

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
- mecanismos transversales de sincronización;
- persistencia funcional de los módulos.

Las particularidades de infraestructura y despliegue se resolverán mediante:

- configuración;
- variables de entorno;
- containerización;
- adaptadores de infraestructura cuando exista una necesidad real;
- documentación operativa específica del entorno.

Regla:

> **Un cambio de proveedor de infraestructura puede requerir cambios de deployment, DNS, networking, secrets, observabilidad o backup, pero no debe exigir rediseñar la lógica de dominio, los contratos públicos ni las invariantes transversales de la plataforma.**

La portabilidad no significa coste cero de migración; significa evitar acoplamientos innecesarios que obliguen a rediseñar el producto base.

---

## 4. Lo que esta ADR no exige

Esta decisión no obliga a implementar:

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

La portabilidad se favorecerá usando componentes, protocolos y contratos estándar cuando resulten adecuados, por ejemplo:

```text
Docker / contenedores
HTTP / OpenAPI
PostgreSQL
Alembic
variables de entorno
TLS estándar
```

La utilización de un servicio administrado concreto no convierte ese servicio en parte del dominio ni en requisito arquitectónico de la plataforma.

Las tecnologías concretas podrán evolucionar mediante decisiones futuras, siempre preservando los contratos e invariantes vigentes o gestionando explícitamente su migración.

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

La separación entre datos estructurados y binarios no modifica las decisiones vigentes de aislamiento y tenancy.

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

Esta ADR no congela:

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

Cuando una integración específica de infraestructura sea necesaria, se aplicará la **mínima abstracción útil**.

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

Este ejemplo expresa una frontera arquitectónica, no autoriza implementar anticipadamente esa interfaz ni ese servicio.

Regla:

> **No se crean adaptadores, ports o providers genéricos sin una necesidad real que justifique su existencia.**

---

## 10. Sincronización y almacenamiento binario

Los mecanismos transversales de sincronización deberán mantener independencia respecto del proveedor de hosting, base de datos administrada u Object Storage.

La sincronización de datos estructurados y la transferencia/sincronización de archivos binarios se consideran capacidades distintas.

Reglas:

1. un mecanismo transversal de sincronización no debe depender de SDK propietarios de infraestructura;
2. la sincronización de datos estructurados no incorpora automáticamente transferencia de binarios;
3. attachments/binarios se incorporarán solo cuando exista una necesidad funcional suficientemente demostrada y un contrato específico;
4. la semántica funcional de qué se sincroniza permanece bajo autoridad del bounded context correspondiente;
5. una carencia verdaderamente transversal detectada por un bounded context se evalúa como incremento de Platform, no se resuelve privadamente dentro del dominio.

Esta sección define una frontera arquitectónica, no una secuencia de cortes ni un roadmap de implementación.

---

## 11. Consecuencias y trade-offs

### Consecuencias positivas

- Core y Platform permanecen reutilizables.
- La marca comercial puede evolucionar sin afectar el núcleo técnico.
- El primer proveedor de infraestructura no se convierte en dependencia de dominio.
- Los mecanismos transversales permanecen sustituibles respecto del entorno de despliegue.
- PostgreSQL no se sobrecarga con archivos binarios pesados.
- Los binarios pueden migrar entre servicios de almacenamiento sin rediseñar bounded contexts, siempre que se preserve la referencia lógica.
- Se conserva capacidad de evolución sin implementar multi-cloud prematuramente.

### Costes aceptados

- Algunas integraciones requerirán adapters/configuración adicional.
- Migrar de proveedor nunca será coste cero: deployment, networking, DNS, backups y secrets pueden requerir trabajo.
- Object Storage introduce una segunda clase de persistencia cuando sea necesario.
- La separación metadata/binario exige gestionar consistencia referencial a nivel de aplicación/infraestructura.

Estos costes se aceptarán cuando exista la necesidad real correspondiente.

---

## 12. Invariantes congeladas

1. Core/Platform no dependen de una marca comercial concreta.
2. La especialización se resuelve mediante configuración, `ImplementationProfile`, módulos u otros mecanismos explícitos fuera del Core transversal.
3. Core, Platform y bounded contexts no dependen directamente de APIs propietarias del proveedor de infraestructura.
4. Las particularidades del proveedor pertenecen a configuración, adapters, deployment y operación.
5. No se exige soporte multi-cloud.
6. No se crean abstracciones anticipadas para servicios no utilizados.
7. PostgreSQL conserva datos estructurados, relaciones, constraints, auditoría, trazabilidad y metadata.
8. Los binarios significativos se almacenarán mediante Object Storage cuando exista una necesidad real.
9. El dominio persiste referencias lógicas estables, no URLs propietarias permanentes como autoridad.
10. Los mecanismos transversales de sincronización permanecen independientes del proveedor de infraestructura.
11. La sincronización de datos estructurados no incorpora automáticamente sincronización de binarios/attachments.
12. Si un bounded context descubre una carencia verdaderamente transversal, esta se analiza y, si corresponde, se incorpora a Platform mediante el gobierno arquitectónico vigente.

---

## 13. Regla resumida

> **ERP Platform debe ser genérica y mantener independencia razonable del proveedor de infraestructura en su lógica de aplicación. La portabilidad se logra evitando acoplamientos propietarios en Core, Platform, bounded contexts y mecanismos transversales, sin exigir multi-cloud ni abstracciones anticipadas. PostgreSQL conserva datos estructurados y metadata; los archivos binarios se almacenarán mediante Object Storage cuando exista una necesidad real, relacionados por referencias lógicas independientes del proveedor. Las decisiones de orden, cortes, staging y puesta en producción pertenecen al Plan Maestro y a los contratos de implementación, no a esta ADR.**
