"""Единая точка входа для веб-приложения и демонстрационной консоли."""

import argparse
import os
from datetime import UTC
from datetime import datetime
from pathlib import Path

from accounts import Accounts
from cli import Console
from conferences.service import Conferences


def main() -> None:
    """Запускает веб-сервер или прежнюю консоль в режиме демонстрации."""
    parser = argparse.ArgumentParser(description="Online Conference")
    parser.add_argument("--cli", action="store_true", help="Запустить консольную демонстрацию")
    if parser.parse_args().cli:
        Console(
            Accounts("admin@example.test", "Admin-demo-2026"),
            Conferences(lambda: datetime.now(UTC)),
            Path("output"),
        ).run()
        return
    run_web()


def run_web() -> None:
    """Загружает веб-зависимости только при запуске сервера."""
    import uvicorn

    from api.application import create_app

    uvicorn.run(
        create_app(),
        host=os.environ.get("APP_HOST", "127.0.0.1"),
        port=int(os.environ.get("APP_PORT", "8000")),
    )


if __name__ == "__main__":
    main()
