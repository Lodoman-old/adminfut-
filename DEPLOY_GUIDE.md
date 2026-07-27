# Guía de Migración a Productivo — AdminFut

## Stack

| Componente | Tecnología |
|---|---|
| Servidor | Hostinger KVM2 (2 vCPU, 8 GB RAM, 100 GB NVMe) |
| Panel | Coolify (self-hosted, open source) |
| App | Django + Gunicorn |
| BD | PostgreSQL 16 ( Coolify) |
| Cache | Redis (Coolify) |
| Almacenamiento | Cloudinary |
| Push | Firebase Cloud Messaging |
| SSL | Automático (Let's Encrypt via Coolify) |

---

## Paso 1: Preparar el servidor

### 1.1 Acceder al VPS por SSH

```bash
ssh root@IP_DEL_SERVIDOR
```

### 1.2 Actualizar el sistema

```bash
apt update && apt upgrade -y
```

### 1.3 Instalar Coolify

```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

Esto instala Docker, Docker Compose y Coolify. El panel estará en:
```
http://IP_DEL_SERVIDOR:8000
```

### 1.4 Acceder al panel de Coolify

1. Abre `http://IP_DEL_SERVIDOR:8000` en tu navegador
2. Crea tu cuenta de administrador
3. Conecta tu servidor (localhost ya está conectado por defecto)

---

## Paso 2: Conectar repositorio GitHub

### 2.1 En Coolify → Sources → Add GitHub App

1. Dale nombre (ej: "AdminFut Repo")
2. Autoriza con tu cuenta de GitHub
3. Selecciona el repositorio `Lodoman-old/adminfut-`
4. Rama: `main`

---

## Paso 3: Crear Base de Datos PostgreSQL

1. En Coolify → Projects → Nuevo proyecto "AdminFut"
2. Add Resource → Database → PostgreSQL
3. Nombre: `adminfut-db`
4. Versión: PostgreSQL 16
5. Guarda las credenciales que genera (host, puerto, user, password, database)
6. Dale click a "Start"

---

## Paso 4: Crear Redis

1. En el mismo proyecto → Add Resource → Database → Redis
2. Nombre: `adminfut-redis`
3. Versión: latest
4. Start

---

## Paso 5: Desplegar la App

### 5.1 Add Resource → Application → Private Repository (GitHub App)

1. Selecciona el repo `adminfut-` y rama `main`
2. Build Pack: **Dockerfile**
3. Dockerfile Path: `./Dockerfile`

### 5.2 Configurar variables de entorno

En la pestaña **Environment Variables**:

```
DEBUG=False
SECRET_KEY=<genera una clave larga aleatoria>
ALLOWED_HOSTS=tudominio.com,www.tudominio.com
CSRF_TRUSTED_ORIGINS=https://tudominio.com,https://www.tudominio.com
DATABASE_URL=postgresql://adminfut_user:PASSWORD@adminfut-db:5432/coolify
PORT=8000
GUNICORN_WORKERS=4
GUNICORN_TIMEOUT=120
CLOUDINARY_URL=cloudinary://API_KEY:API_SECRET@CLOUD_NAME
```

> **Nota:** El `DATABASE_URL` usa el host interno de Coolify que es el nombre del contenedor (`adminfut-db`). Coolify lo resuelve automáticamente dentro de la misma red.

### 5.3 Configurar dominio

1. En la pestaña **Domains** escribe: `tudominio.com`
2. Coolify configurará SSL automáticamente con Let's Encrypt

### 5.4 Deploy

Click en **Deploy**. Coolify:
1. Clona el repo
2. Build la imagen Docker
3. Ejecuta `entrypoint.sh` (migrations + collectstatic)
4. Inicia Gunicorn
5. Configura el proxy inverso con SSL

---

## Paso 6: Configurar DNS

En tu proveedor de dominio (o Hostinger), apunta:

| Tipo | Nombre | Valor |
|---|---|---|
| A | @ | IP_DEL_SERVIDOR |
| A | www | IP_DEL_SERVIDOR |

O si usas subdominio:
| Tipo | Nombre | Valor |
|---|---|---|
| A | admin | IP_DEL_SERVIDOR |

---

## Paso 7: Configurar la app desde la UI

Una vez que la app esté corriendo:

1. Entra a `https://tudominio.com/accounts/login/`
2. Login: `admin` / `admin123` (o el que configuraste)
3. Ve a ⚙️ **Configuración** → pestaña **Infraestructura**
4. Configura:
   - **DATABASE_URL** → la de Neon o la que Coolify te dio
   - **Cloudinary keys** → Cloud Name, API Key, API Secret
   - **Firebase JSON** → pega el JSON de la service account
5. Guarda
6. Los cambios de Cloudinary y Firebase se aplican al momento
7. Los cambios de BD requieren reiniciar el contenedor desde Coolify

---

## Paso 8: Cron Job para Push Notifications

En cron-job.org o similar:
```
GET https://tudominio.com/api/cron-notificar-arbitros/
Cada 5 minutos
```

---

## Agregar más aplicaciones en el futuro

Con Coolify puedes correr múltiples apps en el mismo servidor:

1. En Coolify → Projects → Nuevo proyecto (ej: "OtraApp")
2. Add Resource → Application
3. Selecciona otro repo de GitHub
4. Coolify detecta automáticamente: Python, Node.js, Go, PHP, etc.
5. Add Resource → Database (PostgreSQL, MySQL, MongoDB, Redis...)
6. Configura dominio y variables de entorno
7. Deploy

**Ejemplo de apps que podrías agregar:**
- Dashboard financiero (Python/Node)
- Landing page (HTML/React/Vue)
- API interna (Node/Go)
- WordPress para blog
- n8n para automatizaciones

Cada app tiene su propio dominio, base de datos y SSL independiente.

---

## Comandos útiles

### Ver logs
```bash
# Desde Coolify → Application → Logs
# O por SSH:
docker ps | grep adminfut
docker logs -f CONTAINER_ID
```

### Reiniciar
```bash
# Desde Coolify → Application → Restart
# O por SSH:
docker restart CONTAINER_ID
```

### Entrar al contenedor
```bash
docker exec -it CONTAINER_ID bash
```

### Backup de la BD
```bash
docker exec CONTAINER_ID pg_dump -U adminfut_user coolify > backup.sql
```

### Actualizar Coolify
```bash
curl -fsSL https://cdn.coollabs.io/coolify/install.sh | bash
```

---

## Variables de entorno requeridas

| Variable | Requerida | Descripción |
|---|---|---|
| `SECRET_KEY` | ✅ | Clave secreta de Django (genera una aleatoria) |
| `DEBUG` | ❌ | `False` en producción |
| `ALLOWED_HOSTS` | ✅ | Dominio(s) separados por coma |
| `CSRF_TRUSTED_ORIGINS` | ✅ | URLs con https:// de tus dominios |
| `DATABASE_URL` | ✅ | URL de PostgreSQL |
| `CLOUDINARY_URL` | ✅ | URL de Cloudinary |
| `PORT` | ❌ | Puerto del servidor (default: 8000) |
| `GUNICORN_WORKERS` | ❌ | Workers de Gunicorn (default: 4) |
| `GUNICORN_TIMEOUT` | ❌ | Timeout en segundos (default: 120) |

---

## Generar SECRET_KEY

```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```
