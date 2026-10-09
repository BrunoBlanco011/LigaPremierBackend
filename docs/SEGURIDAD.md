# Seguridad – Liga Premier Backend

Este documento resume las medidas de seguridad de la API para proteger los datos de clubes, jugadores,
usuarios y finanzas. Está organizado por capa y referencia los archivos donde vive cada medida.

> Las medidas marcadas con **(nuevo)** se agregaron en esta iteración. El resto ya existía.

---

## 1. Autenticación

| Medida | Dónde |
|--------|-------|
| Login con Supabase Auth; la API solo acepta `Authorization: Bearer <access_token>` | `app/core/security.py`, `app/api/deps.py` |
| Se valida **firma, expiración y audiencia** (`authenticated`) del JWT. Llaves públicas (JWKS, ES256/RS256) o el secreto HS256 legado | `app/core/security.py` |
| Un token válido de un usuario sin perfil en la liga se rechaza (403) | `app/api/deps.py` |
| Mensaje de error genérico en el login (“Correo o contraseña incorrectos”): no revela si el correo existe | `app/infrastructure/auth_provider.py` |
| **(nuevo) Protección contra fuerza bruta en el login** | `app/core/rate_limit.py` (`LoginThrottle`), `app/api/v1/routers/auth.py` |
| **(nuevo) Política de contraseñas** al crear usuarios | `app/application/dto.py` (`UserCreate`) |

### Fuerza bruta en el login (nuevo)

- **5 intentos fallidos** por *IP + correo* en **15 minutos** bloquean ese correo desde esa IP → `429 Too Many Requests` con cabecera `Retry-After`.
- **20 intentos fallidos** por *IP* (sin importar el correo) bloquean la IP: frena el *password spraying* (probar una contraseña común contra muchos correos).
- Mientras dura el bloqueo, **ni la contraseña correcta** funciona.
- Un login exitoso limpia el contador de esa cuenta.
- Configurable con `LOGIN_MAX_ATTEMPTS` y `LOGIN_WINDOW_SECONDS`.

### Política de contraseñas (nuevo)

- Mínimo **10** caracteres (antes 8) y máximo 72 bytes (límite de bcrypt).
- Debe tener **letras y números**.
- No puede contener la parte local del correo (`juan@liga.mx` → no puede contener `juan`).

> Supabase también tiene su propia política en *Authentication → Providers → Email → Password requirements*;
> conviene igualarla para los usuarios creados desde el panel de Supabase.

---

## 2. Autorización (quién puede ver y modificar qué)

| Rol | Puede |
|-----|-------|
| Público | Leer torneos, clubes, rosters (solo jugadores activos), jornadas, partidos, tabla y estadísticas |
| `coach` | Además: CRUD de jugadores **solo** de los clubes que tiene asignados |
| `admin` | Todo, incluido **finanzas** y **usuarios** |

- Cada endpoint de escritura declara el rol requerido con `AdminActor` / `CoachActor` / `CurrentActor` (`app/api/deps.py`).
- La verificación de que un coach solo toque **sus** clubes está en la capa de aplicación (`app/application/services/players.py`), no en el frontend.
- Finanzas y usuarios son 100 % solo-admin (`app/api/v1/routers/finance.py`, `users.py`).
- Un admin no puede quitarse su propio rol ni borrar su propia cuenta (evita quedarse sin administradores).
- Los DTOs usan `extra="forbid"`: no se pueden colar campos no previstos (p. ej. `role` en un PATCH de jugador) — protección contra *mass assignment*.

---

## 3. Base de datos (Supabase)

| Medida | Dónde |
|--------|-------|
| **RLS activo en todas las tablas** sin políticas: la llave `anon`/publicable no puede leer ni escribir nada | `supabase/migrations/20260929000000_init.sql` y siguientes |
| El backend usa la `service_role` key **solo del lado del servidor** (nunca va al frontend) | `app/infrastructure/supabase_client.py` |
| Vista `team_details` con `security_invoker = true` | `20261001000000_clubs.sql` |
| Funciones con `search_path` fijo; `handle_new_user` no se puede llamar por RPC | `20261001000100_security_hardening.sql` |
| Consultas parametrizadas vía cliente de Supabase (sin SQL concatenado) → sin inyección SQL | `app/infrastructure/repositories/` |
| **(nuevo) Defensa en profundidad:** se revocan los permisos de `anon` y `authenticated` sobre tablas, secuencias y funciones de `public` (también las futuras). Si alguien crea una política RLS por error, la llave pública sigue sin acceso | `20261007000000_security_defense_in_depth.sql` |
| **(nuevo)** El bucket `team-logos` solo acepta PNG/JPG/WEBP de máximo 2 MB a nivel de Storage | `20261007000000_security_defense_in_depth.sql` |

