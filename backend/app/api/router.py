from fastapi import APIRouter

from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.diary import router as diary_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.knowledge_graph import router as knowledge_graph_router
from backend.app.api.routes.food_profile import router as food_profile_router
from backend.app.api.routes.nutrition import router as nutrition_router
from backend.app.api.routes.recipes import router as recipes_router
from backend.app.api.routes.recognition import router as recognition_router
from backend.app.api.routes.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(diary_router)
api_router.include_router(uploads_router)
api_router.include_router(nutrition_router)
api_router.include_router(recognition_router)
api_router.include_router(recipes_router)

api_router.include_router(food_profile_router)


api_router.include_router(knowledge_graph_router)
