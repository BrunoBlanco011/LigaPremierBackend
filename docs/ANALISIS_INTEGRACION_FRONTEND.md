# Análisis de integración Backend ↔ Frontend

30 de septiembre de 2026

| Proyecto | Estado analizado |
|----------|------------------|
| Backend | `LigaPremierBackend` @ `73a6126` (modelo de club, API v1) |
| Frontend | `LigaPremierFront` @ `e1dd25a` (merge de `feat/frontend-base`) |

## Resumen

El frontend tiene una base sólida: cliente HTTP, manejo de errores, autenticación con supabase-js,
guardas por rol y el sitio público. **Pero su código se escribió contra el modelo anterior**, en el que
el equipo pertenecía al torneo y los jugadores al equipo, aunque su `RequerimientosFuncionales.md` ya
es la versión 0.3 (modelo de club).

Por eso hay **4 fallas que rompen en tiempo de ejecución** (§1): el panel del coach completo, el alta de
jugadores y la pestaña de estadísticas. Los tipos de TypeScript tampoco coinciden con varias respuestas
(§2). El panel de administración está casi todo sin construir (§5), aunque los endpoints ya existen.

| Severidad | Cantidad |
|-----------|---------:|
| 🔴 Rompe en ejecución | 4 |
| 🟠 Tipos que no coinciden con la API | 7 |
| 🟡 Bugs de presentación | 3 |
| 🔵 Mejoras sugeridas | 5 |
| ⚪ Funcionalidad pendiente (el endpoint ya existe) | 12 pantallas |

---

## 1. 🔴 Fallas que rompen en ejecución

### 1.1 Panel del coach: `GET /me/teams` ya no existe → 404

- **Frontend:** `src/features/coach/queries.ts:9` llama a `api.get<Team[]>('/me/teams')`.
- **Backend:** el endpoint ahora es `GET /api/v1/me/clubs` y devuelve `Club[]`. El coach se asigna al
  **club**, no a la inscripción de un torneo.
- **Efecto:** el coach siempre ve un error en `/coach`.
- **Cambio:**
  ```ts
  // features/coach/queries.ts
  export function useMyClubs() {
    return useQuery({ queryKey: ['me', 'clubs'], queryFn: () => api.get<Club[]>('/me/clubs') })
  }
  ```

### 1.2 Plantilla del coach: la ruta usa un id de club con endpoints de equipo

- **Frontend:** `CoachHomePage.tsx:34` enlaza a `/coach/equipos/${team.id}`, y
  `CoachRosterPage.tsx:9` hace `useTeam(id)` → `GET /teams/{id}`.
- **Backend:** con el modelo de club, el coach trabaja sobre `/clubs/{club_id}`. `GET /teams/{id}`
  espera el id de una inscripción, así que con un id de club responde **404**.
- **Cambio:** renombrar la ruta a `/coach/clubes/:id`, cargar con `GET /clubs/{id}` y pasar `clubId`
  a `RosterManager`.

### 1.3 Alta de jugador: `POST /teams/{id}/players` → 405 Method Not Allowed

- **Frontend:** `src/features/players/mutations.ts:14` envía `api.post('/teams/${teamId}/players', …)`.
- **Backend:** `/teams/{team_id}/players` es **solo lectura** (`GET`). Los jugadores se crean en el club:
  `POST /api/v1/clubs/{club_id}/players`.
- **Efecto:** "Agregar jugador" falla siempre, tanto para el coach como para el admin.
- **Cambio:**
  ```ts
  export function useCreatePlayer(clubId: string) {
    const qc = useQueryClient()
    return useMutation({
      mutationFn: (input: PlayerInput) => api.post<Player>(`/clubs/${clubId}/players`, input),
      onSuccess: () => qc.invalidateQueries({ queryKey: ['clubs', clubId, 'players'] }),
    })
  }
  ```
  Aplicar el mismo cambio de `queryKey` en `useUpdatePlayer` y `useDeletePlayer`. `PATCH` y `DELETE`
  de `/players/{id}` no cambian. En `RosterManager`, listar con `GET /clubs/{id}/players`, que además
  incluye las bajas cuando quien consulta es el admin o el coach del club.

### 1.4 Estadísticas (líderes): el frontend espera objetos anidados y la API responde plano

- **Frontend:** `StatsTab.tsx:68-83` lee `row.player.id`, `row.player.full_name` y `row.team.name`
  (tipo `PlayerStatLeader` en `types/api.ts:111`).
- **Backend:** `GET /tournaments/{id}/player-stats` devuelve `PlayerTotalsView` **plano**:
  ```json
  { "player_id": "…", "full_name": "…", "jersey_number": 32, "team_id": "…", "team_name": "TOROS",
    "games_attended": 2, "touchdowns": 6, "td_passes": 0, "interceptions": 0, "sacks": 0, "tackles": 5 }
  ```
- **Efecto:** `TypeError: Cannot read properties of undefined (reading 'id')`. La pestaña
  Estadísticas se rompe en cuanto hay al menos un jugador inscrito, porque el backend incluye en cero
  a los jugadores activos.
