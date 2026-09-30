from fastapi import APIRouter

from app.api.v1.routers import auth, finance, matches, teams, tournaments, users

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(tournaments.router)
api_router.include_router(teams.router)
api_router.include_router(matches.router)
api_router.include_router(finance.router)
