"""Учётные записи администратора и организаторов консольного прототипа."""

from dataclasses import dataclass
from dataclasses import field
from enum import StrEnum
from hashlib import scrypt
from secrets import compare_digest
from secrets import token_bytes


class Role(StrEnum):
    """Роль локальной учётной записи."""

    ADMIN = "администратор"
    HOST = "организатор"


@dataclass
class Account:
    """Профиль пользователя и данные для проверки пароля."""

    email: str
    role: Role
    salt: bytes = field(repr=False)
    digest: bytes = field(repr=False)
    blocked: bool = False


class Accounts:
    """Хранит учётные записи в памяти и проверяет полномочия администратора."""

    def __init__(self, admin_email: str, admin_password: str) -> None:
        """Создаёт начального администратора."""
        self._entries: dict[str, Account] = {}
        self._create(admin_email, admin_password, Role.ADMIN)

    def authenticate(self, email: str, password: str) -> Account:
        """Возвращает активную учётную запись с подходящим паролем."""
        account = self._entries.get(email.strip().lower())
        if (
            account is None
            or account.blocked
            or not 12 <= len(password) <= 128
            or not matches_password(account, password)
        ):
            raise ValueError("Не удалось войти. Проверьте адрес и пароль.")
        return account

    def add_host(self, admin: Account, email: str, password: str) -> Account:
        """Создаёт учётную запись организатора."""
        self._require_admin(admin)
        return self._create(email, password, Role.HOST)

    def set_blocked(self, admin: Account, email: str, blocked: bool) -> Account:
        """Блокирует или разблокирует учётную запись организатора."""
        self._require_admin(admin)
        account = self._entries.get(email.strip().lower())
        if account is None or account.role != Role.HOST:
            raise ValueError("Организатор с таким адресом не найден.")
        account.blocked = blocked
        return account

    def _create(self, email: str, password: str, role: Role) -> Account:
        """Проверяет реквизиты и сохраняет хеш пароля с солью."""
        account = build_account(email, password, role)
        if account.email in self._entries:
            raise ValueError("Этот адрес уже используется.")
        self._entries[account.email] = account
        return account

    def _require_admin(self, account: Account) -> None:
        """Разрешает управление профилями активному администратору."""
        if (
            self._entries.get(account.email) is not account
            or account.role != Role.ADMIN
            or account.blocked
        ):
            raise ValueError("Действие доступно администратору.")


def build_account(email: str, password: str, role: Role) -> Account:
    """Проверяет реквизиты и формирует профиль с индивидуальной солью."""
    address = email.strip().lower()
    user, separator, domain = address.partition("@")
    if (
        not (user and separator and domain)
        or "@" in domain
        or len(address) > 254
        or any(char.isspace() for char in address)
    ):
        raise ValueError("Введите адрес электронной почты.")
    if not 12 <= len(password) <= 128:
        raise ValueError("Пароль должен содержать от 12 до 128 символов.")
    salt = token_bytes(16)
    return Account(address, role, salt, _digest(password, salt))


def matches_password(account: Account, password: str) -> bool:
    """Сравнивает вычисленный хеш с хешем профиля."""
    return compare_digest(account.digest, _digest(password, account.salt))


def _digest(password: str, salt: bytes) -> bytes:
    """Вычисляет хеш пароля средствами стандартной библиотеки."""
    return scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
