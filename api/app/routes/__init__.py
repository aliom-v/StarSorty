from fastapi import APIRouter

from .health import router as health_router
from .tasks import router as tasks_router
from .sync import router as sync_router
from .repos import router as repos_router
from .classify import router as classify_router
from .export import router as export_router
from .taxonomy import router as taxonomy_router
from .settings import router as settings_router
from .stats import router as stats_router
from .training import router as training_router
from .user import router as user_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(tasks_router)
api_router.include_router(sync_router)
api_router.include_router(classify_router)
api_router.include_router(repos_router)
api_router.include_router(export_router)
api_router.include_router(taxonomy_router)
api_router.include_router(settings_router)
api_router.include_router(stats_router)
api_router.include_router(training_router)
api_router.include_router(user_router)
