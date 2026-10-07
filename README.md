# Liga Premier – Backend

API para administrar los torneos de **tocho bandera** de la Liga Premier: clubes, torneos, inscripciones, jugadores,
jornadas, rol de juegos automático, partidos, tabla de posiciones automática, estadísticas por jugador
y finanzas.

> Requerimientos funcionales para el frontend: [`docs/REQUERIMIENTOS_FUNCIONALES.md`](docs/REQUERIMIENTOS_FUNCIONALES.md)
>
> Medidas de seguridad y checklist de producción: [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md)

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
| **admin** | CRUD completo: clubes (+logo), torneos, inscripciones, jornadas, rol de juegos, partidos, resultados, ajustes de tabla, estadísticas, finanzas y usuarios |
| **coach** | CRUD de jugadores **solo** de los clubes que tiene asignados (`clubs.coach_user_id`) |

## Clubes e inscripciones

Un **club** es el equipo permanente (nombre, logo, coach y plantilla de jugadores). En cada torneo el
club se **inscribe** (`teams` = inscripción); partidos, tabla, estadísticas y finanzas se ligan a la
inscripción. Así se conserva el historial del club por torneo y la carrera de cada jugador.

## Reglas de la tabla de posiciones

Se calcula siempre en tiempo real a partir de los partidos, así que nunca se desincroniza:

- Cuentan los partidos `finished` y `forfeit`. Los `scheduled`, `postponed` y `cancelled` (p. ej. por lluvia) no cuentan.
- **No hay empates**: se juega tiempo extra. Un partido `finished` con marcador empatado se rechaza.
- Puntos por torneo configurables: `points_win` (2) y `points_loss` (0).
- **Forfeit**: pierde `forfeit_loser_team_id` con marcador fijo **21-0** (lo pone el sistema).
- Desempate: puntos → puntos a favor → diferencia → menos puntos en contra → nombre.
- **Modificar la tabla:** se corrige el resultado (`PUT /matches/{id}/result`) o se registra un ajuste
  manual de puntos con su motivo (`POST /tournaments/{id}/standings/adjustments`), por ejemplo una multa.

## Puesta en marcha

1. **Base de datos:** ejecuta **en orden** los archivos de `supabase/migrations/` en el SQL Editor de Supabase
   (o con `supabase db push`). Crean las tablas, el trigger de perfiles y el bucket público `team-logos`.
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
| Auth | `POST /auth/login`, `GET /me`, `GET /me/clubs` |
| Usuarios (admin) | `GET/POST /users`, `GET/PATCH/DELETE /users/{id}` |
| Torneos | `GET/POST /tournaments`, `GET/PATCH/DELETE /tournaments/{id}` |
| Clubes | `GET/POST /clubs`, `GET/PATCH/DELETE /clubs/{id}`, `POST /clubs/{id}/logo`, `GET /clubs/{id}/history` |
| Inscripciones | `GET/POST /tournaments/{id}/teams` (`club_ids`), `GET/DELETE /teams/{id}` |
| Jugadores | `GET/POST /clubs/{id}/players`, `GET /teams/{id}/players`, `GET/PATCH/DELETE /players/{id}` |
| Jornadas | `GET/POST /tournaments/{id}/rounds`, `GET/PATCH/DELETE /rounds/{id}`, `POST /tournaments/{id}/schedule/generate` |
| Partidos | `GET/POST /tournaments/{id}/matches` (filtros `round_id`, `team_id`, `status`), `GET/PATCH/DELETE /matches/{id}`, `PUT /matches/{id}/result` |
| Tabla | `GET /tournaments/{id}/standings`, `GET/POST /tournaments/{id}/standings/adjustments`, `PATCH/DELETE /standing-adjustments/{id}` |
| Estadísticas | `GET/PUT /matches/{id}/stats`, `DELETE /matches/{id}/stats/{player_id}`, `GET /players/{id}/stats`, `GET /tournaments/{id}/player-stats?sort_by=touchdowns&limit=10` |
| Finanzas (admin) | `GET /tournaments/{id}/finance/summary`, `GET/POST /tournaments/{id}/finance/movements`, `POST /tournaments/{id}/finance/registration-fees`, `PATCH/DELETE /finance/movements/{id}` |

Estadísticas por jugador (basadas en la hoja del ROL DE JUEGOS): asistencia, anotaciones (`touchdowns`),
pases de anotación (`td_passes`), intercepciones, capturas (`sacks`) y tackles.
