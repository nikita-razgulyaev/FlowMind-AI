from dataclasses import dataclass
from typing import Optional

from ..models import Payment, User


@dataclass
class PaymentResult:
    status: str                                   # pending | requires_action | succeeded | failed | canceled
    provider_payment_id: Optional[str] = None
    confirmation_url: Optional[str] = None
    failure_reason: Optional[str] = None
    payment_method_id: Optional[str] = None       # сохранённый способ оплаты для автопродления
    payment_method_label: Optional[str] = None


class PaymentProvider:
    name = "base"

    async def create_payment(self, *, payment: Payment, user: User, description: str, return_url: str) -> PaymentResult:
        raise NotImplementedError

    async def fetch_payment(self, provider_payment_id: str) -> PaymentResult:
        raise NotImplementedError

    async def charge_saved(self, *, payment: Payment, user: User, payment_method_id: str, description: str) -> PaymentResult:
        raise NotImplementedError
