from fastapi import APIRouter

from app.api import auth, quests, runtime, reports, classes

api_router = APIRouter()

# Đăng ký các sub-router
api_router.include_router(auth.router)
api_router.include_router(quests.router)
api_router.include_router(runtime.router)
api_router.include_router(reports.router)
api_router.include_router(classes.router)




