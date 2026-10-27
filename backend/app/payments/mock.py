"""Имитация платёжного провайдера для демо. Деньги не списываются, номер карты нигде не сохраняется."""
import re
import uuid
from datetime import datetime, timezone

from ..models import Payment, User
from .base import PaymentProvider, PaymentResult

# Тестовые карты (как в песочницах реальных провайдеров)
CARD_SUCCESS = "4242424242424242"
CARD_DECLINED = "4000000000000002"
CARD_NO_FUNDS = "4000000000009995"
CARD_3DS = "4000000000003220"

TEST_CARDS = [
    {"number": "4242 4242 4242 4242", "result": "Успешная оплата"},
    {"number": "5555 5555 5555 4444", "result": "Успешная оплата (Mastercard)"},
    {"number": "4000 0000 0000 3220", "result": "Требуется подтверждение 3-D Secure"},
    {"number": "4000 0000 0000 0002", "result": "Отказ банка"},
    {"number": "4000 0000 0000 9995", "result": "Недостаточно средств"},
]


def luhn_ok(number: str) -> bool:
    digits = [int(c) for c in number][::-1]
    total = sum(d if i % 2 == 0 else (d * 2 - 9 if d * 2 > 9 else d * 2) for i, d in enumerate(digits))
    return total % 10 == 0


def card_brand(number: str) -> str:
    if number.startswith("4"):
        return "Visa"
    if re.match(r"^(5[1-5]|2[2-7])", number):
        return "Mastercard"
    if number.startswith("2"):
        return "Мир"
    return "Карта"


def evaluate_card(number: str) -> tuple[str, str | None]:
    """→ (status, reason). status: succeeded | requires_action | failed"""
    if number == CARD_DECLINED:
        return "failed", "Банк отклонил операцию"
    if number == CARD_NO_FUNDS:
        return "failed", "Недостаточно средств на карте"
    if number == CARD_3DS:
        return "requires_action", None
    return "succeeded", None


def method_for_card(number: str) -> tuple[str, str]:
    last4 = number[-4:]
    return f"mock_pm_{last4}_{uuid.uuid4().hex[:8]}", f"{card_brand(number)} •••• {last4}"


class MockProvider(PaymentProvider):
    name = "mock"

    async def create_payment(self, *, payment: Payment, user: User, description: str, return_url: str) -> PaymentResult:
        return PaymentResult(status="pending", provider_payment_id=f"mock_{uuid.uuid4().hex[:16]}")

    async def fetch_payment(self, provider_payment_id: str) -> PaymentResult:
        return PaymentResult(status="pending", provider_payment_id=provider_payment_id)

    async def charge_saved(self, *, payment: Payment, user: User, payment_method_id: str, description: str) -> PaymentResult:
        pid = f"mock_{uuid.uuid4().hex[:16]}"
        if "fail" in payment_method_id:
            return PaymentResult(status="failed", provider_payment_id=pid, failure_reason="Банк отклонил автосписание (демо)")
        return PaymentResult(status="succeeded", provider_payment_id=pid, payment_method_id=payment_method_id)
