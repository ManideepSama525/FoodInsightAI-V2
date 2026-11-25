"""Isolated base Qwen recipe service. Does not touch the FoodInsightAI backend.

Strict output validation; service returns 422 if content is incomplete or unsuitable.
"""
from dataclasses import replace
from typing import Literal
import logging
import os
import threading
from pathlib import Path
from hmac import compare_digest

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .quality import check
from .inference.generator import generate_chat
from .inference.parsing import recipe_format, split_sections
from .inference.settings import get_settings
from .inference import model_loader

app = FastAPI(title='FoodInsightAI Base Recipe Inference', docs_url=None, redoc_url=None, openapi_url=None)
_lock = threading.Lock()


# These are standardized restriction labels, not Food Profile records.
AvoidCategory = Literal[
    'milk', 'egg', 'peanut', 'tree nuts', 'wheat', 'gluten', 'soy',
    'fish', 'crustacean shellfish', 'molluscan shellfish', 'sesame',
    'lactose', 'chickpea', 'onion', 'garlic', 'mustard', 'celery',
]
DietCategory = Literal['vegan', 'vegetarian', 'jain', 'eggetarian']


class Request(BaseModel):
    title: str = Field(min_length=2, max_length=120)
    max_new_tokens: int = Field(default=512, ge=256, le=640)
    avoid_ingredients: list[AvoidCategory] = Field(default_factory=list, max_length=20)
    dietary_styles: list[DietCategory] = Field(default_factory=list, max_length=4)


def recipe_messages(
    title: str,
    avoid_ingredients: list[str] | None = None,
    dietary_styles: list[str] | None = None,
) -> list[dict]:
    """Constrained recipe prompt: advisory only, never an allergen-safety guarantee."""
    avoid = sorted(set(avoid_ingredients or []))
    styles = set(dietary_styles or [])
    vegetarian = any(word in title.casefold() for word in (
        'vegetable', 'vegetarian', 'vegan', 'veg ', 'veg-', 'paneer',
    )) or bool(styles.intersection({'vegan', 'vegetarian', 'jain', 'eggetarian'}))
    diet = (
        'All ingredients and steps must be vegetarian. Exclude chicken, meat, fish, seafood, '
        'fish sauce, meat stock and animal gelatin. ' if vegetarian else ''
    )
    if 'vegan' in styles:
        diet += 'Vegan: exclude all dairy, paneer, ghee, eggs, honey and other animal products. '
    if 'jain' in styles:
        diet += 'Jain-style restriction: exclude onion, garlic, potato, carrot, other root vegetables, eggs and meat. '
    if 'eggetarian' in styles:
        diet += 'Eggetarian: eggs may be included; meat, fish and seafood must be excluded. '
    if avoid:
        diet += 'Exclude these ingredients and their derivatives from BOTH the ingredient list and cooking steps: '
        diet += ', '.join(avoid) + '. Do not suggest substitutions containing them. '
    rice = (
        'Include rice and suitable liquid quantities with fully explained cooking steps. '
        if any(word in title.casefold() for word in ('pulao', 'pilaf', 'biryani', 'fried rice')) else ''
    )
    return [
        {'role': 'system', 'content': (
            'You are a practical home recipe writer. Produce one complete recipe in exactly two sections. '
            'Never claim allergen freedom, dietary verification, medical or nutrition safety. '
            'Do not quote or reveal any dietary restriction metadata in the recipe.'
        )},
        {'role': 'user', 'content': (
            f'Write a complete recipe for: {title}.\n'
            f'{diet}{rice}'
            'Respond using only these two sections:\n'
            'Ingredients:\n- quantity ingredient\n- quantity ingredient\n'
            'Preparation Steps:\n1. First cooking action.\n2. Next cooking action.\n'
            'Use 5 to 9 distinct, practical ingredients and 4 to 7 short, complete numbered steps. '
            'Do not add prefatory text, safety claims, optional substitutions or unrelated dishes.'
        )},
    ]


@app.get('/healthz')
def health():
    return {'status': 'ok', 'inference_model': 'base', 'ready': model_loader.is_ready()}


@app.post('/generate-recipe')
def generate(request: Request, x_recipe_service_token: str | None = Header(default=None)):
    secret = os.environ.get('RECIPE_SERVICE_TOKEN', '')
    if not secret or not x_recipe_service_token or not compare_digest(secret, x_recipe_service_token):
        raise HTTPException(status_code=401, detail='Service authorization required')
    if not _lock.acquire(blocking=False):
        raise HTTPException(status_code=429, detail='Recipe inference busy')
    try:
        settings = replace(get_settings(), adapter_path=None, load_in_4bit=True,
                           compute_dtype='float16', enable_thinking=False,
                           do_sample=False, max_new_tokens=512)
        if not settings.base_model_local or not (Path(settings.base_model_local) / 'config.json').is_file():
            raise HTTPException(status_code=503, detail='Local Qwen base model missing')
        title = request.title.strip()
        generation = generate_chat(recipe_messages(
            title, request.avoid_ingredients, request.dietary_styles,
        ),
                                   max_new_tokens=request.max_new_tokens,
                                   timeout_s=190, settings=settings)
        answer = generation.get('answer', '')
        sections = split_sections(answer)
        result = {
            'title': title, 'answer': answer,
            'ingredients': sections['ingredients'], 'steps': sections['steps'],
            'format': recipe_format(answer),
        }
        problems = check(title, result)
        if problems:
            logging.warning('Recipe quality gate rejected output; reasons=%s', problems)
            raise HTTPException(status_code=422, detail='Generated recipe did not pass structural checks; try another dish')
        return {'success': True, 'model': 'Qwen/Qwen3-4B', 'adapter': None,
                **result, 'note': 'AI-generated. Not verified for allergies, nutrition or food safety.'}
    except HTTPException:
        raise
    except Exception:
        logging.exception('Recipe inference failed')
        raise HTTPException(status_code=503, detail='Recipe model unavailable')
    finally:
        _lock.release()
