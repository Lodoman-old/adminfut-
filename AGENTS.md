# Resumen

## Objective
- PDF cédula arbitral **terminado** (no tocar).
- AdminFut: sistema de publicidad + **métricas de audiencia** para vender anuncios, visibles en `/push-logs/`. Incluye contador de descargas, visitantes únicos/día, origen del tráfico, exclusión de IPs propias, audiencia alcanzable, heatmap día×hora, impresiones únicas y **reporte imprimible por anunciante**. Todo desplegado.

## Important Details
- Repo: `C:\Users\lodo1\Desktop\PROYECTOS\PROYECTOS\Personal\AdminFut` (branch `main`, remoto `Lodoman-old/adminfut-.git`). Ruta con **un solo** `PROYECTOS\PROYECTOS`.
- **Deploy real = Coolify en VPS `31.97.12.7`** (NO Render). El contenedor Django cambia de nombre: `docker ps -a --format '{{.Names}}' | grep w11b37 | head -1` (p.ej. `w11b37h99dyryw19bz6vhwn6-...`), workdir `/app`.
- Acceso remoto: `plink -no-antispoof -batch -pw "Lodomantemoman231602+" root@31.97.12.7 '<cmd>'`; subir con `pscp -batch -pw "..." <local> root@31.97.12.7:/tmp/...`.
- App Coolify uuid `w11b37h99dyryw19bz6vhwn6`, fqdn `https://juventinorosasliga.com`, Coolify v4.3.12.
- **Disparar deploy sin UI**: POST a `http://127.0.0.1:8000/webhooks/source/github/events/manual` con `X-GitHub-Event: push`, `X-Hub-Signature-256: sha256=<hmac>`, body `{"ref":"refs/heads/main","repository":{"full_name":"Lodoman-old/adminfut-"},"commits":[]}`. Secret = `manual_webhook_secret_github` (descifrar con PHP bootstrapping Laravel dentro del contenedor `coolify` en `/var/www/html`). Firma: `printf '%s' "$BODY" | openssl dgst -sha256 -hmac "$SECRET"`. **No hay auto-deploy al push.**
- Monitor deploy: `docker cp /tmp/q.sql coolify-db:/tmp/q.sql && docker exec coolify-db psql -U coolify -d coolify -f /tmp/q.sql`; tabla `application_deployment_queues` (`deployment_uuid`,`status`,`finished_at`).
- **Quoting plink/PowerShell**: usar single-quoted outer en PowerShell para pasar el comando remoto tal cual; `$(...)`, `{{...}}` y `&&` se rompen con comillas dobles. Para lógica compleja subir un `.sh` y `sed -i "s/\r$//"` antes de `bash`.
- **El tool Write agrega BOM UTF-8**; antes de usar un `.py` por stdin hay que quitarlo: `tail -c +4 archivo > archivo2` (GNU sed con `\xEF` no funcionó). Alternativa: `sed -i "1s/^\xEF\xBB\xBF//"`.
- Verificación en prod: `django.test.Client` **dentro de `transaction.atomic()` + `transaction.set_rollback(True)`**, ejecutado con `docker exec -i <c> python manage.py shell < /tmp/v.py`. Usar `Client(HTTP_HOST="juventinorosasliga.com")` (si no, `DisallowedHost: testserver`).
- Middleware (`league_project/middleware.py`): `ContadorVisitasMiddleware` (~L243) registra GET 200 no-staff/no-bot en páginas públicas; `LoginPermisoMiddleware` (L318-356) salta gate si `path.startswith(PREFIJOS_PUBLICOS)` o `path in RUTAS_PUBLICAS`; `PERMISO_POR_URL[url_name]=='__staff__'` exige staff. **`PREFIJOS_PUBLICOS` incluye `/publicidad/`** → las páginas staff-only van bajo `/reportes/...` (no públicas → login requerido, y `@admin.site.admin_view` exige staff).
- Login gate anónimo redirige a `/accounts/login/?next=...` (302).
- `AUTH_USER_MODEL='accounts.Usuario'`; usar `get_user_model()`. `puntos` NO es campo BD (`@property` en `PronosticoQuiniela`).
- No tocar `reports/views.py`. **No stagear** imágenes/icons/`AGENTS.md` ni borrados ajenos.
- Config de liga en dev (`config.nombre_liga`, `config.logo`) vía `ConfiguracionLiga.obtener()`.
- Estado prod (verificado): 5 anuncios (0 activos), 7 push activos, 0 suscriptores correo; `Descarga` con 2 descargas reales de APK.

