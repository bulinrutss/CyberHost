"""Integração com Abacate Pay (API v2) — checkout transparente PIX."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
from fastapi import HTTPException

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

# Bump when changing payment integration (helps confirm uvicorn reloaded).
INTEGRATION_REV = "2026-08-25-sec007-charge-bind"

PIX_EXPIRES_IN_SECONDS = 3600
PAID_STATUSES = {"PAID", "APPROVED"}
ORDER_KIND_VPS = "vps"
ORDER_KIND_GAME = "game"
ORDER_KIND_CLOUD = "cloud"
ORDER_KIND_WEB = "web"
_INVALID_CHARGE_PREFIXES = ("log_", "test-", "test_", "free-")
_METADATA_KEYS = {
    ORDER_KIND_VPS: ("order_id", "orderId"),
    ORDER_KIND_GAME: ("game_order_id", "gameOrderId"),
    ORDER_KIND_CLOUD: ("cloud_storage_order_id", "cloudStorageOrderId"),
    ORDER_KIND_WEB: ("web_order_id", "webOrderId"),
}

ABACATEPAY_PUBLIC_KEY = (
    "t9dXRhHHo3yDEj5pVDYz0frf7q6bMKyMRmxxCPIPp3RCplBfXRxqlC6ZpiWmOqj4L63qEaeUOtrCI8P0VMUgo6iIga2ri9ogaHFs0WIIywSMg0q7RmBfybe1E5XJcfC4IW3alNqym0tXoAKkzvfEjZxV6bE0oG2zJrNNYmUCKZyV0KZ3JS8Votf9EAWWYdiDkMkpbMdPggfh1EqHlVkMiTady6jOR3hyzGEHrIz2Ret0xHKMbiqkr9HS1JhNHDX9"
)


@dataclass
class CheckoutResult:
    external_id: str
    checkout_url: str | None = None
    status: str = "pending"
    pix_br_code: str | None = None
    pix_qr_base64: str | None = None
    pix_expires_at: datetime | None = None


def parse_pix_expires_at(value: object) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
    return parsed


def has_live_pix(order: object) -> bool:
    br_code = getattr(order, "pix_br_code", None)
    external_id = getattr(order, "payment_external_id", None)
    if not br_code or not external_id:
        return False
    expires_at = getattr(order, "pix_expires_at", None)
    if expires_at is None:
        return True
    return datetime.utcnow() < expires_at


def apply_checkout_result(order: object, checkout: CheckoutResult) -> None:
    order.payment_external_id = checkout.external_id
    order.payment_checkout_url = checkout.checkout_url
    if hasattr(order, "payment_provider"):
        order.payment_provider = "abacatepay"
    if hasattr(order, "pix_br_code"):
        order.pix_br_code = checkout.pix_br_code
        order.pix_qr_base64 = checkout.pix_qr_base64
        order.pix_expires_at = checkout.pix_expires_at


class AbacatePayService:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or get_settings()

    @property
    def enabled(self) -> bool:
        return self.settings.abacatepay_enabled and bool(self.settings.abacatepay_api_key)

    @property
    def payment_bypass_enabled(self) -> bool:
        environment = self.settings.app_environment.strip().lower()
        return self.settings.skip_payment_for_testing and environment not in {
            "production",
            "prod",
        }

    @property
    def payments_required(self) -> bool:
        return not self.payment_bypass_enabled

    def _client(self) -> httpx.Client:
        if not self.enabled:
            raise HTTPException(
                status_code=503,
                detail="Provedor de pagamento indisponível",
            )
        return httpx.Client(
            base_url=self.settings.abacatepay_base_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.settings.abacatepay_api_key}"},
            timeout=30,
        )

    def _raw_request(
        self,
        method: str,
        path: str,
        *,
        json: dict | None = None,
        params: dict | None = None,
    ) -> tuple[int, dict]:
        with self._client() as client:
            response = client.request(method, path, json=json, params=params)
            try:
                body = response.json()
            except Exception:
                body = {"success": False, "error": response.text, "data": None}
            return response.status_code, body

    def _request(self, method: str, path: str, *, json: dict | None = None, params: dict | None = None) -> dict:
        status, body = self._raw_request(method, path, json=json, params=params)
        if status >= 400:
            logger.error("AbacatePay %s %s falhou (%s): %s", method, path, status, body)
            raise HTTPException(
                status_code=502,
                detail=f"Abacate Pay: {body.get('error') or body}",
            )
        if not body.get("success"):
            raise HTTPException(
                status_code=502,
                detail=f"Abacate Pay: {body.get('error') or 'erro desconhecido'}",
            )
        return self.extract_charge_payload(body)

    @staticmethod
    def extract_charge_payload(body: dict) -> dict:
        data = body.get("data")
        payload = dict(data) if isinstance(data, dict) else {}
        if payload.get("devMode") is None and "devMode" in body:
            payload["devMode"] = body.get("devMode")
        return payload

    @staticmethod
    def is_explicit_live_charge(charge: dict) -> bool:
        if not isinstance(charge, dict) or "devMode" not in charge:
            return False
        value = charge.get("devMode")
        if isinstance(value, str):
            return value.strip().lower() in {"false", "0", "no"}
        return value is False

    def _post(self, path: str, payload: dict) -> dict:
        return self._request("POST", path, json=payload)

    def get_checkout(self, checkout_id: str) -> dict:
        return self._request("GET", "/checkouts/get", params={"id": checkout_id})

    def get_transparent(self, charge_id: str) -> dict:
        return self._request("GET", "/transparents/check", params={"id": charge_id})

    @staticmethod
    def is_usable_charge_id(charge_id: str | None) -> bool:
        text = (charge_id or "").strip()
        return bool(text) and not text.startswith(_INVALID_CHARGE_PREFIXES)

    def fetch_charge(self, charge_id: str) -> dict:
        if not self.is_usable_charge_id(charge_id):
            raise HTTPException(status_code=400, detail="Cobrança inválida")
        if charge_id.startswith("pix_"):
            return self.get_transparent(charge_id)
        try:
            return self.get_transparent(charge_id)
        except HTTPException:
            return self.get_checkout(charge_id)

    def simulate_sandbox_payment(self, charge_id: str) -> dict:
        if not self.is_usable_charge_id(charge_id):
            raise HTTPException(status_code=400, detail="Cobrança inválida")
        return self._request(
            "POST",
            "/transparents/simulate-payment",
            params={"id": charge_id},
            json={},
        )

    @staticmethod
    def _merge_charge_views(fetched: dict, webhook_payload: dict | None) -> dict:
        webhook_data: dict = {}
        envelope_dev = None
        webhook_meta = None
        if isinstance(webhook_payload, dict):
            data = webhook_payload.get("data")
            if isinstance(data, dict):
                webhook_data = data
                if isinstance(data.get("metadata"), dict):
                    webhook_meta = data["metadata"]
            if "devMode" in webhook_payload:
                envelope_dev = webhook_payload.get("devMode")
        merged = {
            **webhook_data,
            **{key: value for key, value in fetched.items() if value is not None},
        }
        if envelope_dev is not None and merged.get("devMode") is None:
            merged["devMode"] = envelope_dev
        fetched_meta = fetched.get("metadata") if isinstance(fetched.get("metadata"), dict) else None
        merged["metadata"] = {**(webhook_meta or {}), **(fetched_meta or {})}
        return merged

    def assert_paid_charge(
        self,
        charge: dict,
        *,
        expected_id: str,
        expected_amount_cents: int,
        expected_kind: str,
        expected_order_id: int,
        allow_dev_mode: bool = False,
    ) -> None:
        charge_id = str(charge.get("id") or "").strip()
        if charge_id != expected_id:
            raise HTTPException(status_code=409, detail="Cobrança não corresponde ao pedido")

        status = (charge.get("status") or "").upper()
        if status not in PAID_STATUSES:
            raise HTTPException(status_code=409, detail="Cobrança ainda não paga")

        amount = charge.get("amount")
        if amount is None:
            raise HTTPException(status_code=409, detail="Valor da cobrança ausente")
        try:
            amount_cents = int(amount)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Valor da cobrança inválido") from exc
        if amount_cents != int(expected_amount_cents):
            raise HTTPException(status_code=409, detail="Valor da cobrança não confere")

        currency = charge.get("currency")
        if currency is not None and str(currency).strip().upper() not in {"", "BRL"}:
            raise HTTPException(status_code=409, detail="Moeda da cobrança não confere")

        environment = self.settings.app_environment.strip().lower()
        if (
            environment in {"production", "prod"}
            and bool(charge.get("devMode"))
            and not allow_dev_mode
        ):
            raise HTTPException(
                status_code=409,
                detail="Cobrança de teste não é aceita em produção",
            )

        metadata = charge.get("metadata") if isinstance(charge.get("metadata"), dict) else {}
        keys = _METADATA_KEYS[expected_kind]
        raw = next((metadata.get(key) for key in keys if metadata.get(key) is not None), None)
        if raw is None:
            raise HTTPException(status_code=409, detail="Metadados da cobrança ausentes")
        try:
            meta_order_id = int(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=409, detail="Metadados da cobrança inválidos") from exc
        if meta_order_id != int(expected_order_id):
            raise HTTPException(status_code=409, detail="Metadados da cobrança não conferem")

    def verify_paid_charge_for_order(
        self,
        order: object,
        kind: str,
        webhook_payload: dict | None = None,
    ) -> None:
        charge_id = str(getattr(order, "payment_external_id", None) or "").strip()
        if not self.is_usable_charge_id(charge_id):
            raise HTTPException(status_code=409, detail="Pedido sem cobrança vinculada")
        fetched = self.fetch_charge(charge_id)
        merged = self._merge_charge_views(fetched, webhook_payload)
        if not str(merged.get("id") or "").strip():
            merged["id"] = charge_id
        self.assert_paid_charge(
            merged,
            expected_id=charge_id,
            expected_amount_cents=int(getattr(order, "total_cents")),
            expected_kind=kind,
            expected_order_id=int(getattr(order, "id")),
        )

    def order_is_paid_at_provider(
        self,
        order: object,
        kind: str,
        webhook_payload: dict | None = None,
    ) -> bool:
        try:
            self.verify_paid_charge_for_order(order, kind, webhook_payload=webhook_payload)
            return True
        except HTTPException as exc:
            if exc.status_code >= 500:
                raise
            logger.warning(
                "Cobrança não confirmada order=%s kind=%s: %s",
                getattr(order, "id", None),
                kind,
                exc.detail,
            )
            return False

    def is_checkout_paid(self, checkout_id: str) -> bool:
        if not self.is_usable_charge_id(checkout_id):
            return False
        data = self.fetch_charge(checkout_id)
        return (data.get("status") or "").upper() in PAID_STATUSES

    def get_product_by_external_id(self, external_id: str) -> dict | None:
        _, body = self._raw_request(
            "GET",
            "/products/get",
            params={"externalId": external_id},
        )
        data = body.get("data")
        if body.get("success") and isinstance(data, dict):
            return data

        _, list_body = self._raw_request(
            "GET",
            "/products/list",
            params={"externalId": external_id, "limit": 5},
        )
        list_data = list_body.get("data")
        if list_body.get("success") and isinstance(list_data, list) and list_data:
            first = list_data[0]
            return first if isinstance(first, dict) else None
        return None

    def _product_payload(
        self,
        *,
        external_id: str,
        name: str,
        price_cents: int,
        description: str,
    ) -> dict:
        return {
            "externalId": external_id,
            "name": name[:120],
            "description": description[:500],
            "price": price_cents,
            "currency": "BRL",
        }

    def _create_product_raw(self, payload: dict) -> tuple[bool, str | None, str | None]:
        """Retorna (ok, product_id, error_message)."""
        status, body = self._raw_request("POST", "/products/create", json=payload)
        if body.get("success") and isinstance(body.get("data"), dict):
            product_id = body["data"].get("id")
            if product_id:
                return True, product_id, None
        error = body.get("error")
        if isinstance(error, dict):
            error = error.get("message") or str(error)
        if not error and status >= 400:
            error = str(body)
        return False, None, str(error or "erro ao criar produto")

    def _resolve_product_ref(
        self,
        *,
        order_id: int,
        amount_cents: int,
        name: str,
        description: str,
        product_prefix: str = "vps-order",
    ) -> str:
        """
        Retorna referência do produto para o checkout (externalId ou id público).
        Nunca faz POST com externalId fixo — só GET para reutilizar.
        """
        reuse_ids = [
            f"{product_prefix}-{order_id}",
            f"{product_prefix}-{order_id}-a{amount_cents}",
        ]
        for external_id in reuse_ids:
            existing = self.get_product_by_external_id(external_id)
            if existing and int(existing.get("price") or 0) == amount_cents:
                ref = existing.get("id") or external_id
                logger.info(
                    "Reutilizando produto AbacatePay %s (externalId=%s, rev=%s)",
                    ref,
                    external_id,
                    INTEGRATION_REV,
                )
                return ref

        last_error = "erro ao criar produto"
        for attempt in range(5):
            unique_external_id = f"{product_prefix}-{order_id}-{uuid.uuid4().hex[:16]}"
            payload = self._product_payload(
                external_id=unique_external_id,
                name=name,
                price_cents=amount_cents,
                description=description,
            )
            ok, product_id, error = self._create_product_raw(payload)
            if ok and product_id:
                logger.info(
                    "Produto AbacatePay criado %s (externalId=%s, rev=%s)",
                    product_id,
                    unique_external_id,
                    INTEGRATION_REV,
                )
                return product_id

            last_error = self._normalize_error(error, last_error)
            if "already exists" in last_error.lower():
                existing = self.get_product_by_external_id(unique_external_id)
                if existing:
                    return existing.get("id") or unique_external_id
                logger.warning(
                    "Colisão externalId AbacatePay order=%s (%s), tentativa %s",
                    order_id,
                    unique_external_id,
                    attempt + 1,
                )
                continue
            break

        logger.error(
            "Falha ao criar produto AbacatePay order=%s (rev=%s): %s",
            order_id,
            INTEGRATION_REV,
            last_error,
        )
        raise HTTPException(status_code=502, detail=f"Abacate Pay: {last_error}")

    @staticmethod
    def _normalize_error(error: str | None, fallback: str) -> str:
        if not error:
            return fallback
        text = str(error).strip()
        if text.startswith("{") and '"error"' in text:
            try:
                parsed = json.loads(text)
                nested = parsed.get("error")
                if isinstance(nested, str) and nested:
                    return nested
            except Exception:
                pass
        return text

    def _create_pix_charge(
        self,
        *,
        order_id: int,
        amount_cents: int,
        description: str,
        metadata: dict,
        test_id: str,
    ) -> CheckoutResult:
        if amount_cents <= 0:
            return CheckoutResult(external_id=f"free-{order_id}", status="paid")

        if self.payment_bypass_enabled:
            return CheckoutResult(external_id=test_id, status="test_mode")

        if not self.enabled:
            raise HTTPException(
                status_code=503,
                detail="Provedor de pagamento indisponível",
            )

        external_id = f"{test_id}-{uuid.uuid4().hex[:12]}"
        data = self._post(
            "/transparents/create",
            {
                "method": "PIX",
                "data": {
                    "amount": amount_cents,
                    "description": description[:500],
                    "expiresIn": PIX_EXPIRES_IN_SECONDS,
                    "externalId": external_id,
                    "metadata": {**metadata, "customer_phone": metadata.get("customer_phone", "")},
                },
            },
        )

        br_code = data.get("brCode")
        if not br_code:
            raise HTTPException(status_code=502, detail="Abacate Pay não retornou o código Pix")

        logger.info(
            "Pix transparente criado id=%s order_meta=%s rev=%s",
            data.get("id"),
            metadata,
            INTEGRATION_REV,
        )
        return CheckoutResult(
            external_id=data.get("id") or external_id,
            checkout_url=None,
            status=(data.get("status") or "PENDING").lower(),
            pix_br_code=br_code,
            pix_qr_base64=data.get("brCodeBase64"),
            pix_expires_at=parse_pix_expires_at(data.get("expiresAt")),
        )

    def create_checkout(
        self,
        order_id: int,
        amount_cents: int,
        customer_phone: str,
        description: str,
    ) -> CheckoutResult:
        return self._create_pix_charge(
            order_id=order_id,
            amount_cents=amount_cents,
            description=description,
            metadata={"order_id": str(order_id), "customer_phone": customer_phone},
            test_id=f"checkout-{order_id}",
        )

    def create_game_checkout(
        self,
        order_id: int,
        amount_cents: int,
        customer_phone: str,
        description: str,
    ) -> CheckoutResult:
        return self._create_pix_charge(
            order_id=order_id,
            amount_cents=amount_cents,
            description=description,
            metadata={"game_order_id": str(order_id), "customer_phone": customer_phone},
            test_id=f"game-order-{order_id}",
        )

    def create_web_checkout(
        self,
        order_id: int,
        amount_cents: int,
        customer_phone: str,
        description: str,
    ) -> CheckoutResult:
        return self._create_pix_charge(
            order_id=order_id,
            amount_cents=amount_cents,
            description=description,
            metadata={"web_order_id": str(order_id), "customer_phone": customer_phone},
            test_id=f"web-order-{order_id}",
        )

    def create_storage_checkout(
        self,
        order_id: int,
        amount_cents: int,
        customer_phone: str,
        description: str,
    ) -> CheckoutResult:
        return self._create_pix_charge(
            order_id=order_id,
            amount_cents=amount_cents,
            description=description,
            metadata={"cloud_storage_order_id": str(order_id), "customer_phone": customer_phone},
            test_id=f"cloud-storage-{order_id}",
        )

    def verify_webhook_signature(self, payload: bytes, signature: str) -> bool:
        if not signature:
            return False
        expected = hmac.new(
            ABACATEPAY_PUBLIC_KEY.encode("utf-8"),
            payload,
            hashlib.sha256,
        ).digest()
        expected_b64 = base64.b64encode(expected).decode("utf-8")
        return hmac.compare_digest(expected_b64, signature)

    def verify_webhook_secret(self, secret: str | None) -> bool:
        expected = self.settings.abacatepay_webhook_secret
        if not secret or not expected:
            return False
        return hmac.compare_digest(secret, expected)

    def require_authenticated_webhook(
        self,
        payload: bytes,
        secret: str | None,
        signature: str,
    ) -> None:
        if not self.verify_webhook_secret(secret):
            raise HTTPException(status_code=401, detail="Webhook secret inválido")
        if not self.verify_webhook_signature(payload, signature):
            raise HTTPException(status_code=401, detail="Assinatura do webhook inválida")

    @staticmethod
    def extract_order_id(payload: dict) -> int | None:
        """Extrai order_id do payload do webhook (formatos v1/v2)."""
        for key in ("metadata", "data"):
            block = payload.get(key)
            if isinstance(block, dict):
                raw = block.get("order_id") or block.get("orderId")
                if raw is not None:
                    return int(raw)

        raw_external = payload.get("externalId")
        if raw_external is not None:
            try:
                if str(raw_external).startswith("checkout-"):
                    return int(str(raw_external).split("-")[1])
                return int(raw_external)
            except (TypeError, ValueError):
                pass

        data = payload.get("data")
        if isinstance(data, dict):
            raw_external = data.get("externalId")
            if raw_external is not None:
                try:
                    if str(raw_external).startswith("checkout-"):
                        return int(str(raw_external).split("-")[1])
                    return int(raw_external)
                except (TypeError, ValueError):
                    pass
            metadata = data.get("metadata")
            if isinstance(metadata, dict) and metadata.get("order_id"):
                return int(metadata["order_id"])

        return None

    @staticmethod
    def extract_cloud_storage_order_id(payload: dict) -> int | None:
        for key in ("metadata", "data"):
            block = payload.get(key)
            if isinstance(block, dict):
                raw = block.get("cloud_storage_order_id") or block.get("cloudStorageOrderId")
                if raw is not None:
                    return int(raw)

        data = payload.get("data")
        if isinstance(data, dict):
            metadata = data.get("metadata")
            if isinstance(metadata, dict):
                raw = metadata.get("cloud_storage_order_id") or metadata.get("cloudStorageOrderId")
                if raw is not None:
                    return int(raw)
            raw_external = data.get("externalId")
            if raw_external is not None:
                try:
                    if str(raw_external).startswith("cloud-storage-"):
                        return int(str(raw_external).split("-")[2])
                except (TypeError, ValueError, IndexError):
                    pass

        raw_external = payload.get("externalId")
        if raw_external is not None:
            try:
                if str(raw_external).startswith("cloud-storage-"):
                    return int(str(raw_external).split("-")[2])
            except (TypeError, ValueError, IndexError):
                pass

        return None

    @staticmethod
    def extract_game_order_id(payload: dict) -> int | None:
        for key in ("metadata", "data"):
            block = payload.get(key)
            if isinstance(block, dict):
                raw = block.get("game_order_id") or block.get("gameOrderId")
                if raw is not None:
                    return int(raw)

        data = payload.get("data")
        if isinstance(data, dict):
            metadata = data.get("metadata")
            if isinstance(metadata, dict):
                raw = metadata.get("game_order_id") or metadata.get("gameOrderId")
                if raw is not None:
                    return int(raw)
            raw_external = data.get("externalId")
            if raw_external is not None:
                try:
                    if str(raw_external).startswith("game-order-"):
                        return int(str(raw_external).split("-")[2])
                except (TypeError, ValueError, IndexError):
                    pass

        raw_external = payload.get("externalId")
        if raw_external is not None:
            try:
                if str(raw_external).startswith("game-order-"):
                    return int(str(raw_external).split("-")[2])
            except (TypeError, ValueError, IndexError):
                pass

        return None

    @staticmethod
    def extract_charge_id(payload: dict) -> str | None:
        data = payload.get("data")
        if not isinstance(data, dict) or data.get("id") is None:
            return None
        charge_id = str(data["id"]).strip()
        if not AbacatePayService.is_usable_charge_id(charge_id):
            return None
        return charge_id

    @staticmethod
    def is_payment_confirmed_event(payload: dict) -> bool:
        event = payload.get("event") or payload.get("type") or ""
        return event in (
            "checkout.completed",
            "billing.paid",
            "payment.confirmed",
            "transparent.completed",
        )