> **Acción requerida:** aplicar la nueva migración en Supabase (SQL Editor o `supabase db push`).

---

## 4. Subida de archivos (logos) (nuevo)

Antes se aceptaba SVG y se confiaba en el `content-type` y la extensión que mandaba el cliente.

- **SVG eliminado**: un SVG puede llevar `<script>` y el bucket es público → XSS almacenado.
- **Se verifica el contenido real** por sus *magic bytes* (firma PNG, JPEG o WEBP). Un HTML renombrado a `.png` se rechaza.
- **La extensión la decide el servidor** según el tipo verificado; el nombre que manda el cliente se ignora (evita subir `logo.html`).
- Nombre aleatorio (`uuid4`) por subida y límite de tamaño (`MAX_LOGO_SIZE_MB`, 2 MB).

Archivo: `app/application/services/clubs.py` (`detect_image_type`, `upload_logo`).

---

## 5. Capa HTTP

### Cabeceras de seguridad (nuevo)

`app/core/middleware.py` → `SecurityHeadersMiddleware`. Se agregan a **todas** las respuestas, incluidos errores:

| Cabecera | Valor | Protege contra |
|----------|-------|----------------|
| `X-Content-Type-Options` | `nosniff` | Que el navegador “adivine” el tipo y ejecute contenido |
| `X-Frame-Options` | `DENY` | Clickjacking |
| `Content-Security-Policy` | `default-src 'none'; frame-ancestors 'none'` | XSS / embebido (la API solo devuelve JSON). No se aplica en `/docs` |
| `Referrer-Policy` | `no-referrer` | Fuga de URLs |
| `Permissions-Policy` | cámara, micrófono, geolocalización y pagos desactivados | Abuso de APIs del navegador |
| `Cross-Origin-Opener-Policy` | `same-origin` | Ataques entre ventanas |
| `Strict-Transport-Security` | `max-age=63072000; includeSubDomains` (**solo en producción**) | Degradar a HTTP / MITM |
| `Cache-Control` | `no-store` en peticiones **autenticadas** | Que proxies o el navegador guarden datos privados (finanzas, usuarios) |

También se elimina la cabecera `Server` para no anunciar la tecnología.

### CORS (endurecido)

- Solo los orígenes de `CORS_ORIGINS`. En producción `*` **impide arrancar** la app.
- `allow_credentials=False`: la API usa tokens en la cabecera, no cookies, así que no hace falta y reduce superficie.
- Métodos y cabeceras explícitos (`Authorization`, `Content-Type`) en lugar de `*`.

### Host permitido (nuevo)

`ALLOWED_HOSTS` activa `TrustedHostMiddleware`: peticiones con otra cabecera `Host` → 400 (evita *host header injection*).
En producción, si está vacío se registra una advertencia.

### Límite de peticiones por IP (nuevo)

`RateLimitMiddleware`: **300 peticiones/minuto por IP** (`RATE_LIMIT_PER_MINUTE`, `0` lo desactiva) → `429` + `Retry-After`.
Mitiga scraping masivo y DoS de bajo nivel. `/health` y los preflight `OPTIONS` quedan exentos.

### Tamaño máximo del cuerpo (nuevo)

`BodySizeLimitMiddleware`: más de `MAX_REQUEST_BODY_MB` (5 MB) → `413`. Funciona tanto con `Content-Length`
como con envíos *chunked* (cuenta los bytes conforme llegan).

### IP real detrás de un proxy (nuevo)

Con `TRUST_PROXY_HEADERS=true` se usa la **última** IP de `X-Forwarded-For` (la que agrega nuestro proxy),
no la primera, que el cliente puede falsificar para evadir los límites. Actívalo **solo** si la API está detrás
de un proxy propio (Nginx, Render, Railway, Fly…); si está expuesta directo, déjalo en `false`.

### WebSocket en tiempo real (nuevo)

`/api/v1/ws` es público y **solo anuncia qué recurso cambió**, nunca los datos: quien recibe un aviso tiene
que pedir la información por HTTP con sus propios permisos. Usuarios, login, finanzas e invitaciones (su ruta lleva el token secreto) no se anuncian.
CORS no aplica a WebSockets, así que el `Origin` se valida a mano contra `CORS_ORIGINS` (`1008` si no coincide).
Límite de conexiones simultáneas en total (`WS_MAX_CONNECTIONS`) y por IP (`WS_MAX_CONNECTIONS_PER_IP`) → `1013`;
un cliente que no lee sus mensajes se desconecta en vez de acumular memoria.

### Errores sin fugas de información (nuevo)

Cualquier excepción no controlada devuelve `500 {"detail": "Error interno del servidor"}`; la traza completa
solo va al log del servidor. Los errores de negocio siguen devolviendo mensajes claros (400/401/403/404/409/422).

