import asyncio
from datetime import UTC, datetime

from app.database import init_db
from app.services.background_collection_service import run_background_collection_loop


def main() -> None:
    print(f"[collector] {datetime.now(UTC).isoformat()} worker booting", flush=True)
    init_db()
    asyncio.run(run_background_collection_loop())


if __name__ == "__main__":
    main()