- **Cambio:** usar `row.player_id`, `row.full_name`, `row.jersey_number` y `row.team_name`. Para el
  logo, tomarlo de `teamsById.get(row.team_id)`, que ya está en el contexto de `TournamentPage`.

---

## 2. 🟠 Tipos que no coinciden con la API (`src/types/api.ts`)

Hoy no siempre rompen, pero harán fallar las pantallas que se construyan encima.

| Tipo en el front | Debe quedar así (según el OpenAPI del backend) | Impacto |
|------------------|--------------------------------------------------|---------|
| `Player.team_id` | **`club_id`** (el jugador pertenece al club) | Cualquier lógica que agrupe por equipo |
| `Team` | Agregar **`club_id`**. `name`, `logo_url`, `coach_name` y `coach_user_id` vienen del club (solo lectura) | Enlazar del equipo a su club / historial |
| *(no existe)* | Nuevo **`Club`**: `id, name, coach_name, coach_user_id, logo_url` | Panel coach, admin de clubes |
| `PlayerStatLeader` (anidado) | **`PlayerTotalsView`** plano (ver §1.4); `team_id` puede ser `null` en el total de carrera | Estadísticas |
| `FinanceSummary.rows` | **`teams`** | La pantalla de finanzas no mostrará filas |
| `PlayerStat` | Agregar `id`, `match_id`, **`team_id`** | Detalle de partido (ver §4.3) |
| `usePlayerStats` → `{ totals, matches }` | **`{ totals, by_tournament, matches }`** | El perfil del jugador puede mostrar su carrera por torneo |

Otros detalles:

- `User.email` es `string | null` en el backend (`Profile.email` es opcional).
- `Match` del backend (`MatchView`) también trae `home_team`, `away_team`, `round` y
  `forfeit_loser_team_id` (ver §4.1).
- `FinanceMovement` también trae `tournament_id`.

> **Recomendación:** generar los tipos desde el OpenAPI en lugar de escribirlos a mano, como ya sugiere
> `PlanFrontend.md §12`:
> `npx openapi-typescript http://localhost:8000/openapi.json -o src/types/openapi.d.ts`

---

## 3. 🟡 Bugs de presentación

### 3.1 Las fechas sin hora se muestran un día antes

- `formatDate()` hace `new Date('2026-05-18')`. JavaScript interpreta una fecha sin hora como
  **medianoche UTC**, y en México (UTC−6) eso se muestra como **17 de mayo**. Verificado con
  `TZ=America/Mexico_City`.
- **Afecta:** `ScheduleTab.tsx:52` (fecha de jornada), `TournamentCard.tsx:22` y
  `AdminTournamentsPage.tsx:92` (inicio del torneo).
- **Cambio:** para fechas `YYYY-MM-DD`, construir la fecha en hora local:
  ```ts
  export function formatDate(iso: string | null): string {
    if (!iso) return 'Por definir'
    const d = /^\d{4}-\d{2}-\d{2}$/.test(iso)
      ? new Date(Number(iso.slice(0, 4)), Number(iso.slice(5, 7)) - 1, Number(iso.slice(8, 10)))
      : new Date(iso)
    return dateLong.format(d)
  }
  ```
  `scheduled_at` sí trae hora y zona, así que `formatDateTime` y `formatTime` están bien.

### 3.2 Leyenda de desempate desactualizada

- `StandingsTable.tsx`, al pie de la tabla: dice "puntos → diferencia → puntos a favor…".
- La regla acordada y ya implementada es **puntos → puntos a favor → diferencia → menos puntos en contra**.

### 3.3 Detalle de partido: un jugador transferido desaparece de las estadísticas

- `MatchDetailPage` cruza `GET /matches/{id}/stats` con la plantilla **actual** de cada equipo.
  Si un jugador cambió de club después del partido, ya no aparece en ninguna de las dos listas y su
  línea se pierde.
- **Cambio:** agrupar por `stat.team_id`, que el backend ya envía, en lugar de por plantilla.
  Para el nombre del jugador, ver la mejora §4.3.

---

## 4. 🔵 Mejoras sugeridas

### 4.1 Aprovechar los datos que ya vienen en cada partido (menos peticiones)

`GET /matches/{id}` y `GET /tournaments/{id}/matches` ya incluyen `home_team`, `away_team`
(`{id, name, logo_url}`), `round` (`{id, number, name}`) y `winner_team_id`.
`MatchDetailPage` hace 4 peticiones extra (`useTeam` ×2 y `useTeamPlayers` ×2) que se pueden reducir
a 2 (solo las plantillas).

### 4.2 Pestaña Equipos y perfil de equipo → enlazar al club

`TeamProfilePage` (`/equipos/:id`) funciona con el id de la inscripción, pero no muestra el historial.
Agregar un enlace a la ruta del front `/clubes/{club_id}` o incrustar `GET /clubs/{club_id}/history`.

### 4.3 Backend: datos adicionales que simplificarían el front (propuesta)

