# Plan de Infraestructura — AdminFut

## Especificaciones del Servidor

| Recurso | Capacidad |
|---|---|
| **Procesador** | 2 núcleos dedicados |
| **Memoria RAM** | 4 GB |
| **Almacenamiento SSD** | 80 GB |
| **Transferencia mensual** | 4 TB |
| **Sistema operativo** | Linux Ubuntu (LTS) |
| **Panel de administración** | Coolify (autogestionado) |
| **Base de datos** | PostgreSQL (instancias ilimitadas) |
| **SSL** | Automático (Let's Encrypt) |
| **Dominio .com** | 1 año incluido |

## Costo

| Concepto | Monto |
|---|---|
| **Servidor (12 meses)** | $2,880 MXN |
| **Dominio .com (primer año)** | $0 MXN (incluido) |
| **Dominio .com (años siguientes)** | ~$200 MXN/año |
| **Coolify** | $0 MXN (open source) |
| **Cloudinary (imágenes)** | $0 MXN (tier gratuito) |
| **SendGrid (correos)** | $0 MXN (100 emails/día gratis) |
| **Total primer año** | **$2,880 MXN** |
| **Total años siguientes** | **~$3,080 MXN/año** |
| **Costo mensual equivalente** | **~$240 MXN** |

## Capacidad de Transacciones Mensuales

### Estimación por cliente

Una liga de fútbol típica con ~20 equipos y ~400 jugadores genera:

| Actividad | Transacciones/mes |
|---|---|
| Consultas de tabla de posiciones, goleo y tarjetas | ~15,000 |
| Inicios de sesión de administradores y usuarios | ~1,000 |
| Captura de cédulas arbitrales (partidos) | ~200 |
| Registro de pagos y tickets (POS) | ~300 |
| Reportes PDF generados | ~100 |
| Accesos a dashboard y navegación general | ~5,000 |
| **Total por cliente** | **~21,600 transacciones/mes** |

### Capacidad del servidor

| Métrica | Capacidad estimada |
|---|---|
| Transacciones/mes que soporta | **~2,000,000+** |
| Usuarios concurrentes sin degradación | **~150** |
| Reportes PDF simultáneos | **8-10 sin afectar rendimiento** |
| Clientes que soporta cómodamente | **2 (holgura para crecer a 3-4)** |

### Conclusión

Con **~43,200 transacciones/mes (2 clientes)** contra una capacidad superior a **2,000,000 transacciones/mes**, el servidor opera con menos del **3% de su capacidad máxima**. Esto garantiza:

- ✅ Respuestas rápidas en horarios pico (días de partido)
- ✅ Múltiples usuarios consultando estadísticas simultáneamente
- ✅ Generación de reportes PDF sin lentitud
- ✅ Captura de cédulas arbitrales en tiempo real sin latencia
- ✅ Espacio de almacenamiento para años de operación
- ✅ Margen de crecimiento para agregar más clientes sin migrar de plan

**Es más que suficiente para el propósito actual y futuro inmediato.**
