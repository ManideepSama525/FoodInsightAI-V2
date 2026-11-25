from fastapi import APIRouter

from backend.app.api.routes.auth import router as auth_router
from backend.app.api.routes.diary import router as diary_router
from backend.app.api.routes.health import router as health_router
from backend.app.api.routes.freshness import router as freshness_router
from backend.app.api.routes.food_authenticity import router as food_authenticity_router
from backend.app.api.routes.food_fraud import router as food_fraud_router
from backend.app.api.routes.knowledge_graph import router as knowledge_graph_router
from backend.app.api.routes.food_profile import router as food_profile_router
from backend.app.api.routes.nutrition import router as nutrition_router
from backend.app.api.routes.recipes import router as recipes_router
from backend.app.api.routes.recognition import router as recognition_router
from backend.app.api.routes.rag import router as rag_router
from backend.app.api.routes.regulatory import router as regulatory_router
from backend.app.api.routes.uploads import router as uploads_router

api_router = APIRouter()
api_router.include_router(health_router, tags=["health"])
api_router.include_router(auth_router)
api_router.include_router(diary_router)
api_router.include_router(uploads_router)
api_router.include_router(nutrition_router)
api_router.include_router(recognition_router)
api_router.include_router(freshness_router)
api_router.include_router(rag_router)
api_router.include_router(regulatory_router)
api_router.include_router(recipes_router)

api_router.include_router(food_profile_router)


api_router.include_router(knowledge_graph_router)




api_router.include_router(food_authenticity_router)
api_router.include_router(food_fraud_router)

from backend.app.api.routes.sentinel_response import router as sentinel_response_router
api_router.include_router(sentinel_response_router)

from backend.app.api.routes.recipe_generation import router as recipe_generation_router
api_router.include_router(recipe_generation_router)