### Documentación interactiva (nuevo)

`/docs`, `/redoc` y `/openapi.json` se **desactivan en producción** (`ENVIRONMENT=production`) para no publicar
el mapa completo de la API. Se pueden forzar con `DOCS_ENABLED=true/false`.

---

## 6. Validación de entradas

- Todos los cuerpos pasan por modelos Pydantic (`app/application/dto.py`): tipos, longitudes máximas, rangos numéricos, correos válidos, UUIDs.
- `extra="forbid"` rechaza campos desconocidos y `str_strip_whitespace` limpia espacios.
- Listas acotadas (p. ej. máximo 100 clubes por inscripción) para evitar peticiones gigantes.

---

## 7. Bitácora de auditoría (nuevo)

Logger `app.audit` (sale en el log del servidor con fecha, nivel y origen):

| Evento | Nivel |
|--------|-------|
| Login exitoso (IP, id de usuario) | INFO |
| Login fallido / bloqueado (IP, correo) | WARNING |
| Alta, cambio (campos modificados) y baja de usuarios, con el admin que lo hizo | INFO |
| Alta, cambio, baja y cargos masivos de movimientos de finanzas, con el admin que lo hizo | INFO |
| Rate limit excedido (logger `app.security`) | WARNING |

Nunca se registran contraseñas ni tokens.

---

## 8. Secretos y configuración

- `.env` está en `.gitignore`; `.env.example` no tiene valores reales.
- La `SUPABASE_SERVICE_ROLE_KEY` **nunca** debe ir al frontend ni a un repositorio.
- El xlsx con nombres reales de jugadores (`*.xlsx`) está excluido de git.
- Conexión HTTPS a Supabase con los certificados del sistema (`truststore`).

### Variables nuevas

| Variable | Default | Recomendado en producción |
|----------|---------|---------------------------|
| `ENVIRONMENT` | `development` | `production` (activa HSTS, oculta `/docs`, prohíbe CORS `*`) |
| `ALLOWED_HOSTS` | vacío (cualquiera) | `api.tudominio.com` |
| `DOCS_ENABLED` | vacío (auto) | vacío |
| `TRUST_PROXY_HEADERS` | `false` | `true` solo detrás de proxy propio |
| `MAX_REQUEST_BODY_MB` | `5` | `5` |
| `RATE_LIMIT_PER_MINUTE` | `300` | ajustar según tráfico |
| `LOGIN_MAX_ATTEMPTS` | `5` | `5` |
| `LOGIN_WINDOW_SECONDS` | `900` | `900` |
| `WS_MAX_CONNECTIONS` | `1000` | ajustar según tráfico |
| `WS_MAX_CONNECTIONS_PER_IP` | `20` | `20` |

---

## 9. Checklist para producción

- [ ] Aplicar `supabase/migrations/20261007000000_security_defense_in_depth.sql`.
- [ ] `ENVIRONMENT=production`, `ALLOWED_HOSTS` y `CORS_ORIGINS` con los dominios reales.
- [ ] Servir **solo por HTTPS** (el proxy/plataforma redirige HTTP → HTTPS).
- [ ] Arrancar sin cabecera de servidor y detrás del proxy: `uvicorn app.main:app --no-server-header --proxy-headers`.
- [ ] Rotar la `service_role` key si alguna vez se compartió o subió a un repositorio.
- [ ] En Supabase: activar *Leaked password protection* y revisar el *Security Advisor*.
- [ ] Revisar periódicamente los logs `app.audit` / `app.security`.
- [ ] Mantener dependencias actualizadas (`pip list --outdated`, Dependabot en GitHub).

---

## 10. Limitaciones conocidas y siguientes pasos

- **Los límites de peticiones viven en memoria del proceso.** Con varios workers o instancias cada uno lleva su
  propia cuenta y se reinician al reiniciar el servidor. Para limitar de forma global, mover el estado a Redis o
  usar el rate limiting del proxy / plataforma (Cloudflare, Nginx `limit_req`).
- **Sin cierre de sesión del lado del servidor:** un `access_token` sigue siendo válido hasta que expira (1 h por
  defecto en Supabase). Si se necesita revocar al instante, bajar el tiempo de expiración en Supabase.
- **Datos públicos por diseño:** nombres y números de jugadores son visibles sin login (rosters y estadísticas).
  Si la liga decide que esos datos deben ser privados, basta con exigir `CurrentActor` en esos `GET`.
- **MFA** para administradores: Supabase lo soporta (TOTP); requiere cambios en el frontend y en el login.
- La bitácora de auditoría va a logs; si se necesita consultarla desde la app, guardarla en una tabla `audit_log`.
