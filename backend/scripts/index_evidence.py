import argparse
import json
import logging

from backend.app.db.session import SessionLocal
from backend.app.services.vector_evidence import index_evidence_documents

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Index evidence into Neo4j vector search.")
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument(
        "--max-documents",
        type=int,
        default=None,
        help="Maximum eligible evidence documents to index; omit for all documents.",
    )
    args = parser.parse_args()

    db = SessionLocal()
    try:
        result = index_evidence_documents(
            db,
            batch_size=args.batch_size,
            max_documents=args.max_documents,
        )
        print(json.dumps(result, indent=2, sort_keys=True))
        logger.info("Evidence vector indexing finished.")
    except Exception:
        db.rollback()
        logger.exception("Evidence vector indexing failed.")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()