"""Точка входа консольного прототипа ПК-01."""

from accounts import Accounts
from cli import Console

if __name__ == "__main__":
    Console(
        Accounts("admin@example.test", "Admin-demo-2026"),
    ).run()
