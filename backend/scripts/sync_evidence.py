import json
import logging

from backend.app.db.session import SessionLocal
from backend.app.services.evidence import sync_evidence_documents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    db = SessionLocal()
    try:
        result = sync_evidence_documents(db)
        db.commit()
        print(json.dumps(result, indent=2, sort_keys=True))
        logger.info("Evidence synchronization committed successfully.")
    except Exception:
        db.rollback()
        logger.exception("Evidence synchronization failed; transaction rolled back.")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()