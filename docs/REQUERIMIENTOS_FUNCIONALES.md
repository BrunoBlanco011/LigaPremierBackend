# Liga Premier – Requerimientos funcionales (guía para el frontend)

Versión 0.2 · 30 de septiembre de 2026 · Backend: FastAPI + Supabase

Este documento describe **qué debe poder hacer cada tipo de usuario** y **con qué endpoint del backend se
resuelve cada acción**. Es la referencia para construir las pantallas. El contrato exacto (tipos, campos
opcionales, ejemplos) está siempre actualizado en la documentación interactiva del backend:
`http://localhost:8000/docs` (Swagger) y `http://localhost:8000/openapi.json`.

---

## 1. Visión general

La aplicación tiene tres áreas:

| Área | Quién entra | Propósito |
|------|-------------|-----------|
| **Sitio público** | Cualquier persona, sin iniciar sesión | Consultar torneos, rol de juegos, resultados, tabla de posiciones, equipos, rosters y líderes de estadísticas (similar a sportwey.com) |
| **Panel de administrador** | Usuarios con rol `admin` | Administrar todo: torneos, equipos, jornadas, partidos, resultados, estadísticas, finanzas y usuarios |
| **Panel de coach** | Usuarios con rol `coach` | Administrar los jugadores de su(s) equipo(s) |

### 1.1 Roles y permisos

| Acción | Público | Coach | Admin |
|--------|:-------:|:-----:|:-----:|
| Ver torneos, equipos, jornadas, partidos, tabla, estadísticas | ✅ | ✅ | ✅ |
| Ver roster de un equipo (jugadores activos) | ✅ | ✅ | ✅ |
| Ver jugadores dados de baja de un equipo | ❌ | Solo su equipo | ✅ |
| Alta / edición / baja / borrado de jugadores | ❌ | Solo su equipo | ✅ |
| CRUD de torneos, equipos, logos, jornadas, partidos | ❌ | ❌ | ✅ |
| Generar rol de juegos | ❌ | ❌ | ✅ |
| Capturar / corregir resultados y ajustes de tabla | ❌ | ❌ | ✅ |
| Capturar estadísticas de jugadores por partido | ❌ | ❌ | ✅ |
| Módulo de finanzas (ver y editar) | ❌ | ❌ | ✅ |
| Crear usuarios y asignar roles | ❌ | ❌ | ✅ |

---

## 2. Convenciones de la API

- **URL base:** `{API_URL}/api/v1` (en local: `http://localhost:8000/api/v1`).
- **Autenticación:** encabezado `Authorization: Bearer <access_token>` en las peticiones que lo requieren.
  Los endpoints públicos (GET de consulta) funcionan sin token.
- **IDs:** todos son UUID (texto).
- **Fechas:** `YYYY-MM-DD` (ej. `2026-05-18`). **Fecha y hora:** ISO 8601 con zona horaria
  (ej. `2026-05-18T19:00:00-06:00`). Mostrar en hora local de la liga.
- **Montos de dinero:** llegan como **texto** con 2 decimales (ej. `"700.00"`) para no perder precisión.
  Convertirlos para mostrarlos (`$700.00 MXN`); al enviarlos se acepta número o texto.
- **Actualizaciones parciales:** `PATCH` solo modifica los campos enviados.
- **Respuestas vacías:** los `DELETE` responden `204` sin cuerpo.

### 2.1 Errores

Todas las respuestas de error traen `detail`:

| Código | Significado | Qué hacer en el frontend |
|--------|-------------|--------------------------|
| `401` | Sin sesión o token expirado | Redirigir a login |
| `403` | Sin permiso para la acción | Mostrar "No tienes permiso" |
| `404` | El recurso no existe | Pantalla o mensaje de "no encontrado" |
| `409` | Conflicto (duplicado, ya existe) | Mostrar `detail` junto al formulario |
| `422` | Datos inválidos o regla de negocio | Mostrar `detail` (ver formato abajo) |

- Errores de **regla de negocio**: `{"detail": "No hay empates: captura el marcador final incluyendo el tiempo extra"}`
  (`detail` es texto, listo para mostrarse).
