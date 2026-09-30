# Liga Premier – Backend

API para administrar los torneos de **tocho bandera** de la Liga Premier: torneos, equipos, jugadores,
jornadas, partidos, tabla de posiciones automática y estadísticas por jugador.

**Stack:** FastAPI · Supabase (Postgres + Auth + Storage) · Pydantic v2

## Arquitectura

Arquitectura limpia: las dependencias apuntan hacia adentro y el dominio no conoce FastAPI ni Supabase.

```
app/
├── core/            Configuración, excepciones, validación de JWT
├── domain/          Entidades, enums, puertos (interfaces) y reglas puras
│   ├── standings.py     Cálculo de la tabla de posiciones
│   └── player_stats.py  Acumulado de estadísticas
├── application/     Casos de uso (servicios), DTOs de entrada y modelos de lectura
├── infrastructure/  Adaptadores de Supabase: repositorios, Storage y Auth
└── api/             Routers HTTP (v1) e inyección de dependencias
supabase/migrations/ Esquema SQL
tests/               Tests con repositorios en memoria (no requieren Supabase)
```

Para cambiar de base de datos o agregar caché basta con otra implementación de los puertos de
`app/domain/repositories.py`, sin tocar los casos de uso.

## Roles

| Rol | Puede |
|-----|-------|
| **Público** (sin token) | Consultar torneos, equipos, rosters, jornadas, partidos, tabla y estadísticas |
| **admin** | CRUD completo: torneos, equipos (+logo), jornadas, partidos, resultados, ajustes de tabla, estadísticas y usuarios |
| **coach** | CRUD de jugadores **solo** de los equipos que tiene asignados (`teams.coach_user_id`) |

## Reglas de la tabla de posiciones

Se calcula siempre en tiempo real a partir de los partidos, así que nunca se desincroniza:

- Cuentan los partidos `finished` y `forfeit`. Los `scheduled`, `postponed` y `cancelled` (p. ej. por lluvia) no cuentan.
- Puntos por torneo configurables: `points_win` (2), `points_draw` (1), `points_loss` (0).
- En un forfeit pierde `forfeit_loser_team_id`, sin importar el marcador capturado.
- Desempate: puntos → diferencia → puntos a favor → menos puntos en contra → nombre.
- **Modificar la tabla:** se corrige el resultado (`PUT /matches/{id}/result`) o se registra un ajuste
  manual de puntos con su motivo (`POST /tournaments/{id}/standings/adjustments`), por ejemplo una multa.

## Puesta en marcha

1. **Base de datos:** ejecuta `supabase/migrations/20260929000000_init.sql` en el SQL Editor de Supabase
   (o con `supabase db push`). Crea las tablas, el trigger de perfiles y el bucket público `team-logos`.
2. **Variables:** copia `.env.example` a `.env` y llena `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `SUPABASE_SERVICE_ROLE_KEY`.
3. **Primer admin:** crea un usuario en *Authentication → Users* y promuévelo:
   ```sql
   update public.profiles set role = 'admin' where email = 'tu-correo@ejemplo.com';
   ```
   A partir de ahí, el admin crea coaches con `POST /api/v1/users`.
4. **Ejecutar:**
   ```bash
   python -m venv .venv && .venv\Scripts\activate   # Windows
   pip install -r requirements.txt
   uvicorn app.main:app --reload
   ```
   Documentación interactiva en http://localhost:8000/docs. Usa `POST /api/v1/auth/login` y pega el
   `access_token` en **Authorize**.

## Tests

```bash
pytest
```

## Endpoints principales (`/api/v1`)

| Recurso | Endpoints |
|---------|-----------|
| Auth | `POST /auth/login`, `GET /me`, `GET /me/teams` |
| Usuarios (admin) | `GET/POST /users`, `GET/PATCH/DELETE /users/{id}` |
| Torneos | `GET/POST /tournaments`, `GET/PATCH/DELETE /tournaments/{id}` |
| Equipos | `GET/POST /tournaments/{id}/teams`, `GET/PATCH/DELETE /teams/{id}`, `POST /teams/{id}/logo` |
| Jugadores | `GET/POST /teams/{id}/players`, `GET/PATCH/DELETE /players/{id}` |
| Jornadas | `GET/POST /tournaments/{id}/rounds`, `GET/PATCH/DELETE /rounds/{id}` |
| Partidos | `GET/POST /tournaments/{id}/matches` (filtros `round_id`, `team_id`, `status`), `GET/PATCH/DELETE /matches/{id}`, `PUT /matches/{id}/result` |
| Tabla | `GET /tournaments/{id}/standings`, `GET/POST /tournaments/{id}/standings/adjustments`, `PATCH/DELETE /standing-adjustments/{id}` |
| Estadísticas | `GET/PUT /matches/{id}/stats`, `DELETE /matches/{id}/stats/{player_id}`, `GET /players/{id}/stats`, `GET /tournaments/{id}/player-stats?sort_by=touchdowns&limit=10` |

Estadísticas por jugador (basadas en la hoja del ROL DE JUEGOS): asistencia, anotaciones (`touchdowns`),
pases de anotación (`td_passes`), intercepciones, capturas (`sacks`) y tackles.
