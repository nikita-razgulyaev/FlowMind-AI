"""Интеграция с ЮKassa (API v3). Документация: https://yookassa.ru/developers/

Запросы к API идут только с сервера. Подтверждение оплаты берётся из вебхука payment.succeeded,
но статус всегда перепроверяется запросом GET /payments/{id}, а не берётся из тела уведомления.
"""
import httpx

from ..config import settings
from ..models import Payment, User
from .base import PaymentProvider, PaymentResult

API = "https://api.yookassa.ru/v3"


def _amount(kopecks: int) -> dict:
    return {"value": f"{kopecks / 100:.2f}", "currency": "RUB"}


class YooKassaProvider(PaymentProvider):
    name = "yookassa"

    def _auth(self):
        if not (settings.yookassa_shop_id and settings.yookassa_secret_key):
            raise RuntimeError("ЮKassa не настроена: задайте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY")
        return (settings.yookassa_shop_id, settings.yookassa_secret_key)

    def _receipt(self, user: User, description: str, amount: int) -> dict:
        receipt = {
            "customer": {"email": user.email},
            "items": [{
                "description": description[:128],
                "quantity": "1.00",
                "amount": _amount(amount),
                "vat_code": settings.yookassa_vat_code,
                "payment_mode": "full_payment",
                "payment_subject": "service",
            }],
        }
        if settings.yookassa_tax_system_code:
            receipt["tax_system_code"] = settings.yookassa_tax_system_code
        return receipt

    async def _post(self, body: dict, idempotency_key: str) -> dict:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(f"{API}/payments", json=body, auth=self._auth(),
                                  headers={"Idempotence-Key": idempotency_key})
        if r.status_code >= 400:
            raise RuntimeError(f"ЮKassa вернула {r.status_code}: {r.text[:300]}")
        return r.json()

    def _parse(self, data: dict) -> PaymentResult:
        status = data.get("status")
        pm = data.get("payment_method") or {}
        card = pm.get("card") or {}
        saved = pm.get("saved") and pm.get("id")
        label = None
        if saved:
            label = f"{(card.get('card_type') or 'Карта')} •••• {card.get('last4', '')}".strip()
        confirmation = (data.get("confirmation") or {}).get("confirmation_url")
        mapped = {"succeeded": "succeeded", "canceled": "failed", "pending": "pending",
                  "waiting_for_capture": "pending"}.get(status, "pending")
        reason = None
        if status == "canceled":
            details = data.get("cancellation_details") or {}
            reason = details.get("reason") or "Платёж отменён"
        return PaymentResult(
            status=mapped, provider_payment_id=data.get("id"), confirmation_url=confirmation,
            failure_reason=reason, payment_method_id=pm.get("id") if saved else None,
            payment_method_label=label,
        )

    async def create_payment(self, *, payment: Payment, user: User, description: str, return_url: str) -> PaymentResult:
        body = {
            "amount": _amount(payment.amount),
            "capture": True,
            "confirmation": {"type": "redirect", "return_url": return_url},
            "description": description[:128],
            "save_payment_method": True,
            "metadata": {"payment_id": str(payment.id), "user_id": str(user.id)},
        }
        if settings.yookassa_receipts:
            body["receipt"] = self._receipt(user, description, payment.amount)
        return self._parse(await self._post(body, payment.idempotency_key))

    async def fetch_payment(self, provider_payment_id: str) -> PaymentResult:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.get(f"{API}/payments/{provider_payment_id}", auth=self._auth())
        if r.status_code >= 400:
            raise RuntimeError(f"ЮKassa вернула {r.status_code}: {r.text[:300]}")
        return self._parse(r.json())

    async def charge_saved(self, *, payment: Payment, user: User, payment_method_id: str, description: str) -> PaymentResult:
        body = {
            "amount": _amount(payment.amount),
            "capture": True,
            "payment_method_id": payment_method_id,
            "description": description[:128],
            "metadata": {"payment_id": str(payment.id), "user_id": str(user.id)},
        }
        if settings.yookassa_receipts:
            body["receipt"] = self._receipt(user, description, payment.amount)
        return self._parse(await self._post(body, payment.idempotency_key))