- Errores de **formato de datos** (campo faltante, tipo incorrecto): `detail` es una **lista**
  `[{"loc": ["body", "name"], "msg": "Field required", ...}]`. Usar `loc` para marcar el campo del
  formulario con error.

### 2.2 Catálogos (valores fijos y su etiqueta sugerida)

**Estado del torneo** (`status`)

| Valor | Etiqueta |
|-------|----------|
| `draft` | Borrador |
| `active` | En curso |
| `finished` | Finalizado |
| `cancelled` | Cancelado |

**Estado del partido** (`status`)

| Valor | Etiqueta | ¿Cuenta en la tabla? |
|-------|----------|:--------------------:|
| `scheduled` | Programado | No |
| `in_progress` | En juego | No |
| `finished` | Finalizado | Sí |
| `postponed` | Pendiente / reprogramado | No |
| `cancelled` | Cancelado (p. ej. por lluvia) | No |
| `forfeit` | Forfeit (21-0) | Sí |

**Tipo de movimiento financiero** (`type`)

| Valor | Etiqueta | Efecto |
|-------|----------|--------|
| `registration_fee` | Inscripción | Cargo (aumenta el adeudo) |
| `fine` | Multa | Cargo |
| `other_charge` | Otro cargo | Cargo |
| `payment` | Abono | Reduce el adeudo |

**Roles de usuario:** `admin` (Administrador), `coach` (Coach).

---

## 3. Autenticación

### RF-01 Iniciar sesión
- **Quién:** admin y coach.
- **Pantalla:** formulario con correo y contraseña.
- **Endpoint:** `POST /auth/login` → `{ access_token, refresh_token, token_type, expires_in, user_id }`.
- Guardar el `access_token` y enviarlo en cada petición. `expires_in` está en segundos.
- Con credenciales incorrectas responde `401` con "Correo o contrasena incorrectos".
- *Alternativa:* el frontend puede usar directamente `supabase-js` (`signInWithPassword`) con la
  anon key; el `access_token` de Supabase es el mismo que acepta el backend.

### RF-02 Identificar al usuario y su rol
- **Endpoint:** `GET /me` → `{ id, email, full_name, role }`.
- Llamarlo después del login para decidir a qué panel redirigir (`admin` → panel admin, `coach` → panel coach).

### RF-03 Cerrar sesión
- Descartar el token guardado en el cliente (y `supabase.auth.signOut()` si se usa supabase-js).

### RF-04 Sesión expirada
- Ante cualquier `401`, limpiar la sesión y mandar al login.
- Si se usa supabase-js, este renueva el token automáticamente con el `refresh_token`.

---

## 4. Sitio público

### RF-10 Lista de torneos
- **Endpoint:** `GET /tournaments?status=active` (filtro opcional por estado).
- Mostrar nombre, temporada, categoría, fechas y estado. Por defecto, destacar los torneos `active`.

### RF-11 Portada de un torneo
- **Endpoint:** `GET /tournaments/{id}`.
- Navegación con pestañas: **Tabla · Rol de juegos · Resultados · Equipos · Estadísticas**.

### RF-12 Tabla de posiciones
- **Endpoint:** `GET /tournaments/{id}/standings` (ya viene ordenada).
- Columnas (como en el Excel ROL DE JUEGOS):

| Columna | Campo |
|---------|-------|
| Pos. | `position` |
| Equipo (con logo) | `team.name`, `team.logo_url` |
| JJ (jugados) | `played` |
| JG (ganados) | `won` |
| JP (perdidos) | `lost` |
| A favor | `points_for` |
| En contra | `points_against` |
| Dif. | `point_difference` |
| Pts | `points` |

- Si `adjustment_points ≠ 0`, mostrar un indicador junto a los puntos (ej. "−2 *") con tooltip que
  liste `adjustment_reasons` (ej. "Adeudo de arbitraje").
- Criterios de orden (informativo para mostrar al pie de la tabla): puntos → diferencia → puntos a
  favor → menos puntos en contra. *(Pendiente de decisión: enfrentamiento directo, ver §9).*

