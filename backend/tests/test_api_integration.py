from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.db.base import Base
from backend.app.db.session import get_db
from backend.app.main import app
from backend.app.models.food import Food, FoodNutrient

engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
TestingSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base.metadata.create_all(bind=engine)

def override_get_db():
    db = TestingSession()
    try:
        yield db
    finally:
        db.close()

app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)

def setup_food():
    with TestingSession() as db:
        db.query(FoodNutrient).delete()
        db.query(Food).delete()
        db.commit()
        food = Food(name="Test cooked rice", normalized_name="test cooked rice", source="test")
        food.nutrients.append(FoodNutrient(
            nutrient_key="protein", display_name="Protein", amount=2.5,
            unit="g", basis_g=100, source="test",
        ))
        db.add(food)
        db.commit()
        return food.id

def test_catalog_search_and_portion_calculation():
    food_id = setup_food()
    response = client.get("/api/v1/nutrition/foods", params={"q": "rice"})
    assert response.status_code == 200
    assert response.json()[0]["name"] == "Test cooked rice"
    calculated = client.get(f"/api/v1/nutrition/foods/{food_id}/calculate", params={"quantity_g": 200})
    assert calculated.status_code == 200
    assert float(calculated.json()["nutrients"][0]["amount"]) == 5.0

def test_catalog_can_be_listed_for_recipe_selector():
    setup_food()
    response = client.get("/api/v1/nutrition/foods")
    assert response.status_code == 200
    assert len(response.json()) == 1

def test_recipe_create_and_per_serving_nutrition():
    food_id = setup_food()
    response = client.post("/api/v1/recipes", json={
        "name": "Rice bowl", "servings": 2,
        "ingredients": [{"food_id": food_id, "quantity_g": 200}],
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Rice bowl"
    assert float(data["nutrition_per_recipe"][0]["amount"]) == 5.0
    assert float(data["nutrition_per_serving"][0]["amount"]) == 2.5
    detail = client.get(f"/api/v1/recipes/{data['id']}")
    assert detail.status_code == 200

def test_recipe_rejects_unknown_food_id():
    response = client.post("/api/v1/recipes", json={
        "name": "Invalid recipe", "servings": 1,
        "ingredients": [{"food_id": 999999, "quantity_g": 100}],
    })
    assert response.status_code == 404

def test_recognition_reports_model_not_configured_instead_of_guessing():
    get_image = BytesIO()
    Image.new("RGB", (32, 32), "green").save(get_image, format="PNG")
    response = client.post(
        "/api/v1/recognition/predict",
        files={"file": ("meal.png", get_image.getvalue(), "image/png")},
    )
    assert response.status_code == 503