Son cambios pequeños en el backend que puedo hacer si te sirven:

| Endpoint | Agregar | Para qué |
|----------|---------|----------|
| `GET /tournaments/{id}/player-stats` | `team_logo_url` | Mostrar el escudo en líderes sin cruzar datos |
| `GET /matches/{id}/stats` | `full_name` y `jersey_number` del jugador | Detalle de partido sin pedir plantillas (resuelve §3.3) |

### 4.4 Login

El front usa `supabase.auth.signInWithPassword` directamente, que es la alternativa válida de RF-01.
El backend valida esos tokens (ES256, vía JWKS del proyecto). No hace falta `POST /auth/login`.

### 4.5 Variables de entorno del front (`.env.local`)

```env
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=https://wrewdoqrdadjvflceqeu.supabase.co
VITE_SUPABASE_ANON_KEY=sb_publishable_w5uMo9tFnLD3CXl-ZPLn-g_2xqIyves
```

La llave publicable es segura en el navegador: con RLS activo no puede leer las tablas. El backend ya
permite CORS desde `http://localhost:5173` (Vite) y `http://localhost:3000`.

---

## 5. ⚪ Funcionalidad pendiente en el front (el endpoint ya existe)

| Pantalla | RF | Endpoints | Estado en el front |
|----------|----|-----------|--------------------|
| Lista de clubes (pública) | RF-17b | `GET /clubs` | No existe |
| Perfil e historial del club | RF-17b | `GET /clubs/{id}`, `/players`, `/history` | No existe |
| Carrera del jugador por torneo | RF-19 | `GET /players/{id}/stats` → `by_tournament` | Solo muestra totales |
| Admin: CRUD de clubes + logo + coach | RF-21, RF-22 | `/clubs`, `POST /clubs/{id}/logo` | No existe |
| Admin: plantilla de un club (+ transferencias) | RF-41 | `/clubs/{id}/players`, `PATCH /players/{id}` con `club_id` | No existe (`RosterManager` es reutilizable) |
| Admin: inscribir clubes al torneo | RF-22b | `POST /tournaments/{id}/teams` `{club_ids}` | Placeholder |
| Admin: generar rol de juegos + jornadas | RF-23, RF-24 | `POST /tournaments/{id}/schedule/generate`, `/rounds` | Placeholder |
| Admin: CRUD de partidos + capturar resultado | RF-25, RF-26 | `/matches`, `PUT /matches/{id}/result` | Placeholder |
| Admin: ajustes de tabla | RF-27 | `/standings/adjustments` | Placeholder |
| Admin: hoja de captura de estadísticas | RF-28 | `GET/PUT /matches/{id}/stats` | Placeholder |
| Admin: finanzas | RF-29 a RF-31 | `/finance/summary`, `/finance/movements`, `/finance/registration-fees` | Placeholder |
| Admin: usuarios | RF-32 | `/users` | Placeholder |

Rutas del mapa de pantallas (RF §8) que faltan en `App.tsx`: `/clubes`, `/clubes/:id`,
`/admin/clubes`, `/admin/clubes/:id/jugadores` y `/coach/clubes/:id` (hoy existe `/coach/equipos/:id`).

---

## 6. ✅ Lo que ya está alineado

- **Errores:** `ApiError` distingue bien `detail` como texto (regla de negocio) y como lista (validación
  con `loc`). Coincide con el backend, incluidos 401, 403, 404, 409 y 422.
- **Respuestas vacías:** el cliente maneja `204` sin cuerpo en los `DELETE`.
- **Torneos:** el payload de `TournamentForm` coincide con `TournamentCreate`/`TournamentUpdate`
  (sin `points_draw`, que ya no existe). El backend rechaza campos extra, y el front no los envía.
- **Tabla de posiciones:** los campos de `StandingRow` coinciden con `StandingView`.
- **Jornadas y partidos:** `GET /rounds` y `GET /matches` con los filtros `round_id`, `team_id` y
  `status` coinciden. También `bye_team_id` y `winner_team_id`.
- **Forfeit:** `MatchCard` muestra "Forfeit (21-0)" y el backend fija ese marcador.
- **Dinero:** `formatMoney` acepta texto (`"700.00"`), que es como lo envía el backend.
- **Detalle y roster público de equipo:** `GET /teams/{id}` y `GET /teams/{id}/players` siguen
  existiendo y funcionan con el id de la inscripción.
- **Guardas por rol:** `ProtectedRoute` redirige según `GET /me` → `role`.

---

## 7. Orden sugerido de corrección

1. **§1.3 y §1.1–1.2:** alta de jugadores y panel del coach sobre clubes. Es lo que desbloquea el uso real.
2. **§1.4:** pestaña Estadísticas.
3. **§2:** actualizar `types/api.ts`, idealmente generándolo desde el OpenAPI.
4. **§3.1 y §3.2:** fechas y leyenda de desempate. Son cambios de una línea.
5. **§5:** construir el admin empezando por **Clubes → Inscripciones → Generar rol → Resultados**,
   que es el flujo mínimo para operar un torneo.
