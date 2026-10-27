from typing import Optional

from ..config import settings
from .base import PaymentProvider, PaymentResult  # noqa: F401
from .mock import MockProvider
from .yookassa import YooKassaProvider


def get_provider(name: Optional[str] = None) -> PaymentProvider:
    """Провайдер выбирается переменной PAYMENT_PROVIDER. Чтобы подключить другого — добавьте класс и ветку здесь."""
    name = name or settings.payment_provider
    if name == "yookassa":
        return YooKassaProvider()
    return MockProvider()