### RF-13 Rol de juegos (calendario)
- **Endpoints:** `GET /tournaments/{id}/rounds` (jornadas) y `GET /tournaments/{id}/matches?round_id={roundId}`.
- Agrupar partidos por jornada: "Jornada 1 – 18 de mayo".
- Cada partido muestra: local vs visitante (nombre y logo), fecha/hora (`scheduled_at`), sede (`venue`)
  y estado.
- Si la jornada tiene `bye_team_id`, mostrar "Descansa: {equipo}". Buscar el nombre en la lista de
  equipos del torneo.
- Partidos `postponed` o `cancelled`: mostrar la etiqueta del estado y `notes` si existe
  (ej. "Se canceló por lluvia").

### RF-14 Resultados
- **Endpoint:** `GET /tournaments/{id}/matches?status=finished` (y `status=forfeit`), o todos y filtrar.
- Mostrar marcador `home_score` – `away_score` y resaltar al ganador (`winner_team_id`).
- En forfeit, mostrar "Forfeit" y el marcador 21-0.

### RF-15 Detalle de partido
- **Endpoints:** `GET /matches/{id}` y `GET /matches/{id}/stats` (estadísticas de jugadores en ese partido).
- Mostrar el marcador y, por equipo, la tabla de jugadores con sus estadísticas del partido
  (cruzar `player_id` con los rosters de ambos equipos).

### RF-16 Equipos del torneo
- **Endpoint:** `GET /tournaments/{id}/teams`.
- Tarjetas con logo, nombre y nombre del entrenador (`coach_name`).

### RF-17 Perfil de equipo
- **Endpoints:** `GET /teams/{id}`, `GET /teams/{id}/players`,
  `GET /tournaments/{tid}/matches?team_id={id}` y `GET /tournaments/{tid}/player-stats?team_id={id}`.
- Muestra el roster (número de jersey y nombre), los partidos del equipo y las estadísticas de sus jugadores.

### RF-18 Líderes de estadísticas
- **Endpoint:** `GET /tournaments/{id}/player-stats?sort_by={campo}&limit=10`.
- `sort_by`: `touchdowns` (anotaciones), `td_passes` (pases de anotación), `interceptions`
  (intercepciones), `sacks` (capturas), `tackles`, `games_attended` (asistencia).
