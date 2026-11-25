from backend.app.db.base import Base
from backend.app.db.session import engine
from backend.app import models  # noqa: F401
from backend.app.models.security_ip_block import SecurityIPBlock  # noqa: F401

from backend.app.models.sentinel_login_hold import SentinelLoginHold  # noqa: F401
def initialize_database() -> None:
    Base.metadata.create_all(bind=engine)
