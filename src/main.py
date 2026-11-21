"""Точка входа консольного прототипа ПК-01."""

from datetime import UTC
from datetime import datetime

from accounts import Accounts
from cli import Console
from conferences.service import Conferences

if __name__ == "__main__":
    Console(
        Accounts("admin@example.test", "Admin-demo-2026"),
        Conferences(lambda: datetime.now(UTC)),
    ).run()
