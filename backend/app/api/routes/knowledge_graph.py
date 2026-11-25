from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.core.auth import get_current_user
from backend.app.core.config import get_settings
from backend.app.db.session import get_db
from backend.app.models.user import User
from backend.app.services.knowledge_graph import knowledge_graph

router = APIRouter(prefix="/knowledge-graph", tags=["food knowledge graph"])

AuthenticatedUser = Annotated[User, Depends(get_current_user)]


@router.get("/status")
def graph_status(_user: AuthenticatedUser) -> dict[str, object]:
    return {
        "enabled": knowledge_graph.enabled,
        "connected": knowledge_graph.verify() if knowledge_graph.enabled else False,
        "database": "neo4j",
    }


@router.post("/sync")
def synchronize_graph(
    _user: AuthenticatedUser,
    db: Session = Depends(get_db),
) -> dict[str, int]:
    if get_settings().app_env == "production":
        raise HTTPException(
            status_code=404,
            detail="This endpoint is not available.",
        )

    try:
        return knowledge_graph.sync(db)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail="Knowledge graph synchronization failed",
        ) from exc


@router.get("/foods/{food_id}")
def food_neighborhood(
    food_id: int,
    _user: AuthenticatedUser,
) -> dict:
    try:
        result = knowledge_graph.food_neighborhood(food_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Food not found in knowledge graph")
    return result