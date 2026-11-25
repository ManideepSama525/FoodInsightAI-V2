"""Optional authenticated FoodInsightAI recipe proxy, isolated from stored recipes.

Only explicitly configured, local inference hosts are allowed. The independent
inference service provides its own token authentication and quality gate.
"""
import logging
import os
from typing import Annotated
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field

from backend.app.core.auth import get_current_user
from backend.app.models.user import User
from backend.app.models.user_food_profile import UserFoodProfile
from backend.app.db.session import get_db
from backend.app.schemas.food_profile import FoodSafetyRead
from backend.app.services.recipe_generation_constraints import build_constraints
from backend.app.services.generated_recipe_safety import (
    blocked_matches, screen_requested_title, screen_generated_recipe,
)

router = APIRouter(prefix="/recipes", tags=["recipe-generation"])
logger = logging.getLogger(__name__)

class RecipeGenerationRequest(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    max_new_tokens: int = Field(default=512, ge=256, le=640)

class RecipeGenerationResult(BaseModel):
    title: str
    answer: str
    ingredients: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    model: str
    adapter: str | None = None
    note: str = "AI-generated recipe. Verify cooking times, ingredients, allergens and dietary suitability."
    safety: FoodSafetyRead | None = None
    quality_warnings: list[str] = Field(default_factory=list)

@router.post("/generate", response_model=RecipeGenerationResult)
def generate_recipe(
    payload: RecipeGenerationRequest,
    user: Annotated[User, Depends(get_current_user)],
    db: Annotated[Session, Depends(get_db)],
):
    if os.getenv("FOOD_RECIPE_GENERATION_ENABLED", "0") != "1":
        raise HTTPException(status_code=503, detail="Recipe generation is disabled.")

    token = os.getenv("RECIPE_SERVICE_TOKEN", "")
    if len(token) < 32:
        raise HTTPException(status_code=503, detail="Recipe inference authentication is not configured.")

    raw_url = os.getenv(
        "FOOD_RECIPE_INFERENCE_URL", "http://host.docker.internal:8023"
    ).rstrip("/")
    parts = urlsplit(raw_url)
    if (
        parts.scheme != "http"
        or parts.hostname not in {"host.docker.internal", "recipe-inference", "127.0.0.1"}
        or parts.port != 8023
        or parts.username or parts.password
        or parts.path or parts.query or parts.fragment
    ):
        raise HTTPException(status_code=503, detail="Recipe inference URL is not configured safely.")

    # Query is scoped strictly to the authenticated user. Do not send the
    # raw Food Profile or user identifiers to the inference service.
    profile = db.scalar(
        select(UserFoodProfile).where(UserFoodProfile.user_id == user.id)
    )
    preflight = screen_requested_title(payload.title, profile)
    preflight_conflicts = blocked_matches(preflight)
    if preflight_conflicts:
        raise HTTPException(status_code=409, detail={
            "code": "RECIPE_REQUEST_CONFLICT",
            "message": "Requested dish may conflict with your saved Food Profile. Please choose a suitable alternative or review the restriction.",
            "assessment": preflight.model_dump(),
        })

    try:
        with httpx.Client(
            timeout=httpx.Timeout(connect=5, read=235, write=5, pool=5),
            follow_redirects=False,
            trust_env=False,
        ) as client:
            response = client.post(
                raw_url + "/generate-recipe",
                json={**payload.model_dump(), **build_constraints(profile)},
                headers={"X-Recipe-Service-Token": token},
            )
        if response.status_code != 200:
            logger.warning("Recipe inference responded with HTTP %s", response.status_code)
            raise HTTPException(status_code=503, detail="Recipe inference unavailable or output rejected.")
        result = response.json()
        if result.get("success") is not True or result.get("adapter") is not None:
            raise ValueError("Unexpected inference result")
        output = RecipeGenerationResult.model_validate(result)
        if not output.ingredients or not output.steps:
            raise ValueError("Incomplete recipe")
        assessment, issues = screen_generated_recipe(
            payload.title, output.ingredients, output.steps, output.answer, profile
        )
        conflicts = blocked_matches(assessment)
        if conflicts:
            raise HTTPException(status_code=409, detail={
                "code": "GENERATED_RECIPE_CONFLICT",
                "message": "Generated ingredients or cooking steps conflict with your saved Food Profile. The recipe was withheld.",
                "assessment": assessment.model_dump(),
            })
        critical_quality_issue = any(
            issue.startswith("Repeated ingredient detected")
            or issue.startswith("Named main ingredient is absent")
            or issue.startswith("Unsupported absolute")
            for issue in issues
        )
        if critical_quality_issue:
            raise ValueError("Generated recipe failed additional quality checks")
        output.safety = assessment
        output.quality_warnings = issues
        output.note = (
            "AI-generated recipe. Personalized screening cannot establish allergen "
            "safety or rule out cross-contact. Check every ingredient and label."
            if profile is not None else
            "AI-generated recipe. No personal Food Profile was found; "
            "allergen and dietary safety cannot be established."
        )
        return output
    except HTTPException:
        raise
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Recipe inference failed: %s", type(exc).__name__)
        raise HTTPException(status_code=503, detail="Recipe inference unavailable.") from exc
