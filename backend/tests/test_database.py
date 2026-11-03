from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from backend.app.db.base import Base
from backend.app.models import Food, FoodNutrient

def test_food_and_nutrient_persist_with_nullable_amount() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        food = Food(name="Test lentils", normalized_name="test lentils", source="test")
        food.nutrients.append(FoodNutrient(nutrient_key="protein", display_name="Protein", amount=None, unit="g", source="test"))
        session.add(food)
        session.commit()
        stored = session.query(Food).one()
        assert stored.name == "Test lentils"
        assert stored.nutrients[0].amount is None