### Modelos de métricas
- `Visita` (L~2636): `inicio` marca la primera visita de sesión.
- `Anuncio` (L~2664): `impresiones`, `clics`, `activo`, `tamano` (PREMIUM/MEDIO/ECONOMICO), `fecha_inicio/fecha_fin`, `orden`, `get_tamano_display`, `activos()`.
- `AnuncioClick` (L~2756): FK `related_name="registros_click"`.
- `AnuncioImpresion` (`related_name="impresiones_unicas"`): 1 fila por anuncio+fecha+clave (`session_key` o IP); `unique_together`.
- `AnuncioDia` (`related_name="dias"`): totales diarios `impresiones`/`clics`; `unique_together=["anuncio","fecha"]`; se incrementa con `_anuncio_dia_bump()` desde `impresion_anuncio`/`detalle_anuncio`.
- `Descarga`: `tipo` APK/REGLAMENTO, ip, user_agent, referer, sesion, usuario, fecha.
- `ConfiguracionLiga.ips_excluidas` (TextField) + `ips_excluidas_set()` (caché 2 min) + `es_ip_excluida(ip)` (exacta + comodín sufijo `*`); aplicada a visitas, descargas, impresiones y clics. Campo editable en tab Publicidad → "Métricas" de `configuracion_form.html`.
- Regex UA móvil: `Android|iPhone|iPad|iPod|Mobile|Windows Phone|BlackBerry|Opera Mini|IEMobile`. Regex bots descarga: `_BOTS_DESCARGA` en views.py.

## Work State
### Completed
- PDF cédula (`31b42a0`), banner app en `base.html` (`bd0efc4`,`76de9a2`,`2e58c4c`), sistema publicidad (`652d463`), métricas base (`8a4af01`).
- Crash loop deploy resuelto (`1b4f477`, deploy 228): `league/storage.py` import tolerante Cloudinary con fallback `FileSystemStorage`; `league/apps.py` `ready()` con `.filter(pk=1).values(...)`.
- Quiniela "por jornada" (`37a6daf`, deploy 229) e Histórico de Quiniela (`46bfa41`, deploy 230).
- Contador de descargas APK/Reglamento (`291a11b`, deploy 231): modelo `Descarga`, `_registrar_descarga`, pestaña "Descargas" en `/push-logs/`.
- Métricas DAU + origen de tráfico + exclusión de IPs (`682e94e`, deploy 232).
- Audiencia alcanzable + heatmap 7×24 + impresiones únicas (`06b413f` deploy 233 con bug → `d73678d` deploy 234 OK; bug: colisión con `related_name`, renombrado a `unicas_total`/`unicas_mes`).
- **Reporte imprimible por anunciante** (`d7aaed4`, deploy `zxr7vnnibjccynka3ccuklgz`): modelo `AnuncioDia` + migración `0099`; vista `reporte_anuncio` (`/reportes/anuncio/<id>/`, staff-only, selector `?mes=YYYY-MM`, botón imprimir/guardar PDF, tabla diaria con barras + acumulado + bloque "Audiencia del sitio (30 días)"); template `templates/publicidad/reporte.html`; botón impresora por anuncio en pestaña Publicidad de `push_logs.html`. Verificado en prod: staff 200 con contenido, anónimo 302 al login, contadores diarios correctos (2 impresiones/1 clic), enlace presente, rollback limpio.

### Active
- (ninguno) — funcionalidad entregada y verificada.

### Blocked
- (ninguno)

## Next Move
1. Esperar validación visual del usuario en prod (`https://juventinorosasliga.com`): métricas en `/push-logs/`, botón de impresora por anuncio en la pestaña Publicidad.
2. El usuario creará los anuncios reales desde el admin (los de prueba se eliminan/desactivan en prod).
3. Opcionales: tests específicos de publicidad (impresión/clic/vigencia/reporte) y, si el usuario lo pide, media kit público.

## Relevant Files
- `league/models.py`: `Visita`, `Anuncio`, `AnuncioClick`, `AnuncioImpresion`, **`AnuncioDia`**, `Descarga`, `ConfiguracionLiga` (`ips_excluidas`, `obtener()`).
- `league/views.py`: `_registrar_descarga`, `_anuncio_dia_bump`, `detalle_anuncio`, `impresion_anuncio`, `_mes_rango`, **`reporte_anuncio`**, `admin_push_logs`, `historico_quiniela`.
- `league/urls.py`: `/publicidad/<id>/`, `/publicidad/<id>/impresion/`, **`/reportes/anuncio/<id>/`** (`reporte_anuncio`), quiniela/histórico.
- `league/admin.py`: `AnuncioAdmin`, `AnuncioClick`, `AnuncioImpresionAdmin`, **`AnuncioDiaAdmin`**, `DescargaAdmin`.
- `league/migrations/`: ...`0096_descarga`, `0097_configuracionliga_ips_excluidas`, `0098_anuncioimpresion`, **`0099_anunciodia`**.
- `templates/admin/push_logs.html`: tabs Visitas/Dispositivos/Logs/Publicidad/Descargas; DAU, origen, audiencia, heatmap, impr. únicas; **botón Reporte** por anuncio.
- `templates/publicidad/`: banner_premium/medio/economico, detalle, **reporte.html**.
- `templates/league/configuracion_form.html`: campo `ips_excluidas`.
- `templates/home.html`: includes de banners + JS de impresión.
- `league_project/middleware.py`, `league_project/views.py`, `league_project/urls.py` (`/push-logs/`).
- `league/storage.py`, `league/apps.py`, `entrypoint.sh`, `Dockerfile` (fix deploy).
- `C:\Users\lodo1\AppData\Local\Temp\opencode\`: `verify_reporte.py`, `trigger_deploy.sh`, `mon_deploy.sh`, etc.
- `reports/views.py`: PDF cédula — NO TOCAR.
