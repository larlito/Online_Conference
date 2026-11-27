"""Ожидаемые ошибки прикладных операций."""


class Problem(Exception):
    """Ошибка с HTTP-совместимым кодом и безопасным для пользователя пояснением."""

    def __init__(self, status: int, detail: str) -> None:
        """Сохраняет код и текст ошибки."""
        super().__init__(detail)
        self.status = status
