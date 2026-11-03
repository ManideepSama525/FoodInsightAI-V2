from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app import models  # noqa: F401

def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