- Una pestaña o tarjeta por estadística: "Líderes en anotaciones", etc.
- Tabla completa con columnas: Jugador (#número y nombre), Equipo, Asistencia, Anotaciones,
  Pases de anotación, Intercepciones, Capturas, Tackles.

### RF-19 Perfil de jugador
- **Endpoints:** `GET /players/{id}` y `GET /players/{id}/stats` → `{ totals, matches }`.
- Totales del jugador y desglose partido por partido.

---

## 5. Panel de administrador

### 5.1 Torneos

#### RF-20 Listar, crear, editar y eliminar torneos
- **Endpoints:** `GET /tournaments`, `POST /tournaments`, `PATCH /tournaments/{id}`, `DELETE /tournaments/{id}`.
- **Formulario:**

| Campo | Obligatorio | Notas |
|-------|:-----------:|-------|
| `name` | Sí | Máx. 120 caracteres |
| `season` | No | Ej. "2026" o "Apertura 2026" |
| `category` | No | Ej. "Mixta", "Juvenil" |
| `description` | No | Texto libre |
| `start_date`, `end_date` | No | `end_date` no puede ser anterior a `start_date` |
| `status` | No | Por defecto `draft` |
| `points_win` | No | Puntos por victoria, por defecto 2 |
| `points_loss` | No | Puntos por derrota, por defecto 0 |

- **Eliminar:** pedir confirmación con advertencia clara, porque **borra en cascada** equipos, jugadores,
  jornadas, partidos, estadísticas y finanzas del torneo. Sugerencia: preferir cambiar el estado a
  `cancelled` o `finished`.

### 5.2 Equipos

#### RF-21 CRUD de equipos del torneo
- **Endpoints:** `GET/POST /tournaments/{id}/teams`, `GET/PATCH/DELETE /teams/{id}`.
- **Formulario:** `name` (obligatorio, único dentro del torneo, sin distinguir mayúsculas),
  `coach_name` (nombre del entrenador para mostrar) y `coach_user_id` (cuenta de coach que podrá
  administrar el roster, opcional).
- Para el selector de `coach_user_id`, usar `GET /users?role=coach`.
- Nombre duplicado → `409`.

#### RF-22 Logo del equipo
- **Endpoint:** `POST /teams/{id}/logo` (multipart/form-data, campo `file`).
- Formatos permitidos: PNG, JPG, WEBP y SVG. Tamaño máximo: 2 MB. Validar también en el cliente.
- Responde el equipo con `logo_url` nuevo. Subir otro logo reemplaza el anterior.
- Mostrar una vista previa antes de subir.

### 5.3 Jornadas y rol de juegos

#### RF-23 Generar rol de juegos automático
- **Endpoint:** `POST /tournaments/{id}/schedule/generate`.
- Genera jornadas y partidos **todos contra todos**: cada equipo juega una vez contra cada equipo del
  torneo. Si el número de equipos es impar, en cada jornada **un equipo descansa** (BYE).
- La localía queda balanceada automáticamente.
- **Formulario:**

| Campo | Por defecto | Descripción |
|-------|-------------|-------------|
| `start_date` | vacío | Fecha de la jornada 1 |
| `days_between_rounds` | 7 | Días entre jornadas |
| `double_round` | false | Ida y vuelta |
| `replace_existing` | false | Reemplaza jornadas y partidos existentes |

- Responde `{ rounds_created, matches_created }`.
- Si el torneo ya tiene jornadas o partidos, responde `409`. Ofrecer "Reemplazar rol existente"
  (reenviar con `replace_existing: true`) tras una confirmación.
- Si ya hay partidos jugados, no se puede regenerar (`409`).
- Requiere al menos 2 equipos (`422`).
- **Flujo sugerido:** registrar todos los equipos → generar rol → ajustar fecha, hora y sede de cada partido (RF-25).

#### RF-24 CRUD manual de jornadas
- **Endpoints:** `GET/POST /tournaments/{id}/rounds`, `GET/PATCH/DELETE /rounds/{id}`.
- **Campos:** `number` (obligatorio, único en el torneo), `name` (si se omite, será "Jornada N"),
  `start_date`, `end_date` y `bye_team_id` (equipo que descansa).
- Al eliminar una jornada, sus partidos **no se borran**: quedan sin jornada asignada.

### 5.4 Partidos

#### RF-25 CRUD de partidos
- **Endpoints:** `GET/POST /tournaments/{id}/matches`, `GET/PATCH/DELETE /matches/{id}`.
- **Campos:** `home_team_id` y `away_team_id` (obligatorios, distintos y del mismo torneo), `round_id`,
  `scheduled_at` (fecha y hora), `venue` (sede), `status` y `notes`.
- Filtros del listado: `round_id`, `team_id` y `status`.
- **Casos del Excel que se deben poder representar:**
  - Cambiar fecha u hora de un partido: `PATCH` con `scheduled_at`.
  - Partido pendiente: `status: postponed` (+ `notes`).
  - Cancelado por lluvia: `status: cancelled` + `notes: "Se canceló por lluvia"`.

#### RF-26 Capturar / corregir resultado
- **Endpoint:** `PUT /matches/{id}/result`.
- **Resultado normal:** `{ "home_score": 32, "away_score": 27 }` (el estado pasa a `finished`).
  - **No existen empates**: el marcador debe incluir el tiempo extra. Si llega empatado, responde `422`.
    Validarlo también en el formulario.
- **Forfeit:** `{ "status": "forfeit", "forfeit_loser_team_id": "<equipo que pierde>" }`. El sistema fija
  el marcador en **21-0** automáticamente. En la UI basta con un botón "Forfeit" y elegir qué equipo pierde.
- La tabla de posiciones se recalcula sola; no hay que hacer nada más.
- Corregir un resultado es la misma acción: volver a enviar el marcador.

### 5.5 Tabla de posiciones

#### RF-27 Ajustes manuales de puntos
- Se usan para sanciones o bonificaciones que no dependen de un partido.
- **Endpoints:** `GET/POST /tournaments/{id}/standings/adjustments`, `PATCH/DELETE /standing-adjustments/{id}`.
- **Campos:** `team_id`, `points` (entero; negativo resta, positivo suma) y `reason` (obligatorio).
- En la vista de tabla del admin, mostrar la lista de ajustes con opción de editar o eliminar.

### 5.6 Estadísticas por partido

#### RF-28 Capturar estadísticas de un partido
- **Endpoints:** `GET /matches/{id}/stats`, `PUT /matches/{id}/stats`, `DELETE /matches/{id}/stats/{player_id}`.
- **Pantalla sugerida:** hoja de captura con dos tablas (local y visitante) que listan el roster de
  cada equipo (`GET /teams/{id}/players`). Cada fila es un jugador y cada columna una estadística:

| Campo | Etiqueta | Tipo |
|-------|----------|------|
| `attended` | Asistió | casilla (por defecto marcada) |
| `touchdowns` | Anotaciones | entero ≥ 0 |
| `td_passes` | Pases de anotación | entero ≥ 0 |
| `interceptions` | Intercepciones | entero ≥ 0 |
| `sacks` | Capturas | entero ≥ 0 |
| `tackles` | Tackles | entero ≥ 0 |

- El `PUT` recibe una **lista** `[{ player_id, attended, touchdowns, ... }]` y crea o reemplaza la fila de
  cada jugador enviado; los jugadores no enviados no se tocan. Se puede guardar todo de una vez.
- Solo se aceptan jugadores de los dos equipos del partido (si no, `422`).
- La "asistencia" del acumulado es el número de partidos con `attended = true`.

### 5.7 Finanzas (solo admin)

Reproduce la sección de finanzas del Excel: **Inscripción + Multas − Abonos = Adeudo**.

#### RF-29 Estado de cuenta del torneo
- **Endpoint:** `GET /tournaments/{id}/finance/summary`.
- Tabla por equipo: Equipo · Inscripción (`registration_fees`) · Multas (`fines`) · Otros
  (`other_charges`) · Total cargos (`total_charges`) · Abonos (`payments`) · **Adeudo** (`balance`).
- Viene ordenada de mayor a menor adeudo. `balance > 0` significa que el equipo debe (resaltar en rojo);
  `0` significa que está al corriente; un valor negativo es saldo a favor.
- Totales generales: `total_charges`, `total_payments` y `total_balance`.

#### RF-30 Cargar inscripción a todos los equipos
- **Endpoint:** `POST /tournaments/{id}/finance/registration-fees` con `{ amount, description?, occurred_on? }`.
- Crea el cargo de inscripción solo a los equipos que aún no lo tienen (se puede repetir sin duplicar,
  por ejemplo después de agregar equipos nuevos).

#### RF-31 Registrar cargos y abonos
- **Endpoints:** `GET/POST /tournaments/{id}/finance/movements` (filtros `team_id` y `type`),
  `PATCH/DELETE /finance/movements/{id}`.
- **Campos:** `team_id`, `type` (ver catálogo §2.2), `amount` (> 0, dos decimales), `description`
  (ej. "Cambio de fecha", "Pierde por forfeit"), `occurred_on` (por defecto hoy) y `match_id` (opcional,
  para ligar una multa a un partido).
- **Pantalla sugerida:** detalle de cuenta por equipo con su historial de movimientos, y botones
  "Registrar abono" y "Registrar multa".

### 5.8 Usuarios

#### RF-32 Gestión de usuarios
- **Endpoints:** `GET /users?role=coach`, `POST /users`, `GET/PATCH/DELETE /users/{id}`.
- **Crear:** `email`, `password` (mínimo 8 caracteres), `full_name` y `role` (por defecto `coach`).
  El usuario queda confirmado y puede iniciar sesión de inmediato.
- Después de crear un coach, asignarlo a su equipo desde RF-21 (`coach_user_id`).
- Un admin no puede cambiar su propio rol ni eliminarse a sí mismo (`422`).

---

## 6. Panel de coach

#### RF-40 Mis equipos
- **Endpoint:** `GET /me/teams` → equipos donde el coach está asignado.
- Si tiene un solo equipo, entrar directo a su roster. Si no tiene ninguno, mostrar
  "Aún no tienes equipo asignado; contacta al administrador".

#### RF-41 Administrar jugadores de mi equipo
- **Endpoints:** `GET /teams/{id}/players`, `POST /teams/{id}/players`, `PATCH /players/{id}`, `DELETE /players/{id}`.
- **Formulario del jugador:**

| Campo | Obligatorio | Notas |
|-------|:-----------:|-------|
| `full_name` | Sí | Nombre del jugador |
| `jersey_number` | No | 0 a 999; no puede repetirse entre jugadores activos del equipo (`409`) |

- **Dar de baja vs. eliminar:**
  - *Dar de baja* (`PATCH` con `is_active: false`): el jugador deja de aparecer en el roster público pero
    **conserva sus estadísticas** y libera su número. Es la opción recomendada.
  - *Eliminar* (`DELETE`): borra al jugador **y todas sus estadísticas**. Pedir confirmación.
- El coach recibe `403` si intenta modificar jugadores de un equipo que no es suyo.
- El coach solo lee (no edita) resultados, tabla y estadísticas; puede usar las mismas vistas del sitio público.

---

## 7. Reglas de negocio (resumen)

1. **Sin empates.** Todo partido finalizado tiene un ganador; el marcador incluye el tiempo extra.
2. **Forfeit = 21-0** a favor del rival del equipo que pierde por forfeit.
3. **Puntos en la tabla:** victoria = `points_win` (2), derrota = `points_loss` (0), más los ajustes manuales.
4. Solo cuentan los partidos `finished` y `forfeit`.
5. **Rol de juegos:** todos contra todos; con equipos impares descansa uno por jornada.
6. Un equipo pertenece a un torneo; su nombre es único dentro de ese torneo.
7. El número de jersey es único entre los jugadores **activos** de un equipo.
8. Un coach solo administra los jugadores de los equipos donde es `coach_user_id`.
9. Finanzas: adeudo = inscripción + multas + otros cargos − abonos. Solo el admin lo ve.

---

## 8. Mapa de pantallas sugerido

```
Público
├── /                              Torneos activos
├── /torneos/:id                   Tabla | Rol de juegos | Resultados | Equipos | Estadísticas
├── /torneos/:id/partidos/:mid     Detalle de partido
├── /equipos/:id                   Perfil de equipo
├── /jugadores/:id                 Perfil de jugador
└── /login

Admin (/admin)
├── /admin/torneos                        Lista + crear
├── /admin/torneos/:id                    Resumen del torneo
│   ├── equipos                           CRUD + logo + asignar coach
│   ├── equipos/:teamId/jugadores         CRUD de roster
│   ├── rol-de-juegos                     Generar rol + CRUD de jornadas
│   ├── partidos                          CRUD + capturar resultado
│   ├── partidos/:mid/estadisticas        Hoja de captura
│   ├── tabla                             Tabla + ajustes manuales
│   └── finanzas                          Estado de cuenta + movimientos
└── /admin/usuarios                       Coaches y admins

Coach (/coach)
├── /coach                         Mis equipos
└── /coach/equipos/:id             Roster (CRUD de jugadores)
```

---

## 9. Decisiones pendientes

| # | Tema | Impacto en el frontend |
|---|------|------------------------|
| 1 | **Desempate por enfrentamiento directo:** decidir si, al empatar en puntos, se ordena primero por quién ganó el partido entre esos equipos | Solo cambia el orden de la tabla y el texto del pie; no cambia pantallas |
| 2 | **Equipos permanentes entre temporadas ("club" vs. "inscripción al torneo")** | Si se aprueba: nuevas pantallas "Clubes" e "Inscribir club a torneo", roster por temporada e historial del equipo y del jugador. Conviene decidirlo antes de construir las pantallas de equipos |
| 3 | **Multas automáticas** (ej. cargar $700 al perder por forfeit o $200 por cambio de fecha) | Hoy el admin las registra a mano (RF-31) |
