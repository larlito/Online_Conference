"""Консольный интерфейс для проверки сценариев встречи в одном терминале."""

from collections.abc import Callable
from dataclasses import dataclass
from getpass import getpass
from shlex import split

from accounts import Account
from accounts import Accounts


@dataclass(frozen=True)
class Command:
    """Имя, формат, описание и обработчик команды."""

    syntax: str
    description: str
    action: Callable[..., str]


class Console:
    """Разбирает ввод, управляет текущим пользователем и выводит результаты."""

    def __init__(self, accounts: Accounts) -> None:
        """Подключает операции для текущего этапа."""
        self._accounts = accounts
        self._account: Account | None = None
        self._commands = (
            Command("login EMAIL", "войти, пароль вводится отдельно", self._login),
            Command("logout", "сбросить текущий вход", self._logout),
            Command("add-host EMAIL", "создать организатора", self._add_host),
            Command(
                "block EMAIL STATE", "заблокировать (on) или разблокировать (off)", self._block
            ),
        )
        self._by_name = {command.syntax.split()[0]: command for command in self._commands}

    def run(self) -> None:
        """Читает и выполняет команды до выхода из программы."""
        print("ПК-01 · Консольная платформа онлайн-конференций")
        print("Учебный вход: admin@example.test / Admin-demo-2026")
        print("help — список команд, exit — выход")
        while True:
            try:
                raw = input(f"{self._identity()}> ")
                if raw.strip() == "exit":
                    break
                result = self.execute(raw)
                if result:
                    print(result)
            except ValueError as error:
                print(f"Ошибка · {error}")
            except OSError as error:
                print(f"Ошибка ввода или вывода · {error}")
            except (EOFError, KeyboardInterrupt):
                print()
                break
        print("Работа завершена.")

    def execute(self, raw: str) -> str:
        """Проверяет формат одной команды и возвращает результат."""
        parts = split(raw)
        if not parts:
            return ""
        name, *arguments = parts
        if name == "help" and not arguments:
            return "\n".join(
                f"{command.syntax:<29} {command.description}" for command in self._commands
            )
        command = self._by_name.get(name)
        if command is None:
            raise ValueError("Неизвестная команда. Введите help.")
        parameters = command.syntax.split()[1:]
        required = sum(not parameter.startswith("[") for parameter in parameters)
        if not required <= len(arguments) <= len(parameters):
            raise ValueError(f"Формат команды · {command.syntax}")
        return command.action(*arguments)

    def _identity(self) -> str:
        """Возвращает подпись текущего пользователя для приглашения ввода."""
        if self._account is not None:
            return self._account.email
        return "ПК-01"

    def _login(self, email: str) -> str:
        """Открывает сессию администратора или организатора."""
        self._account = self._accounts.authenticate(email, getpass("Пароль: "))
        return f"Вход · {self._account.role}"

    def _logout(self) -> str:
        """Возвращает терминал в режим выбора пользователя."""
        self._account = None
        return "Текущий вход сброшен."

    def _add_host(self, email: str) -> str:
        """Запрашивает пароль и регистрирует организатора от имени администратора."""
        admin = self._current_account()
        account = self._accounts.add_host(admin, email, getpass("Пароль организатора: "))
        return f"Организатор создан · {account.email}"

    def _block(self, email: str, state: str) -> str:
        """Блокирует или разблокирует учётную запись организатора."""
        blocked = _switch(state)
        account = self._accounts.set_blocked(self._current_account(), email, blocked)
        return f"{account.email} · {'заблокирован' if blocked else 'разблокирован'}"

    def _current_account(self) -> Account:
        """Возвращает текущую активную учётную запись."""
        if self._account is None or self._account.blocked:
            raise ValueError("Сначала войдите с помощью login.")
        return self._account


def _switch(value: str) -> bool:
    """Разбирает переключатель on или off."""
    if value not in {"on", "off"}:
        raise ValueError("Значение должно быть on или off.")
    return value == "on"
